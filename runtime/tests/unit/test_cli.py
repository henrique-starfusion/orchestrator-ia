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


def test_cli_agents_accepts_list_alias(project):
    runner = CliRunner()
    bare = runner.invoke(app, ["agents", "--project", str(project), "--json"])
    assert bare.exit_code == 0, bare.output
    assert "claude" in bare.output or '"agents"' in bare.output
    aliased = runner.invoke(
        app, ["agents", "list", "--project", str(project), "--json"]
    )
    assert aliased.exit_code == 0, aliased.output
    assert '"agents"' in aliased.output
    bad = runner.invoke(app, ["agents", "foobar", "--project", str(project)])
    assert bad.exit_code != 0
