from orchestrator_runtime.tasks.models import TaskRecord
from orchestrator_runtime.tasks.repository import TaskRepository


def test_memory_search(project):
    repo = TaskRepository(str(project / ".orchestrator" / "data" / "orchestrator.db"))
    task = TaskRecord(prompt="soma module", project_path=str(project))
    repo.create(task)
    repo.save_memory("episode", "implemented soma with pytest", task_id=task.id)
    hits = repo.search_memories("soma pytest", limit=3)
    assert hits
    assert "soma" in hits[0]["content"]
