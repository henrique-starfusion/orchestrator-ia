import asyncio

from orchestrator_runtime.tasks.service import build_service
from orchestrator_runtime.tasks.state_machine import TaskState


def test_resume_after_create(project):
    service = build_service(project, fake_agents=True, verbose=False)
    task = service.create_task(
        "Crie um modulo Python com funcao soma, adicione testes e documente o uso."
    )
    assert task.status == TaskState.RECEIVED

    async def _run():
        return await service.resume(task.id)

    done = asyncio.run(_run())
    assert done.status == TaskState.COMPLETED
