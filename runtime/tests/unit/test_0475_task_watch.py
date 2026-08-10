"""0.4.75 — `orchestrator task watch`: acompanhar sem escrever laco de shell.

Motivo concreto: no trustsafe apareceram TRES tarefas de segundo plano vigiando a
MESMA task (`c210252e2c58`), cada uma com um `until ... sleep` escrito a mao e com
intervalo diferente (120s, 150s, 150s). Nao era task duplicada — era o vigia
duplicado. O pipe (`| grep -qE`) engolia a saida, o painel ficava mudo entre os
`sleep`, e a sessao recriava o vigia achando que tinha travado.

O material ja existia desde a 0.4.73: cada batida do heartbeat e um evento com
fase, idade da fase, `agent_active` e pid. Faltava transmitir.

A logica testavel mora em `follow_events` e em `watch.py`; o comando e `print` e
`sleep` em cima disso.
"""

from __future__ import annotations

import json
from pathlib import Path

from orchestrator_runtime.events import EventType, RuntimeEvent
from orchestrator_runtime.tasks.service import build_service
from orchestrator_runtime.tasks.state_machine import TaskState
from orchestrator_runtime.watch import (
    RUIDO,
    format_event_line,
    format_live_line,
    relevant,
)


def _evento(svc, task_id: str, tipo: EventType, **dados) -> None:
    svc.repo.add_event(
        RuntimeEvent(task_id=task_id, type=tipo, data=dados or {"summary": "x"})
    )


# --------------------------------------------------------------------------
# follow_events: o cursor e o fim
# --------------------------------------------------------------------------


def test_cursor_devolve_so_o_que_chegou_depois(project: Path) -> None:
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("x")
    primeira = svc.follow_events(task.id, 0)

    _evento(svc, task.id, EventType.AGENT_STARTED, summary="comecou")
    segunda = svc.follow_events(task.id, primeira["cursor"])

    assert [e["data"]["summary"] for e in segunda["events"]] == ["comecou"]
    assert segunda["cursor"] > primeira["cursor"]


def test_sem_evento_novo_o_cursor_nao_anda(project: Path) -> None:
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("x")
    volta = svc.follow_events(task.id, 0)

    de_novo = svc.follow_events(task.id, volta["cursor"])

    assert de_novo["events"] == []
    assert de_novo["cursor"] == volta["cursor"]


def test_terminal_e_o_que_encerra_o_laco(project: Path) -> None:
    """Sem este campo o laco teria que adivinhar "parece pronto"."""
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("x")
    assert svc.follow_events(task.id, 0)["terminal"] is False

    svc.repo.transition(
        svc.get(task.id), TaskState.COMPLETED, reason="fim", agent="runtime"
    )

    volta = svc.follow_events(task.id, 0)
    assert volta["terminal"] is True
    assert volta["status"] == "COMPLETED"


def test_task_viva_traz_o_sinal_de_vida(project: Path) -> None:
    import os

    svc = build_service(project, fake_agents=True)
    task = svc.create_task("x")
    svc._emit_loop_progress(task.id, pid=os.getpid(), elapsed_s=5)

    volta = svc.follow_events(task.id, 0)

    assert volta["live"]["pid_alive"] is True


def test_task_terminal_nao_traz_sinal_de_vida(project: Path) -> None:
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("x")
    svc.repo.transition(
        svc.get(task.id), TaskState.COMPLETED, reason="fim", agent="runtime"
    )

    assert "live" not in svc.follow_events(task.id, 0)


def test_ordem_dos_eventos_e_preservada(project: Path) -> None:
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("x")
    for i in range(5):
        _evento(svc, task.id, EventType.AGENT_OUTPUT, summary=f"n{i}")

    volta = svc.follow_events(task.id, 0)
    resumos = [e["data"].get("summary") for e in volta["events"] if e["data"].get("summary")]

    assert resumos[-5:] == ["n0", "n1", "n2", "n3", "n4"]


def test_limite_nao_pula_evento(project: Path) -> None:
    """Com `limit` menor que a fila, o cursor tem que permitir buscar o resto."""
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("x")
    for i in range(10):
        _evento(svc, task.id, EventType.AGENT_OUTPUT, summary=f"n{i}")

    vistos: list[str] = []
    cursor = 0
    for _ in range(10):
        volta = svc.follow_events(task.id, cursor, limit=3)
        if not volta["events"]:
            break
        cursor = volta["cursor"]
        vistos.extend(
            e["data"]["summary"] for e in volta["events"] if e["data"].get("summary")
        )

    assert [v for v in vistos if v.startswith("n")] == [f"n{i}" for i in range(10)]


# --------------------------------------------------------------------------
# formatacao
# --------------------------------------------------------------------------


def test_linha_traz_hora_tipo_e_quem() -> None:
    linha = format_event_line(
        {
            "timestamp": "2026-08-10T18:29:51.762219+00:00",
            "type": "agent_progress",
            "role": "executor",
            "agent": "codex",
            "data": {"summary": "rodando ha 240s"},
        }
    )

    assert linha == "[18:29:51] agent_progress codex/executor — rodando ha 240s"


def test_linha_aceita_timestamp_do_sqlite_com_espaco() -> None:
    """O roundtrip pelo SQLite grava "YYYY-MM-DD HH:MM:SS", sem o T."""
    linha = format_event_line(
        {"timestamp": "2026-08-10 18:27:49.627358", "type": "task_created", "data": {}}
    )

    assert linha.startswith("[18:27:49] task_created")


def test_linha_sem_resumo_nao_deixa_travessao_solto() -> None:
    assert format_event_line({"type": "task_created", "data": {}}) == (
        "[--:--:--] task_created"
    )


def test_linha_usa_o_erro_quando_nao_ha_resumo() -> None:
    linha = format_event_line({"type": "task_failed", "data": {"error": "estourou"}})

    assert "erro: estourou" in linha


def test_linha_de_transicao_usa_o_destino() -> None:
    """`state_changed` grava `to`, nao `summary`."""
    linha = format_event_line({"type": "state_changed", "data": {"to": "EXECUTING"}})

    assert linha.endswith("— EXECUTING")


def test_linha_de_vida_diz_o_estado_do_pid() -> None:
    linha = format_live_line(
        {"summary": "EXECUTING há 412s", "signal_age_s": 8, "pid": 50764, "pid_alive": True}
    )

    assert "pid=50764 pid vivo" in linha
    assert "sinal há 8s" in linha


def test_linha_de_vida_marca_pid_morto() -> None:
    assert "pid MORTO" in format_live_line({"pid": 1, "pid_alive": False})


def test_sem_sinal_nao_ha_linha_de_vida() -> None:
    assert format_live_line(None) == ""
    assert format_live_line({}) == ""


# --------------------------------------------------------------------------
# filtro de ruido
# --------------------------------------------------------------------------


def test_heartbeat_fica_de_fora_por_padrao() -> None:
    """A batida repete a mesma frase a cada 20-30s: sozinha, ela e o ruido que
    faz o dono parar de ler a tela."""
    eventos = [
        {"type": "loop_progress"},
        {"type": "agent_progress"},
        {"type": "state_changed"},
    ]

    assert [e["type"] for e in relevant(eventos, verbose=False)] == ["state_changed"]


def test_verbose_mostra_tudo() -> None:
    eventos = [{"type": "loop_progress"}, {"type": "state_changed"}]

    assert len(relevant(eventos, verbose=True)) == 2


def test_ruido_cobre_os_dois_heartbeats() -> None:
    assert set(RUIDO) == {"loop_progress", "agent_progress"}


# --------------------------------------------------------------------------
# o comando existe e esta registrado
# --------------------------------------------------------------------------


def test_watch_registrado_no_cli() -> None:
    """bug-108: um decorator roubado deixou `run` fora do CLI e 555 testes nao
    viram. Comando novo entra com o proprio teste de registro."""
    from typer.main import get_command

    from orchestrator_runtime.cli import app

    grupos = get_command(app).commands
    assert "watch" in grupos["task"].commands


def test_watch_de_task_terminal_sai_na_primeira_volta(project: Path, monkeypatch) -> None:
    """Nao pode ficar preso esperando uma task que ja acabou."""
    from typer.testing import CliRunner

    from orchestrator_runtime.cli import app

    svc = build_service(project, fake_agents=True)
    task = svc.create_task("x")
    svc.repo.transition(
        svc.get(task.id), TaskState.COMPLETED, reason="fim", agent="runtime"
    )

    resultado = CliRunner().invoke(
        app, ["task", "watch", task.id, "--project", str(project), "--interval", "0.2"]
    )

    assert resultado.exit_code == 0, resultado.output
    assert "COMPLETED" in resultado.output


def test_watch_sai_diferente_de_zero_quando_nao_completou(project: Path) -> None:
    """Mesmo contrato do `run`: terminal != COMPLETED e falha."""
    from typer.testing import CliRunner

    from orchestrator_runtime.cli import app

    svc = build_service(project, fake_agents=True)
    task = svc.create_task("x")
    svc.repo.transition(
        svc.get(task.id), TaskState.INCOMPLETE, reason="fim", agent="runtime"
    )

    resultado = CliRunner().invoke(
        app, ["task", "watch", task.id, "--project", str(project), "--interval", "0.2"]
    )

    assert resultado.exit_code == 1, resultado.output


def test_watch_timeout_nao_cancela_a_task(project: Path) -> None:
    """Desistir de olhar nao pode ser confundido com cancelar."""
    from typer.testing import CliRunner

    from orchestrator_runtime.cli import app

    svc = build_service(project, fake_agents=True)
    task = svc.create_task("x")
    svc.repo.transition(
        svc.get(task.id), TaskState.ANALYZING, reason="rodando", agent="runtime"
    )

    resultado = CliRunner().invoke(
        app,
        [
            "task", "watch", task.id,
            "--project", str(project),
            "--interval", "0.2",
            "--timeout", "1",
        ],
    )

    assert resultado.exit_code == 2, resultado.output
    assert "NÃO foi cancelada" in resultado.output
    assert svc.get(task.id).status == TaskState.ANALYZING


def test_watch_json_emite_uma_linha_por_evento(project: Path) -> None:
    """Modo para outro agente consumir sem parsear texto."""
    from typer.testing import CliRunner

    from orchestrator_runtime.cli import app

    svc = build_service(project, fake_agents=True)
    task = svc.create_task("x")
    _evento(svc, task.id, EventType.AGENT_STARTED, summary="comecou")
    svc.repo.transition(
        svc.get(task.id), TaskState.COMPLETED, reason="fim", agent="runtime"
    )

    resultado = CliRunner().invoke(
        app,
        ["task", "watch", task.id, "--project", str(project), "--json", "--all"],
    )

    assert resultado.exit_code == 0, resultado.output
    tipos = [
        json.loads(linha)["type"]
        for linha in resultado.output.splitlines()
        if linha.strip().startswith("{")
    ]
    assert "agent_started" in tipos
