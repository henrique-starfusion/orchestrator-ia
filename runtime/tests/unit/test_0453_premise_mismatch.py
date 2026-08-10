"""Outcome terminal para premissa factual incorreta (2026-07-31)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from orchestrator_runtime.agents.base import AgentResult
from orchestrator_runtime.agents.base_adapters import FakeAgentAdapter
from orchestrator_runtime.config import load_config
from orchestrator_runtime.events import EventType
from orchestrator_runtime.memory.database import MemoryRow, TestRunRow as DbTestRunRow
from orchestrator_runtime.tasks.service import TaskService
from orchestrator_runtime.tasks.state_machine import TaskState


@pytest.mark.parametrize(
    ("stdout", "expected"),
    [
        (
            "PREMISE_MISMATCH: o campo external_id já existe no HEAD\n",
            "o campo external_id já existe no HEAD",
        ),
        (
            "Resultado da inspeção:\n\n- **PREMISE_MISMATCH:** bug já corrigido em abc123\n\nFim.\n",
            "bug já corrigido em abc123",
        ),
    ],
)
def test_parse_premise_mismatch_extrai_explicacao(
    stdout: str, expected: str
) -> None:
    assert TaskService._parse_premise_mismatch(stdout) == expected


@pytest.mark.parametrize(
    "stdout",
    [
        None,
        "",
        "A premissa parece incorreta, mas não há marcador.",
        "PREMISE_MISMATCH:",
        "texto PREMIISE_MISMATCH: marcador digitado errado",
    ],
)
def test_parse_premise_mismatch_retorna_none_sem_marcador_valido(
    stdout: str | None,
) -> None:
    assert TaskService._parse_premise_mismatch(stdout) is None


class PremiseMismatchExecutor(FakeAgentAdapter):
    """Executor honesto: prova que a entrega pedida já está no HEAD."""

    async def continue_session(self, session, request):  # type: ignore[no-untyped-def]
        if request.role not in {"executor", "corrector"}:
            return await super().continue_session(session, request)
        return AgentResult(
            session_id=session.id,
            agent_id=self.id,
            role=request.role,
            status="completed",
            exit_code=0,
            stdout=(
                "Inspecionei o código e o teste existente.\n"
                "PREMISE_MISMATCH: o campo external_id já existe no HEAD com teste\n"
            ),
            stderr="",
            changed_files=[],
            started_at=datetime.now(timezone.utc).isoformat(),
            finished_at=datetime.now(timezone.utc).isoformat(),
        )


def test_premise_mismatch_completa_sem_gates_e_persiste_sucesso(project) -> None:
    config = load_config(project, fake_agents=True)
    service = TaskService(config, verbose=False)
    for name in ("claude", "codex", "opencode"):
        service.registry._adapters[name] = PremiseMismatchExecutor(name, project)

    task = service.create_task(
        "Adicione o campo external_id que estaria ausente",
        max_iterations=3,
    )
    done = asyncio.run(service.run_task(task.id))

    assert done.status == TaskState.COMPLETED
    assert done.iteration == 1
    # CONTRATO MUDADO em 0.4.71 (bug-107): era `== 1.0`. Ninguém validou nada
    # neste caminho — o 1.0 era fabricado, chegava ao dono e entrava em
    # `strategy_performance` como sucesso perfeito. O campo é nullable e serve
    # só para relatório: nulo é a informação honesta.
    assert done.last_score is None
    assert done.analysis["premise_verified"] is False
    assert done.analysis["premise_mismatch"] == (
        "o campo external_id já existe no HEAD com teste"
    )
    assert done.documentation_review is None
    assert not (project / "soma").exists(), "outcome não pode inventar alterações"

    transitions = [
        event
        for event in service.repo.list_events(task.id)
        if event["type"] == EventType.STATE_CHANGED.value
    ]
    assert any(
        event["data"].get("from") == TaskState.EXECUTING.value
        and event["data"].get("to") == TaskState.COMPLETED.value
        and event["data"].get("reason") == "premise_mismatch"
        for event in transitions
    )

    emitted_types = [event.type for event in service.bus.history]
    assert EventType.TEST_STARTED not in emitted_types
    assert EventType.VALIDATION_STARTED not in emitted_types
    assert EventType.DOCUMENTATION_STARTED not in emitted_types

    with service.repo.session() as session:
        test_runs = session.scalars(
            select(DbTestRunRow).where(DbTestRunRow.task_id == task.id)
        ).all()
        episodes = session.scalars(
            select(MemoryRow).where(
                MemoryRow.task_id == task.id,
                MemoryRow.kind == "episode",
            )
        ).all()

    # A baseline pré-executor pode registrar "baseline:<none>"; nenhum registro
    # posterior do gate de testes pode existir para este outcome.
    assert all(
        test_run.discovery_source.startswith("baseline:")
        for test_run in test_runs
    )
    assert any("success=True" in episode.content for episode in episodes)


def test_executor_prompt_explica_outcome_premise_mismatch(project) -> None:
    service = TaskService(load_config(project, fake_agents=True), verbose=False)
    task = service.create_task("Implemente o campo que estaria ausente")

    prompt = service._build_executor_prompt(task, {}, [])

    assert "PREMISE_MISMATCH:" in prompt
    assert "não invente trabalho" in prompt.lower()
    assert "resultado de primeira classe" in prompt.lower()
