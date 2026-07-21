"""CLI Typer do runtime."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

import typer

from orchestrator_runtime import __version__
from orchestrator_runtime.tasks.service import build_service

app = typer.Typer(
    name="orchestrator-runtime",
    help="Runtime persistente de orquestração multiagente (StarFusion)",
    no_args_is_help=True,
)
task_app = typer.Typer(help="Gerenciamento de tarefas")
app.add_typer(task_app, name="task")


def _print_json(data) -> None:
    typer.echo(json.dumps(data, ensure_ascii=False, indent=2, default=str))


@app.callback()
def main_callback() -> None:
    """Orquestrador Runtime."""


@app.command("version")
def version_cmd() -> None:
    typer.echo(__version__)


@app.command("run")
def run_cmd(
    prompt: str = typer.Option(..., "--prompt", help="Atividade a executar"),
    project: Optional[Path] = typer.Option(None, "--project", help="Caminho do projeto"),
    profile: str = typer.Option("balanced", "--profile"),
    max_iterations: Optional[int] = typer.Option(None, "--max-iterations"),
    timeout: Optional[int] = typer.Option(None, "--timeout"),
    planner: Optional[str] = typer.Option(None, "--planner"),
    executor: Optional[str] = typer.Option(None, "--executor"),
    validator: Optional[str] = typer.Option(None, "--validator"),
    manager_provider: Optional[str] = typer.Option(None, "--manager-provider"),
    fake_agents: bool = typer.Option(False, "--fake-agents", help="Adapters falsos (CI)"),
    json_out: bool = typer.Option(False, "--json"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    verbose: bool = typer.Option(True, "--verbose/--quiet"),
) -> None:
    service = build_service(
        project,
        fake_agents=fake_agents,
        manager_provider=manager_provider,
        verbose=verbose and not json_out,
    )
    task = asyncio.run(
        service.run_prompt(
            prompt,
            profile=profile,
            max_iterations=max_iterations,
            timeout=timeout,
            planner=planner,
            executor=executor,
            validator=validator,
            dry_run=dry_run,
        )
    )
    if json_out:
        _print_json(task.model_dump())
    else:
        typer.echo(f"task={task.id} status={task.status.value} score={task.last_score}")
    raise typer.Exit(0 if task.status.value == "COMPLETED" else 1)


@task_app.command("create")
def task_create(
    prompt: str = typer.Option(..., "--prompt"),
    project: Optional[Path] = typer.Option(None, "--project"),
    profile: str = typer.Option("balanced", "--profile"),
    max_iterations: Optional[int] = typer.Option(None, "--max-iterations"),
    timeout: Optional[int] = typer.Option(None, "--timeout"),
    planner: Optional[str] = typer.Option(None, "--planner"),
    executor: Optional[str] = typer.Option(None, "--executor"),
    validator: Optional[str] = typer.Option(None, "--validator"),
    fake_agents: bool = typer.Option(False, "--fake-agents"),
    json_out: bool = typer.Option(False, "--json"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    service = build_service(project, fake_agents=fake_agents, verbose=False)
    task = service.create_task(
        prompt,
        profile=profile,
        max_iterations=max_iterations,
        timeout=timeout,
        planner=planner,
        executor=executor,
        validator=validator,
        dry_run=dry_run,
    )
    if json_out:
        _print_json(task.model_dump())
    else:
        typer.echo(task.id)


@task_app.command("run")
def task_run(
    task_id: str = typer.Argument(...),
    project: Optional[Path] = typer.Option(None, "--project"),
    fake_agents: bool = typer.Option(False, "--fake-agents"),
    manager_provider: Optional[str] = typer.Option(None, "--manager-provider"),
    json_out: bool = typer.Option(False, "--json"),
    verbose: bool = typer.Option(True, "--verbose/--quiet"),
) -> None:
    service = build_service(
        project,
        fake_agents=fake_agents,
        manager_provider=manager_provider,
        verbose=verbose and not json_out,
    )
    task = asyncio.run(service.run_task(task_id))
    if json_out:
        _print_json(task.model_dump())
    else:
        typer.echo(f"task={task.id} status={task.status.value}")
    raise typer.Exit(0 if task.status.value == "COMPLETED" else 1)


@task_app.command("status")
def task_status(
    task_id: str = typer.Argument(...),
    project: Optional[Path] = typer.Option(None, "--project"),
    json_out: bool = typer.Option(True, "--json/--text"),
) -> None:
    service = build_service(project, verbose=False)
    data = service.status(task_id)
    if json_out:
        _print_json(data)
    else:
        typer.echo(f"{data['id']} {data['status']}")


@task_app.command("list")
def task_list(
    project: Optional[Path] = typer.Option(None, "--project"),
    json_out: bool = typer.Option(False, "--json"),
    limit: int = typer.Option(50, "--limit"),
) -> None:
    service = build_service(project, verbose=False)
    tasks = service.list_tasks(limit=limit)
    if json_out:
        _print_json([t.model_dump() for t in tasks])
    else:
        for t in tasks:
            typer.echo(f"{t.id}\t{t.status.value}\t{t.prompt[:60]}")


@task_app.command("cancel")
def task_cancel(
    task_id: str = typer.Argument(...),
    project: Optional[Path] = typer.Option(None, "--project"),
) -> None:
    service = build_service(project, verbose=False)
    task = service.cancel(task_id)
    typer.echo(f"{task.id} {task.status.value}")


@task_app.command("resume")
def task_resume(
    task_id: str = typer.Argument(...),
    project: Optional[Path] = typer.Option(None, "--project"),
    fake_agents: bool = typer.Option(False, "--fake-agents"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    service = build_service(project, fake_agents=fake_agents, verbose=not json_out)
    task = asyncio.run(service.resume(task_id))
    if json_out:
        _print_json(task.model_dump())
    else:
        typer.echo(f"{task.id} {task.status.value}")
    raise typer.Exit(0 if task.status.value == "COMPLETED" else 1)


@task_app.command("logs")
def task_logs(
    task_id: str = typer.Argument(...),
    project: Optional[Path] = typer.Option(None, "--project"),
) -> None:
    service = build_service(project, verbose=False)
    _print_json(service.logs(task_id))


@task_app.command("artifacts")
def task_artifacts(
    task_id: str = typer.Argument(...),
    project: Optional[Path] = typer.Option(None, "--project"),
) -> None:
    service = build_service(project, verbose=False)
    _print_json(service.artifacts(task_id))


if __name__ == "__main__":
    app()
