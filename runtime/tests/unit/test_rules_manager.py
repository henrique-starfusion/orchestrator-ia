import asyncio

from orchestrator_runtime.agents import AgentRegistry
from orchestrator_runtime.config import load_config
from orchestrator_runtime.manager_model import RulesManager
from orchestrator_runtime.routing.manager import RulesRouter


def test_rules_manager(project):
    config = load_config(project, fake_agents=True)
    router = RulesRouter(config, AgentRegistry(config))
    mgr = RulesManager(router)

    async def _run():
        analysis = await mgr.analyze_task(
            "Crie um modulo Python com funcao soma, testes e documentacao"
        )
        assert analysis.acceptance_criteria
        assert all(c.id.startswith("AC-") for c in analysis.acceptance_criteria)
        from orchestrator_runtime.tasks.models import TaskRecord

        task = TaskRecord(
            prompt="x",
            project_path=str(project),
            acceptance_criteria=analysis.acceptance_criteria,
        )
        plan = await mgr.select_strategy(task, analysis)
        assert plan.strategy == "execute_review_repair"
        decision = await mgr.evaluate_iteration(
            task, {"status": "approved", "score": 0.95, "blocking_issues": []}, 1
        )
        assert decision.action == "approve"

    asyncio.run(_run())
