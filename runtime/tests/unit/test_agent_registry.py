from orchestrator_runtime.agents import AgentRegistry
from orchestrator_runtime.config import load_config


def test_agent_registry_cursor_not_worker(project):
    config = load_config(project, fake_agents=True)
    registry = AgentRegistry(config)
    cursor = registry.get("cursor")
    assert cursor is not None
    assert cursor.capabilities().executable is False
    assert "cursor" not in registry.available_workers("executor")
    assert "claude" in registry.available_workers("planner")
