"""0.4.19 — Fila de tasks por workspace (QUEUED + dequeue automático)."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from orchestrator_runtime.agents.base_adapters import FakeAgentAdapter
from orchestrator_runtime.config import load_config
from orchestrator_runtime.tasks.service import TaskService
from orchestrator_runtime.tasks.state_machine import TaskState, assert_transition
from orchestrator_runtime.errors import InvalidTransitionError


def _service(project: Path) -> TaskService:
    config = load_config(project, fake_agents=True)
    service = TaskService(config, verbose=False)
    for name in ("claude", "codex", "opencode"):
        service.registry._adapters[name] = FakeAgentAdapter(name, project)
    return service


def _force_status(service: TaskService, task_id: str, status: TaskState) -> None:
    """Bypass state machine for fixtures (simula task já no meio do pipeline)."""
    task = service.get(task_id)
    task.status = status
    service.repo.save(task)


def test_queued_transitions() -> None:
    assert_transition(TaskState.RECEIVED, TaskState.QUEUED)
    assert_transition(TaskState.QUEUED, TaskState.RECEIVED)
    assert_transition(TaskState.QUEUED, TaskState.ANALYZING)
    assert_transition(TaskState.QUEUED, TaskState.CANCELLED)
    try:
        assert_transition(TaskState.QUEUED, TaskState.EXECUTING)
        raise AssertionError("QUEUED -> EXECUTING should be invalid")
    except InvalidTransitionError:
        pass


def test_second_run_enqueues_when_lock_busy(project, monkeypatch) -> None:
    """AC1: 2ª run com workspace ocupado → QUEUED."""
    service = _service(project)
    t1 = service.create_task(
        "Crie um modulo Python com funcao soma, testes e documentacao",
        max_iterations=1,
    )
    t2 = service.create_task(
        "Crie um modulo Python com funcao multiplica, testes e documentacao",
        max_iterations=1,
    )

    # Simula t1 já em execução (ocupa o workspace).
    service._running_tasks.add(t1.id)
    _force_status(service, t1.id, TaskState.EXECUTING)

    out = asyncio.run(service.run_task(t2.id))
    assert out.status == TaskState.QUEUED
    assert (out.error or "").startswith(f"queued_behind:{t1.id}")
    st = service.status(t2.id)
    assert st["queue_position"] == 1
    assert st["blocked_by"] == t1.id

    service._running_tasks.discard(t1.id)


def test_auto_dequeue_starts_next(project) -> None:
    """AC2: ao liberar o lock, a próxima QUEUED inicia sozinha."""
    service = _service(project)
    t1 = service.create_task(
        "Crie um modulo Python com funcao soma, testes e documentacao",
        max_iterations=1,
    )
    t2 = service.create_task(
        "Crie um modulo Python com funcao multiplica, testes e documentacao",
        max_iterations=1,
    )

    service._running_tasks.add(t1.id)
    _force_status(service, t1.id, TaskState.EXECUTING)
    asyncio.run(service.run_task(t2.id))
    assert service.get(t2.id).status == TaskState.QUEUED

    # Libera t1 e dispara dequeue como o finally de run_task faria.
    _force_status(service, t1.id, TaskState.COMPLETED)
    service._running_tasks.discard(t1.id)
    service._maybe_start_next(t1.project_path)

    deadline = time.time() + 15
    while time.time() < deadline:
        st = service.get(t2.id).status
        if st not in {TaskState.QUEUED, TaskState.RECEIVED}:
            break
        time.sleep(0.1)

    final = service.get(t2.id)
    assert final.status != TaskState.QUEUED
    assert final.status in {
        TaskState.COMPLETED,
        TaskState.ANALYZING,
        TaskState.RETRIEVING_MEMORY,
        TaskState.PLANNING,
        TaskState.SELECTING_AGENTS,
        TaskState.EXECUTING,
        TaskState.TESTING,
        TaskState.VALIDATING,
        TaskState.UPDATING_DOCUMENTATION,
        TaskState.CONSOLIDATING,
        TaskState.INCOMPLETE,
        TaskState.FAILED,
    }


def test_distinct_projects_not_blocked(project, tmp_path) -> None:
    """AC3: projetos distintos podem ter execução 'ativa' sem se enfileirar."""
    other = tmp_path / "other-project"
    other.mkdir()
    # Minimal orchestrator layout for second project
    for sub in (
        "config",
        "agents/profiles",
        "runtime/locks",
        "data",
        "memory",
    ):
        (other / ".orchestrator" / sub).mkdir(parents=True, exist_ok=True)
    (other / ".orchestrator" / "VERSION").write_text("0.4.19\n", encoding="utf-8")
    import shutil

    shutil.copy(
        project / ".orchestrator" / "config" / "policies.json",
        other / ".orchestrator" / "config" / "policies.json",
    )
    shutil.copy(
        project / ".orchestrator" / "config" / "models.json",
        other / ".orchestrator" / "config" / "models.json",
    )
    shutil.copy(
        project / ".orchestrator" / "config" / "manager_model.json",
        other / ".orchestrator" / "config" / "manager_model.json",
    )
    for name in ("claude", "codex"):
        src = project / ".orchestrator" / "agents" / "profiles" / f"{name}.json"
        if src.exists():
            shutil.copy(src, other / ".orchestrator" / "agents" / "profiles" / f"{name}.json")

    s1 = _service(project)
    s2 = _service(other)
    a = s1.create_task("task a project1", max_iterations=1)
    b = s2.create_task("task b project2", max_iterations=1)
    s1._running_tasks.add(a.id)
    _force_status(s1, a.id, TaskState.EXECUTING)

    # Mesmo com s1 ocupado, s2 (outro project_path) não vê busy.
    assert s2._busy_task_id(b.project_path, exclude_id=b.id) is None
    assert s1._busy_task_id(a.project_path, exclude_id=a.id) is None
    assert s1._busy_task_id(a.project_path) == a.id


def test_cancel_queued_does_not_kill_active(project) -> None:
    """AC4: cancel da enfileirada não afeta a ativa."""
    service = _service(project)
    t1 = service.create_task("ativa", max_iterations=1)
    t2 = service.create_task("fila", max_iterations=1)
    service._running_tasks.add(t1.id)
    _force_status(service, t1.id, TaskState.EXECUTING)
    asyncio.run(service.run_task(t2.id))
    assert service.get(t2.id).status == TaskState.QUEUED

    cancelled = service.cancel(t2.id)
    assert cancelled.status == TaskState.CANCELLED
    assert service.get(t1.id).status == TaskState.EXECUTING
    service._running_tasks.discard(t1.id)
