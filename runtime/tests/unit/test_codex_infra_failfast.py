"""0.4.15 — Testes para fail-fast de infra (740/sandbox) e override de sandbox Windows."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from orchestrator_runtime.agents.base import AgentRequest
from orchestrator_runtime.agents.base_adapters import ProfileCliAdapter
from orchestrator_runtime.agents.process import INFRA_FAIL_MARKERS, CliExecutor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _codex_profile(sandbox_flags: list[str] | None = None) -> dict[str, Any]:
    return {
        "id": "codex",
        "kind": "cli",
        "verified": True,
        "invoke": {
            "subcommand": ["exec"],
            "prompt_via": "arg",
            "prompt_flag": None,
            "sandbox_flags": (
                ["--sandbox", "workspace-write", "--skip-git-repo-check"]
                if sandbox_flags is None
                else sandbox_flags
            ),
        },
        "output": {"format": "text"},
        "exit_codes": {"success": 0},
        "timeout_default_s": 60,
    }


def _make_adapter(project: Path, sandbox_flags: list[str] | None = None) -> ProfileCliAdapter:
    exe = CliExecutor(project, echo=False)
    return ProfileCliAdapter(_codex_profile(sandbox_flags), exe)


# ---------------------------------------------------------------------------
# A) Sandbox override — Windows
# ---------------------------------------------------------------------------


def test_sandbox_override_on_windows(project: Path) -> None:
    """No Windows, workspace-write é substituído por danger-full-access."""
    adapter = _make_adapter(project)
    req = AgentRequest(role="executor", prompt="test", cwd=str(project))
    with patch("orchestrator_runtime.agents.base_adapters.os.name", "nt"):
        cmd = adapter.build_command(req)
    assert "--sandbox" in cmd
    idx = cmd.index("--sandbox")
    assert cmd[idx + 1] == "danger-full-access", (
        f"Esperado danger-full-access, obtido {cmd[idx + 1]!r}"
    )


def test_sandbox_no_override_on_posix(project: Path) -> None:
    """Em Linux/macOS, workspace-write é mantido."""
    adapter = _make_adapter(project)
    req = AgentRequest(role="executor", prompt="test", cwd=str(project))
    with patch("orchestrator_runtime.agents.base_adapters.os.name", "posix"):
        cmd = adapter.build_command(req)
    assert "--sandbox" in cmd
    idx = cmd.index("--sandbox")
    assert cmd[idx + 1] == "workspace-write"


def test_sandbox_override_only_replaces_workspace_write(project: Path) -> None:
    """Override não toca sandbox_flags que já usam danger-full-access."""
    adapter = _make_adapter(project, ["--sandbox", "danger-full-access"])
    req = AgentRequest(role="executor", prompt="test", cwd=str(project))
    with patch("orchestrator_runtime.agents.base_adapters.os.name", "nt"):
        cmd = adapter.build_command(req)
    idx = cmd.index("--sandbox")
    assert cmd[idx + 1] == "danger-full-access"


def test_sandbox_override_no_sandbox_flag(project: Path) -> None:
    """Profiles sem --sandbox não são afetados."""
    adapter = _make_adapter(project, [])
    req = AgentRequest(role="executor", prompt="test", cwd=str(project))
    with patch("orchestrator_runtime.agents.base_adapters.os.name", "nt"):
        cmd = adapter.build_command(req)
    assert "--sandbox" not in cmd


# ---------------------------------------------------------------------------
# B) INFRA_FAIL_MARKERS constant
# ---------------------------------------------------------------------------


def test_infra_fail_markers_present() -> None:
    assert "createprocessasuserw failed: 740" in INFRA_FAIL_MARKERS
    assert "windows sandbox: runner failed" in INFRA_FAIL_MARKERS
    assert "windows error 740" in INFRA_FAIL_MARKERS


# ---------------------------------------------------------------------------
# C) Fail-fast streaming
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="Python subprocess eco em Windows requer .CMD")
def test_infra_failfast_kills_after_n_markers(project: Path) -> None:
    """Processo que emite N marcadores 740 é morto antes do timeout."""
    # Script emite 5 linhas com marcador + loop infinito de sleep.
    # Com fail_fast_count=3, deve morrer em < 5s (não esperar timeout_s=30).
    marker = "CreateProcessAsUserW failed: 740"
    script = textwrap.dedent(
        f"""
        import sys, time
        for _ in range(5):
            print({marker!r}, flush=True)
        # Ficaria preso aqui sem o fail-fast.
        while True:
            time.sleep(0.1)
        """
    ).strip()
    exe = CliExecutor(project, echo=False, infra_fail_fast_count=3)
    result = exe.run(
        ["python", "-c", script],
        cwd=project,
        timeout_s=30,
        allow_nested=True,
    )
    assert not result.timed_out, "Processo não deveria ter expirado o timeout"
    assert result.duration_s < 10, f"Fail-fast demorou {result.duration_s:.1f}s (esperado < 10s)"
    assert "windows sandbox: runner failed" in result.stderr.lower() or "[INFRA-FAIL-FAST]" in result.stderr


@pytest.mark.skipif(sys.platform == "win32", reason="Python subprocess eco em Windows requer .CMD")
def test_infra_failfast_disabled_when_count_zero(project: Path) -> None:
    """infra_fail_fast_count=0 desabilita o fail-fast; processo termina normalmente."""
    marker = "CreateProcessAsUserW failed: 740"
    script = textwrap.dedent(
        f"""
        import sys
        for _ in range(5):
            print({marker!r}, flush=True)
        print("done", flush=True)
        """
    ).strip()
    exe = CliExecutor(project, echo=False, infra_fail_fast_count=0)
    result = exe.run(
        ["python", "-c", script],
        cwd=project,
        timeout_s=30,
        allow_nested=True,
    )
    assert result.exit_code == 0
    assert "done" in result.stdout
    # Sem fail-fast, stderr não deve ter o marcador de kill.
    assert "[INFRA-FAIL-FAST]" not in result.stderr


@pytest.mark.skipif(sys.platform == "win32", reason="Python subprocess eco em Windows requer .CMD")
def test_infra_failfast_not_triggered_below_threshold(project: Path) -> None:
    """Menos de N marcadores → processo termina normalmente sem kill."""
    marker = "CreateProcessAsUserW failed: 740"
    script = textwrap.dedent(
        f"""
        import sys
        for _ in range(2):
            print({marker!r}, flush=True)
        print("done", flush=True)
        """
    ).strip()
    exe = CliExecutor(project, echo=False, infra_fail_fast_count=3)
    result = exe.run(
        ["python", "-c", script],
        cwd=project,
        timeout_s=30,
        allow_nested=True,
    )
    assert result.exit_code == 0
    assert "done" in result.stdout
    assert "[INFRA-FAIL-FAST]" not in result.stderr


# ---------------------------------------------------------------------------
# D) Config wiring
# ---------------------------------------------------------------------------


def test_config_agent_infra_fail_fast_count_default(project: Path) -> None:
    """agent_infra_fail_fast_count default = 3 quando policies.json não define."""
    from orchestrator_runtime.config import load_config

    cfg = load_config(project)
    assert cfg.limits.agent_infra_fail_fast_count == 3


def test_config_agent_infra_fail_fast_count_from_policies(project: Path) -> None:
    """agent_infra_fail_fast_count lido de policies.json."""
    import json

    policies_path = project / ".orchestrator" / "config" / "policies.json"
    data = json.loads(policies_path.read_text(encoding="utf-8"))
    data["agent_infra_fail_fast_count"] = 5
    policies_path.write_text(json.dumps(data), encoding="utf-8")

    from orchestrator_runtime.config import load_config

    cfg = load_config(project)
    assert cfg.limits.agent_infra_fail_fast_count == 5


def test_executor_receives_infra_fail_fast_count_from_service(project: Path) -> None:
    """TaskService.__init__ repassa agent_infra_fail_fast_count ao CliExecutor."""
    import json

    policies_path = project / ".orchestrator" / "config" / "policies.json"
    data = json.loads(policies_path.read_text(encoding="utf-8"))
    data["agent_infra_fail_fast_count"] = 7
    policies_path.write_text(json.dumps(data), encoding="utf-8")

    from orchestrator_runtime.config import load_config
    from orchestrator_runtime.tasks.service import TaskService

    cfg = load_config(project)
    svc = TaskService(cfg, verbose=False)
    assert svc.executor.infra_fail_fast_count == 7
