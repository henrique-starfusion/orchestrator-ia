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
