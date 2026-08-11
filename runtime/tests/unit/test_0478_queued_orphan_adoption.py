"""0.4.78 - adoption of orphaned QUEUED tasks through existing polls.

Production incident reproduced on 2026-08-10:

    blocker=COMPLETED, queued age=10 min, status poll -> still QUEUED, started=[]

The queue handoff only happened in ``run_task``'s ``finally``. If both the
enqueuing process and workspace owner died, no surviving code claimed the FIFO
head. These tests keep adoption conservative: age lease, owner-death evidence,
normal admission, strict FIFO for the adopter, and a persisted cross-process
claim are all required together.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from orchestrator_runtime.config import load_config
from orchestrator_runtime.memory.database import TaskRow
from orchestrator_runtime.tasks.service import TaskService, build_service
from orchestrator_runtime.tasks.state_machine import TaskState


PROMPT = "Crie um modulo Python com funcao soma, testes e documentacao"


def _service(
    project: Path, *, adopt_after_s: int = 1, max_parallel_tasks: int = 3
) -> TaskService:
    policies_path = project / ".orchestrator" / "config" / "policies.json"
    policies = json.loads(policies_path.read_text(encoding="utf-8"))
    policies["orphan_queued_adopt_after_s"] = adopt_after_s
    policies["orphan_received_adopt_after_s"] = adopt_after_s
    policies["max_parallel_tasks"] = max_parallel_tasks
    policies_path.write_text(json.dumps(policies), encoding="utf-8")
    return build_service(project, fake_agents=True, verbose=False)


def _force_status(
    service: TaskService, task_id: str, status: TaskState
) -> None:
    """Set persisted state directly; fixtures model a process that already died."""
    with service.repo.session() as session:
        row = session.get(TaskRow, task_id)
        assert row is not None
        row.status = status.value
        session.commit()


def _age(
    service: TaskService,
    task_id: str,
    *,
    minutes: int = 10,
    created_too: bool = False,
) -> None:
    old = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    with service.repo.session() as session:
        row = session.get(TaskRow, task_id)
        assert row is not None
        row.updated_at = old
        if created_too:
            row.created_at = old
        session.commit()


def _active(
    service: TaskService, prompt: str, scope: list[str]
) -> str:
    task = service.create_task(prompt, scope=scope)
    service.repo.transition(
        service.get(task.id),
        TaskState.ANALYZING,
        reason="fixture: live owner",
        agent="runtime",
    )
    return task.id


def _queued(
    service: TaskService,
    prompt: str,
    scope: list[str],
    *,
    blocked_by: str,
) -> str:
    task = service.create_task(prompt, scope=scope)
    queued = service._enqueue_task(service.get(task.id), blocked_by=blocked_by)
    # ``create_task`` may already have queued it behind another active task.
    # The persisted blocker below models the owner that later died.
    queued.error = f"queued_behind:{blocked_by}|pos={service._queue_position(task.id, task.project_path)}"
    service.repo.save(queued)
    return task.id


def _terminal_blocker(service: TaskService, prompt: str = "old blocker") -> str:
    blocker = service.create_task(prompt, scope=["src/old"])
    _force_status(service, blocker.id, TaskState.COMPLETED)
    return blocker.id


def test_terminal_blocker_is_adopted_and_executed_by_later_status_poll(
    project: Path,
) -> None:
    service = _service(project, max_parallel_tasks=1)
    blocker = _active(service, "workspace owner", ["src/runtime"])
    queued = _queued(
        service,
        PROMPT,
        ["src/runtime"],
        blocked_by=blocker,
    )
    _force_status(service, blocker, TaskState.COMPLETED)
    _age(service, queued)

    service.status(queued)
    service.join_background(timeout_s=30)

    done = service.get(queued)
    assert done.status == TaskState.COMPLETED, done.error


def test_live_non_terminal_blocker_is_never_stolen_even_when_scope_fits(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = _service(project, max_parallel_tasks=3)
    blocker = _active(service, "live api owner", ["src/api"])
    queued = _queued(
        service,
        "disjoint but still owned",
        ["src/web"],
        blocked_by=blocker,
    )
    _age(service, queued)
    started: list[str] = []
    monkeypatch.setattr(
        service,
        "_start_background",
        lambda task_id, *, name: started.append(f"{name}:{task_id}"),
    )

    service.status(queued)

    assert service._blocking_task_id(str(project), service.get(queued)) is None
    assert started == []
    assert service.get(queued).status == TaskState.QUEUED


def test_fifo_head_blocked_by_scope_prevents_adopting_disjoint_middle_task(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = _service(project, max_parallel_tasks=3)
    dead = _terminal_blocker(service)
    _active(service, "live api", ["src/api"])
    head = _queued(
        service,
        "fifo head overlaps api",
        ["src/api/routes.py"],
        blocked_by=dead,
    )
    middle = _queued(
        service,
        "middle is disjoint",
        ["src/web"],
        blocked_by=dead,
    )
    _age(service, head)
    _age(service, middle)
    started: list[str] = []
    monkeypatch.setattr(
        service,
        "_start_background",
        lambda task_id, *, name: started.append(task_id),
    )

    service.status(head)

    assert [task.id for task in service.repo.list_queued(str(project))][:2] == [
        head,
        middle,
    ]
    assert started == [], "adopter must not skip the blocked FIFO head"


def test_adoption_respects_max_parallel_tasks(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = _service(project, max_parallel_tasks=1)
    dead = _terminal_blocker(service)
    _active(service, "machine slot in use", ["src/a"])
    queued = _queued(
        service,
        "disjoint but above ceiling",
        ["src/b"],
        blocked_by=dead,
    )
    _age(service, queued)
    started: list[str] = []
    monkeypatch.setattr(
        service,
        "_start_background",
        lambda task_id, *, name: started.append(task_id),
    )

    service.status(queued)

    assert started == []
    assert service.get(queued).status == TaskState.QUEUED


def test_persisted_lease_makes_two_pollers_idempotent(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _service(project, max_parallel_tasks=1)
    blocker = _active(first, "owner that exits", ["src/runtime"])
    queued = _queued(first, "one start only", ["src/runtime"], blocked_by=blocker)
    _force_status(first, blocker, TaskState.COMPLETED)
    _age(first, queued)
    second = TaskService(load_config(project, fake_agents=True), verbose=False)
    started: list[str] = []
    for service in (first, second):
        monkeypatch.setattr(
            service,
            "_start_background",
            lambda task_id, *, name: started.append(f"{name}:{task_id}"),
        )

    first.status(queued)
    second.status(queued)
    first.status(queued)

    assert started == [f"adopt-queued:{queued}"]


@pytest.mark.parametrize("poll", ["status", "list", "watch", "create"])
def test_existing_poll_entrypoints_reach_queued_adopter(
    project: Path, monkeypatch: pytest.MonkeyPatch, poll: str
) -> None:
    service = _service(project, max_parallel_tasks=1)
    blocker = _active(service, f"owner for {poll}", ["src/runtime"])
    queued = _queued(
        service,
        f"orphan for {poll}",
        ["src/runtime"],
        blocked_by=blocker,
    )
    _force_status(service, blocker, TaskState.COMPLETED)
    _age(service, queued)
    started: list[str] = []
    monkeypatch.setattr(
        service,
        "_start_background",
        lambda task_id, *, name: started.append(f"{name}:{task_id}"),
    )

    if poll == "status":
        service.status(queued)
    elif poll == "list":
        service.list_tasks()
    elif poll == "watch":
        service.follow_events(queued)
    else:
        service.create_task("poll through create_task", scope=["docs"])

    assert started == [f"adopt-queued:{queued}"]


def test_recent_queued_task_is_not_adopted(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = _service(project, adopt_after_s=120, max_parallel_tasks=1)
    blocker = _active(service, "recent owner", ["src/runtime"])
    queued = _queued(service, "recent queued", ["src/runtime"], blocked_by=blocker)
    _force_status(service, blocker, TaskState.COMPLETED)
    started: list[str] = []
    monkeypatch.setattr(
        service,
        "_start_background",
        lambda task_id, *, name: started.append(task_id),
    )

    service.status(queued)

    assert started == []


def test_received_orphan_adoption_from_bug_085_is_preserved(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = _service(project, adopt_after_s=1)
    received = service.create_task("old received orphan")
    _age(service, received.id, created_too=True)
    started: list[str] = []
    monkeypatch.setattr(
        service,
        "_start_background",
        lambda task_id, *, name: started.append(f"{name}:{task_id}"),
    )

    service.status(received.id)

    assert started == [f"adopt:{received.id}"]


def test_queued_adoption_threshold_is_loaded_from_policy(project: Path) -> None:
    service = _service(project, adopt_after_s=37)

    assert service.config.limits.orphan_queued_adopt_after_s == 37
