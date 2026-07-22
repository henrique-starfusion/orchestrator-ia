from orchestrator_runtime.agents import AgentRegistry
from orchestrator_runtime.config import load_config
from orchestrator_runtime.routing.manager import RulesRouter
from orchestrator_runtime.tasks.models import TaskAnalysis, TaskRecord


def test_routing_mvp(project):
    config = load_config(project, fake_agents=True)
    registry = AgentRegistry(config)
    router = RulesRouter(config, registry)
    task = TaskRecord(prompt="x", project_path=str(project))
    analysis = TaskAnalysis(task_type="implementation", languages=["python"])
    plan = router.select_plan(task, analysis)
    assert plan.planner == "claude"
    assert plan.executor == "codex"
    assert plan.validator == "claude"
    assert plan.validator != plan.executor
