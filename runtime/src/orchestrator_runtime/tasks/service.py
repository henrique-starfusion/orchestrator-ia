"""Serviço principal de orquestração de tarefas."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from orchestrator_runtime.agents import AgentRegistry
from orchestrator_runtime.agents.base import AgentRequest
from orchestrator_runtime.agents.process import CliExecutor
from orchestrator_runtime.config import RuntimeConfig, load_config
from orchestrator_runtime.documentation import DocumentationUpdater
from orchestrator_runtime.errors import TaskNotFoundError
from orchestrator_runtime.events import EventBus, EventType, RuntimeEvent
from orchestrator_runtime.execution.locks import WriteLock
from orchestrator_runtime.manager_model import build_manager
from orchestrator_runtime.memory.database import dumps
from orchestrator_runtime.planning.analyzer import Planner
from orchestrator_runtime.routing.manager import RulesRouter
from orchestrator_runtime.tasks.models import TaskConstraints, TaskRecord
from orchestrator_runtime.tasks.repository import TaskRepository
from orchestrator_runtime.tasks.state_machine import TaskState, can_resume
from orchestrator_runtime.testing import TestRunner
from orchestrator_runtime.validation import (
    CompletionGate,
    DeterministicValidator,
    LlmReviewValidator,
)


class TaskService:
    def __init__(
        self,
        config: RuntimeConfig,
        *,
        verbose: bool = True,
    ) -> None:
        self.config = config
        self.bus = EventBus(verbose=verbose)
        self.repo = TaskRepository(str(config.db_path))
        self.executor = CliExecutor(config.project_path, echo=verbose)
        self.registry = AgentRegistry(config, self.executor)
        self.router = RulesRouter(config, self.registry)
        self.manager = build_manager(config, self.router)
        self.planner = Planner()
        self.tests = TestRunner(self.executor)
        self.det_validator = DeterministicValidator()
        self.llm_validator = LlmReviewValidator()
        self.gate = CompletionGate(config.limits.minimum_validation_score)
        # task_ids com _execute_loop ativo neste processo (anti double-start MCP)
        self._running_tasks: set[str] = set()
        self.docs = DocumentationUpdater()
        self.lock = WriteLock(
            config.orchestrator_root / "runtime" / "locks" / "workspace.write.lock"
        )

    def create_task(
        self,
        prompt: str,
        *,
        profile: str = "balanced",
        max_iterations: int | None = None,
        timeout: int | None = None,
        planner: str | None = None,
        executor: str | None = None,
        validator: str | None = None,
        dry_run: bool = False,
    ) -> TaskRecord:
        constraints = TaskConstraints(
            maximum_iterations=max_iterations
            or self.config.limits.maximum_iterations,
            maximum_duration_seconds=timeout
            or self.config.limits.maximum_duration_seconds,
            profile=profile,
            planner=planner,
            executor=executor,
            validator=validator,
            dry_run=dry_run,
        )
        task = TaskRecord(
            prompt=prompt,
            project_path=str(self.config.project_path),
            constraints=constraints,
        )
        self.repo.create(task)
        event = RuntimeEvent(
            task_id=task.id, type=EventType.TASK_CREATED, data={"prompt": prompt[:200]}
        )
        self.bus.emit(event)
        self.repo.add_event(event)
        return task

    def get(self, task_id: str) -> TaskRecord:
        task = self.repo.get(task_id)
        if not task:
            raise TaskNotFoundError(task_id)
        return task

    def list_tasks(self, limit: int = 50) -> list[TaskRecord]:
        return self.repo.list_tasks(limit=limit)

    def cancel(self, task_id: str) -> TaskRecord:
        task = self.get(task_id)
        task.cancel_requested = True
        if can_resume(task.status):
            self.repo.transition(
                task, TaskState.CANCELLED, reason="cancel requested", agent="runtime"
            )
            self.bus.emit(
                RuntimeEvent(task_id=task.id, type=EventType.TASK_CANCELLED)
            )
        else:
            self.repo.save(task)
        return task

    def status(self, task_id: str) -> dict[str, Any]:
        task = self.get(task_id)
        return {
            "id": task.id,
            "status": task.status.value,
            "iteration": task.iteration,
            "last_score": task.last_score,
            "plan": task.plan,
            "error": task.error,
            "documentation_review": task.documentation_review,
        }

    def logs(self, task_id: str) -> list[dict[str, Any]]:
        self.get(task_id)
        return self.repo.list_events(task_id)

    def artifacts(self, task_id: str) -> list[dict[str, Any]]:
        self.get(task_id)
        return self.repo.list_artifacts(task_id)

    async def run_task(self, task_id: str) -> TaskRecord:
        task = self.get(task_id)
        if task.status == TaskState.CANCELLED:
            return task
        if task.status in {TaskState.COMPLETED, TaskState.FAILED, TaskState.INCOMPLETE}:
            return task
        if task_id in self._running_tasks:
            # Segunda invocação (MCP retry / poll) enquanto o loop já roda —
            # não contender o WriteLock nem marcar FAILED.
            return task
        if task.constraints.dry_run:
            return await self._dry_run(task)
        try:
            with self.lock:
                self._running_tasks.add(task_id)
                try:
                    return await self._execute_loop(task)
                finally:
                    self._running_tasks.discard(task_id)
        except TimeoutError as exc:
            # Lock ocupado por outra execução: NÃO envenenar a tarefa em andamento.
            task = self.get(task_id)
            self.bus.emit(
                RuntimeEvent(
                    task_id=task.id,
                    type=EventType.TASK_FAILED,
                    data={
                        "error": str(exc),
                        "non_fatal": True,
                        "reason": "workspace_lock_busy",
                    },
                )
            )
            return task
        except Exception as exc:  # noqa: BLE001
            task = self.get(task_id)
            if can_resume(task.status):
                self.repo.transition(
                    task,
                    TaskState.FAILED,
                    reason="unhandled error",
                    error=str(exc),
                )
            else:
                task.error = str(exc)
                self.repo.save(task)
            self.bus.emit(
                RuntimeEvent(
                    task_id=task.id,
                    type=EventType.TASK_FAILED,
                    data={"error": str(exc)},
                )
            )
            self._persist_episode(task, success=False)
            raise

    async def resume(self, task_id: str) -> TaskRecord:
        task = self.get(task_id)
        if not can_resume(task.status):
            return task
        return await self.run_task(task_id)

    async def run_prompt(self, prompt: str, **kwargs: Any) -> TaskRecord:
        task = self.create_task(prompt, **kwargs)
        return await self.run_task(task.id)

    async def _dry_run(self, task: TaskRecord) -> TaskRecord:
        analysis = await self.manager.analyze_task(task.prompt)
        plan_roles = await self.manager.select_strategy(task, analysis)
        task.analysis = analysis.model_dump()
        task.plan = self.planner.plan(task, analysis, plan_roles)
        task.acceptance_criteria = analysis.acceptance_criteria
        self.repo.save(task)
        self.bus.emit(
            RuntimeEvent(
                task_id=task.id,
                type=EventType.PLAN_CREATED,
                data={"dry_run": True, "plan": task.plan},
            )
        )
        return task

    async def _execute_loop(self, task: TaskRecord) -> TaskRecord:
        # RECEIVED -> ANALYZING
        if task.status == TaskState.RECEIVED:
            self.repo.transition(task, TaskState.ANALYZING, reason="start analysis")

        if task.cancel_requested:
            return self.cancel(task.id)

        project_files = [p.name for p in self.config.project_path.iterdir()]
        analysis = await self.manager.analyze_task(task.prompt, project_files)
        task.task_type = analysis.task_type
        task.languages = analysis.languages
        task.risk = analysis.risk
        task.complexity = analysis.complexity
        task.requirements = analysis.requirements
        task.acceptance_criteria = analysis.acceptance_criteria
        task.analysis = analysis.model_dump()
        self.repo.save(task)

        self.repo.transition(task, TaskState.RETRIEVING_MEMORY, reason="memory lookup")
        memories = self.repo.search_memories(task.prompt, limit=5)
        self.bus.emit(
            RuntimeEvent(
                task_id=task.id,
                type=EventType.MEMORY_UPDATED,
                data={"retrieved": len(memories)},
            )
        )

        self.repo.transition(task, TaskState.PLANNING, reason="planning")
        plan_roles = await self.manager.select_strategy(task, analysis)
        task.plan = self.planner.plan(task, analysis, plan_roles)
        self.repo.save(task)
        self.repo.add_routing_decision(task.id, plan_roles.strategy, plan_roles.model_dump())
        self.bus.emit(
            RuntimeEvent(
                task_id=task.id,
                type=EventType.PLAN_CREATED,
                data={"plan": task.plan},
            )
        )

        self.repo.transition(task, TaskState.SELECTING_AGENTS, reason="select agents")
        self.bus.emit(
            RuntimeEvent(
                task_id=task.id,
                type=EventType.ROUTING_DECIDED,
                data=plan_roles.model_dump(),
            )
        )

        # Planner agent (Claude no MVP) — refina plano; falha nao aborta se dry artifacts ok
        try:
            plan_prompt = (
                f"Refine o plano para: {task.prompt}\n"
                f"Plano atual: {dumps(task.plan)}\n"
                "Responda com passos objetivos sem abreviação."
            )
            await self._run_agent(plan_roles.planner, "planner", plan_prompt, task)
        except Exception as exc:  # noqa: BLE001
            self.bus.emit(
                RuntimeEvent(
                    task_id=task.id,
                    type=EventType.AGENT_COMPLETED,
                    role="planner",
                    agent=plan_roles.planner,
                    data={"status": "failed", "error": str(exc)},
                )
            )

        changed_files: list[str] = []
        last_validation: dict[str, Any] = {}
        last_test_results: list[dict[str, Any]] = []
        issue_counts: dict[str, int] = {}

        while True:
            task = self.get(task.id)
            if task.cancel_requested:
                return self.cancel(task.id)

            if task.iteration >= task.constraints.maximum_iterations:
                self.repo.transition(
                    task,
                    TaskState.INCOMPLETE,
                    reason="maximum_iterations",
                )
                self.bus.emit(
                    RuntimeEvent(task_id=task.id, type=EventType.TASK_INCOMPLETE)
                )
                self._persist_episode(task, success=False)
                return task

            task.iteration += 1
            self.repo.save(task)

            task = self.get(task.id)
            if task.status == TaskState.SELECTING_AGENTS:
                self.repo.transition(
                    task,
                    TaskState.EXECUTING,
                    reason=f"start execute iter={task.iteration}",
                    agent=plan_roles.executor,
                )
            elif task.status == TaskState.CORRECTING:
                self.repo.transition(
                    task,
                    TaskState.EXECUTING,
                    reason=f"retry execute iter={task.iteration}",
                    agent=plan_roles.executor,
                )
            elif task.status != TaskState.EXECUTING:
                raise RuntimeError(f"Estado inesperado antes de executar: {task.status}")

            role = "corrector" if task.iteration > 1 else "executor"
            exec_prompt = self._build_executor_prompt(
                task, last_validation, memories, test_results=last_test_results
            )
            try:
                exec_result = await self._run_agent(
                    plan_roles.executor, role, exec_prompt, task
                )
            except Exception as exec_exc:  # noqa: BLE001
                # Spawn/CLI falhou: não abortar o workflow — tratar como iteração
                # rejeitada para entrar em CORRECTING / fallback na próxima volta.
                task = self.get(task.id)
                self.bus.emit(
                    RuntimeEvent(
                        task_id=task.id,
                        type=EventType.AGENT_COMPLETED,
                        role=role,
                        agent=plan_roles.executor,
                        data={"status": "failed", "error": str(exec_exc)},
                    )
                )
                last_validation = {
                    "status": "rejected",
                    "score": 0.0,
                    "blocking_issues": [
                        {
                            "id": "EXEC-FAIL",
                            "severity": "blocking",
                            "description": f"Falha ao executar {role}/{plan_roles.executor}: {exec_exc}",
                        }
                    ],
                    "summary": f"executor failed: {exec_exc}",
                }
                decision = await self.manager.evaluate_iteration(
                    task, last_validation, task.iteration
                )
                self.repo.add_iteration(
                    task.id,
                    task.iteration,
                    0.0,
                    decision.action,
                    {"reason": decision.reason, "error": str(exec_exc)},
                )
                if decision.action in {"stop_incomplete", "fail"}:
                    target = (
                        TaskState.FAILED
                        if decision.action == "fail"
                        else TaskState.INCOMPLETE
                    )
                    self.repo.transition(task, target, reason=decision.reason, error=str(exec_exc))
                    self._persist_episode(task, success=False)
                    return task
                self.repo.transition(
                    task,
                    TaskState.CORRECTING,
                    reason=f"executor error → correct: {exec_exc}",
                    agent=plan_roles.executor,
                )
                continue

            spawn_failed = exec_result.exit_code == 127 or (
                exec_result.status == "failed"
                and "FileNotFoundError" in (exec_result.stderr or "")
            )
            if spawn_failed:
                last_validation = {
                    "status": "rejected",
                    "score": 0.0,
                    "blocking_issues": [
                        {
                            "id": "EXEC-SPAWN",
                            "severity": "blocking",
                            "description": (
                                f"Falha ao iniciar CLI {plan_roles.executor}: "
                                f"{(exec_result.stderr or '')[:300]}"
                            ),
                        }
                    ],
                    "summary": "executor spawn failed",
                }
                decision = await self.manager.evaluate_iteration(
                    task, last_validation, task.iteration
                )
                self.repo.add_iteration(
                    task.id,
                    task.iteration,
                    0.0,
                    decision.action,
                    {"reason": decision.reason, "spawn_failed": True},
                )
                if decision.action in {"stop_incomplete", "fail"}:
                    target = (
                        TaskState.FAILED
                        if decision.action == "fail"
                        else TaskState.INCOMPLETE
                    )
                    self.repo.transition(
                        task,
                        target,
                        reason=decision.reason,
                        error=exec_result.stderr,
                    )
                    self._persist_episode(task, success=False)
                    return task
                # Tentar fallback de executor na próxima iteração
                fallbacks = (task.plan or {}).get("fallbacks", {}).get("executor") or []
                for fb in fallbacks:
                    if fb != plan_roles.executor and self.registry.get(fb):
                        plan_roles.executor = fb
                        break
                self.repo.transition(
                    task,
                    TaskState.CORRECTING,
                    reason="executor spawn failed → correct/fallback",
                    agent=plan_roles.executor,
                )
                continue

            changed_files = list(
                dict.fromkeys(changed_files + exec_result.changed_files)
            )

            # TESTING
            task = self.get(task.id)
            self.repo.transition(task, TaskState.TESTING, reason="deterministic tests")
            self.bus.emit(RuntimeEvent(task_id=task.id, type=EventType.TEST_STARTED))
            test_results = self.tests.run_all(self.config.project_path)
            last_test_results = test_results
            for tr in test_results:
                self.repo.add_test_run(task_id=task.id, **tr)
            self.bus.emit(
                RuntimeEvent(
                    task_id=task.id,
                    type=EventType.TEST_COMPLETED,
                    data={"results": [{"command": t["command"], "status": t["status"]} for t in test_results]},
                )
            )
            tests_passed = all(
                t["status"] in {"passed", "skipped"} for t in test_results
            )

            # VALIDATING
            task = self.get(task.id)
            self.repo.transition(
                task, TaskState.VALIDATING, reason="independent validation", agent=plan_roles.validator
            )
            self.bus.emit(
                RuntimeEvent(task_id=task.id, type=EventType.VALIDATION_STARTED)
            )
            det = self.det_validator.evaluate(
                task,
                changed_files=changed_files,
                test_results=test_results,
                project_path=self.config.project_path,
            )
            # Independent agent validation — policy hard gate
            val_agent = plan_roles.validator
            if (
                self.config.limits.require_independent_validation
                and val_agent == plan_roles.executor
            ):
                det["status"] = "rejected"
                det["blocking_issues"] = list(det.get("blocking_issues") or []) + [
                    {
                        "id": "VAL-IND",
                        "severity": "blocking",
                        "description": (
                            "validator==executor com require_independent_validation"
                        ),
                    }
                ]
                det["score"] = min(float(det.get("score") or 0.0), 0.5)
                det["summary"] = (
                    det.get("summary", "")
                    + " | blocking: validator==executor (independent validation required)"
                )
            val_prompt = self._build_validator_prompt(task, det, test_results, changed_files)
            val_result = await self._run_agent(val_agent, "validator", val_prompt, task)
            last_validation = self.llm_validator.parse(val_result.stdout, det)
            # Prefer stricter: if deterministic rejected, keep rejected
            if det["status"] != "approved":
                last_validation["status"] = "rejected"
                last_validation["blocking_issues"] = det["blocking_issues"]
                last_validation["score"] = min(
                    float(last_validation.get("score") or 1.0), float(det["score"])
                )
            # Testes falhos sempre forçam ciclo de correção (mesmo se o LLM aprovou)
            if not tests_passed:
                failed = [
                    t
                    for t in test_results
                    if t.get("status") not in {"passed", "skipped"}
                ]
                last_validation["status"] = "rejected"
                issues = list(last_validation.get("blocking_issues") or [])
                issues.append(
                    {
                        "id": "TEST-FAIL",
                        "severity": "blocking",
                        "description": (
                            "Suite determinística falhou: "
                            + ", ".join(
                                f"{t.get('command')}:{t.get('status')}" for t in failed
                            )
                        ),
                    }
                )
                last_validation["blocking_issues"] = issues
                last_validation["score"] = min(
                    float(last_validation.get("score") or 0.0), 0.4
                )

            self.repo.add_validation_round(
                task_id=task.id,
                iteration=task.iteration,
                status=last_validation.get("status", "rejected"),
                score=last_validation.get("score"),
                payload_json=dumps(last_validation),
            )
            for issue in last_validation.get("blocking_issues") or []:
                iid = issue.get("id") if isinstance(issue, dict) else str(issue)
                desc = issue.get("description") if isinstance(issue, dict) else str(issue)
                self.repo.add_validation_issue(
                    task_id=task.id,
                    issue_id=iid,
                    severity="blocking",
                    description=desc or "",
                )
                issue_counts[iid] = issue_counts.get(iid, 0) + 1

            task.last_score = float(last_validation.get("score") or 0)
            self.repo.save(task)
            self.bus.emit(
                RuntimeEvent(
                    task_id=task.id,
                    type=EventType.VALIDATION_COMPLETED,
                    data={
                        "status": last_validation.get("status"),
                        "score": last_validation.get("score"),
                    },
                )
            )

            decision = await self.manager.evaluate_iteration(
                task, last_validation, task.iteration
            )
            # same issue repeat
            if any(
                c >= self.config.limits.same_issue_repeat_limit
                for c in issue_counts.values()
            ):
                decision.action = "stop_incomplete"
                decision.reason = "same_issue_repeat_limit"

            self.repo.add_iteration(
                task.id,
                task.iteration,
                task.last_score,
                decision.action,
                {"reason": decision.reason, "issues": decision.issues},
            )

            if decision.action == "approve" and tests_passed:
                break
            if decision.action == "approve" and not tests_passed:
                decision.action = "correct"
                decision.reason = "tests_failed"
            if decision.action in {"stop_incomplete", "fail"}:
                target = (
                    TaskState.FAILED
                    if decision.action == "fail"
                    else TaskState.INCOMPLETE
                )
                self.repo.transition(task, target, reason=decision.reason)
                self.bus.emit(
                    RuntimeEvent(
                        task_id=task.id,
                        type=(
                            EventType.TASK_FAILED
                            if target == TaskState.FAILED
                            else EventType.TASK_INCOMPLETE
                        ),
                    )
                )
                self._persist_episode(task, success=False)
                return task

            # correct
            self.bus.emit(
                RuntimeEvent(
                    task_id=task.id,
                    type=EventType.CORRECTION_REQUESTED,
                    data={"issues": decision.issues},
                )
            )
            self.repo.transition(
                task, TaskState.CORRECTING, reason=decision.reason, agent=plan_roles.executor
            )

        # Documentation gate
        task = self.get(task.id)
        self.repo.transition(
            task, TaskState.UPDATING_DOCUMENTATION, reason="documentation gate"
        )
        self.bus.emit(
            RuntimeEvent(task_id=task.id, type=EventType.DOCUMENTATION_STARTED)
        )
        doc_review = self.docs.ensure_usage_docs(
            self.config.project_path, task.prompt, changed_files
        )
        task.documentation_review = doc_review
        self.repo.save(task)
        self.repo.save_documentation_update(task.id, doc_review)
        self.bus.emit(
            RuntimeEvent(
                task_id=task.id,
                type=EventType.DOCUMENTATION_COMPLETED,
                data=doc_review,
            )
        )

        ok, reason = self.gate.can_complete(
            validation=last_validation,
            tests_passed=tests_passed,
            documentation_review=doc_review,
        )
        self.repo.transition(task, TaskState.CONSOLIDATING, reason="completion gate")
        if not ok:
            self.repo.transition(task, TaskState.INCOMPLETE, reason=reason)
            self._persist_episode(task, success=False)
            self.bus.emit(
                RuntimeEvent(
                    task_id=task.id,
                    type=EventType.TASK_INCOMPLETE,
                    data={"reason": reason},
                )
            )
            return task

        self.repo.transition(task, TaskState.COMPLETED, reason="all gates passed")
        self.bus.emit(RuntimeEvent(task_id=task.id, type=EventType.TASK_COMPLETED))
        self._persist_episode(task, success=True, strategy=plan_roles.strategy)
        # human-readable memory export
        self._export_memory_markdown(task)
        return task

    def _build_executor_prompt(
        self,
        task: TaskRecord,
        validation: dict[str, Any],
        memories: list[dict],
        *,
        test_results: list[dict[str, Any]] | None = None,
    ) -> str:
        parts = [
            f"Tarefa: {task.prompt}",
            "Critérios:",
            *[f"- {c.id}: {c.description}" for c in task.acceptance_criteria],
        ]
        if validation.get("blocking_issues"):
            parts.append("Corrija os issues:")
            for issue in validation["blocking_issues"]:
                if isinstance(issue, dict):
                    parts.append(f"- {issue.get('id')}: {issue.get('description')}")
                else:
                    parts.append(f"- {issue}")
        if test_results:
            failed = [
                t
                for t in test_results
                if t.get("status") not in {"passed", "skipped"}
            ]
            if failed:
                parts.append("Testes que falharam (corrija até passarem):")
                for t in failed:
                    parts.append(
                        f"- cmd={t.get('command')} status={t.get('status')} "
                        f"exit={t.get('exit_code')}"
                    )
        if memories:
            parts.append("Memória relevante:")
            for m in memories[:3]:
                parts.append(f"- {m.get('content', '')[:200]}")
        parts.append(
            "Não use abreviação caveman. Não declare sucesso sem evidências."
        )
        return "\n".join(parts)

    def _build_validator_prompt(
        self,
        task: TaskRecord,
        det: dict[str, Any],
        tests: list[dict],
        changed_files: list[str],
    ) -> str:
        return (
            "Valide a tarefa e responda APENAS JSON com status/score/blocking_issues.\n"
            f"Prompt original: {task.prompt}\n"
            f"Critérios: {dumps([c.model_dump() for c in task.acceptance_criteria])}\n"
            f"Diff/arquivos: {changed_files}\n"
            f"Testes: {dumps([{k: t.get(k) for k in ('command','status','exit_code')} for t in tests])}\n"
            f"Validação determinística: {dumps(det)}\n"
        )

    async def _run_agent(
        self, agent_id: str, role: str, prompt: str, task: TaskRecord
    ):
        adapter = self.registry.get(agent_id)
        if adapter is None or not adapter.detect().available:
            # try fallbacks from plan
            fallbacks = (task.plan or {}).get("fallbacks", {}).get(
                "executor" if role in {"executor", "corrector"} else role, []
            )
            for fb in fallbacks:
                adapter = self.registry.get(fb)
                if adapter and adapter.detect().available:
                    agent_id = fb
                    break
        if adapter is None or not adapter.detect().available:
            raise RuntimeError(f"Agente indisponivel para papel {role}: {agent_id}")

        model, model_flag = self.router.resolve_model(agent_id, task.task_type)
        self.bus.emit(
            RuntimeEvent(
                task_id=task.id,
                type=EventType.AGENT_STARTED,
                role=role,
                agent=agent_id,
                data={"model": model},
            )
        )
        request = AgentRequest(
            role=role,
            prompt=prompt,
            model=model,
            model_flag=model_flag,
            cwd=str(self.config.project_path),
            timeout_s=min(600, task.constraints.maximum_duration_seconds),
        )
        result = await adapter.run(request)
        self.repo.add_agent_run(
            task_id=task.id,
            role=role,
            agent=agent_id,
            model=model,
            command_json=dumps(result.command),
            cwd=result.cwd,
            started_at=result.started_at,
            finished_at=result.finished_at,
            exit_code=result.exit_code,
            timed_out=1 if result.timed_out else 0,
            stdout=result.stdout[-20000:],
            stderr=result.stderr[-20000:],
            status=result.status,
            changed_files_json=dumps(result.changed_files),
        )
        art_dir = (
            self.config.orchestrator_root / "runtime" / "results" / task.id
        )
        art_dir.mkdir(parents=True, exist_ok=True)
        out_path = art_dir / f"{role}-{agent_id}.txt"
        out_path.write_text(
            result.stdout + "\n" + result.stderr, encoding="utf-8"
        )
        self.repo.add_artifact(task.id, "agent_output", str(out_path))
        self.repo.update_agent_performance(
            agent_id, result.status == "completed", result.duration_s, task.last_score
        )
        self.bus.emit(
            RuntimeEvent(
                task_id=task.id,
                type=EventType.AGENT_COMPLETED,
                role=role,
                agent=agent_id,
                data={"status": result.status, "exit_code": result.exit_code},
            )
        )
        return result

    def _persist_episode(
        self, task: TaskRecord, *, success: bool, strategy: str | None = None
    ) -> None:
        content = (
            f"task={task.id} status={task.status.value} success={success} "
            f"type={task.task_type} prompt={task.prompt[:300]}"
        )
        self.repo.save_memory(
            "episode",
            content,
            task_id=task.id,
            meta={
                "status": task.status.value,
                "score": task.last_score,
                "documentation": task.documentation_review,
            },
        )
        if strategy:
            self.repo.update_strategy_performance(
                strategy, success, task.last_score
            )
        self.bus.emit(
            RuntimeEvent(task_id=task.id, type=EventType.MEMORY_UPDATED, data={"kind": "episode"})
        )

    def _export_memory_markdown(self, task: TaskRecord) -> None:
        mem_dir = self.config.orchestrator_root / "memory" / "episodes"
        mem_dir.mkdir(parents=True, exist_ok=True)
        path = mem_dir / f"{task.id}.md"
        path.write_text(
            f"# Episode {task.id}\n\n"
            f"- status: {task.status.value}\n"
            f"- score: {task.last_score}\n"
            f"- prompt: {task.prompt}\n"
            f"- documentation: {dumps(task.documentation_review)}\n",
            encoding="utf-8",
        )


def build_service(
    project_path: str | Path | None = None,
    *,
    fake_agents: bool = False,
    manager_provider: str | None = None,
    verbose: bool = True,
) -> TaskService:
    config = load_config(
        project_path, fake_agents=fake_agents, manager_provider=manager_provider
    )
    return TaskService(config, verbose=verbose)
