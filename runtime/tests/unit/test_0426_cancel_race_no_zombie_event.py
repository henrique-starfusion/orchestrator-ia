"""0.4.26 — corrida cancel x transition: sem evento zumbi.

Cenario real medido na frota (2026-07-26): 19 tasks emitiram eventos
state_changed DEPOIS do cancel (printbee 10, bootstrap 8, adzora 1), ex.:
RECEIVED->CANCELLED e, 24 ms depois, RECEIVED->ANALYZING.

Causa: transition() relia o status do DB (nao-terminal) e so gravava depois;
um cancel concorrente vencia a janela. save() (0.4.24) protegia a LINHA do DB,
mas transition() seguia emitindo o evento e retornando como se tivesse
avancado — o loop continuava.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator_runtime.config import load_config
from orchestrator_runtime.errors import CancelledError
from orchestrator_runtime.tasks.models import TaskRecord
from orchestrator_runtime.tasks.repository import TaskRepository
from orchestrator_runtime.tasks.state_machine import TaskState


def _events_to(repo: TaskRepository, task_id: str, state: TaskState) -> int:
    total = 0
    for ev in repo.list_events(task_id):
        data = ev.get("data") or {}
        if data.get("to") == state.value:
            total += 1
    return total


def test_cancel_race_raises_and_emits_no_event(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cancel vence a corrida DEPOIS da releitura: aborta sem evento falso."""
    config = load_config(project, fake_agents=True)
    repo = TaskRepository(str(config.db_path))
    task = TaskRecord(prompt="x", project_path=str(project))
    repo.create(task)
    repo.transition(task, TaskState.ANALYZING, reason="start")

    # DB ja esta CANCELLED (cancel concorrente persistiu)...
    cancelled = repo.get(task.id)
    repo.transition(cancelled, TaskState.CANCELLED, reason="user cancel", error="stop")
    assert repo.get(task.id).status == TaskState.CANCELLED

    # ...mas a releitura dentro de transition() ainda enxerga o estado antigo
    # (exatamente a janela de corrida). Um unico get() stale.
    real_get = repo.get
    stale_calls = {"n": 0}

    def racing_get(task_id: str):
        stale_calls["n"] += 1
        fresh = real_get(task_id)
        if stale_calls["n"] == 1 and fresh is not None:
            fresh.status = TaskState.ANALYZING
            fresh.cancel_requested = False
        return fresh

    monkeypatch.setattr(repo, "get", racing_get)

    loop_task = TaskRecord(prompt="x", project_path=str(project))
    loop_task.id = task.id
    loop_task.status = TaskState.ANALYZING

    with pytest.raises(CancelledError):
        repo.transition(
            loop_task, TaskState.RETRIEVING_MEMORY, reason="loop segue cego"
        )

    monkeypatch.undo()

    # Estado terminal preservado e NENHUM evento de transicao fantasma.
    assert repo.get(task.id).status == TaskState.CANCELLED
    assert _events_to(repo, task.id, TaskState.RETRIEVING_MEMORY) == 0


def test_normal_transition_still_emits_event(project: Path) -> None:
    """Guard nao pode calar o caminho feliz."""
    config = load_config(project, fake_agents=True)
    repo = TaskRepository(str(config.db_path))
    task = TaskRecord(prompt="x", project_path=str(project))
    repo.create(task)
    repo.transition(task, TaskState.ANALYZING, reason="start")

    assert repo.get(task.id).status == TaskState.ANALYZING
    assert _events_to(repo, task.id, TaskState.ANALYZING) == 1
