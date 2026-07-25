"""0.4.24 — P0–P2: cancel hard-stop, terminal save protect, cancel_reason, queue event."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator_runtime.config import load_config
from orchestrator_runtime.errors import CancelledError
from orchestrator_runtime.events import EventType
from orchestrator_runtime.tasks.models import TaskRecord
from orchestrator_runtime.tasks.repository import TaskRepository
from orchestrator_runtime.tasks.service import build_service
from orchestrator_runtime.tasks.state_machine import TaskState


def test_save_does_not_resurrect_cancelled(project: Path) -> None:
    config = load_config(project, fake_agents=True)
    repo = TaskRepository(str(config.db_path))
    task = TaskRecord(prompt="x", project_path=str(project))
    repo.create(task)
    repo.transition(task, TaskState.ANALYZING, reason="start")
    repo.transition(task, TaskState.CANCELLED, reason="user cancel", error="user cancel")

    stale = repo.get(task.id)
    assert stale.status == TaskState.CANCELLED
    # Simula loop com objeto stale apontando para VALIDATING
    stale.status = TaskState.VALIDATING
    stale.cancel_requested = False
    repo.save(stale)

    fresh = repo.get(task.id)
    assert fresh.status == TaskState.CANCELLED
    assert fresh.cancel_requested is True


def test_transition_from_terminal_raises_cancelled(project: Path) -> None:
    config = load_config(project, fake_agents=True)
    repo = TaskRepository(str(config.db_path))
    task = TaskRecord(prompt="x", project_path=str(project))
    repo.create(task)
    repo.transition(task, TaskState.ANALYZING, reason="start")
    repo.transition(task, TaskState.CANCELLED, reason="stop", error="stop")

    zombie = repo.get(task.id)
    zombie.status = TaskState.EXECUTING  # stale memory — transition reloads DB
    with pytest.raises(CancelledError):
        repo.transition(zombie, TaskState.TESTING, reason="should not happen")

    assert repo.get(task.id).status == TaskState.CANCELLED


def test_cancel_persists_reason(project: Path) -> None:
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("hello")
    cancelled = svc.cancel(task.id, reason="user asked to stop")
    assert cancelled.status == TaskState.CANCELLED
    assert "user asked to stop" in (cancelled.error or "")


def test_enqueue_emits_task_queued(project: Path) -> None:
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("queued please")
    events: list = []
    svc.bus.on(lambda e: events.append(e))

    queued = svc._enqueue_task(task, blocked_by="other123")
    assert queued.status == TaskState.QUEUED
    types = [e.type for e in events] + [e.type for e in svc.bus.history]
    assert EventType.TASK_QUEUED in types


def test_first_run_writes_legacy_index(project: Path) -> None:
    skill = (
        project
        / ".orchestrator"
        / "skills"
        / "legacy-import"
        / "claude"
        / "demo"
        / "SKILL.md"
    )
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: demo\n---\n# demo\n", encoding="utf-8")

    svc = build_service(project, fake_agents=True)
    svc.create_task("first")
    idx = project / ".orchestrator" / "memory" / "legacy-import" / "INDEX.md"
    assert idx.is_file()
    text = idx.read_text(encoding="utf-8")
    assert "demo" in text or "SKILL.md" in text


def test_winerror_message_mentions_command(project: Path) -> None:
    from orchestrator_runtime.agents.process import CliExecutor

    exe = CliExecutor(project, echo=False)
    result = exe.run(
        ["definitely-not-a-real-binary-xyz-0424", "--help"],
        cwd=project,
    )
    assert result.exit_code == 127
    assert "WinError 2" in result.stderr or "FileNotFoundError" in result.stderr
    assert "definitely-not-a-real-binary-xyz-0424" in result.stderr
