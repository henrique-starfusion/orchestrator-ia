"""Memory retrieval helpers."""

from orchestrator_runtime.tasks.repository import TaskRepository


class MemoryRetrieval:
    def __init__(self, repo: TaskRepository) -> None:
        self.repo = repo

    def similar(self, query: str, limit: int = 5):
        return self.repo.search_memories(query, limit=limit)
