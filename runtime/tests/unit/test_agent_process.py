import os
import sys
from pathlib import Path

import pytest

from orchestrator_runtime.agents.process import CliExecutor, redact


def test_redact_secrets():
    text = "API_KEY=supersecret\nok line"
    out = redact(text)
    assert "REDACTED" in out
    assert "ok line" in out


@pytest.mark.skipif(sys.platform != "win32", reason="PATHEXT/.CMD resolution is Windows-specific")
def test_cli_executor_resolves_cmd_via_which(project, tmp_path, monkeypatch):
    """CreateProcess não resolve PATHEXT; CliExecutor deve usar shutil.which."""
    bat = tmp_path / "fake-agent.cmd"
    bat.write_text("@echo off\r\necho fake-ok\r\n", encoding="utf-8")
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ.get("PATH", ""))
    exe = CliExecutor(project, echo=False)
    result = exe.run(["fake-agent"], cwd=project, timeout_s=30, allow_nested=True)
    assert result.exit_code == 0
    assert "fake-ok" in result.stdout
    assert Path(result.command[0]).suffix.lower() in {".cmd", ".bat", ".exe"}


def test_cli_executor_echo(project, tmp_path):
    exe = CliExecutor(project, echo=False)
    result = exe.run(
        ["python", "-c", "print('hi')"],
        cwd=project,
        timeout_s=30,
        allow_nested=True,
    )
    assert result.exit_code == 0
    assert "hi" in result.stdout


def test_cli_executor_live_echo_redacts(project, capsys):
    exe = CliExecutor(project, echo=True)
    result = exe.run(
        ["python", "-c", "print('API_KEY=supersecret')"],
        cwd=project,
        timeout_s=30,
        allow_nested=True,
    )
    assert result.exit_code == 0
    captured = capsys.readouterr()
    # Echo ao vivo vai para stderr (stdout livre para MCP stdio).
    assert "supersecret" not in captured.out
    assert "supersecret" not in captured.err
    assert "REDACTED" in captured.err or "REDACTED" in result.stdout


def test_cli_executor_no_heartbeat_on_stdout(project, capsys):
    """Heartbeat/echo nunca podem ir para stdout (quebra JSON-RPC do MCP)."""
    exe = CliExecutor(project, echo=True)
    result = exe.run(
        [
            "python",
            "-c",
            "import time; time.sleep(0.2); print('done')",
        ],
        cwd=project,
        timeout_s=30,
        heartbeat_s=1,
        allow_nested=True,
    )
    assert result.exit_code == 0
    out = capsys.readouterr().out
    assert "[heartbeat]" not in out
    assert "[exec]" not in out
