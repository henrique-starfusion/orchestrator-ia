"""0.4.71 — a superficie do CLI e verificada, nao presumida (bug-108).

Na 0.4.66 o helper `_drain_queue` foi inserido LOGO ABAIXO do
`@app.command("run")` e engoliu o decorator. O typer registrou o HELPER como o
comando `run`, e o `run_cmd` real ficou orfao. Resultado em toda a frota:

    $ orchestrator run --prompt "..."
    Usage: run [OPTIONS] {service} {json_out}
    Error: No such option: --prompt

Nenhum teste pegou: a suite exercitava `TaskService` direto e nunca perguntava ao
typer quais comandos existem nem quais opcoes cada um aceita. Duas releases
passaram com o comando principal quebrado.

Este arquivo faz a pergunta que faltava — ao typer, nao ao codigo-fonte.
"""

from __future__ import annotations

import pytest
from typer.main import get_command

from orchestrator_runtime.cli import app


def _comando(nome: str):
    return get_command(app).commands[nome]


def _opcoes(nome: str) -> set[str]:
    return {o for p in _comando(nome).params for o in getattr(p, "opts", [])}


def test_comandos_de_primeiro_nivel_existem() -> None:
    registrados = set(get_command(app).commands)
    assert {"run", "task", "agents", "version", "mcp", "cursor"} <= registrados


@pytest.mark.parametrize(
    ("comando", "opcao"),
    [
        ("run", "--prompt"),
        ("run", "--project"),
        ("run", "--loop"),
        ("run", "--max-iterations"),
        ("run", "--timeout"),
        ("run", "--executor"),
        ("run", "--validator"),
        ("run", "--json"),
        ("run", "--fake-agents"),
    ],
)
def test_run_aceita_as_opcoes_documentadas(comando: str, opcao: str) -> None:
    assert opcao in _opcoes(comando)


def test_run_nao_expoe_parametro_interno() -> None:
    """A assinatura exata do bug: `service`/`json_out` como argumentos do `run`.

    Era o helper `_drain_queue(service, *, json_out)` ocupando o lugar do
    comando — `Usage: run [OPTIONS] {service} {json_out}`.
    """
    nomes = {p.name for p in _comando("run").params}
    assert "service" not in nomes, "o helper _drain_queue voltou a roubar o decorator"


def test_helper_de_fila_nao_e_comando() -> None:
    assert "_drain_queue" not in get_command(app).commands
    assert "drain-queue" not in get_command(app).commands


def test_subcomandos_de_task_existem() -> None:
    grupo = _comando("task")
    assert {"run", "status", "list", "logs", "resume"} <= set(grupo.commands)
