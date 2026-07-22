import asyncio

from orchestrator_runtime.tasks.service import build_service
from orchestrator_runtime.tasks.state_machine import TaskState


def test_end_to_end_fake_agents(project):
    service = build_service(project, fake_agents=True, verbose=False)
    prompt = "Crie um modulo Python com uma funcao soma, adicione testes e documente o uso."

    async def _run():
        return await service.run_prompt(prompt)

    task = asyncio.run(_run())
    assert task.status == TaskState.COMPLETED, (task.status, task.error, task.documentation_review)
    assert (project / "soma" / "core.py").is_file()
    assert (project / "tests" / "test_soma.py").is_file()
    assert "soma" in (project / "README.md").read_text(encoding="utf-8").lower()
    assert task.documentation_review is not None
    assert task.documentation_review.get("validation") == "passed"

    # Nova tarefa recupera experiencia
    hits = service.repo.search_memories("soma", limit=3)
    assert hits
