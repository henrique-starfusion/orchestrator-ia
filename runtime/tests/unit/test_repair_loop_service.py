"""Garante o ciclo execute → test → validate → correct (repair loop)."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from orchestrator_runtime.agents.base import AgentResult
from orchestrator_runtime.agents.base_adapters import FakeAgentAdapter
from orchestrator_runtime.agents.process import CliExecutor, ProcessResult
from orchestrator_runtime.config import load_config
from orchestrator_runtime.tasks.service import TaskService
from orchestrator_runtime.tasks.state_machine import TaskState


class RejectThenApproveValidator(FakeAgentAdapter):
    """Validator fake: rejeita na 1ª chamada, aprova depois — força CORRECTING."""

    def __init__(self, agent_id: str, project_path: Path) -> None:
        super().__init__(agent_id, project_path)
        self._validator_calls = 0

    async def continue_session(self, session, request):  # type: ignore[no-untyped-def]
        if request.role != "validator":
            return await super().continue_session(session, request)

        self._validator_calls += 1
        if self._validator_calls == 1:
            body = {
                "status": "rejected",
                "score": 0.4,
                "blocking_issues": [
                    {
                        "id": "VAL-LOOP",
                        "severity": "blocking",
                        "description": "force repair loop",
                    }
                ],
                "summary": "reject once",
            }
        else:
            body = {
                "status": "approved",
                "score": 0.95,
                "blocking_issues": [],
                "summary": "ok after repair",
            }
        return AgentResult(
            session_id=session.id,
            agent_id=self.id,
            role=request.role,
            status="completed",
            exit_code=0,
            stdout=json.dumps(body),
            stderr="",
            started_at=datetime.now(timezone.utc).isoformat(),
            finished_at=datetime.now(timezone.utc).isoformat(),
        )


def test_repair_loop_enters_correcting_then_completes(project):
    config = load_config(project, fake_agents=True)
    service = TaskService(config, verbose=False)
    for name in ("claude", "codex", "opencode"):
        service.registry._adapters[name] = RejectThenApproveValidator(name, project)

    task = service.create_task(
        "Crie um modulo Python com funcao soma, testes e documentacao",
        max_iterations=3,
    )

    done = asyncio.run(service.run_task(task.id))
    assert done.iteration >= 2, f"esperava repair loop, iter={done.iteration}"
    assert done.status == TaskState.COMPLETED


def test_lock_timeout_does_not_mark_task_failed(project, monkeypatch):
    config = load_config(project, fake_agents=True)
    service = TaskService(config, verbose=False)
    task = service.create_task("hello lock test", max_iterations=1)

    def _boom():
        raise TimeoutError("Não foi possível obter lock: fake")

    monkeypatch.setattr(service.lock, "acquire", _boom)
    result = asyncio.run(service.run_task(task.id))
    refreshed = service.get(task.id)
    assert refreshed.status == TaskState.RECEIVED
    assert refreshed.status != TaskState.FAILED
    assert result.status == TaskState.RECEIVED


def test_double_run_task_is_noop_while_running(project):
    config = load_config(project, fake_agents=True)
    service = TaskService(config, verbose=False)
    task = service.create_task(
        "Crie um modulo Python com funcao soma, testes e documentacao",
        max_iterations=2,
    )
    service._running_tasks.add(task.id)
    out = asyncio.run(service.run_task(task.id))
    assert out.status == TaskState.RECEIVED
    service._running_tasks.discard(task.id)


def test_cli_executor_file_not_found_returns_127(project):
    exe = CliExecutor(project, echo=False)
    result = exe.run(
        ["definitely-missing-agent-xyz-9f3a"],
        cwd=project,
        timeout_s=10,
        allow_nested=True,
    )
    assert isinstance(result, ProcessResult)
    assert result.exit_code == 127
    assert "FileNotFoundError" in result.stderr
