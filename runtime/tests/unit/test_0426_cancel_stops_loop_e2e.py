"""0.4.26 — bug-022 e2e: cancel no meio do loop encerra de verdade.

Regressao pedida pela auditoria de 2026-07-25 (R1): "cancelar em VALIDATING e
afirmar ausencia de eventos posteriores". Na frota foram medidos 19 casos de
transicao APOS o cancel (printbee 10, bootstrap 8, adzora 1) — task zumbi
seguia consumindo agente e segurando o lock do workspace.

O cancel aqui parte de DENTRO do executor (simula o operador cancelando com a
task em execucao), que e exatamente a corrida do incidente real.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from orchestrator_runtime.agents.base import AgentResult
from orchestrator_runtime.agents.base_adapters import FakeAgentAdapter
from orchestrator_runtime.config import load_config
from orchestrator_runtime.tasks.service import TaskService
from orchestrator_runtime.tasks.state_machine import TERMINAL_STATES, TaskState

NON_TERMINAL_AFTER_CANCEL: set[str] = {
    s.value for s in TaskState if s not in TERMINAL_STATES
}


class CancelMidFlightExecutor(FakeAgentAdapter):
    """Cancela a propria task na primeira chamada de executor."""

    def __init__(self, agent_id: str, project_path: Path) -> None:
        super().__init__(agent_id, project_path)
        self.service: TaskService | None = None
        self.task_id: str | None = None
        self.fired = False

    async def continue_session(self, session, request):  # type: ignore[no-untyped-def]
        if request.role == "executor" and not self.fired and self.service and self.task_id:
            self.fired = True
            self.service.cancel(self.task_id, reason="operador cancelou no meio")
        return AgentResult(
            session_id=session.id,
            agent_id=self.id,
            role=request.role,
            status="completed",
            exit_code=0,
            stdout=json.dumps({"summary": "trabalho parcial"}),
            stderr="",
            started_at=datetime.now(timezone.utc).isoformat(),
            finished_at=datetime.now(timezone.utc).isoformat(),
        )


def _states_after_cancel(service: TaskService, task_id: str) -> list[str]:
    """Estados para os quais a task transicionou DEPOIS de virar CANCELLED."""
    seen_cancel = False
    out: list[str] = []
    for ev in service.repo.list_events(task_id):
        data = ev.get("data") or {}
        to = data.get("to")
        if not to:
            continue
        if to == TaskState.CANCELLED.value:
            seen_cancel = True
            continue
        if seen_cancel:
            out.append(to)
    return out


def test_cancel_mid_execution_stops_loop(project: Path) -> None:
    config = load_config(project, fake_agents=True)
    service = TaskService(config, verbose=False)

    executor = CancelMidFlightExecutor("claude", project)
    for name in ("claude", "codex", "opencode"):
        service.registry._adapters[name] = executor

    task = service.create_task("tarefa que sera cancelada no meio", max_iterations=3)
    executor.service = service
    executor.task_id = task.id

    asyncio.run(service.run_task(task.id))

    final = service.get(task.id)
    assert executor.fired, "o executor precisa ter disparado o cancel"
    assert final.status == TaskState.CANCELLED
    assert final.cancel_requested is True

    zumbis = [s for s in _states_after_cancel(service, task.id) if s in NON_TERMINAL_AFTER_CANCEL]
    assert zumbis == [], f"transicoes zumbis apos o cancel: {zumbis}"


def test_cancelled_task_is_not_rerun(project: Path) -> None:
    """run_task numa task ja CANCELLED nao ressuscita nem gera eventos."""
    config = load_config(project, fake_agents=True)
    service = TaskService(config, verbose=False)

    task = service.create_task("tarefa cancelada antes de rodar", max_iterations=1)
    service.cancel(task.id, reason="cancelada antes de comecar")
    before = len(service.repo.list_events(task.id))

    result = asyncio.run(service.run_task(task.id))

    assert result.status == TaskState.CANCELLED
    assert len(service.repo.list_events(task.id)) == before
