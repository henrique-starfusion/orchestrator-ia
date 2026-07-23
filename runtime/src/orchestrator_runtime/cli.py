"""CLI Typer do runtime."""

from __future__ import annotations

import asyncio
import json
import sys
import textwrap
from pathlib import Path
from typing import Optional

import typer

from orchestrator_runtime import __version__
from orchestrator_runtime.tasks.service import build_service


def _configure_utf8_stdio() -> None:
    """Keep Windows pipes/MCP/IDE consumers on one encoding contract."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8", errors="strict")
        except (OSError, ValueError):
            # Test/capture streams and already-detached wrappers may reject it.
            continue


def _task_preview(prompt: str, width: int = 72) -> str:
    """Single-line, word-safe text preview; JSON keeps the complete prompt."""
    normalized = " ".join(prompt.split())
    shortened = textwrap.shorten(normalized, width=width, placeholder="…")
    if shortened.endswith("…"):
        shortened = shortened[:-1].rstrip(".,;:") + "…"
    return shortened


_configure_utf8_stdio()

app = typer.Typer(
    name="orchestrator-runtime",
    help="Runtime persistente de orquestração multiagente (StarFusion)",
    no_args_is_help=True,
)
task_app = typer.Typer(help="Gerenciamento de tarefas")
mcp_app = typer.Typer(help="Servidor MCP orchestrator-ia")
cursor_app = typer.Typer(help="Integração Cursor (front controller)")
app.add_typer(task_app, name="task")
app.add_typer(mcp_app, name="mcp")
app.add_typer(cursor_app, name="cursor")


def _print_json(data) -> None:
    typer.echo(json.dumps(data, ensure_ascii=False, indent=2, default=str))


@app.callback()
def main_callback() -> None:
    """Orquestrador Runtime."""


@app.command("version")
def version_cmd(
    json_out: bool = typer.Option(False, "--json", help="Inclui fingerprint/features"),
) -> None:
    """Versão do runtime (+ fingerprint para detectar MCP stale)."""
    if json_out:
        from orchestrator_runtime.diagnostics import code_fingerprint

        fp = code_fingerprint()
        _print_json(
            {
                "version": __version__,
                "code_fingerprint": fp["sha256_16"],
                "features": fp["features"],
                "module_path": fp["module_path"],
                "package_root": fp["package_root"],
            }
        )
        return
    typer.echo(__version__)


@app.command("agents")
def agents_cmd(
    action: Optional[str] = typer.Argument(
        None,
        help="Opcional: 'list' ou 'ls' (alias; mesmo efeito sem argumento)",
    ),
    project: Optional[Path] = typer.Option(None, "--project", help="Caminho do projeto"),
    json_out: bool = typer.Option(True, "--json/--text"),
) -> None:
    """Lista agentes do registry (equivalente a orchestrator_agents no MCP)."""
    if action is not None and action.lower() not in {"list", "ls"}:
        raise typer.BadParameter(
            "use 'list'/'ls' ou omita o argumento", param_hint="ACTION"
        )
    from orchestrator_runtime.mcp.tools import OrchestratorMcpTools

    tools = OrchestratorMcpTools(
        default_workspace=project or Path.cwd(), verbose=False
    )
    data = tools.agents()
    if json_out:
        _print_json(data)
    else:
        for item in data.get("agents") or []:
            status = "available" if item.get("available") else "unavailable"
            typer.echo(f"{item.get('id')}\t{status}\t{item.get('kind')}")


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
            typer.echo(f"{t.id}\t{t.status.value}\t{_task_preview(t.prompt)}")


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


@mcp_app.command("serve")
def mcp_serve(
    transport: str = typer.Option("stdio", "--transport"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
    project: Optional[Path] = typer.Option(None, "--project"),
    fake_agents: bool = typer.Option(False, "--fake-agents"),
) -> None:
    from orchestrator_runtime.mcp.server import serve

    serve(
        transport=transport,
        host=host,
        port=port,
        workspace=project,
        fake_agents=fake_agents or None,
    )


@mcp_app.command("status")
def mcp_status(
    project: Optional[Path] = typer.Option(None, "--project"),
    json_out: bool = typer.Option(True, "--json/--text"),
) -> None:
    from orchestrator_runtime.mcp.tools import OrchestratorMcpTools

    tools = OrchestratorMcpTools(default_workspace=project or Path.cwd(), verbose=False)
    data = tools.health()
    if json_out:
        _print_json(data)
    else:
        typer.echo(data.get("status"))


@mcp_app.command("doctor")
def mcp_doctor(
    project: Optional[Path] = typer.Option(None, "--project"),
) -> None:
    from orchestrator_runtime.mcp.server import doctor

    _print_json(doctor(project))


@cursor_app.command("configure")
def cursor_configure(
    project: Optional[Path] = typer.Option(None, "--project"),
    transport: str = typer.Option("stdio", "--transport"),
    url: Optional[str] = typer.Option(None, "--url"),
    command: str = typer.Option("orchestrator", "--command"),
) -> None:
    from orchestrator_runtime.mcp.cursor_config import write_cursor_mcp_config

    root = (project or Path.cwd()).resolve()
    path = write_cursor_mcp_config(
        root, transport=transport, command=command, url=url
    )
    # ensure rule exists from template copy if present in package adapters
    rule_dst = root / ".cursor" / "rules" / "multiagent-orchestrator.mdc"
    if not rule_dst.is_file():
        rule_dst.parent.mkdir(parents=True, exist_ok=True)
        rule_dst.write_text(
            """---
description: Integração do chat do Cursor com o Orquestrador Multiagente
alwaysApply: true
---

Você é o agente principal da conversa no Cursor (cliente IDE, não worker).

## Modo padrão: orquestrador (obrigatório, sem o usuário pedir)

`orchestrator_run` é o modo DEFAULT para qualquer tarefa não-trivial.
O usuário NÃO precisa pedir. Se qualquer gatilho abaixo se aplica, inicie
`orchestrator_run` (ou `orchestrator_delegate` para papel read-only pontual).

## Gatilhos (qualquer um → orquestrador)

- Alterar código-fonte (mesmo 1 linha de lógica, mesmo 1 arquivo)
- Corrigir bug reportado (bug fix NUNCA é exceção "trivial")
- Criar/alterar testes, build ou configuração de runtime
- Tarefa com critérios de aceitação, validação ou multi-arquivo

## Exceções (resposta direta permitida)

- Dúvida conceitual ou leitura pontual de arquivo (sem edição)
- Typo/comentário/formatação sem mudança de lógica, 1 arquivo
- Reformatação de resposta anterior no chat

## Anti-padrões (proibido)

- Fix inline "porque é rápido/simples" — se muda lógica, é orquestrador.
- Inventar preferência/política de projeto (ex.: "preferência do projeto:
  trabalho inline"). Alegação de preferência exige citação arquivo:linha de
  uma rule real; sem citação, a preferência não existe e vale o default.
- Subagentes `Task` do Cursor como workflow principal (só fallback legado,
  sempre com `model=` explícito).

Não simule respostas de agentes CLI.

Não afirme que Claude, Codex, Gemini, Kimi ou outro agente executou algo
sem uma chamada real ao Orchestrator.

Não use o mesmo agente como único executor e validador quando outro estiver
disponível.

Exija critérios de aceitação, testes determinísticos e evidências.

Aguarde o resultado real ou consulte `orchestrator_status` e
`orchestrator_result`.

Toda tarefa deve revisar e atualizar a documentação afetada antes da
conclusão.

Quando o runtime estiver indisponível, informe claramente e não simule a
orquestração.
""",
            encoding="utf-8",
        )
    typer.echo(f"[OK] Cursor MCP config: {path}")
    typer.echo(f"[OK] Cursor rule: {rule_dst}")


@cursor_app.command("verify")
def cursor_verify(
    project: Optional[Path] = typer.Option(None, "--project"),
) -> None:
    root = (project or Path.cwd()).resolve()
    mcp_path = root / ".cursor" / "mcp.json"
    rule_path = root / ".cursor" / "rules" / "multiagent-orchestrator.mdc"
    ok = mcp_path.is_file() and rule_path.is_file()
    _print_json(
        {
            "ok": ok,
            "mcp_json": str(mcp_path),
            "mcp_exists": mcp_path.is_file(),
            "rule": str(rule_path),
            "rule_exists": rule_path.is_file(),
        }
    )
    raise typer.Exit(0 if ok else 1)


@cursor_app.command("print-config")
def cursor_print_config(
    transport: str = typer.Option("stdio", "--transport"),
    url: Optional[str] = typer.Option(None, "--url"),
) -> None:
    from orchestrator_runtime.mcp.cursor_config import print_config

    _print_json(print_config(transport=transport, url=url))


if __name__ == "__main__":
    app()
