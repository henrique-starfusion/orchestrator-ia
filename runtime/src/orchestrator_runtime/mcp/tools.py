"""Tools MCP — fachada fina sobre TaskService (sem duplicar workflow)."""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os
import sys
from pathlib import Path
from typing import Any, Coroutine, TypeVar

from orchestrator_runtime.agents.base import AgentRequest
from orchestrator_runtime.agents.process import redact
from orchestrator_runtime.config import load_config, resolve_default_workspace
from orchestrator_runtime.mcp.errors import McpError, McpSecurityError
from orchestrator_runtime.mcp.schemas import (
    AnalyzeInput,
    CancelInput,
    DelegateInput,
    EventsInput,
    MemorySearchInput,
    MessageInput,
    ResumeInput,
    RunInput,
    TaskIdInput,
)
from orchestrator_runtime.tasks.service import TaskService, build_service
from orchestrator_runtime.tasks.state_machine import TaskState, can_resume


BLOCKED_ROLES_FOR_CURSOR = {"planner", "executor", "tester", "validator", "corrector"}
WRITE_ROLES = {"executor", "corrector", "tester"}
MAX_PROMPT_CHARS = 100_000
_LOG = logging.getLogger("orchestrator_runtime.mcp")
T = TypeVar("T")


def _run_coro(coro: Coroutine[Any, Any, T]) -> T:
    """Executa coroutine sem quebrar se já houver event loop (MCP async)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _bg_log(context: str, exc: BaseException) -> None:
    msg = f"[orchestrator-mcp] {context}: {exc}"
    _LOG.exception(msg)
    print(msg, file=sys.stderr)


class OrchestratorMcpTools:
    """Camada de transporte MCP → TaskService."""

    def __init__(
        self,
        *,
        default_workspace: Path | None = None,
        fake_agents: bool | None = None,
        verbose: bool = False,
        mcp_wait_timeout_s: int = 120,
    ) -> None:
        self.default_workspace = resolve_default_workspace(default_workspace)
        env_fake = os.environ.get("ORCHESTRATOR_FAKE_AGENTS", "").lower() in {
            "1",
            "true",
            "yes",
        }
        self.fake_agents = env_fake if fake_agents is None else fake_agents
        self.verbose = verbose
        self.mcp_wait_timeout_s = mcp_wait_timeout_s
        self._services: dict[str, TaskService] = {}

    def _resolve_workspace(self, workspace: str | None) -> Path:
        raw = Path(workspace) if workspace else self.default_workspace
        if not raw.is_absolute():
            raw = (self.default_workspace / raw).resolve()
        else:
            raw = raw.resolve()
        if not raw.is_dir():
            raise McpSecurityError(f"workspace inexistente: {raw}")
        in_allowlist = False
        try:
            raw.relative_to(self.default_workspace)
            in_allowlist = True
        except ValueError:
            in_allowlist = False
        if not in_allowlist:
            raise McpSecurityError(
                f"workspace fora da allowlist: {raw} (cwd={self.default_workspace})"
            )
        if not (raw / ".orchestrator").is_dir():
            raise McpSecurityError(
                f".orchestrator/ ausente em {raw}; rode orchestrator install"
            )
        return raw

    def _service(self, workspace: str | None = None) -> TaskService:
        root = self._resolve_workspace(workspace)
        key = str(root)
        if key not in self._services:
            self._services[key] = build_service(
                root, fake_agents=self.fake_agents, verbose=self.verbose
            )
        return self._services[key]

    def health(self) -> dict[str, Any]:
        warnings: list[str] = []
        try:
            service = self._service()
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "unavailable",
                "runtime": {"error": str(exc)},
                "manager_model": {},
                "agents": [],
                "warnings": [str(exc)],
            }
        agents = []
        for st in service.registry.list_statuses():
            agents.append(st.model_dump())
            if st.id != "cursor" and not st.available:
                warnings.append(f"agent unavailable: {st.id}")
        mgr = service.config.manager
        db_ok = service.config.db_path.parent.is_dir()
        status = "healthy"
        if not db_ok:
            status = "degraded"
            warnings.append("data dir missing")
        if not any(a.get("available") for a in agents if a.get("id") != "cursor"):
            status = "degraded"
            warnings.append("no CLI workers available")
        from orchestrator_runtime import __version__ as runtime_version

        return {
            "status": status,
            "runtime": {
                "version": runtime_version,
                "project_path": str(service.config.project_path),
                "db_path": str(service.config.db_path),
                "db_exists": service.config.db_path.is_file(),
            },
            "manager_model": {
                "provider": mgr.provider,
                "enabled": mgr.enabled,
            },
            "agents": agents,
            "warnings": warnings,
        }

    def analyze(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = AnalyzeInput.model_validate(payload)
        if len(data.objective) > MAX_PROMPT_CHARS:
            raise McpSecurityError("objective exceeds max size")
        service = self._service(data.workspace)

        async def _go():
            from orchestrator_runtime.tasks.models import TaskRecord

            analysis = await service.manager.analyze_task(data.objective)
            ephemeral = TaskRecord(
                prompt=data.objective,
                project_path=str(service.config.project_path),
                acceptance_criteria=analysis.acceptance_criteria,
            )
            try:
                plan = await service.manager.select_strategy(ephemeral, analysis)
                return analysis, plan.roles, plan.strategy
            except Exception:  # noqa: BLE001
                return analysis, {}, "execute_review_repair"

        analysis, roles, strategy = asyncio.run(_go())
        return {
            "task_type": analysis.task_type,
            "complexity": analysis.complexity,
            "risk": analysis.risk,
            "languages": analysis.languages,
            "requirements": analysis.requirements,
            "unknowns": [],
            "acceptance_criteria": [c.model_dump() for c in analysis.acceptance_criteria],
            "recommended_strategy": strategy,
            "recommended_roles": roles,
            "confidence": 0.75,
            "read_only": True,
        }

    def agents(self) -> dict[str, Any]:
        service = self._service()
        items = []
        for st in service.registry.list_statuses():
            adapter = service.registry.get(st.id)
            caps = adapter.capabilities().model_dump() if adapter else {}
            items.append({**st.model_dump(), "capabilities": caps})
        return {"agents": items}

    def delegate(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = DelegateInput.model_validate(payload)
        if data.agent == "cursor" or data.role in BLOCKED_ROLES_FOR_CURSOR and data.agent == "cursor":
            raise McpSecurityError("cursor nao pode ser worker")
        if data.agent == "cursor":
            raise McpSecurityError("cursor nao pode ser worker")
        if len(data.objective) > MAX_PROMPT_CHARS:
            raise McpSecurityError("objective exceeds max size")
        if os.environ.get("ORCHESTRATOR_CHILD_AGENT"):
            raise McpSecurityError("recursao bloqueada (ORCHESTRATOR_CHILD_AGENT)")

        if data.read_only and data.role in WRITE_ROLES:
            raise McpSecurityError(
                f"read_only=true bloqueia role de escrita: {data.role}"
            )

        service = self._service(data.workspace)
        adapter = service.registry.get(data.agent)
        if adapter is None:
            raise McpError(f"agente desconhecido: {data.agent}")
        status = adapter.detect()
        if not status.available or not adapter.capabilities().executable:
            raise McpError(f"agente indisponivel: {data.agent}")
        caps = adapter.capabilities()
        if data.role not in caps.roles and data.role != "corrector":
            raise McpSecurityError(
                f"role {data.role} nao suportado por {data.agent}"
            )

        task = service.create_task(
            f"[delegate:{data.role}] {data.objective}",
            dry_run=False,
            max_iterations=1,
            timeout=data.timeout_seconds,
        )
        model = data.model
        model_flag = None
        if not model:
            model, model_flag = service.router.resolve_model(data.agent, "implementation")
        request = AgentRequest(
            role=data.role,
            prompt=data.objective,
            model=model,
            model_flag=model_flag,
            cwd=str(service.config.project_path),
            timeout_s=data.timeout_seconds,
        )
        result = _run_coro(adapter.run(request))
        summary = redact((result.stdout or "")[-1200:])
        service.repo.add_agent_run(
            task_id=task.id,
            role=data.role,
            agent=data.agent,
            model=model,
            command_json=__import__("json").dumps(result.command),
            cwd=result.cwd,
            started_at=result.started_at,
            finished_at=result.finished_at,
            exit_code=result.exit_code,
            timed_out=1 if result.timed_out else 0,
            stdout=redact(result.stdout[-8000:]),
            stderr=redact(result.stderr[-4000:]),
            status=result.status,
            changed_files_json=__import__("json").dumps(result.changed_files),
        )
        warnings = [
            "exit_code_0_not_quality_proof",
            "delegate_is_single_role_not_full_workflow",
        ]
        if data.read_only:
            warnings.append("read_only_enforced")
        return {
            "run_id": f"{task.id}:{data.role}:{data.agent}",
            "task_id": task.id,
            "status": result.status,
            "agent": data.agent,
            "role": data.role,
            "summary": summary[:500] or f"{data.agent}/{data.role} finished",
            "artifacts": result.changed_files,
            "warnings": warnings,
            "unresolved_issues": [],
            "exit_code": result.exit_code,
            "read_only": data.read_only,
        }

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = RunInput.model_validate(payload)
        if len(data.objective) > MAX_PROMPT_CHARS:
            raise McpSecurityError("objective exceeds max size")
        for name in (data.planner, data.executor, data.validator):
            if name == "cursor":
                raise McpSecurityError("cursor nao pode ser worker")
        if data.constraints.allow_network:
            raise McpSecurityError(
                "allow_network=true bloqueado pela politica MCP (rede desabilitada)"
            )
        if data.constraints.allow_dependency_install:
            raise McpSecurityError("install de dependencias bloqueado pela politica MCP")

        # Overrides explícitos têm precedência mesmo com routing=automatic
        planner = data.planner
        executor = data.executor
        validator = data.validator

        service = self._service(data.workspace)
        # temporary fake override
        prev_fake = service.config.fake_agents
        if data.fake_agents:
            service.config.fake_agents = True
            service.registry = type(service.registry)(service.config, service.executor)

        task = service.create_task(
            data.objective,
            profile=data.profile,
            max_iterations=data.constraints.maximum_iterations,
            timeout=data.constraints.maximum_duration_seconds,
            planner=planner,
            executor=executor,
            validator=validator,
        )

        if data.wait:
            try:

                async def _wait():
                    return await asyncio.wait_for(
                        service.run_task(task.id),
                        timeout=min(
                            self.mcp_wait_timeout_s,
                            data.constraints.maximum_duration_seconds,
                        ),
                    )

                done = _run_coro(_wait())
                return {
                    "task_id": done.id,
                    "status": done.status.value,
                    "message": f"Tarefa terminou em {done.status.value}",
                    "status_resource": f"orchestrator://tasks/{done.id}",
                    "events_resource": f"orchestrator://tasks/{done.id}/events",
                    "next_poll_after_seconds": 0,
                    "error": done.error,
                }
            except asyncio.TimeoutError:
                return {
                    "task_id": task.id,
                    "status": "EXECUTING",
                    "message": (
                        "Timeout MCP de espera; continue com orchestrator_status "
                        f"(poll a cada 5s; task_id={task.id})"
                    ),
                    "status_resource": f"orchestrator://tasks/{task.id}",
                    "events_resource": f"orchestrator://tasks/{task.id}/events",
                    "next_poll_after_seconds": 5,
                }
            finally:
                service.config.fake_agents = prev_fake

        # async: start in background thread
        def _bg() -> None:
            try:
                asyncio.run(service.run_task(task.id))
            except Exception as exc:  # noqa: BLE001
                _bg_log(f"run_task {task.id}", exc)
                try:
                    t = service.get(task.id)
                    if t.status not in {
                        TaskState.COMPLETED,
                        TaskState.FAILED,
                        TaskState.CANCELLED,
                        TaskState.INCOMPLETE,
                    }:
                        service.repo.transition(
                            t,
                            TaskState.FAILED,
                            reason="background error",
                            error=str(exc),
                        )
                except Exception as mark_exc:  # noqa: BLE001
                    _bg_log(f"mark_failed {task.id}", mark_exc)

        import threading

        threading.Thread(target=_bg, daemon=True).start()
        return {
            "task_id": task.id,
            "status": "RECEIVED",
            "message": (
                "Workflow iniciado. Poll orchestrator_status a cada "
                "next_poll_after_seconds; use orchestrator_events para detalhe; "
                "só declare sucesso após orchestrator_result."
            ),
            "status_resource": f"orchestrator://tasks/{task.id}",
            "events_resource": f"orchestrator://tasks/{task.id}/events",
            "next_poll_after_seconds": 5,
            "poll_hint": {
                "status": "orchestrator_status",
                "events": "orchestrator_events",
                "result": "orchestrator_result",
            },
        }

    def status(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = TaskIdInput.model_validate(payload)
        service = self._service()
        task = service.get(data.task_id)
        events = service.logs(data.task_id)
        progress = [
            {
                "type": e.get("type"),
                "summary": (e.get("data") or {}).get("summary")
                or (e.get("data") or {}).get("to")
                or e.get("type"),
                "role": e.get("role"),
                "agent": e.get("agent"),
            }
            for e in events[-12:]
        ]
        last = events[-1] if events else {}
        last_data = last.get("data") or {}
        plan = task.plan or {}
        steps = plan.get("steps") or []
        active_step = None
        for step in steps:
            if step.get("role") in {"planner", "executor", "validator"} and task.status.value in {
                "SELECTING_AGENTS",
                "PLANNING",
                "EXECUTING",
                "VALIDATING",
                "CORRECTING",
            }:
                active_step = step
                break
        blocking = []
        if isinstance(task.analysis, dict):
            blocking = list(task.analysis.get("blocking_issues") or [])
        if task.error:
            blocking.append({"type": "error", "detail": task.error})

        requires_input = task.status == TaskState.WAITING_FOR_USER
        terminal = task.status.value in {
            "COMPLETED",
            "FAILED",
            "INCOMPLETE",
            "CANCELLED",
        }
        message_parts = [f"Estado: {task.status.value}"]
        if task.iteration:
            message_parts.append(f"iter={task.iteration}")
        if active_step:
            message_parts.append(
                f"agente={active_step.get('agent')}/{active_step.get('role')}"
            )
        elif last.get("agent"):
            message_parts.append(f"ultimo={last.get('agent')}/{last.get('role')}")
        if last_data.get("summary"):
            message_parts.append(str(last_data.get("summary")))
        if task.error:
            message_parts.append(f"erro={task.error}")
        if not terminal:
            message_parts.append("poll orchestrator_status / orchestrator_events")

        out = {
            "task_id": task.id,
            "status": task.status.value,
            "current_state": task.status.value,
            "current_iteration": task.iteration,
            "selected_agents": plan.get("roles")
            or {
                s.get("role"): s.get("agent")
                for s in steps
                if s.get("role") and s.get("agent")
            },
            "active_agent": (active_step or {}).get("agent"),
            "active_role": (active_step or {}).get("role"),
            "progress": progress,
            "blocking_issues": blocking,
            "documentation": task.documentation_review or {},
            "started_at": task.created_at,
            "updated_at": task.updated_at,
            "requires_input": requires_input,
            "error": task.error,
            "message": " | ".join(message_parts),
            "next_poll_after_seconds": 0 if terminal else 5,
            "acceptance_criteria": [
                c.model_dump() if hasattr(c, "model_dump") else c
                for c in (task.acceptance_criteria or [])
            ],
        }
        if requires_input:
            out["question"] = (task.analysis or {}).get("user_question") or (
                "Runtime aguarda decisão humana"
            )
            out["options"] = (task.analysis or {}).get("user_options") or []
            out["risk"] = task.risk
        return out

    def events(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = EventsInput.model_validate(payload)
        service = self._service()
        rows = service.logs(data.task_id)
        # after_event_id is 1-based index into list for simplicity
        start = 0
        if data.after_event_id is not None:
            start = max(0, int(data.after_event_id))
        sliced = rows[start : start + data.limit]
        compact = []
        for i, e in enumerate(sliced, start=start):
            compact.append(
                {
                    "event_id": i,
                    "type": e.get("type"),
                    "role": e.get("role"),
                    "agent": e.get("agent"),
                    "timestamp": e.get("timestamp"),
                    "summary": (e.get("data") or {}).get("summary")
                    or (e.get("data") or {}).get("to")
                    or e.get("type"),
                }
            )
        return {"task_id": data.task_id, "events": compact, "next_event_id": start + len(compact)}

    def result(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = TaskIdInput.model_validate(payload)
        service = self._service()
        task = service.get(data.task_id)
        arts = service.artifacts(data.task_id)
        return {
            "task_id": task.id,
            "status": task.status.value,
            "summary": (task.analysis or {}).get("summary") or task.prompt[:240],
            "plan": task.plan,
            "agents": (task.plan or {}).get("roles") or {},
            "changes": [a for a in arts if a.get("kind") == "agent_output"],
            "tests": "see runtime DB test_runs",
            "validation": {"last_score": task.last_score},
            "documentation": task.documentation_review,
            "memory": {"episode_saved": task.status.value in {"COMPLETED", "INCOMPLETE", "FAILED"}},
            "remaining_issues": [],
            "error": task.error,
        }

    def cancel(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = CancelInput.model_validate(payload)
        service = self._service()
        task = service.cancel(data.task_id)
        return {
            "task_id": task.id,
            "status": task.status.value,
            "reason": data.reason,
        }

    def resume(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = ResumeInput.model_validate(payload)
        service = self._service()
        task = service.get(data.task_id)
        if data.instruction:
            # stash instruction in analysis
            analysis = dict(task.analysis or {})
            analysis["resume_instruction"] = data.instruction
            task.analysis = analysis
            service.repo.save(task)
        if not can_resume(task.status):
            return {
                "task_id": task.id,
                "status": task.status.value,
                "message": "tarefa terminal; nao pode resume",
            }
        import threading

        def _bg() -> None:
            try:
                asyncio.run(service.resume(data.task_id))
            except Exception as exc:  # noqa: BLE001
                _bg_log(f"resume {data.task_id}", exc)
                try:
                    t = service.get(data.task_id)
                    if t.status not in {
                        TaskState.COMPLETED,
                        TaskState.FAILED,
                        TaskState.CANCELLED,
                        TaskState.INCOMPLETE,
                    }:
                        service.repo.transition(
                            t,
                            TaskState.FAILED,
                            reason="background resume error",
                            error=str(exc),
                        )
                except Exception as mark_exc:  # noqa: BLE001
                    _bg_log(f"mark_failed resume {data.task_id}", mark_exc)

        threading.Thread(target=_bg, daemon=True).start()
        return {
            "task_id": task.id,
            "status": task.status.value,
            "message": (
                "resume iniciado; poll orchestrator_status "
                f"(task_id={task.id})"
            ),
            "next_poll_after_seconds": 5,
            "error": task.error,
        }

    def message(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = MessageInput.model_validate(payload)
        service = self._service()
        task = service.get(data.task_id)
        if task.status != TaskState.WAITING_FOR_USER:
            raise McpError(
                f"tarefa nao esta WAITING_FOR_USER (atual={task.status.value})"
            )
        analysis = dict(task.analysis or {})
        analysis["user_message"] = data.message
        task.analysis = analysis
        service.repo.save(task)
        service.repo.transition(
            task, TaskState.PLANNING, reason="user message received"
        )
        import threading

        def _bg() -> None:
            try:
                asyncio.run(service.resume(data.task_id))
            except Exception as exc:  # noqa: BLE001
                _bg_log(f"message/resume {data.task_id}", exc)

        threading.Thread(target=_bg, daemon=True).start()
        return {
            "task_id": task.id,
            "status": "PLANNING",
            "message": (
                "mensagem aceita; workflow retomado — "
                "poll orchestrator_status"
            ),
            "next_poll_after_seconds": 5,
        }

    def memory_search(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = MemorySearchInput.model_validate(payload)
        service = self._service(data.workspace)
        hits = service.repo.search_memories(data.query, limit=data.limit)
        if data.types:
            hits = [h for h in hits if h.get("kind") in data.types]
        # privacy: truncate content
        safe = []
        for h in hits:
            safe.append(
                {
                    "kind": h.get("kind"),
                    "task_id": h.get("task_id"),
                    "content": redact(str(h.get("content", ""))[:400]),
                }
            )
        return {"query": data.query, "results": safe}
