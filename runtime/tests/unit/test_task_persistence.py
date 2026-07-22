from orchestrator_runtime.tasks.models import TaskRecord
from orchestrator_runtime.tasks.repository import TaskRepository
from orchestrator_runtime.tasks.state_machine import TaskState


def test_task_persistence(project):
    repo = TaskRepository(str(project / ".orchestrator" / "data" / "orchestrator.db"))
    task = TaskRecord(prompt="hello", project_path=str(project))
    repo.create(task)
    loaded = repo.get(task.id)
    assert loaded is not None
    assert loaded.prompt == "hello"
    repo.transition(loaded, TaskState.ANALYZING, reason="test")
    again = repo.get(task.id)
    assert again.status == TaskState.ANALYZING
    events = repo.list_events(task.id)
    assert any(e["type"] == "state_changed" for e in events)
