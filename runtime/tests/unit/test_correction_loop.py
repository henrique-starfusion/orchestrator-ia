import asyncio

from orchestrator_runtime.manager_model import RulesManager
from orchestrator_runtime.agents import AgentRegistry
from orchestrator_runtime.config import load_config
from orchestrator_runtime.routing.manager import RulesRouter
from orchestrator_runtime.tasks.models import TaskRecord


def test_correction_loop_stops_at_max(project):
    config = load_config(project, fake_agents=True)
    mgr = RulesManager(RulesRouter(config, AgentRegistry(config)))
    task = TaskRecord(prompt="x", project_path=str(project))
    task.constraints.maximum_iterations = 2

    async def _run():
        d = await mgr.evaluate_iteration(
            task,
            {"status": "rejected", "score": 0.4, "blocking_issues": [{"id": "VAL-001"}]},
            2,
        )
        assert d.action == "stop_incomplete"

    asyncio.run(_run())
