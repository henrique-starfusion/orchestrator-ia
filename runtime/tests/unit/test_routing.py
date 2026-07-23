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


def test_resolve_model_claude_alias_and_codex_concrete(project):
    """Claude passa alias CLI; Codex resolve tier→id concreto (models.json)."""
    config = load_config(project, fake_agents=True)
    # Espelha o models.json do produto no fixture do projeto de teste
    config.models = {
        "clients": {
            "claude": {
                "model_flag": "--model",
                "prefer_aliases": True,
                "aliases": {
                    "fast": "haiku",
                    "balanced": "sonnet",
                    "deep": "opus",
                    "max": "fable",
                },
                "models": {
                    "haiku": "claude-haiku-4-5",
                    "sonnet": "claude-sonnet-5",
                    "opus": "claude-opus-4-8",
                    "fable": "claude-fable-5",
                },
                "task_map": {"implementation": "sonnet", "complex_analysis": "fable"},
            },
            "codex": {
                "model_flag": "-m",
                "prefer_aliases": False,
                "models": {
                    "fast": "gpt-5.6-sol",
                    "balanced": "gpt-5.6-sol",
                    "deep": "gpt-5.6-sol",
                },
                "task_map": {"implementation": "balanced"},
            },
        }
    }
    router = RulesRouter(config, AgentRegistry(config))
    assert router.resolve_model("claude", "implementation") == ("sonnet", "--model")
    assert router.resolve_model("codex", "implementation") == ("gpt-5.6-sol", "-m")
    # Sem prefer_aliases no cliente mas só tiers em models → concreto
    config.models["clients"]["codex"].pop("prefer_aliases", None)
    assert router.resolve_model("codex", "implementation") == ("gpt-5.6-sol", "-m")
