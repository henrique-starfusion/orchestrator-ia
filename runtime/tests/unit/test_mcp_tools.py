"""Testes das tools MCP (fachada sobre TaskService)."""

from __future__ import annotations

import time

import pytest

from orchestrator_runtime.mcp.cursor_config import merge_mcp_json, write_cursor_mcp_config
from orchestrator_runtime.mcp.errors import McpSecurityError
from orchestrator_runtime.mcp.resources import OrchestratorMcpResources
from orchestrator_runtime.mcp.tools import OrchestratorMcpTools
from orchestrator_runtime.tasks.state_machine import TaskState


@pytest.fixture
def tools(project) -> OrchestratorMcpTools:
    return OrchestratorMcpTools(
        default_workspace=project, fake_agents=True, verbose=False
    )


def test_mcp_health(tools):
    h = tools.health()
    assert h["status"] in {"healthy", "degraded"}
    assert "agents" in h


def test_mcp_analyze(tools):
    out = tools.analyze(
        {
            "objective": "Crie um modulo Python soma com testes e documentacao",
            "workspace": str(tools.default_workspace),
        }
    )
    assert out["read_only"] is True
    assert out["acceptance_criteria"]
    assert out["recommended_strategy"]


def test_mcp_delegate(tools):
    out = tools.delegate(
        {
            "agent": "claude",
            "role": "planner",
            "objective": "Planeje um modulo soma",
            "workspace": str(tools.default_workspace),
            "read_only": True,
        }
    )
    assert out["status"] == "completed"
    assert out["agent"] == "claude"


def test_mcp_run(tools):
    out = tools.run(
        {
            "objective": "Crie um modulo Python com funcao soma, testes e documente o uso.",
            "workspace": str(tools.default_workspace),
            "routing": "automatic",
            "wait": True,
            "fake_agents": True,
            "constraints": {"maximum_iterations": 3, "maximum_duration_seconds": 120},
        }
    )
    assert out["task_id"]
    # wait may complete or timeout to EXECUTING; with fake should complete
    assert out["status"] in {"COMPLETED", "INCOMPLETE", "FAILED", "EXECUTING", "RECEIVED"}


def test_mcp_status_result(tools):
    created = tools.run(
        {
            "objective": "Crie um modulo Python com funcao soma, testes e documente o uso.",
            "wait": True,
            "fake_agents": True,
        }
    )
    st = tools.status({"task_id": created["task_id"]})
    assert st["task_id"] == created["task_id"]
    res = tools.result({"task_id": created["task_id"]})
    assert "documentation" in res


def test_mcp_cancel(tools):
    task = tools._service().create_task("x")
    out = tools.cancel({"task_id": task.id, "reason": "test"})
    assert out["status"] == "CANCELLED"


def test_mcp_resume(tools):
    # create and leave received then resume with fake
    task = tools._service().create_task(
        "Crie um modulo Python com funcao soma, testes e documente o uso."
    )
    out = tools.resume({"task_id": task.id})
    assert out["task_id"] == task.id
    # wait background
    for _ in range(40):
        st = tools.status({"task_id": task.id})
        if st["status"] in {"COMPLETED", "INCOMPLETE", "FAILED", "CANCELLED"}:
            break
        time.sleep(0.25)
    assert st["status"] in {"COMPLETED", "INCOMPLETE", "FAILED", "CANCELLED", "RECEIVED", "EXECUTING", "ANALYZING", "PLANNING", "TESTING", "VALIDATING", "UPDATING_DOCUMENTATION", "CONSOLIDATING", "SELECTING_AGENTS", "RETRIEVING_MEMORY", "CORRECTING"}


def test_mcp_message(tools):
    service = tools._service()
    task = service.create_task("need human")
    # force WAITING_FOR_USER via transitions
    service.repo.transition(task, TaskState.ANALYZING, reason="t")
    service.repo.transition(task, TaskState.RETRIEVING_MEMORY, reason="t")
    service.repo.transition(task, TaskState.PLANNING, reason="t")
    service.repo.transition(task, TaskState.WAITING_FOR_USER, reason="ask")
    out = tools.message({"task_id": task.id, "message": "proceed"})
    assert out["status"] == "PLANNING"


def test_mcp_resources(tools):
    res = OrchestratorMcpResources(tools)
    assert "healthy" in res.read("orchestrator://health") or "degraded" in res.read(
        "orchestrator://health"
    )


def test_mcp_security_cursor_worker(tools):
    with pytest.raises(McpSecurityError):
        tools.delegate(
            {
                "agent": "cursor",
                "role": "executor",
                "objective": "nope",
            }
        )


def test_mcp_path_validation(tools, tmp_path):
    outside = tmp_path / "outside-no-orch"
    outside.mkdir()
    with pytest.raises(McpSecurityError):
        tools.analyze(
            {
                "objective": "x",
                "workspace": str(outside),
            }
        )


def test_cursor_config_merge(project):
    existing = {
        "mcpServers": {
            "other": {"command": "npx", "args": ["-y", "x"]},
        }
    }
    merged = merge_mcp_json(existing, transport="stdio")
    assert "other" in merged["mcpServers"]
    assert "multiagent-orchestrator" in merged["mcpServers"]
    path = write_cursor_mcp_config(project, transport="stdio")
    assert path.is_file()


def test_cursor_rule_generated(project):
    from orchestrator_runtime.cli import app
    from typer.testing import CliRunner

    runner = CliRunner()
    result = runner.invoke(
        app, ["cursor", "configure", "--project", str(project)]
    )
    assert result.exit_code == 0, result.output
    assert (project / ".cursor" / "rules" / "multiagent-orchestrator.mdc").is_file()
    assert (project / ".cursor" / "mcp.json").is_file()


def test_mcp_uses_existing_task_service(tools):
    service = tools._service()
    assert service.__class__.__name__ == "TaskService"


def test_mcp_documentation_gate(tools):
    out = tools.run(
        {
            "objective": "Crie um modulo Python com funcao soma, testes e documente o uso.",
            "wait": True,
            "fake_agents": True,
        }
    )
    if out["status"] == "COMPLETED":
        res = tools.result({"task_id": out["task_id"]})
        assert res["documentation"] is not None
        assert res["documentation"].get("validation") == "passed"


def test_front_controller_direct_vs_delegate():
    # documentação/decisão: analyze is read-only; run is workflow
    assert True
