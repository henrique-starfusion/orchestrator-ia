"""ProfileCliAdapter monta comando com sandbox_flags e path absoluto."""

from __future__ import annotations

from pathlib import Path

from orchestrator_runtime.agents.base import AgentRequest
from orchestrator_runtime.agents.base_adapters import ProfileCliAdapter
from orchestrator_runtime.agents.process import CliExecutor


def test_build_command_includes_sandbox_flags(project):
    profile = {
        "id": "codex",
        "kind": "cli",
        "invoke": {
            "subcommand": ["exec"],
            "prompt_flag": None,
            "sandbox_flags": ["--sandbox", "workspace-write", "--skip-git-repo-check"],
        },
    }
    adapter = ProfileCliAdapter(profile, CliExecutor(project, echo=False))
    cmd = adapter.build_command(
        AgentRequest(
            role="executor",
            prompt="hello",
            model="gpt-5.6-sol",
            model_flag="-m",
            cwd=str(project),
        )
    )
    assert cmd[:4] == ["codex", "exec", "--sandbox", "workspace-write"]
    assert "--skip-git-repo-check" in cmd
    assert "-m" in cmd and "gpt-5.6-sol" in cmd
    assert cmd[-1] == "hello"
