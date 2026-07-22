from pathlib import Path

from orchestrator_runtime.agents.process import CliExecutor, redact


def test_redact_secrets():
    text = "API_KEY=supersecret\nok line"
    out = redact(text)
    assert "REDACTED" in out
    assert "ok line" in out


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
