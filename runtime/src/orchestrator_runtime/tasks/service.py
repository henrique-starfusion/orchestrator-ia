"""Serviço principal de orquestração de tarefas."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

from orchestrator_runtime.agents import AgentRegistry
from orchestrator_runtime.agents.base import AgentRequest, AgentResult
from orchestrator_runtime.agents.process import NO_OUTPUT_MARKER, CliExecutor
from orchestrator_runtime.callers import caller_profile, detect_caller
from orchestrator_runtime.config import RuntimeConfig, load_config
from orchestrator_runtime.documentation import DocumentationUpdater
from orchestrator_runtime.errors import CancelledError, TaskNotFoundError
from orchestrator_runtime.events import EventBus, EventType, RuntimeEvent
from orchestrator_runtime.execution.git_workspace import (
    GitBaseline,
    capture_baseline,
    changed_files_since,
)
from orchestrator_runtime.execution.locks import WriteLock
from orchestrator_runtime.execution.timeouts import (
    MIN_AGENT_TIMEOUT_S,
    resolve_agent_timeout,
)
from orchestrator_runtime.manager_model import build_manager
from orchestrator_runtime.memory.database import dumps
from orchestrator_runtime.textutil import repair_mojibake
from orchestrator_runtime.planning.analyzer import Planner
from orchestrator_runtime.routing.manager import RulesRouter
from orchestrator_runtime.tasks.models import TaskConstraints, TaskRecord
from orchestrator_runtime.tasks.repository import TaskRepository
from orchestrator_runtime.tasks.state_machine import (
    TERMINAL_STATES,
    TaskState,
    can_resume,
)

TERMINAL_LIKE = TERMINAL_STATES
from orchestrator_runtime.testing import TestRunner
from orchestrator_runtime.testing.discovery import stack_test_commands
from orchestrator_runtime.validation import (
    CompletionGate,
    DeterministicValidator,
    LlmReviewValidator,
)



def _collect_input_hashes(project_path, changed_files):
    """Hashes de auditoria da validação (prompts.md Type 7, 0.4.52-C2):
    sha256 por arquivo alterado (máx 20, pula ausentes e >2MB) +
    rev-parse HEAD quando o projeto for repo git. Tolerante a falhas:
    qualquer erro vira omissão da chave, nunca derruba a validação."""
    import hashlib
    import subprocess

    out = {}
    files = {}
    for rel in (changed_files or [])[:20]:
        try:
            p = project_path / rel
            if not p.is_file() or p.stat().st_size > 2 * 1024 * 1024:
                continue
            files[str(rel).replace(chr(92), "/")] = hashlib.sha256(
                p.read_bytes()
            ).hexdigest()
        except OSError:
            continue
    if files:
        out["files"] = files
    try:
        rev = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(project_path),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if rev.returncode == 0 and rev.stdout.strip():
            out["head"] = rev.stdout.strip()
    except Exception:
        pass
    return out


class TaskService:
    # Teto do refino de plano (advisory) — o workflow nunca fica preso em
    # SELECTING_AGENTS mais que isso; o plano determinístico já existe.
    PLANNER_REFINE_CAP_S = 300
    # 0.4.24 — teto total da fase SELECTING_AGENTS (skill_selector + planner refine)
    SELECTING_AGENTS_CAP_S = 180

    def __init__(
        self,
        config: RuntimeConfig,
        *,
        verbose: bool = True,
    ) -> None:
        self.config = config
        # 0.4.29 — quem chamou define o tratamento: superficie sem console (MCP,
        # Cursor) nao ganha nada com eco no stdout e depende dos eventos;
        # sessao bloqueante (Claude Code, Codex) precisa ver saida ao vivo.
        self.caller = detect_caller()
        self.caller_profile = caller_profile(self.caller)
        echo = verbose and self.caller_profile.echo
        self.bus = EventBus(verbose=echo)
        self.repo = TaskRepository(str(config.db_path))
        self.executor = CliExecutor(
            config.project_path,
            echo=echo,
            infra_fail_fast_count=config.limits.agent_infra_fail_fast_count,
            heartbeat_s=self.caller_profile.heartbeat_s,
        )
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
        # bug-085 — órfãs já adotadas por este processo: sem isto, cada poll de
        # status dispararia uma nova thread para a mesma task na janela entre o
        # start e a primeira transição de estado.
        self._adopted: set[str] = set()
        self.docs = DocumentationUpdater()
        self.lock = WriteLock(
            config.orchestrator_root / "runtime" / "locks" / "workspace.write.lock"
        )
        self._loop_started_monotonic: float | None = None
        self._git_baseline: GitBaseline = GitBaseline()
        # Contexto do run corrente para o learning (locals do loop não
        # persistidos na task): changed_files, test_results, last_validation.
        self._run_ctx: dict[str, Any] = {}
        # 0.4.25 — modelos com cota esgotada neste processo/run (agent, model)
        self._exhausted_models: set[tuple[str, str]] = set()

    def _cancel_stale_received(self) -> int:
        """Auto-cancel RECEIVED tasks older than stale_received_ttl_hours (P1-D 0.4.16)."""
        ttl_hours = self.config.limits.stale_received_ttl_hours
        if not ttl_hours:
            return 0
        cutoff_s = ttl_hours * 3600
        now = datetime.now(timezone.utc)
        cancelled = 0
        for task in self.repo.list_tasks(limit=200):
            if task.status != TaskState.RECEIVED:
                continue
            try:
                ts = task.created_at.replace("Z", "+00:00")
                dt = datetime.fromisoformat(ts)
                # Roundtrip pelo SQLite perde o tzinfo ("...+00:00" vira
                # string naïve); subtrair de `now` (aware) levantava TypeError
                # e o except engolia — a varredura nunca cancelava NADA lido
                # do DB. Assumir UTC quando naïve.
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                age_s = (now - dt).total_seconds()
            except Exception:
                continue
            if age_s > cutoff_s:
                self.repo.transition(
                    task,
                    TaskState.CANCELLED,
                    reason=f"auto-cancel: stale RECEIVED > {ttl_hours}h",
                    agent="runtime",
                )
                cancelled += 1
        return cancelled

    # bug-064 — janela de idempotencia do create_task: double-submit (MCP/CLI
    # chamando create 2x seguidas; medido: 16s de intervalo no corehub) gerava
    # tasks gêmeas e uma travava RECEIVED sem dono.
    _DEDUP_WINDOW_S = 120

    def _find_recent_duplicate(self, prompt: str, *, dry_run: bool) -> TaskRecord | None:
        """Task nao-terminal recente com o MESMO prompt e mesmo dry_run."""
        now = datetime.now(timezone.utc)
        for task in self.repo.list_tasks(limit=50):
            if task.status in TERMINAL_STATES:
                continue
            if task.prompt != prompt:
                continue
            if bool(getattr(task.constraints, "dry_run", False)) != dry_run:
                continue
            try:
                ts = task.created_at.replace("Z", "+00:00")
                dt = datetime.fromisoformat(ts)
                if dt.tzinfo is None:  # roundtrip SQLite perde o tz; assumir UTC
                    dt = dt.replace(tzinfo=timezone.utc)
                age_s = (now - dt).total_seconds()
            except Exception:  # noqa: BLE001
                continue
            if 0 <= age_s <= self._DEDUP_WINDOW_S:
                return task
        return None

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
        # bug-049 — prompt vindo de terminal CP1252 chega com mojibake UTF-8
        # ("exigÃªncia"); repara na ingestão, antes de persistir/analisar.
        prompt = repair_mojibake(prompt)
        self._cancel_stale_received()
        # bug-064 — idempotencia: mesmo prompt + mesmo dry_run em janela curta
        # com task nao-terminal devolve a existente (auditada com evento dedup)
        # em vez de criar duplicata que pode travar RECEIVED sem dono.
        existing = self._find_recent_duplicate(prompt, dry_run=dry_run)
        if existing is not None:
            event = RuntimeEvent(
                task_id=existing.id,
                type=EventType.TASK_CREATED,
                agent="runtime",
                data={"dedup": True, "prompt": prompt[:200]},
            )
            self.bus.emit(event)
            self.repo.add_event(event)
            return existing
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
        prior_count = len(self.repo.list_tasks(limit=2))
        first_run = prior_count == 0
        self.repo.create(task)
        event = RuntimeEvent(
            task_id=task.id,
            type=EventType.TASK_CREATED,
            data={
                "prompt": prompt[:200],
                "first_run": first_run,
            },
        )
        self.bus.emit(event)
        self.repo.add_event(event)
        if first_run:
            self._onboard_first_run(task)
        return task

    def _onboard_first_run(self, task: TaskRecord) -> None:
        """0.4.24 — primeiro run no projeto: probe de agentes + índice legacy-import."""
        probe: dict[str, Any] = {"agents": []}
        try:
            for st in self.registry.list_statuses():
                probe["agents"].append(
                    {
                        "id": st.id,
                        "available": bool(st.available),
                        "path": st.path,
                        "notes": (st.notes or "")[:160] if getattr(st, "notes", None) else None,
                    }
                )
        except Exception as exc:  # noqa: BLE001
            probe["error"] = str(exc)
        idx_path = self._write_legacy_import_index()
        self.bus.emit(
            RuntimeEvent(
                task_id=task.id,
                type=EventType.MEMORY_UPDATED,
                agent="runtime",
                data={
                    "summary": "first_run_onboarding",
                    "agent_probe": probe,
                    "legacy_import_index": str(idx_path) if idx_path else None,
                },
            )
        )

    def _write_legacy_import_index(self) -> Path | None:
        """Gera índice das skills/rules em legacy-import (requires-review)."""
        root = self.config.project_path / ".orchestrator"
        skills_root = root / "skills" / "legacy-import"
        rules_root = root / "rules" / "legacy-import"
        if not skills_root.is_dir() and not rules_root.is_dir():
            return None
        lines = [
            "# Legacy import index",
            "",
            "Gerado no primeiro `orchestrator_run` do projeto (0.4.23+).",
            "Status: requires-review — promover manualmente para paths ativos.",
            "",
            "## Skills",
            "",
        ]
        if skills_root.is_dir():
            for skill_md in sorted(skills_root.rglob("SKILL.md")):
                rel = skill_md.relative_to(root).as_posix()
                lines.append(f"- `{rel}`")
        else:
            lines.append("- _(nenhuma)_")
        lines += ["", "## Rules", ""]
        if rules_root.is_dir():
            for rule in sorted(rules_root.rglob("*")):
                if rule.is_file() and rule.name != "LEGACY-IMPORT.md":
                    lines.append(f"- `{rule.relative_to(root).as_posix()}`")
        else:
            lines.append("- _(nenhuma)_")
        out = root / "memory" / "legacy-import" / "INDEX.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return out

    def get(self, task_id: str) -> TaskRecord:
        task = self.repo.get(task_id)
        if not task:
            raise TaskNotFoundError(task_id)
        return task

    def list_tasks(self, limit: int = 50) -> list[TaskRecord]:
        # bug-064 — zumbis RECEIVED so eram varridos no create_task; quem
        # observa por MCP (list/status) agora tambem dispara a limpeza.
        self._cancel_stale_received()
        # bug-085 — e adota a orfã: cancelar depois de 6h resolvia o zumbi mas
        # nunca o trabalho; quem observa tem processo vivo, entao pode rodar.
        self._adopt_orphan_received_safe()
        return self.repo.list_tasks(limit=limit)

    def _adopt_orphan_received_safe(self, project_path: str | None = None) -> None:
        """Adoção nunca derruba leitura: observar é read-only para o chamador."""
        path = project_path or str(self.config.project_path)
        try:
            if self._busy_task_id(path) is None:
                self._adopt_orphan_received(path)
        except Exception:  # noqa: BLE001
            pass

    def cancel(self, task_id: str, reason: str = "cancel requested") -> TaskRecord:
        task = self.get(task_id)
        task.cancel_requested = True
        reason_text = (reason or "cancel requested").strip() or "cancel requested"
        if not task.error:
            task.error = reason_text
        elif reason_text not in str(task.error):
            task.error = f"{task.error} | cancel: {reason_text}"
        # Propaga o cancel para os CLIs filhos ainda vivos — sem isso o Codex
        # órfão segue rodando e segurando o workspace após o cancelamento.
        killed: list[int] = []
        try:
            killed = self.executor.kill_active()
        except Exception:  # noqa: BLE001
            killed = []
        if killed:
            self.bus.emit(
                RuntimeEvent(
                    task_id=task.id,
                    type=EventType.TASK_CANCELLED,
                    data={
                        "killed_pids": killed,
                        "summary": "child CLIs killed",
                        "reason": reason_text,
                    },
                )
            )
        if can_resume(task.status):
            started = task.status not in {
                TaskState.RECEIVED,
                TaskState.QUEUED,
            }
            self.repo.transition(
                task,
                TaskState.CANCELLED,
                reason=reason_text,
                agent="runtime",
                error=reason_text,
            )
            self.bus.emit(
                RuntimeEvent(
                    task_id=task.id,
                    type=EventType.TASK_CANCELLED,
                    data={"reason": reason_text},
                )
            )
            # Learn-then-compact também no cancelamento após execução (0.4.14).
            if started:
                self._persist_episode(task, success=False)
        else:
            self.repo.save(task)
        # bug-059: cancelar quem segurava (ou encabeçava) a fila precisa
        # destravar quem está atrás — sem isto o dequeue só acontecia quando
        # alguma outra run_task terminasse.
        try:
            self._maybe_start_next(task.project_path)
        except Exception:  # noqa: BLE001
            pass
        return task

    def _ensure_runnable(self, task: TaskRecord) -> TaskRecord:
        """Recarrega do DB; aborta se cancel/terminal (bug-022 hard-stop)."""
        fresh = self.get(task.id)
        if fresh.cancel_requested and fresh.status not in TERMINAL_STATES:
            self.cancel(fresh.id, reason=fresh.error or "cancel requested")
            raise CancelledError(f"task {fresh.id} cancelled")
        if fresh.status in TERMINAL_STATES:
            raise CancelledError(
                f"task {fresh.id} terminal ({fresh.status.value})"
            )
        return fresh

    def status(self, task_id: str) -> dict[str, Any]:
        # bug-064 — zumbis RECEIVED so eram varridos no create_task; o poll de
        # status (MCP) tambem dispara a limpeza, senao task orfã fica eterna.
        self._cancel_stale_received()
        task = self.get(task_id)
        # bug-085 — o poll de status é o evento mais frequente da frota; é ele
        # que tira a órfã do limbo quando o processo criador não voltou.
        self._adopt_orphan_received_safe(task.project_path)
        out: dict[str, Any] = {
            "id": task.id,
            "status": task.status.value,
            "iteration": task.iteration,
            "last_score": task.last_score,
            "plan": task.plan,
            "error": task.error,
            "documentation_review": task.documentation_review,
        }
        if task.status == TaskState.QUEUED:
            out["queue_position"] = self._queue_position(task.id, task.project_path)
            out["blocked_by"] = self._blocked_by_from_error(task.error)
        return out

    @staticmethod
    def _blocked_by_from_error(error: str | None) -> str | None:
        if not error:
            return None
        m = re.match(r"queued_behind:([^|\s]+)", error)
        return m.group(1) if m else None

    def _queue_position(self, task_id: str, project_path: str) -> int:
        for i, t in enumerate(self.repo.list_queued(project_path), start=1):
            if t.id == task_id:
                return i
        return len(self.repo.list_queued(project_path)) + 1

    def _busy_task_id(self, project_path: str, exclude_id: str | None = None) -> str | None:
        """Id da task que ocupa o workspace, ou None se livre."""
        active = self.repo.find_active_execution(project_path)
        if active and active.id != exclude_id:
            return active.id
        for rid in list(self._running_tasks):
            if rid == exclude_id:
                continue
            other = self.repo.get(rid)
            # bug-059: coroutine zumbi (presa no pré-loop) mantém a task em
            # _running_tasks mesmo depois de CANCELLED no DB — a fila inteira
            # ficava QUEUED "behind <task cancelada>". Terminal nunca ocupa.
            if (
                other
                and other.project_path == project_path
                and other.status not in TERMINAL_STATES
            ):
                return rid
        return None

    def _enqueue_task(self, task: TaskRecord, blocked_by: str) -> TaskRecord:
        """Coloca task na fila FIFO do workspace (estado QUEUED)."""
        task = self.get(task.id)
        if task.status in TERMINAL_LIKE:
            return task
        if task.status == TaskState.RECEIVED:
            self.repo.transition(
                task,
                TaskState.QUEUED,
                reason=f"workspace busy; behind {blocked_by}",
                agent="runtime",
            )
            task = self.get(task.id)
        elif task.status != TaskState.QUEUED:
            # Já saiu da fila / está em pipeline — não re-enfileirar.
            return task
        pos = self._queue_position(task.id, task.project_path)
        task.error = f"queued_behind:{blocked_by}|pos={pos}"
        self.repo.save(task)
        self.bus.emit(
            RuntimeEvent(
                task_id=task.id,
                type=EventType.TASK_QUEUED,
                agent="runtime",
                data={
                    "to": TaskState.QUEUED.value,
                    "summary": f"QUEUED behind {blocked_by} pos={pos}",
                    "blocked_by": blocked_by,
                    "queue_position": pos,
                    "reason": "workspace_busy",
                },
            )
        )
        self.bus.emit(
            RuntimeEvent(
                task_id=task.id,
                type=EventType.STATE_CHANGED,
                data={
                    "to": TaskState.QUEUED.value,
                    "summary": f"QUEUED behind {blocked_by} pos={pos}",
                    "blocked_by": blocked_by,
                    "queue_position": pos,
                    "reason": "workspace_busy",
                },
            )
        )
        return task

    def _maybe_start_next(self, project_path: str) -> None:
        """Dequeue FIFO: inicia a próxima QUEUED quando o workspace liberar."""
        if self._busy_task_id(project_path) is not None:
            return
        queued = self.repo.list_queued(project_path)
        if not queued:
            self._adopt_orphan_received(project_path)
            return
        nxt = queued[0]
        nxt = self.get(nxt.id)
        if nxt.status != TaskState.QUEUED:
            return
        nxt.error = None
        self.repo.save(nxt)
        self.repo.transition(
            nxt,
            TaskState.RECEIVED,
            reason="dequeued — workspace free",
            agent="runtime",
        )
        self._start_background(nxt.id, name="dequeue")

    def _start_background(self, task_id: str, *, name: str) -> None:
        def _bg() -> None:
            try:
                asyncio.run(self.run_task(task_id))
            except Exception as exc:  # noqa: BLE001
                _log.exception("%s run_task %s failed: %s", name, task_id, exc)

        threading.Thread(
            target=_bg, daemon=True, name=f"orch-{name}-{task_id[:8]}"
        ).start()

    def _adopt_orphan_received(self, project_path: str) -> None:
        """Assume task RECEIVED que ficou sem dono (bug-085).

        ``_maybe_start_next`` só olhava a fila QUEUED. Task criada por um
        processo que morreu antes de rodar o loop — cliente MCP recém-instalado
        que ainda não recarregou, CLI interrompido no meio do create — ficava
        em RECEIVED até o auto-cancel de 6h. Medido na trustsafe
        (c4b7a1d12d6b): criada 23:02, primeiro agente só 23:33, e nenhuma outra
        task ocupava o workspace — 30 min de fila parada sem motivo. Como
        `status`/`list` também chamam isto, qualquer poll adota a órfã.

        A janela ``orphan_received_adopt_after_s`` evita roubar a task de quem
        acabou de criá-la e vai chamar ``run_task`` em seguida.
        """
        after_s = self.config.limits.orphan_received_adopt_after_s
        if after_s <= 0:
            return
        now = datetime.now(timezone.utc)
        candidates: list[tuple[float, TaskRecord]] = []
        for task in self.repo.list_tasks(limit=100):
            if task.status != TaskState.RECEIVED:
                continue
            if task.project_path != project_path:
                continue
            if task.id in self._running_tasks or task.id in self._adopted:
                continue
            if task.cancel_requested:
                continue
            try:
                ts = task.created_at.replace("Z", "+00:00")
                dt = datetime.fromisoformat(ts)
                if dt.tzinfo is None:  # roundtrip SQLite perde o tz
                    dt = dt.replace(tzinfo=timezone.utc)
                age_s = (now - dt).total_seconds()
            except Exception:  # noqa: BLE001
                continue
            if age_s >= after_s:
                candidates.append((age_s, task))
        if not candidates:
            return
        # FIFO: a mais velha primeiro, como no dequeue.
        oldest = max(candidates, key=lambda pair: pair[0])[1]
        self._adopted.add(oldest.id)
        self.bus.emit(
            RuntimeEvent(
                task_id=oldest.id,
                type=EventType.STATE_CHANGED,
                agent="runtime",
                data={
                    "to": TaskState.RECEIVED.value,
                    "reason": "orphan_adopted",
                    "summary": (
                        "task RECEIVED sem dono adotada pelo runtime "
                        "(processo criador não rodou o loop)"
                    ),
                },
            )
        )
        self._start_background(oldest.id, name="adopt")

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

        # 0.4.19 — se outra task já ocupa o workspace, enfileira (não compete).
        busy = self._busy_task_id(task.project_path, exclude_id=task_id)
        if busy:
            return self._enqueue_task(task, blocked_by=busy)
        if task.status == TaskState.QUEUED:
            # Dequeued (RECEIVED) ou liberou — segue; se ainda QUEUED e livre,
            # promove para RECEIVED antes do loop.
            task = self.get(task_id)
            if task.status == TaskState.QUEUED:
                task.error = None
                self.repo.save(task)
                self.repo.transition(
                    task,
                    TaskState.RECEIVED,
                    reason="workspace free — leaving queue",
                    agent="runtime",
                )
                task = self.get(task_id)

        project_path = task.project_path
        held_lock = False
        result = task
        try:
            with self.lock:
                held_lock = True
                self._running_tasks.add(task_id)
                try:
                    result = await self._execute_loop(task)
                except CancelledError:
                    result = self.get(task_id)
                finally:
                    self._running_tasks.discard(task_id)
            return result
        except CancelledError:
            return self.get(task_id)
        except TimeoutError as exc:
            # Lock ocupado (outra coroutine/processo): fila explícita QUEUED.
            task = self.get(task_id)
            blocked = (
                self._busy_task_id(project_path, exclude_id=task_id) or "unknown"
            )
            _log.debug("enqueue %s behind %s (%s)", task_id, blocked, exc)
            return self._enqueue_task(task, blocked_by=blocked)
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
        finally:
            # Só dequeue se realmente rodamos sob o lock (não no caminho QUEUED).
            if held_lock:
                self._maybe_start_next(project_path)

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
        _a = analysis.model_dump()
        _a["caller"] = self.caller
        task.analysis = _a
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
        # bug-059: cancel chegando durante o pré-loop (baseline git etc.) tem
        # que abortar AQUI — o objeto task recebido é snapshot e o check
        # antigo de cancel_requested só rodava depois do primeiro transition.
        task = self._ensure_runnable(self.get(task.id))
        self._loop_started_monotonic = time.monotonic()
        self._git_baseline = capture_baseline(self.config.project_path)
        self._run_ctx = {}
        self._exhausted_models = set()

        # RECEIVED -> ANALYZING (WAITING_FOR_USER -> ANALYZING no resume)
        if task.status == TaskState.RECEIVED:
            self.repo.transition(task, TaskState.ANALYZING, reason="start analysis")
        elif task.status == TaskState.WAITING_FOR_USER:
            self.repo.transition(
                task, TaskState.ANALYZING, reason="resume after user input"
            )
        if task.error and (
            str(task.error).startswith("blocked_by_lock")
            or str(task.error).startswith("queued_behind:")
        ):
            task.error = None
            self.repo.save(task)

        if task.cancel_requested:
            return self.cancel(task.id, reason=task.error or "cancel requested")

        project_files = [p.name for p in self.config.project_path.iterdir()]
        analysis = await self.manager.analyze_task(task.prompt, project_files)
        task = self._ensure_runnable(task)
        task.task_type = analysis.task_type
        task.languages = analysis.languages
        task.risk = analysis.risk
        task.complexity = analysis.complexity
        task.requirements = analysis.requirements
        task.acceptance_criteria = analysis.acceptance_criteria
        # Preserva contexto de requires_input/resume — o re-analyze não pode
        # apagar a resposta do usuário nem o contador de perguntas.
        prior_analysis = task.analysis if isinstance(task.analysis, dict) else {}
        merged_analysis = analysis.model_dump()
        for key in (
            "user_message",
            "user_question",
            "user_options",
            "resume_instruction",
            "requires_input_count",
        ):
            if key in prior_analysis:
                merged_analysis[key] = prior_analysis[key]
        # 0.4.29 — origem da chamada fica registrada na task (relatorio/auditoria)
        merged_analysis["caller"] = self.caller
        task.analysis = merged_analysis
        self.repo.save(task)

        task = self._ensure_runnable(task)
        self.repo.transition(task, TaskState.RETRIEVING_MEMORY, reason="memory lookup")
        memories = self.repo.search_memories(task.prompt, limit=5)
        # 0.4.14 — aprendizados de tarefas anteriores (kind=learning) além dos episodes
        learnings = self.repo.search_memories(task.prompt, limit=3, kind="learning")
        self.bus.emit(
            RuntimeEvent(
                task_id=task.id,
                type=EventType.MEMORY_UPDATED,
                data={"retrieved": len(memories), "learnings": len(learnings)},
            )
        )

        task = self._ensure_runnable(task)
        # SKILL SELECTION (0.4.13): fast model picks installed skills before heavy models
        await self._select_skills(task)

        task = self._ensure_runnable(task)
        self.repo.transition(task, TaskState.PLANNING, reason="planning")
        plan_roles = await self.manager.select_strategy(task, analysis)
        task.plan = self.planner.plan(task, analysis, plan_roles)
        self._run_ctx["strategy"] = plan_roles.strategy
        self.repo.save(task)
        self.repo.add_routing_decision(task.id, plan_roles.strategy, plan_roles.model_dump())
        self.bus.emit(
            RuntimeEvent(
                task_id=task.id,
                type=EventType.PLAN_CREATED,
                data={"plan": task.plan},
            )
        )

        task = self._ensure_runnable(task)
        selecting_started = time.monotonic()
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
            selecting_elapsed = time.monotonic() - selecting_started
            if selecting_elapsed >= self.SELECTING_AGENTS_CAP_S:
                raise TimeoutError(
                    f"SELECTING_AGENTS excedeu {self.SELECTING_AGENTS_CAP_S}s "
                    f"(elapsed={selecting_elapsed:.0f}s)"
                )
            task = self._ensure_runnable(task)
            _tooling = self._required_tooling_block()
            _skills = self._skills_block(task)
            _learnings = self._learnings_block(learnings)
            _child = self._child_agent_restriction_block()
            plan_prompt = (
                f"{_child}\n"
                + (f"{_tooling}\n" if _tooling else "")
                + (f"{_skills}\n" if _skills else "")
                + (f"{_learnings}\n" if _learnings else "")
                + (
                    f"Refine o plano para: {task.prompt}\n"
                    f"Plano atual: {dumps(task.plan)}\n"
                    "Responda com passos objetivos sem abreviação. "
                    "NÃO delegue a subagentes — refine o plano sozinho."
                )
            )
            # O plano determinístico já existe; o refino é advisory.
            # 0.4.24: teto = min(PLANNER_REFINE_CAP, restante SELECTING_AGENTS_CAP).
            remaining_selecting = max(
                30,
                int(self.SELECTING_AGENTS_CAP_S - (time.monotonic() - selecting_started)),
            )
            refine_cap = min(self.PLANNER_REFINE_CAP_S, remaining_selecting)
            await self._run_agent(
                plan_roles.planner,
                "planner",
                plan_prompt,
                task,
                timeout_cap_s=refine_cap,
            )
        except CancelledError:
            raise
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
        # 0.4.28 — continuação de plano incompleto (não é iteração de validação)
        continuations = 0
        continuation_note = ""

        while True:
            task = self._ensure_runnable(self.get(task.id))

            remaining = self._remaining_duration_s(task)
            if remaining < MIN_AGENT_TIMEOUT_S:
                self.repo.transition(
                    task,
                    TaskState.INCOMPLETE,
                    reason="maximum_duration_seconds",
                    error=(
                        f"Orçamento de tempo esgotado "
                        f"(restante={remaining}s < {MIN_AGENT_TIMEOUT_S}s)"
                    ),
                )
                self.bus.emit(
                    RuntimeEvent(task_id=task.id, type=EventType.TASK_INCOMPLETE)
                )
                self._persist_episode(task, success=False)
                return task

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
            # bug-065 — baseline de testes ANTES de o executor tocar a árvore.
            # Suite já quebrada na entrada (corehub: restore NuGet falho no
            # CLI; printbee: suite da raiz quebrada — INCOMPLETE 1d63d2a5cb28)
            # era cobrada como "introduced" e a task estava condenada por
            # mérito alheio. Assinatura igual na iteração vira "preexisting".
            if task.iteration == 1 and "test_baseline" not in self._run_ctx:
                try:
                    baseline = self.tests.run_all(self.config.project_path)
                    self._run_ctx["test_baseline"] = baseline
                    for br in baseline:
                        self.repo.add_test_run(
                            task_id=task.id,
                            **{
                                **br,
                                "discovery_source": f"baseline:{br.get('discovery_source')}",
                            },
                        )
                    self.bus.emit(
                        RuntimeEvent(
                            task_id=task.id,
                            type=EventType.TEST_COMPLETED,
                            data={
                                "phase": "baseline",
                                "results": [
                                    {"command": t["command"], "status": t["status"]}
                                    for t in baseline
                                ],
                            },
                        )
                    )
                except Exception as base_exc:  # noqa: BLE001
                    # Infra no baseline: segue sem ele (comportamento estrito
                    # de antes da 0.4.44) em vez de derrubar a task.
                    self._run_ctx["test_baseline_error"] = str(base_exc)
            exec_prompt = self._build_executor_prompt(
                task,
                last_validation,
                memories,
                test_results=last_test_results,
                learnings=learnings,
                continuation_note=continuation_note,
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

            task = self.get(task.id)
            if task.cancel_requested:
                return self.cancel(task.id)

            premise_mismatch = self._parse_premise_mismatch(exec_result.stdout)
            if premise_mismatch:
                # Outcome terminal honrado: não há mudança, teste ou documentação
                # a exigir quando a própria premissa da tarefa está incorreta.
                analysis_d = dict(task.analysis or {})
                analysis_d["premise_mismatch"] = premise_mismatch
                task.analysis = analysis_d
                task.last_score = 1.0
                self.repo.save(task)
                self.repo.transition(
                    task,
                    TaskState.COMPLETED,
                    reason="premise_mismatch",
                    agent=plan_roles.executor,
                )
                self.bus.emit(
                    RuntimeEvent(
                        task_id=task.id,
                        type=EventType.STATE_CHANGED,
                        role=role,
                        agent=plan_roles.executor,
                        data={
                            "to": TaskState.COMPLETED.value,
                            "reason": "premise_mismatch",
                            "summary": premise_mismatch[:200],
                        },
                    )
                )
                self.bus.emit(
                    RuntimeEvent(
                        task_id=task.id,
                        type=EventType.TASK_COMPLETED,
                        data={"reason": "premise_mismatch"},
                    )
                )
                self._persist_episode(
                    task, success=True, strategy=plan_roles.strategy
                )
                self._export_memory_markdown(task)
                return task

            requires_input = (
                None
                if exec_result.changed_files
                else self._parse_requires_input(exec_result.stdout)
            )
            if requires_input:
                analysis_d = dict(task.analysis or {})
                count = int(analysis_d.get("requires_input_count") or 0) + 1
                analysis_d["requires_input_count"] = count
                analysis_d["user_question"] = requires_input["question"]
                analysis_d["user_options"] = requires_input["options"]
                task.analysis = analysis_d
                if count == 1:
                    # Pergunta estruturada pausa a task sem queimar a iteração.
                    task.iteration = max(0, task.iteration - 1)
                    self.repo.save(task)
                    self.repo.transition(
                        task,
                        TaskState.WAITING_FOR_USER,
                        reason="executor requires_input",
                        agent=plan_roles.executor,
                    )
                    self.bus.emit(
                        RuntimeEvent(
                            task_id=task.id,
                            type=EventType.STATE_CHANGED,
                            role=role,
                            agent=plan_roles.executor,
                            data={
                                "to": TaskState.WAITING_FOR_USER.value,
                                "summary": requires_input["question"][:200],
                            },
                        )
                    )
                    return task
                # Repetiu a pergunta após resposta do usuário: infra reject +
                # rotação de executor (não fica em loop de perguntas).
                self.repo.save(task)
                terminal, last_validation = await self._reject_iteration_infra(
                    task,
                    plan_roles,
                    issue_id="AGENT-REQUIRES-INPUT",
                    description=(
                        f"{role}/{plan_roles.executor} voltou a pedir decisão em "
                        f"vez de implementar: {requires_input['question'][:200]}"
                    ),
                    summary="executor asked instead of implementing",
                    error_text=(
                        "AGENT-REQUIRES-INPUT: executor repetiu pergunta após "
                        "resposta do usuário"
                    ),
                    issue_counts=issue_counts,
                )
                if terminal is not None:
                    return terminal
                continue

            spawn_failed = exec_result.exit_code == 127 or (
                exec_result.status == "failed"
                and "FileNotFoundError" in (exec_result.stderr or "")
            )
            # CLI "completou" mas não produziu nada (stdout vazio + nenhum arquivo
            # alterado, mesmo após fallback git). Sem este guard a iteração segue
            # para VALIDATING e vira rejeição falsa de AC workspace_changes.
            empty_output = (
                not spawn_failed
                and exec_result.status == "completed"
                and not (exec_result.stdout or "").strip()
                and not exec_result.changed_files
            )
            # bug-078 - CLI falhou (exit != 0) sem produzir NADA e a iteracao
            # seguia para validacao: task C (0.4.52) teve executor E corrector
            # codex morrendo exit 1 com changed=[] e o validador APROVOU 1.0
            # confundindo com o diff de outra task no mesmo arquivo -
            # fechamento falso com zero codigo entregue. failed + sem changed
            # (mesmo apos fallback git) e infra, nunca merito a validar.
            failed_no_output = (
                not spawn_failed
                and exec_result.status == "failed"
                and not exec_result.changed_files
            )
            if spawn_failed or empty_output or failed_no_output:
                if spawn_failed:
                    issue_id = "EXEC-SPAWN"
                    description = (
                        f"Falha ao iniciar CLI {plan_roles.executor}: "
                        f"{(exec_result.stderr or '')[:300]}"
                    )
                    summary = "executor spawn failed"
                    error_text = exec_result.stderr
                elif failed_no_output:
                    issue_id = "AGENT-FAILED-NO-OUTPUT"
                    description = (
                        f"{role}/{plan_roles.executor} falhou "
                        f"(exit={exec_result.exit_code}) sem alterar arquivos: "
                        f"{(exec_result.stderr or '')[:200]}"
                    )
                    summary = "agent failed without output"
                    error_text = (
                        f"AGENT-FAILED-NO-OUTPUT: {role}/{plan_roles.executor} "
                        f"exit={exec_result.exit_code} sem mudancas"
                    )
                else:
                    issue_id = "AGENT-EMPTY-OUTPUT"
                    description = (
                        f"{role}/{plan_roles.executor} terminou exit=0 sem stdout "
                        "e sem arquivos alterados (saída vazia do CLI)"
                    )
                    summary = "agent empty output"
                    error_text = (
                        f"AGENT-EMPTY-OUTPUT: {role}/{plan_roles.executor} "
                        "retornou saída vazia"
                    )
                terminal, last_validation = await self._reject_iteration_infra(
                    task,
                    plan_roles,
                    issue_id=issue_id,
                    description=description,
                    summary=summary,
                    error_text=error_text,
                    issue_counts=issue_counts,
                )
                if terminal is not None:
                    return terminal
                continue

            changed_files = list(
                dict.fromkeys(changed_files + exec_result.changed_files)
            )
            self._run_ctx["changed_files"] = changed_files

            # ---------------------------------------------------------------
            # 0.4.28 — plano incompleto: mandar CONTINUAR em vez de validar.
            # Agentes de CLI param no meio de planos longos ("concluí 1-3, quer
            # que eu siga?"). Sem isto o runtime tratava a parada como execução
            # terminada e ia validar trabalho pela metade.
            # ---------------------------------------------------------------
            plan_status = self._parse_plan_status(exec_result.stdout)
            plan_incomplete = self._is_plan_incomplete(plan_status, exec_result.stdout)
            if plan_incomplete and not exec_result.timed_out:
                if continuations < self.config.limits.max_plan_continuations:
                    continuations += 1
                    remaining = []
                    if isinstance(plan_status, dict):
                        remaining = [str(x) for x in (plan_status.get("remaining") or [])]
                    self.bus.emit(
                        RuntimeEvent(
                            task_id=task.id,
                            type=EventType.AGENT_COMPLETED,
                            role=role,
                            agent=plan_roles.executor,
                            data={
                                "status": "incomplete_plan",
                                "continuation": continuations,
                                "remaining": remaining[:10],
                                "summary": (
                                    f"plano incompleto — continuando "
                                    f"({continuations}/"
                                    f"{self.config.limits.max_plan_continuations})"
                                ),
                            },
                        )
                    )
                    continuation_note = self._continuation_note(
                        remaining, changed_files, continuations
                    )
                    # Continuar não é nova iteração de validação: devolve o
                    # contador que o topo do loop vai incrementar de novo.
                    task.iteration = max(0, task.iteration - 1)
                    self.repo.save(task)
                    continue
                # Orçamento de continuações esgotado: segue para validação com o
                # que existe, mas registra que o plano não fechou sozinho.
                self.bus.emit(
                    RuntimeEvent(
                        task_id=task.id,
                        type=EventType.AGENT_COMPLETED,
                        role=role,
                        agent=plan_roles.executor,
                        data={
                            "status": "continuation_budget_exhausted",
                            "summary": (
                                f"plano seguiu incompleto após "
                                f"{continuations} continuações; validando o que há"
                            ),
                        },
                    )
                )
            continuation_note = ""

            agent_timed_out = bool(exec_result.timed_out)
            if agent_timed_out and not exec_result.changed_files:
                # Padrão Codex/Windows (quoting/heredoc PowerShell): timeout sem
                # escrever nada. "Continue do disco" é inútil sem arquivos —
                # rejeita como infra e rotaciona o executor via fallback.
                #
                # bug-087 — três mortes diferentes vinham com o MESMO rótulo
                # "AGENT-TIMEOUT-NO-OUTPUT". Na GuardLine e0457603df65 o
                # corrector tinha 20KB de stderr e o registro dizia "timeout sem
                # arquivos alterados": quem leu o log procurou o defeito no
                # lugar errado. Rotular pela evidência.
                issue_id, description, error_text = self._timeout_issue(
                    role, plan_roles.executor, exec_result, task
                )
                terminal, last_validation = await self._reject_iteration_infra(
                    task,
                    plan_roles,
                    issue_id=issue_id,
                    description=description,
                    summary="executor timeout without changed files",
                    error_text=error_text,
                    issue_counts=issue_counts,
                )
                if terminal is not None:
                    return terminal
                continue

            # TESTING
            task = self._ensure_runnable(self.get(task.id))
            self.repo.transition(task, TaskState.TESTING, reason="deterministic tests")
            self.bus.emit(RuntimeEvent(task_id=task.id, type=EventType.TEST_STARTED))
            # bug-048 — pasta-mãe de repos aninhados: descoberta na raiz não
            # acha stack nenhuma; roda também nos repos filhos tocados.
            nested_test_dirs = sorted(
                {
                    f.split("/", 1)[0]
                    for f in changed_files
                    if "/" in f
                    and (
                        self.config.project_path / f.split("/", 1)[0] / ".git"
                    ).exists()
                }
            )
            test_results = self.tests.run_all(
                self.config.project_path,
                extra_dirs=nested_test_dirs,
                baseline=self._run_ctx.get("test_baseline"),
            )
            last_test_results = test_results
            self._run_ctx["test_results"] = test_results
            for tr in test_results:
                self.repo.add_test_run(task_id=task.id, **tr)
            self.bus.emit(
                RuntimeEvent(
                    task_id=task.id,
                    type=EventType.TEST_COMPLETED,
                    data={"results": [{"command": t["command"], "status": t["status"]} for t in test_results]},
                )
            )
            # bug-065 — falha "preexisting" (mesma assinatura da baseline
            # pré-executor) NÃO derruba o gate de testes: é quebra que já
            # existia, não mérito da iteração. Sem isto, o TEST-FAIL abaixo
            # condenava a task mesmo com o det aprovando (e2e 0.4.44).
            tests_passed = all(
                t["status"] in {"passed", "skipped"}
                or t.get("failure_kind") == "preexisting"
                for t in test_results
            )

            # VALIDATING
            task = self._ensure_runnable(self.get(task.id))
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
                # bug-053 — validator==executor após rotação de infra (ex.:
                # executor girou para o agente do validator após EXEC-SPAWN,
                # ou o validator caiu no agente do executor por quota) tornava
                # a aprovação IMPOSSÍVEL: VAL-IND bloqueava toda iteração até o
                # repeat-limit, mesmo com entrega válida (task ff270e3ff814).
                # Antes de bloquear, girar o validator para um fallback
                # disponível ≠ executor; só bloqueia se não houver alternativa.
                rotated = self._next_validator_fallback(task, plan_roles, val_agent)
                if rotated:
                    self.bus.emit(
                        RuntimeEvent(
                            task_id=task.id,
                            type=EventType.AGENT_COMPLETED,
                            role="validator",
                            agent=rotated,
                            data={
                                "status": "validator_rotated",
                                "reason": (
                                    f"validator==executor ({val_agent}); "
                                    f"validator → {rotated} (independent validation)"
                                ),
                            },
                        )
                    )
                    plan_roles.validator = rotated
                    val_agent = rotated
                else:
                    det["status"] = "rejected"
                    det["blocking_issues"] = list(det.get("blocking_issues") or []) + [
                        {
                            "id": "VAL-IND",
                            "severity": "blocking",
                            "description": (
                                "validator==executor com require_independent_validation "
                                "e nenhum validator alternativo disponível"
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
            if last_validation is det and self._validator_infra_failure(val_result):
                # Sem veredito LLM por falha de infra (ex.: sandbox Windows 740):
                # tentar validator alternativo; nunca virar rejeição de mérito.
                fb_agent = self._next_validator_fallback(task, plan_roles, val_agent)
                if fb_agent:
                    try:
                        val_result = await self._run_agent(
                            fb_agent, "validator", val_prompt, task
                        )
                        last_validation = self.llm_validator.parse(
                            val_result.stdout, det
                        )
                    except Exception:  # noqa: BLE001
                        last_validation = det
                if last_validation is det:
                    last_validation = dict(det)
                    last_validation["validator_infra_failure"] = True
                    last_validation["summary"] = (
                        str(det.get("summary") or "")
                        + " | validator infra failure — veredito LLM indisponível"
                        " (não é rejeição de mérito)"
                    )
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
                    and t.get("failure_kind") != "preexisting"
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

            if agent_timed_out:
                last_validation["status"] = "rejected"
                timeout_issues = list(last_validation.get("blocking_issues") or [])
                timeout_issues.insert(
                    0,
                    {
                        "id": "AGENT-TIMEOUT",
                        "severity": "blocking",
                        "description": (
                            f"{role}/{plan_roles.executor} atingiu timeout "
                            f"({exec_result.duration_s:.0f}s). Retome a partir dos "
                            f"arquivos já no disco; não reinvente o inventário."
                        ),
                    },
                )
                last_validation["blocking_issues"] = timeout_issues
                last_validation["score"] = min(
                    float(last_validation.get("score") or 0.0), 0.2
                )

            # 0.4.52-C2 — hashes dos inputs da validação: re-auditoria
            # futura reproduz o estado exato medido nesta rodada.
            last_validation["input_hashes"] = _collect_input_hashes(
                self.config.project_path, changed_files
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
                # Timeout: não contar VAL-* de workspace/evidence vazios no
                # same_issue_repeat (evita INCOMPLETE falso por entrega "vazia").
                if agent_timed_out and self._is_empty_delivery_issue(issue):
                    continue
                # bug-052 — identidade da issue = id + descrição normalizada.
                # IDs são posicionais (VAL-001 = 1ª issue da rodada): problemas
                # DIFERENTES caem no mesmo id entre iterações (iter1 "Critério
                # não atendido: coleção Postman..." → iter3 "Teste falhou: go
                # test") e o repeat-limit encerrava a task por coincidência de
                # posição, não por repetição real (task ff270e3ff814).
                norm = " ".join(str(desc or "").lower().split())[:160]
                issue_counts[f"{iid}|{norm}"] = issue_counts.get(f"{iid}|{norm}", 0) + 1

            task.last_score = float(last_validation.get("score") or 0)
            self._run_ctx["last_validation"] = last_validation
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

    def _required_tooling_block(self) -> str:
        """Bloco de ferramentas obrigatórias injetado em todos os prompts (0.4.12)."""
        if not self.config.limits.caveman_enabled:
            return ""
        return (
            "Ferramentas obrigatórias (always-on, 0.4.12):\n"
            "- OpenWolf: leia .wolf/STATUS.md ANTES de qualquer ação; "
            "consulte .wolf/cerebrum.md (Do-Not-Repeat) antes de gerar código; "
            "use .wolf/anatomy.md como índice de arquivos.\n"
            "- Graphify: se .codegraph/ existir, use `codegraph explore` "
            "para localizar símbolos antes de ler arquivos.\n"
            "- Superpowers: invoque a skill `using-superpowers` antes de qualquer ação; "
            "aplique skills de processo relevantes (brainstorming, systematic-debugging, etc.).\n"
            "- Caveman (full): prosa concisa sem artigos/enchimento. "
            "NUNCA abreviar JSON, logs, erros, planos, docs ou código."
        )

    def _pick_selector_agent(self) -> str | None:
        """Return best available CLI agent for skill selection (fast-tier capable)."""
        for name in ("claude", "codex", "opencode", "gemini", "kimi"):
            adapter = self.registry.get(name)
            if adapter and adapter.detect().available:
                return name
        return None

    async def _select_skills(self, task: TaskRecord) -> None:
        """Discover installed skills and select relevant ones with a fast model (0.4.13).

        Result stored in task.analysis["selected_skills"]. Fails silently so
        the workflow continues even when skill discovery or the CLI call fails.
        """
        if not self.config.limits.skill_selection_enabled:
            return
        from orchestrator_runtime.skills.discovery import discover_skills
        from orchestrator_runtime.skills.selector import (
            build_selector_prompt,
            parse_and_validate,
            select_skills_heuristic,
        )
        try:
            catalog = discover_skills(
                self.config.project_path,
                include_user_global=self.config.limits.skill_selection_include_user_global,
            )
        except Exception:  # noqa: BLE001
            return
        if not catalog:
            return
        max_skills = self.config.limits.skill_selection_max_skills
        selected: list[str] = []
        selector_agent = self._pick_selector_agent()
        if selector_agent:
            sel_prompt = build_selector_prompt(task.prompt, catalog, max_skills)
            try:
                sel_result = await self._run_agent(
                    selector_agent,
                    "skill_selector",
                    sel_prompt,
                    task,
                    timeout_cap_s=self.config.limits.skill_selection_timeout_s,
                )
                selected = parse_and_validate(sel_result.stdout, catalog, max_skills)
            except Exception:  # noqa: BLE001
                pass
        if not selected:
            selected = select_skills_heuristic(
                catalog,
                task.prompt,
                task.task_type,
                max_skills=max_skills,
            )
        if selected:
            analysis_d = dict(task.analysis or {})
            analysis_d["selected_skills"] = selected
            task.analysis = analysis_d
            self.repo.save(task)
            self.bus.emit(
                RuntimeEvent(
                    task_id=task.id,
                    type=EventType.ROUTING_DECIDED,
                    data={"selected_skills": selected, "skill_count": len(selected)},
                )
            )

    def _skills_block(self, task: TaskRecord) -> str:
        """Render selected skills for injection into prompts (0.4.13)."""
        analysis_d = task.analysis if isinstance(task.analysis, dict) else {}
        selected: list[str] = list(analysis_d.get("selected_skills") or [])
        if not selected:
            return ""
        from orchestrator_runtime.skills.discovery import discover_skills
        try:
            catalog = discover_skills(
                self.config.project_path,
                include_user_global=self.config.limits.skill_selection_include_user_global,
            )
        except Exception:  # noqa: BLE001
            catalog = []
        desc_map = {e.skill_id: e.description for e in catalog}
        lines = []
        for sid in selected:
            desc = desc_map.get(sid, "")
            lines.append(f"- {sid}: {desc}" if desc else f"- {sid}")
        return (
            "Skills selecionadas (instaladas; use APENAS estas, não invente outras):\n"
            + "\n".join(lines)
        )

    def _agents_block(self) -> str:
        """Personas de agente definidas no projeto (bug-081): o executor herda
        as INSTRUÇÕES como guia de escopo/convenções do time — nunca a
        delegação (delegação aninhada é proibida: faça você mesmo)."""
        roots = (
            (".claude/agents", "*.md"),
            (".codex/agents", "*.toml"),
            (".kimi-code/agents", "*.md"),
            (".opencode/agent", "*.md"),
        )
        found: list[str] = []
        for rel, pat in roots:
            d = self.config.project_path / rel
            if not d.is_dir():
                continue
            for f in sorted(d.glob(pat)):
                found.append(f"- {rel}/{f.name}")
        if not found:
            return ""
        return (
            "Agentes definidos no projeto (personas; use as INSTRUÇÕES como "
            "guia de escopo e convenções — NÃO delege: delegação aninhada é "
            "proibida, faça você mesmo sequencialmente):\n"
            + "\n".join(found[:12])
        )

    def _rules_block(self, task: TaskRecord) -> str:
        """Regras do projeto aplicáveis ao pedido (0.4.27).

        Sem isto o executor reimplementava padrões que o time já tinha escrito
        em `.cursor/rules/` — as regras existiam mas nunca chegavam ao agente.
        """
        from orchestrator_runtime.rules.discovery import select_rules

        analysis_d = task.analysis if isinstance(task.analysis, dict) else {}
        languages = list(analysis_d.get("languages") or [])
        try:
            rules = select_rules(
                self.config.project_path, task.prompt, languages=languages
            )
        except Exception:  # noqa: BLE001
            return ""
        if not rules:
            return ""

        lines = [
            "Regras do projeto aplicáveis (autoritativas; LEIA o arquivo antes "
            "de mexer na área que ele cobre):"
        ]
        for rule in rules:
            try:
                rel = rule.path.relative_to(self.config.project_path)
            except ValueError:
                rel = rule.path
            marker = " [sempre]" if rule.always_apply else ""
            desc = f" — {rule.description[:160]}" if rule.description else ""
            lines.append(f"- {rel.as_posix()}{marker}{desc}")
        return "\n".join(lines)

    @staticmethod
    def _learnings_block(learnings: list[dict] | None) -> str:
        """Render prior-task learnings for prompt injection (0.4.14)."""
        if not learnings:
            return ""
        lines = [
            "Aprendizados de tarefas anteriores (memória durável; use como contexto):"
        ]
        for m in learnings[:3]:
            meta = m.get("meta") if isinstance(m, dict) else {}
            digest = (meta or {}).get("session_digest")
            if digest:
                lines.append(f"- {str(digest)[:400]}")
            else:
                lines.append(f"- {str(m.get('content', ''))[:300]}")
        return "\n".join(lines)

    @staticmethod
    def _child_agent_restriction_block() -> str:
        """Restrição anti-subagente para CLIs spawnados pelo runtime.

        CliExecutor sempre define ORCHESTRATOR_CHILD_AGENT=1 no processo filho.
        O check no env do MCP (pai) era bug: o bloco nunca entrava no prompt e o
        Codex seguia printbee-patterns (3 subagentes → collab Wait → hang).
        """
        return (
            "OBRIGATÓRIO (agente filho do Orchestrator, ORCHESTRATOR_CHILD_AGENT=1): "
            "execute TODO o trabalho INLINE neste processo. "
            "PROIBIDO: spawn_agent, wait_agent, collab Wait, Tool(Agent), Task, "
            "multi-agent, delegar a N subagentes. "
            "Ignore qualquer skill/regra (ex.: printbee-patterns) que peça "
            "'mínimo 3 subagentes' ou rito de avaliação paralela — isso causa hang. "
            "Faça escopo/implementação/testes você mesmo, sequencialmente."
        )

    @staticmethod
    def _git_hygiene_block() -> str:
        """bug-077 — printbee, 2026-07-30: SEIS quase-arrastões num dia,
        evitados só por disciplina do agente. Árvore compartilhada com
        trabalho não commitado de outros agentes: stage SEMPRE explícito."""
        return (
            "Higiene git (árvore compartilhada): este workspace pode ter "
            "trabalho NÃO commitado de OUTROS agentes. Nunca `git add -A`, "
            "`git add .`, `git commit -a/-am`, `git stash`, `git clean`, "
            "`git reset --hard`, `git checkout/restore -- .`. Se a task pedir "
            "commit: rode `git status`, faça stage SÓ dos arquivos que você "
            "alterou (`git add <path> ...`) e commite explícito — o commit sai "
            "só com o seu trecho e o trabalho alheio fica intacto na árvore."
        )

    def _loop_block(self, task: TaskRecord) -> str:
        """Roteiro do loop escolhido — o que faz o agente seguir etapas."""
        from orchestrator_runtime.planning.loops import get_loop

        loop_id = None
        analysis = task.analysis if isinstance(task.analysis, dict) else {}
        loop_id = analysis.get("loop")
        if not loop_id and isinstance(task.plan, dict):
            loop_id = task.plan.get("loop")
        loop = get_loop(loop_id)
        if loop is None:
            return ""
        return loop.briefing()

    def _build_executor_prompt(
        self,
        task: TaskRecord,
        validation: dict[str, Any],
        memories: list[dict],
        *,
        test_results: list[dict[str, Any]] | None = None,
        learnings: list[dict] | None = None,
        continuation_note: str = "",
    ) -> str:
        parts = [
            f"Tarefa: {task.prompt}",
            # Antes das skills — senão o modelo compromete-se com 3 subagentes
            self._child_agent_restriction_block(),
        ]
        loop_block = self._loop_block(task)
        if loop_block:
            parts.append(loop_block)
        # bug-077 — higiene git sempre ligada no executor/corrector: árvore
        # compartilhada não pode depender de disciplina do agente.
        parts.append(self._git_hygiene_block())
        # 0.4.52-C1 - cap de 3 commits por iteracao (prompts.md Global Rule 17):
        # escopo grande convida a drift e fadiga de revisao.
        # bug-081 — o executor também herda os agentes do projeto (personas
        # como guia de escopo; delegação continua proibida).
        agents_block = self._agents_block()
        if agents_block:
            parts.append(agents_block)
        parts.append(
            "Cap de commits: máximo 3 commits nesta iteração. Se a correção "
            "natural pedir mais, pare nos 3 e descreva no relatório o plano de "
            "sub-slices restantes (sequenciais, na MESMA branch - nunca branch "
            "nova por sub-slice)."
        )

        if continuation_note:
            parts.append(continuation_note)
        parts.extend(
            [
                "Critérios:",
                *[f"- {c.id}: {c.description}" for c in task.acceptance_criteria],
            ]
        )
        if validation.get("blocking_issues"):
            parts.append("Corrija os issues:")
            for issue in validation["blocking_issues"]:
                if isinstance(issue, dict):
                    parts.append(f"- {issue.get('id')}: {issue.get('description')}")
                else:
                    parts.append(f"- {issue}")
            if any(
                isinstance(i, dict) and i.get("id") == "AGENT-TIMEOUT"
                for i in validation["blocking_issues"]
            ):
                parts.append(
                    "Atenção: a iteração anterior estourou timeout. "
                    "Inspecione o disco (git status) e continue o trabalho; "
                    "não recomece do zero."
                )
        if test_results:
            failed = [
                t
                for t in test_results
                if t.get("status") not in {"passed", "skipped"}
            ]
            introduced = [t for t in failed if t.get("failure_kind") != "preexisting"]
            preexisting = [t for t in failed if t.get("failure_kind") == "preexisting"]
            if introduced:
                parts.append("Testes que falharam (corrija até passarem):")
                for t in introduced:
                    parts.append(
                        f"- cmd={t.get('command')} status={t.get('status')} "
                        f"exit={t.get('exit_code')}"
                    )
            if preexisting:
                # bug-065 — já falhavam na baseline: informar para não
                # assustar, mas NÃO exigir correção (fora do escopo da task).
                parts.append(
                    "Falhas pré-existentes da suíte (já falhavam antes da "
                    "task; NÃO é exigido corrigir):"
                )
                for t in preexisting:
                    parts.append(
                        f"- cmd={t.get('command')} status={t.get('status')} "
                        f"exit={t.get('exit_code')}"
                    )
        if memories:
            parts.append("Memória relevante:")
            for m in memories[:3]:
                parts.append(f"- {m.get('content', '')[:200]}")
        learnings_block = self._learnings_block(learnings)
        if learnings_block:
            parts.append(learnings_block)
        analysis_d = task.analysis if isinstance(task.analysis, dict) else {}
        user_answer = analysis_d.get("user_message") or analysis_d.get(
            "resume_instruction"
        )
        if user_answer:
            parts.append(f"Decisão do usuário (já autorizada): {user_answer}")
        skills = self._skills_block(task)
        if skills:
            parts.append(skills)
        rules = self._rules_block(task)
        if rules:
            parts.append(rules)
        tooling = self._required_tooling_block()
        if tooling:
            parts.append(tooling)
        parts.append(
            "Escopo: o objetivo acima já define o que fazer. NÃO faça perguntas "
            "abertas nem pare para pedir decisão de negócio — implemente o "
            "escopo definido."
        )
        parts.append(
            "NÃO pare no meio do plano para perguntar se deve continuar: trabalhe "
            "até cumprir todos os critérios. Ao encerrar, emita como ÚLTIMA linha:\n"
            'PLAN_STATUS: {"complete": true}\n'
            'ou, se algo ficou pendente: PLAN_STATUS: {"complete": false, '
            '"remaining": ["o que falta", "..."]}\n'
            "O orquestrador usa essa linha para mandar continuar automaticamente."
        )
        parts.append(
            "Se a premissa da task for factualmente errada (já corrigido, já "
            "existe, já entregue no HEAD), NÃO invente trabalho: pare e responda "
            "com a linha `PREMISE_MISMATCH: <o que existe de verdade, com "
            "evidência>` — é um resultado de primeira classe, não uma falha."
        )
        parts.append(
            "Somente se estiver bloqueado por decisão externa obrigatória, "
            'escreva uma única linha REQUIRES_INPUT: {"question": "...", '
            '"options": ["..."]} e encerre imediatamente sem alterar arquivos.'
        )
        parts.append(self._stack_hint())
        if os.name == "nt":
            parts.append(
                "Ambiente Windows: NÃO use heredoc nem quoting complexo de "
                "PowerShell para criar arquivos; prefira a ferramenta de escrita "
                "de arquivos do agente, `python -c` ou arquivo temporário."
            )
        parts.append(
            "Caveman full na prosa; NUNCA abreviar JSON/logs/erros/planos/docs/código. "
            "Não declare sucesso sem evidências."
        )
        return "\n".join(parts)

    def _stack_hint(self) -> str:
        cmds = stack_test_commands(self.config.project_path)
        if not cmds:
            return (
                "Nenhuma suite de testes detectada no workspace; "
                "não invente comandos de teste."
            )
        return (
            "Testes detectados no workspace: "
            + "; ".join(cmds)
            + ". Use SOMENTE estes comandos de teste; não exija outros "
            "(ex.: pytest em projeto Node/Angular)."
        )

    _REQUIRES_INPUT_RE = re.compile(
        r"^\s*REQUIRES_INPUT\s*:\s*(.+)$", re.MULTILINE
    )

    # Aceita marcador puro ou envolvido por bullet/ênfase Markdown na própria linha.
    _PREMISE_MISMATCH_RE = re.compile(
        r"^[\t ]*(?:[-*>]\s*)*(?:[`*_~]+\s*)?"
        r"PREMISE_MISMATCH(?:\s*[`*_~]+)?\s*:\s*"
        r"(?:[`*_~]+\s*)?(.+?)\s*$",
        re.MULTILINE | re.IGNORECASE,
    )

    # Contrato explícito de conclusão emitido pelo executor.
    _PLAN_STATUS_RE = re.compile(
        r"^\s*PLAN_STATUS\s*:\s*(\{.*\})\s*$", re.MULTILINE
    )

    # Fallback: frases com que os CLIs param no meio do plano pedindo permissão.
    _EARLY_STOP_RE = re.compile(
        r"(?:"
        r"quer(?:e|ia)?\s+que\s+eu\s+(?:continue|siga|prossiga)"
        r"|posso\s+(?:continuar|seguir|prosseguir)"
        r"|deseja\s+que\s+eu\s+(?:continue|siga|prossiga)"
        r"|(?:me\s+)?avise\s+se\s+(?:quiser|deseja|posso)"
        r"|continuo\s*\?"
        r"|shall\s+i\s+(?:continue|proceed)"
        r"|(?:do\s+you\s+)?want\s+me\s+to\s+(?:continue|proceed)"
        r"|let\s+me\s+know\s+if\s+you(?:'d| would)?\s+like\s+me\s+to"
        r"|(?:next|remaining)\s+steps?\s*:"
        r"|(?:proximos|próximos)\s+passos\s*:"
        r"|(?:ainda\s+)?falta(?:m|ndo)?\s+(?:implementar|fazer|concluir|as\s+etapas)"
        r"|n[aã]o\s+implementei"
        r"|parte\s+\d+\s+de\s+\d+"
        r"|etapa\s+\d+\s+de\s+\d+"
        r")",
        re.IGNORECASE,
    )

    @classmethod
    def _parse_plan_status(cls, stdout: str | None) -> dict[str, Any] | None:
        """Lê a linha PLAN_STATUS que o executor deve emitir ao terminar."""
        match = cls._PLAN_STATUS_RE.search(stdout or "")
        if not match:
            return None
        try:
            data = json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    @classmethod
    def _is_plan_incomplete(
        cls, plan_status: dict[str, Any] | None, stdout: str | None
    ) -> bool:
        """Plano ficou pela metade?

        Primeiro o contrato explícito (PLAN_STATUS). Sem ele, cai nas frases de
        parada que os CLIs usam para pedir permissão de seguir — o comportamento
        que o usuário relata como "o agente para no meio do plano".
        """
        if isinstance(plan_status, dict) and "complete" in plan_status:
            return not bool(plan_status.get("complete"))
        if plan_status is not None:
            return False
        return bool(cls._EARLY_STOP_RE.search(stdout or ""))

    @staticmethod
    def _continuation_note(
        remaining: list[str], changed_files: list[str], attempt: int
    ) -> str:
        parts = [
            f"CONTINUACAO {attempt}: a execucao anterior parou com o plano "
            "INCOMPLETO. Retome de onde parou; NAO recomece do zero e NAO "
            "refaca o que ja esta no disco.",
        ]
        if changed_files:
            parts.append(
                "Ja alterado: " + ", ".join(changed_files[:12])
                + (" ..." if len(changed_files) > 12 else "")
            )
        if remaining:
            parts.append("Falta concluir:")
            parts.extend(f"- {item}" for item in remaining[:10])
        parts.append(
            "Trabalhe ate cumprir TODOS os criterios de aceitacao. Nao pergunte "
            "se deve continuar — continue."
        )
        return "\n".join(parts)

    @classmethod
    def _parse_requires_input(cls, stdout: str | None) -> dict[str, Any] | None:
        match = cls._REQUIRES_INPUT_RE.search(stdout or "")
        if not match:
            return None
        payload = match.group(1).strip()
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict) and data.get("question"):
            return {
                "question": str(data["question"]),
                "options": [str(o) for o in data.get("options") or []],
            }
        return {"question": payload[:500], "options": []}

    @classmethod
    def _parse_premise_mismatch(cls, stdout: str | None) -> str | None:
        """Extrai a explicação do outcome terminal PREMISE_MISMATCH."""
        match = cls._PREMISE_MISMATCH_RE.search(stdout or "")
        if not match:
            return None
        explanation = re.sub(
            r"\s*[`*_~]+\s*$", "", match.group(1).strip()
        ).strip()
        return explanation[:500] or None

    def _build_validator_prompt(
        self,
        task: TaskRecord,
        det: dict[str, Any],
        tests: list[dict],
        changed_files: list[str],
    ) -> str:
        tooling = self._required_tooling_block()
        tooling_section = f"{tooling}\n" if tooling else ""
        skills = self._skills_block(task)
        skills_section = f"{skills}\n" if skills else ""
        child = self._child_agent_restriction_block()
        return (
            "Valide a tarefa e responda APENAS JSON com status/score/blocking_issues.\n"
            f"{child}\n"
            # bug-067 — o juiz roda `git status` com as próprias ferramentas e
            # via arquivos sujos da INFRA do orquestrador (update/propagação,
            # adapters) como "alteração fora de escopo" — iter 1 da task
            # c003522e25e2 (printbee) foi reprovada por isso. Não é trabalho
            # do agente nem violação: ignorar explicitamente.
            "Infra do orquestrador (NUNCA é escopo da task nem violação de "
            "escopo, mesmo suja no `git status`): .orchestrator/, .wolf/, "
            ".cursor/, .codex/, .claude/, .gemini/, .kimi/, AGENTS.md, "
            "CLAUDE.md, CURSOR.md, GEMINI.md, KIMI.md. Ignore esses arquivos "
            "ao julgar escopo e changed_files.\n"
            f"Prompt original: {task.prompt}\n"
            f"Critérios: {dumps([c.model_dump() for c in task.acceptance_criteria])}\n"
            f"Diff/arquivos: {changed_files}\n"
            # bug-065 — failure_kind no payload: o juiz precisa distinguir
            # falha introduzida de pré-existente (baseline) para não reprovar
            # mérito alheio.
            f"Testes: {dumps([{k: t.get(k) for k in ('command','status','exit_code','failure_kind')} for t in tests])}\n"
            "Regra: failure_kind=preexisting significa que o teste JÁ "
            "falhava antes da task (baseline pré-executor); não reprove a "
            "task por ele. Falhas introduced sim são mérito da iteração.\n"
            "Commits: se a iteração produziu mais de 3 commits novos do agente, "
            "sinalize como non-blocking (indício de escopo estourado/drift); "
            "não reprove só por isso.\n"
            f"Validação determinística: {dumps(det)}\n"
            f"{self._stack_hint()}\n"
            f"{skills_section}"
            f"{tooling_section}"
        )

    # bug-087 — quem morreu por quê. As três causas têm remédios opostos:
    # pendurado => trocar de agente; orçamento => aumentar o teto da task;
    # timeout com saída => o agente falou mas não entregou (mérito, não infra).
    _BUDGET_FLOOR_S = 30

    def _timeout_issue(
        self,
        role: str,
        agent_id: str,
        result: AgentResult,
        task: TaskRecord,
    ) -> tuple[str, str, str]:
        produced = bool((result.stdout or "").strip() or (result.stderr or "").strip())
        hung = NO_OUTPUT_MARKER in (result.stderr or "")
        budget_over = self._remaining_duration_s(task) <= self._BUDGET_FLOOR_S
        secs = f"{result.duration_s:.0f}s"
        if hung:
            return (
                "AGENT-NO-OUTPUT-HANG",
                f"{role}/{agent_id} pendurado: {secs} sem NENHUMA saída e sem "
                "tocar no workspace; morto pelo watchdog antes de consumir o "
                "orçamento da task",
                f"AGENT-NO-OUTPUT-HANG: {role}/{agent_id} pendurado sem saída",
            )
        if budget_over:
            return (
                "TASK-BUDGET-EXHAUSTED",
                f"{role}/{agent_id} cortado em {secs} pelo "
                f"maximum_duration_seconds da task "
                f"({task.constraints.maximum_duration_seconds}s), não pelo "
                f"timeout do papel"
                + (" — havia saída em andamento" if produced else ""),
                f"TASK-BUDGET-EXHAUSTED: {role}/{agent_id} morto pelo teto da task",
            )
        if produced:
            return (
                "AGENT-TIMEOUT-NO-CHANGES",
                f"{role}/{agent_id} atingiu timeout ({secs}) com saída mas sem "
                "alterar arquivo nenhum",
                f"AGENT-TIMEOUT-NO-CHANGES: {role}/{agent_id} timeout com saída "
                "e sem mudanças",
            )
        return (
            "AGENT-TIMEOUT-NO-OUTPUT",
            f"{role}/{agent_id} atingiu timeout ({secs}) sem alterar arquivos",
            f"AGENT-TIMEOUT-NO-OUTPUT: {role}/{agent_id} timeout sem arquivos "
            "alterados",
        )

    def _remaining_duration_s(self, task: TaskRecord) -> int:
        started = self._loop_started_monotonic
        if started is None:
            return int(task.constraints.maximum_duration_seconds)
        elapsed = time.monotonic() - started
        return max(0, int(task.constraints.maximum_duration_seconds - elapsed))

    def _resolve_agent_timeout(self, role: str, task: TaskRecord) -> int:
        return resolve_agent_timeout(
            role,
            remaining_s=self._remaining_duration_s(task),
            by_role=self.config.limits.agent_timeout_by_role,
            default_s=self.config.limits.agent_timeout_default_s,
        )

    # Marcadores de falha de infra do validator (sandbox Windows sem elevação).
    _VALIDATOR_INFRA_MARKERS = (
        "createprocessasuserw failed: 740",
        "windows error 740",
        "requer elevação",
        "requer elevacao",
        "windows sandbox: runner failed",
    )

    @classmethod
    def _validator_infra_failure(cls, result: AgentResult) -> bool:
        """Validator falhou por infra (processo/sandbox), não por mérito."""
        if result.status != "completed":
            return True
        blob = ((result.stdout or "") + (result.stderr or "")).lower()
        return any(m in blob for m in cls._VALIDATOR_INFRA_MARKERS)

    # bug-070 — circuit breaker: o binário existe (detect() passa) mas o
    # SERVIÇO está morto (opencode: "Unexpected server error" em ~8s — 15
    # falhas instantâneas registradas no printbee entre validator/executor).
    # Toda rotação de fallback caía no mesmo agente morto e queimava a
    # iteração. N falhas rápidas consecutivas dentro da janela => quarentena:
    # os pontos de escolha de fallback pulam para o próximo candidato.
    _QUARANTINE_RUNS = 3
    _QUARANTINE_MAX_DURATION_S = 30.0
    _QUARANTINE_WINDOW_S = 6 * 3600  # cooldown: falha velha não condena para sempre

    @staticmethod
    def _duration_between(start: Any, end: Any) -> float | None:
        if not start or not end:
            return None
        try:
            a = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
            b = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
            if a.tzinfo is None:
                a = a.replace(tzinfo=timezone.utc)
            if b.tzinfo is None:
                b = b.replace(tzinfo=timezone.utc)
            return (b - a).total_seconds()
        except Exception:  # noqa: BLE001
            return None

    def _agent_quarantined(self, agent_id: str) -> bool:
        try:
            runs = self.repo.list_recent_agent_runs(agent_id, self._QUARANTINE_RUNS)
        except Exception:  # noqa: BLE001
            return False
        if len(runs) < self._QUARANTINE_RUNS:
            return False
        now = datetime.now(timezone.utc)
        for r in runs:
            if str(r.get("status")) != "failed":
                return False
            dur = self._duration_between(r.get("started_at"), r.get("finished_at"))
            if dur is None or dur > self._QUARANTINE_MAX_DURATION_S:
                return False
            started = self._duration_between(
                r.get("started_at"), now.isoformat()
            )
            if started is None or started > self._QUARANTINE_WINDOW_S:
                return False  # fora da janela: cooldown encerrado
        return True

    def _next_validator_fallback(
        self, task: TaskRecord, plan_roles: Any, current: str
    ) -> str | None:
        fallbacks = (task.plan or {}).get("fallbacks", {}).get("validator") or []
        for fb in fallbacks:
            if fb in {current, plan_roles.executor}:
                continue
            if self._agent_quarantined(fb):
                continue  # bug-070 — serviço morto; próximo candidato
            adapter = self.registry.get(fb)
            if adapter and adapter.detect().available:
                return fb
        return None

    async def _reject_iteration_infra(
        self,
        task: TaskRecord,
        plan_roles: Any,
        *,
        issue_id: str,
        description: str,
        summary: str,
        error_text: str | None,
        issue_counts: dict[str, int],
    ) -> tuple[TaskRecord | None, dict[str, Any]]:
        """Iteração rejeitada por falha de infra do executor (spawn/saída vazia).

        Retorna (task_terminal | None, last_validation). None → caller continua
        o loop em CORRECTING com fallback de executor aplicado.
        """
        last_validation: dict[str, Any] = {
            "status": "rejected",
            "score": 0.0,
            "blocking_issues": [
                {
                    "id": issue_id,
                    "severity": "blocking",
                    "description": description,
                }
            ],
            "summary": summary,
        }
        self._run_ctx["last_validation"] = last_validation
        decision = await self.manager.evaluate_iteration(
            task, last_validation, task.iteration
        )
        issue_counts[issue_id] = issue_counts.get(issue_id, 0) + 1
        if issue_counts[issue_id] >= self.config.limits.same_issue_repeat_limit:
            decision.action = "stop_incomplete"
            decision.reason = "same_issue_repeat_limit"
        self.repo.add_iteration(
            task.id,
            task.iteration,
            0.0,
            decision.action,
            {"reason": decision.reason, "infra_issue": issue_id},
        )
        if decision.action in {"stop_incomplete", "fail"}:
            target = (
                TaskState.FAILED
                if decision.action == "fail"
                else TaskState.INCOMPLETE
            )
            self.repo.transition(
                task, target, reason=decision.reason, error=error_text
            )
            self._persist_episode(task, success=False)
            return task, last_validation
        # Tentar fallback de executor na próxima iteração
        fallbacks = (task.plan or {}).get("fallbacks", {}).get("executor") or []
        for fb in fallbacks:
            if (
                fb != plan_roles.executor
                and self.registry.get(fb)
                and not self._agent_quarantined(fb)  # bug-070 — serviço morto
            ):
                plan_roles.executor = fb
                break
        self.repo.transition(
            task,
            TaskState.CORRECTING,
            reason=f"{issue_id} → correct/fallback",
            agent=plan_roles.executor,
        )
        return None, last_validation

    @staticmethod
    def _is_empty_delivery_issue(issue: Any) -> bool:
        """VAL de workspace/evidence vazio — não deve acelerar same_issue após timeout."""
        if not isinstance(issue, dict):
            return False
        if issue.get("id") == "AGENT-TIMEOUT":
            return False
        kind = str(issue.get("kind") or "").lower()
        if kind in {"workspace_changes", "evidence"}:
            return True
        desc = str(issue.get("description") or "").lower()
        markers = (
            "workspace_changes",
            "entregável",
            "entregavel",
            "arquivos vazio",
            "diff/arquivos vazio",
            "nenhum entregável",
            "changed_files",
        )
        return any(m in desc for m in markers)

    def _enrich_changed_files(self, result: AgentResult) -> AgentResult:
        if result.changed_files:
            return result
        from_git = changed_files_since(self.config.project_path, self._git_baseline)
        if from_git:
            result.changed_files = list(from_git)
        return result

    def _register_heartbeat(self, task: TaskRecord, *, role: str, agent_id: str) -> None:
        """Sinal de vida do CLI durante EXECUTING.

        0.4.28 fez o heartbeat virar evento; 0.4.29 fez o evento ser PERSISTIDO
        (o bus so imprime no console de quem chamou) e a cadencia vir do perfil
        do chamador — sessao bloqueante fica muda entre um sinal e outro.
        """
        if getattr(self, "executor", None) is None:
            return

        def _emit_heartbeat(elapsed: int, pid: int, _t=task, _r=role, _a=agent_id):
            evt = RuntimeEvent(
                task_id=_t.id,
                type=EventType.AGENT_PROGRESS,
                role=_r,
                agent=_a,
                data={
                    "elapsed_s": elapsed,
                    "pid": pid,
                    "summary": f"{_r}/{_a} rodando ha {elapsed}s",
                },
            )
            try:
                self.bus.emit(evt)
                self.repo.add_event(evt)
            except Exception:  # noqa: BLE001
                pass  # sinal de vida nunca derruba a execucao

        try:
            self.executor.on_heartbeat = _emit_heartbeat
        except Exception:  # noqa: BLE001
            pass

        # bug-086 — watchdog de silencio. A sonda existe porque `claude -p` so
        # imprime no fim: silencio sozinho nao prova nada, silencio COM zero
        # arquivo tocado prova. Sem isso, 40 min de agente pendurado saiam do
        # orcamento do agente seguinte, que morria trabalhando.
        def _workspace_progress() -> bool:
            try:
                return bool(
                    changed_files_since(self.config.project_path, self._git_baseline)
                )
            except Exception:  # noqa: BLE001
                # Git indisponivel/lento: sem prova de morte, nao mata.
                return True

        try:
            self.executor.no_output_timeout_s = (
                self.config.limits.agent_no_output_timeout_s
            )
            self.executor.progress_probe = _workspace_progress
        except Exception:  # noqa: BLE001
            pass

    async def _run_agent(
        self,
        agent_id: str,
        role: str,
        prompt: str,
        task: TaskRecord,
        *,
        timeout_cap_s: int | None = None,
    ):
        self._register_heartbeat(task, role=role, agent_id=agent_id)

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

        timeout_s = self._resolve_agent_timeout(role, task)
        if timeout_cap_s is not None:
            timeout_s = min(timeout_s, int(timeout_cap_s))
        if timeout_s < MIN_AGENT_TIMEOUT_S:
            raise RuntimeError(
                f"Orçamento de tempo insuficiente para {role} "
                f"(timeout_s={timeout_s})"
            )

        from orchestrator_runtime.routing.quota import should_retry_next_model

        candidates = self.router.resolve_model_candidates(
            agent_id, task.task_type, role=role
        )
        if not candidates:
            candidates = [(None, None)]

        # Filtra modelos já esgotados neste run; se todos esgotados, tenta o 1º.
        usable = [
            c
            for c in candidates
            if (agent_id, str(c[0] or "")) not in self._exhausted_models
        ]
        if not usable:
            usable = list(candidates)

        last_result = None
        art_dir = self.config.orchestrator_root / "runtime" / "results" / task.id
        art_dir.mkdir(parents=True, exist_ok=True)

        for idx, (model, model_flag) in enumerate(usable):
            self.bus.emit(
                RuntimeEvent(
                    task_id=task.id,
                    type=EventType.AGENT_STARTED,
                    role=role,
                    agent=agent_id,
                    data={
                        "model": model,
                        "timeout_s": timeout_s,
                        "model_attempt": idx + 1,
                        "model_candidates": [c[0] for c in usable],
                    },
                )
            )
            request = AgentRequest(
                role=role,
                prompt=prompt,
                model=model,
                model_flag=model_flag,
                cwd=str(self.config.project_path),
                timeout_s=timeout_s,
            )
            result = await adapter.run(request)
            result = self._enrich_changed_files(result)
            last_result = result
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
            out_path = art_dir / f"{role}-{agent_id}.txt"
            out_path.write_text(
                result.stdout + "\n" + result.stderr, encoding="utf-8"
            )
            self.repo.add_artifact(task.id, "agent_output", str(out_path))
            self.repo.update_agent_performance(
                agent_id,
                result.status == "completed",
                result.duration_s,
                task.last_score,
            )

            if result.status == "completed":
                self.bus.emit(
                    RuntimeEvent(
                        task_id=task.id,
                        type=EventType.AGENT_COMPLETED,
                        role=role,
                        agent=agent_id,
                        data={
                            "status": result.status,
                            "exit_code": result.exit_code,
                            "timed_out": result.timed_out,
                            "timeout_s": timeout_s,
                            "model": model,
                        },
                    )
                )
                return result

            # 0.4.25 — cota/rate-limit: tenta próximo modelo da preferência do papel
            has_next = idx + 1 < len(usable)
            if has_next and should_retry_next_model(result):
                exhausted_key = (agent_id, str(model or ""))
                self._exhausted_models.add(exhausted_key)
                next_model = usable[idx + 1][0]
                self.bus.emit(
                    RuntimeEvent(
                        task_id=task.id,
                        type=EventType.AGENT_COMPLETED,
                        role=role,
                        agent=agent_id,
                        data={
                            "status": "quota_exhausted",
                            "exit_code": result.exit_code,
                            "model": model,
                            "fallback_model": next_model,
                            "summary": (
                                f"cota/rate-limit em {model}; "
                                f"fallback → {next_model}"
                            ),
                        },
                    )
                )
                continue

            self.bus.emit(
                RuntimeEvent(
                    task_id=task.id,
                    type=EventType.AGENT_COMPLETED,
                    role=role,
                    agent=agent_id,
                    data={
                        "status": result.status,
                        "exit_code": result.exit_code,
                        "timed_out": result.timed_out,
                        "timeout_s": timeout_s,
                        "model": model,
                    },
                )
            )
            return result

        assert last_result is not None
        self.bus.emit(
            RuntimeEvent(
                task_id=task.id,
                type=EventType.AGENT_COMPLETED,
                role=role,
                agent=agent_id,
                data={
                    "status": last_result.status,
                    "exit_code": last_result.exit_code,
                    "timed_out": last_result.timed_out,
                    "timeout_s": timeout_s,
                    "model": getattr(last_result, "model", None),
                },
            )
        )
        return last_result

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
        # 0.4.14 — learn-then-compact: grava aprendizado durável ANTES de qualquer
        # compactação. Nunca compacta sem o learning já em disco.
        self._learn_then_compact(task, success=success, strategy=strategy)

    def _learn_then_compact(
        self, task: TaskRecord, *, success: bool, strategy: str | None = None
    ) -> None:
        """Save enriched learning THEN compact result artifacts (0.4.14).

        Ordem obrigatória: (1) extrair + persistir learning (SQLite kind=learning
        com meta rico + digest), export markdown + index.json, atualizar .wolf/;
        (2) só depois truncar artefatos grandes. Falha aqui nunca aborta a task.
        """
        limits = self.config.limits
        if not limits.context_compaction_enabled:
            return
        from orchestrator_runtime.memory import learnings as L

        try:
            learning = L.extract_learning(
                task,
                success=success,
                strategy=strategy,
                run_ctx=self._run_ctx,
            )
            digest = L.build_digest(learning, max_chars=limits.digest_max_chars)
            # Disponibiliza o digest para o result/status do MCP.
            analysis_d = dict(task.analysis or {})
            analysis_d["session_digest"] = digest
            task.analysis = analysis_d
            self.repo.save(task)

            if limits.save_learning_before_compact:
                # 1a. SQLite memory kind=learning (retrieval na próxima conversa)
                self.repo.save_memory(
                    "learning",
                    L.memory_content(learning),
                    task_id=task.id,
                    meta={**learning, "session_digest": digest},
                )
                # 1b. Markdown + index
                mem_root = self.config.orchestrator_root / "memory"
                L.write_markdown(mem_root / "learnings", learning, digest)
                L.update_index(mem_root, learning, digest)
                # 1c. .wolf/ (STATUS + cerebrum Do-Not-Repeat em pitfall)
                if limits.update_wolf_status:
                    wolf_dir = self.config.project_path / ".wolf"
                    L.update_wolf_status(wolf_dir, learning)
                    L.append_cerebrum_pitfall(wolf_dir, learning)
            self.bus.emit(
                RuntimeEvent(
                    task_id=task.id,
                    type=EventType.MEMORY_UPDATED,
                    data={"kind": "learning", "digest_chars": len(digest)},
                )
            )
            # 2. Compactação dos artefatos grandes — SÓ depois do learning salvo.
            # Invariante: nunca compacta sem o learning já em disco.
            if limits.save_learning_before_compact:
                results_dir = (
                    self.config.orchestrator_root / "runtime" / "results" / task.id
                )
                L.compact_result_artifacts(
                    results_dir, max_chars=limits.truncate_result_artifacts_chars
                )
        except Exception as exc:  # noqa: BLE001
            self.bus.emit(
                RuntimeEvent(
                    task_id=task.id,
                    type=EventType.MEMORY_UPDATED,
                    data={"kind": "learning", "error": str(exc)},
                )
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
