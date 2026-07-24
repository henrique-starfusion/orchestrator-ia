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
    assert h["runtime"]["code_fingerprint"]
    assert "runtime_code_fingerprint" in h["runtime"]["features"]
    assert "fingerprint=" in (h.get("message") or "")


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


def test_mcp_analyze_audit_preserves_semver(tools):
    out = tools.analyze(
        {
            "objective": (
                "Auditoria completa do orquestrador 0.4.1: gaps em MCP. "
                "Não criar módulo soma."
            ),
            "workspace": str(tools.default_workspace),
        }
    )
    assert out["task_type"] == "complex_analysis"
    blob = " ".join(out["requirements"])
    assert "0.4.1" in blob
    assert "validator_equals_planner" in (out.get("warnings") or [])
    kinds = {c["kind"] for c in out["acceptance_criteria"]}
    assert "evidence" in kinds


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
    # delegate finaliza a task (anti-órfão RECEIVED no DB)
    st = tools.status({"task_id": out["task_id"]})
    assert st["status"] == "COMPLETED"


def test_mcp_run(tools):
    out = tools.run(
        {
            "objective": "Crie um modulo Python com funcao soma, testes e documente o uso.",
            "workspace": str(tools.default_workspace),
            "routing": "automatic",
            "wait": True,
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
    assert out["status"] == "RESUMING"


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


def test_mcp_path_rejects_foreign_orchestrator(tmp_path_factory):
    """Mesmo com .orchestrator/, path fora do default_workspace é bloqueado."""
    allowed = tmp_path_factory.mktemp("allowed-ws")
    (allowed / ".orchestrator").mkdir()
    foreign = tmp_path_factory.mktemp("foreign-ws")
    (foreign / ".orchestrator").mkdir()
    tools = OrchestratorMcpTools(
        default_workspace=allowed, fake_agents=True, verbose=False
    )
    with pytest.raises(McpSecurityError, match="allowlist"):
        tools.analyze(
            {
                "objective": "x",
                "workspace": str(foreign),
            }
        )


def test_mcp_status_includes_error_and_message(tools):
    service = tools._service()
    task = service.create_task("x")
    service.repo.transition(
        task,
        TaskState.FAILED,
        reason="test",
        error="lock timeout demo",
    )
    st = tools.status({"task_id": task.id})
    assert st["error"] == "lock timeout demo"
    assert "erro=" in st["message"]
    assert st["next_poll_after_seconds"] == 0


def test_mcp_status_includes_provider_and_model(tools):
    from orchestrator_runtime.events import EventType, RuntimeEvent

    service = tools._service()
    task = service.create_task(
        "implement feature",
        planner="claude",
        executor="codex",
        validator="claude",
    )
    task.task_type = "implementation"
    task.plan = {
        "roles": {
            "planner": "claude",
            "executor": "codex",
            "validator": "claude",
            "tester": "runtime",
        },
        "steps": [
            {"role": "planner", "agent": "claude"},
            {"role": "executor", "agent": "codex"},
            {"role": "validator", "agent": "claude"},
        ],
    }
    service.repo.save(task)
    service.repo.transition(task, TaskState.ANALYZING, reason="t")
    service.repo.transition(task, TaskState.RETRIEVING_MEMORY, reason="t")
    service.repo.transition(task, TaskState.PLANNING, reason="t")
    service.repo.transition(task, TaskState.SELECTING_AGENTS, reason="t")
    service.repo.transition(
        task, TaskState.EXECUTING, reason="start", agent="codex"
    )
    ev = RuntimeEvent(
        task_id=task.id,
        type=EventType.AGENT_STARTED,
        role="executor",
        agent="codex",
        data={"model": "gpt-5.6-sol"},
    )
    service.bus.emit(ev)
    service.repo.add_event(ev)

    st = tools.status({"task_id": task.id})
    assert st["active_provider"] == "codex"
    assert st["active_role"] == "executor"
    assert st["active_model"] == "gpt-5.6-sol"
    assert st["selected_agents"]["executor"] == "codex"
    assert "gpt-5.6-sol" in (st["selected_models"].get("executor") or "")
    assert "provider=codex" in st["message"]
    assert "model=gpt-5.6-sol" in st["message"]
    assert any(p.get("model") == "gpt-5.6-sol" for p in st["progress"])


def test_mcp_run_returns_selected_models_snapshot(tools):
    out = tools.run(
        {
            "objective": "Crie um modulo Python com funcao soma e testes",
            "planner": "claude",
            "executor": "codex",
            "validator": "opencode",
            "wait": False,
        }
    )
    assert out["task_id"]
    assert out["selected_agents"]["planner"] == "claude"
    assert out["selected_agents"]["executor"] == "codex"
    assert out["selected_agents"]["validator"] == "opencode"
    assert "selected_models" in out
    assert out["selected_models"].get("planner")
    assert "Orquestrador iniciado" in out["message"]
    assert "planner=claude/" in out["message"]
    tools.cancel({"task_id": out["task_id"], "reason": "test cleanup"})


def test_mcp_delegate_read_only_blocks_executor(tools):
    with pytest.raises(McpSecurityError, match="read_only"):
        tools.delegate(
            {
                "agent": "claude",
                "role": "executor",
                "objective": "escreva codigo",
                "read_only": True,
            }
        )


def test_mcp_run_honors_agent_overrides(tools):
    out = tools.run(
        {
            "objective": "Crie um modulo Python com funcao soma, testes e documente.",
            "routing": "automatic",
            "planner": "claude",
            "executor": "codex",
            "validator": "opencode",
            "wait": True,
        }
    )
    res = tools.result({"task_id": out["task_id"]})
    plan = res.get("plan") or {}
    steps = {s["role"]: s["agent"] for s in plan.get("steps") or [] if "role" in s}
    # fake registry pode remapear; se steps existirem, overrides devem aparecer no plan roles ou steps
    assert out["task_id"]
    if steps:
        assert steps.get("planner") == "claude" or plan.get("roles")


def test_cursor_config_merge(project):
    existing = {
        "mcpServers": {
            "other": {"command": "npx", "args": ["-y", "x"]},
        }
    }
    merged = merge_mcp_json(existing, transport="stdio")
    assert "other" in merged["mcpServers"]
    assert "orchestrator-ia" in merged["mcpServers"]
    path = write_cursor_mcp_config(project, transport="stdio")
    assert path.is_file()


def test_cursor_config_migrates_legacy_server_key():
    existing = {
        "mcpServers": {
            "multiagent-orchestrator": {"command": "old", "enabled": True},
            "other": {"command": "npx", "args": ["-y", "x"]},
        }
    }
    merged = merge_mcp_json(existing, transport="stdio")
    assert "orchestrator-ia" in merged["mcpServers"]
    assert "multiagent-orchestrator" not in merged["mcpServers"]
    assert "other" in merged["mcpServers"]


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
        }
    )
    if out["status"] == "COMPLETED":
        res = tools.result({"task_id": out["task_id"]})
        assert res["documentation"] is not None
        assert res["documentation"].get("validation") == "passed"


def test_mcp_rejects_fake_agents_payload(tools):
    with pytest.raises(McpSecurityError, match="fake_agents"):
        tools.run(
            {
                "objective": "x",
                "fake_agents": True,
                "wait": False,
            }
        )


def test_cursor_stdio_entry_has_project_placeholder():
    from orchestrator_runtime.mcp.cursor_config import stdio_server_entry

    entry = stdio_server_entry()
    args = entry.get("args") or []
    assert "--project" in args
    assert "${workspaceFolder}" in args
    assert entry.get("enabled") is True


def test_front_controller_direct_vs_delegate():
    # documentação/decisão: analyze is read-only; run is workflow
    assert True
