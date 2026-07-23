"""Orçamento de timeout por role + precedência request vs profile."""

from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from orchestrator_runtime.agents.base import AgentRequest, AgentSession
from orchestrator_runtime.agents.base_adapters import ProfileCliAdapter
from orchestrator_runtime.agents.process import ProcessResult
from orchestrator_runtime.config import load_config
from orchestrator_runtime.execution.timeouts import (
    MIN_AGENT_TIMEOUT_S,
    resolve_agent_timeout,
)
from orchestrator_runtime.tasks.models import TaskConstraints, TaskRecord
from orchestrator_runtime.tasks.service import TaskService


def test_resolve_executor_timeout_not_hardcapped_at_600():
    timeout = resolve_agent_timeout(
        "executor",
        remaining_s=3600,
        by_role={"executor": 2400},
        default_s=1800,
    )
    assert timeout == 2400
    assert timeout > 600


def test_resolve_timeout_caps_to_remaining():
    timeout = resolve_agent_timeout(
        "executor",
        remaining_s=120,
        by_role={"executor": 2400},
    )
    assert timeout == 120


def test_resolve_timeout_exhausted_returns_remaining_below_min():
    timeout = resolve_agent_timeout("executor", remaining_s=30)
    assert timeout == 30
    assert timeout < MIN_AGENT_TIMEOUT_S


def test_service_resolve_uses_policies_not_min_600(project):
    config = load_config(project, fake_agents=True)
    # policies fixture sem agent_timeout_* → defaults RuntimeLimits
    assert config.limits.agent_timeout_by_role["executor"] == 2400
    service = TaskService(config, verbose=False)
    task = TaskRecord(
        prompt="x",
        project_path=str(project),
        constraints=TaskConstraints(maximum_duration_seconds=3600),
    )
    service._loop_started_monotonic = __import__("time").monotonic()
    timeout = service._resolve_agent_timeout("executor", task)
    assert timeout == 2400


def test_no_min_600_hardcap_in_service_source():
    import orchestrator_runtime.tasks.service as svc_mod

    source = inspect.getsource(svc_mod)
    assert "min(600" not in source
    assert "min(600," not in source


@pytest.mark.asyncio
async def test_adapter_request_timeout_overrides_profile(project):
    profile = {
        "id": "codex",
        "kind": "cli",
        "verified": True,
        "invoke": {"subcommand": ["exec"], "prompt_flag": None},
        "timeout_default_s": 600,
        "exit_codes": {"success": 0},
    }
    executor = MagicMock()
    executor.run.return_value = ProcessResult(
        exit_code=0,
        stdout="ok",
        stderr="",
        timed_out=False,
        duration_s=0.1,
        command=["codex"],
        cwd=str(project),
    )
    adapter = ProfileCliAdapter(profile, executor)
    # bypass detect/which path rewrite
    adapter.detect = lambda: MagicMock(  # type: ignore[method-assign]
        available=True, path=None
    )
    request = AgentRequest(
        role="executor",
        prompt="do work",
        cwd=str(project),
        timeout_s=2400,
    )
    session = AgentSession(agent_id="codex", role="executor")
    await adapter.continue_session(session, request)
    assert executor.run.call_args.kwargs["timeout_s"] == 2400


@pytest.mark.asyncio
async def test_adapter_profile_fallback_when_request_timeout_zero(project):
    profile = {
        "id": "codex",
        "kind": "cli",
        "verified": True,
        "invoke": {"subcommand": ["exec"], "prompt_flag": None},
        "timeout_default_s": 1800,
        "exit_codes": {"success": 0},
    }
    executor = MagicMock()
    executor.run.return_value = ProcessResult(
        exit_code=0,
        stdout="ok",
        stderr="",
        timed_out=False,
        duration_s=0.1,
        command=["codex"],
        cwd=str(project),
    )
    adapter = ProfileCliAdapter(profile, executor)
    adapter.detect = lambda: MagicMock(available=True, path=None)  # type: ignore[method-assign]
    request = AgentRequest(
        role="executor",
        prompt="do work",
        cwd=str(project),
        timeout_s=0,
    )
    session = AgentSession(agent_id="codex", role="executor")
    await adapter.continue_session(session, request)
    assert executor.run.call_args.kwargs["timeout_s"] == 1800


def test_load_config_reads_agent_timeout_policies(project: Path):
    policies = project / ".orchestrator" / "config" / "policies.json"
    import json

    data = json.loads(policies.read_text(encoding="utf-8"))
    data["agent_timeout_default_s"] = 1500
    data["agent_timeout_by_role"] = {"executor": 3000, "validator": 900}
    policies.write_text(json.dumps(data), encoding="utf-8")
    config = load_config(project, fake_agents=True)
    assert config.limits.agent_timeout_default_s == 1500
    assert config.limits.agent_timeout_by_role["executor"] == 3000
    assert config.limits.agent_timeout_by_role["validator"] == 900
    # roles omitidos mantêm default
    assert config.limits.agent_timeout_by_role["planner"] == 900
