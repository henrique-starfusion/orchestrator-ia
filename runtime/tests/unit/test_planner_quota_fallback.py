"""0.4.25 — planner usa melhor modelo; cota esgotada → próximo da lista."""

from __future__ import annotations

from pathlib import Path

from orchestrator_runtime.agents import AgentRegistry
from orchestrator_runtime.config import load_config
from orchestrator_runtime.routing.manager import RulesRouter
from orchestrator_runtime.routing.quota import is_model_quota_exhausted, should_retry_next_model


def _claude_models_config() -> dict:
    return {
        "role_model_preferences": {
            "planner": {
                "claude": ["fable", "opus", "sonnet"],
            },
        },
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
                "task_map": {"implementation": "opus", "complex_analysis": "fable"},
            },
        },
    }


def test_planner_candidates_best_first(project: Path) -> None:
    config = load_config(project, fake_agents=True)
    config.models = _claude_models_config()
    router = RulesRouter(config, AgentRegistry(config))
    cands = router.resolve_model_candidates("claude", "implementation", role="planner")
    models = [m for m, _ in cands]
    assert models[0] == "fable"
    assert "opus" in models
    assert models.index("opus") < models.index("sonnet")
    assert router.resolve_model("claude", "implementation", role="planner") == (
        "fable",
        "--model",
    )


def test_quota_detection_rate_limit() -> None:
    assert is_model_quota_exhausted(
        status="failed",
        exit_code=1,
        stderr="Error: rate_limit exceeded for model fable",
    )
    assert is_model_quota_exhausted(exit_code=429, stderr="")
    assert not is_model_quota_exhausted(
        status="failed",
        exit_code=1,
        stderr="syntax error in file foo.py",
    )


def test_should_retry_next_model_object() -> None:
    class R:
        status = "failed"
        exit_code = 1
        stdout = ""
        stderr = "You've hit your usage limit for Max"

    assert should_retry_next_model(R()) is True
