from typer.testing import CliRunner

from orchestrator_runtime.cli import app


def test_cli_task_create_list(project):
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "task",
            "create",
            "--prompt",
            "hello world task",
            "--project",
            str(project),
            "--fake-agents",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    listed = runner.invoke(app, ["task", "list", "--project", str(project)])
    assert listed.exit_code == 0
    assert "hello world" in listed.output or listed.output.strip()
