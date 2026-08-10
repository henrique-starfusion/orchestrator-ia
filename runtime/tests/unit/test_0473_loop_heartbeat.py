"""0.4.73 — heartbeat do LOOP, nao so do agente.

O `agent_progress` (0.4.28) so existe enquanto um CLI esta no ar. Nos vaos —
escolha de agentes, consolidacao, gravacao de memoria, gate de documentacao, a
troca de uma etapa para a seguinte — NADA era emitido. Quem olhava `task status`
via a mesma linha por minutos, com `updated_at` parado (ele so muda em
transicao), e nao tinha como distinguir fase legitima de processo morto.

Custou tres investigacoes manuais na frota para concluir "nao travou": foi
preciso ler o log inteiro e conferir o PID a mao. printbee `8e4329205f01` e
trustsafe `e89063f15776` estavam ambas trabalhando.

Duas garantias aqui:

1. O loop bate mesmo sem agente no ar, dizendo a fase, a idade DA FASE e quem
   esta (ou esteve) rodando.
2. O reaper IGNORA essa batida. Ela nasce de uma thread do processo dono e
   continuaria batendo com o loop travado num lock — conta-la como progresso
   trocaria a fila parada de 11h do bug-090 por uma eterna.
"""

from __future__ import annotations

import os
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from orchestrator_runtime.events import EventType
from orchestrator_runtime.tasks import service as service_mod
from orchestrator_runtime.tasks.service import build_service
from orchestrator_runtime.tasks.state_machine import TaskState


def _loop_events(svc, task_id: str) -> list[dict]:
    return [
        e
        for e in svc.repo.list_events(task_id)
        if e["type"] == EventType.LOOP_PROGRESS.value
    ]


# --------------------------------------------------------------------------
# a batida em si
# --------------------------------------------------------------------------


def test_batida_persiste_evento_com_a_fase(project: Path) -> None:
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("x")

    svc._emit_loop_progress(task.id, pid=os.getpid(), elapsed_s=42)

    eventos = _loop_events(svc, task.id)
    assert len(eventos) == 1
    dados = eventos[0]["data"]
    assert dados["phase"] == svc.get(task.id).status.value
    assert dados["elapsed_s"] == 42
    assert dados["pid"] == os.getpid()


def test_batida_traz_idade_da_fase_nao_da_task(project: Path) -> None:
    """bug-105 de novo: mensagem tem que dizer QUAL relogio esta mostrando."""
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("x")

    svc._emit_loop_progress(task.id, pid=os.getpid(), elapsed_s=999)

    dados = _loop_events(svc, task.id)[0]["data"]
    idade_da_fase = svc._age_seconds(
        svc.get(task.id).updated_at, datetime.now(timezone.utc)
    )
    assert dados["phase_elapsed_s"] is not None
    # a idade da fase e a do `updated_at`, nao o elapsed_s do loop
    assert dados["phase_elapsed_s"] < 60
    assert abs(dados["phase_elapsed_s"] - int(idade_da_fase or 0)) <= 2


def test_sem_agente_no_ar_a_batida_diz_isso(project: Path) -> None:
    """O caso que motivou tudo: vao entre etapas nao pode parecer silencio."""
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("x")
    svc._ctx(task).current_agent = ("executor", "codex")
    svc.executor._active_pids.clear()

    svc._emit_loop_progress(task.id, pid=os.getpid(), elapsed_s=10)

    dados = _loop_events(svc, task.id)[0]["data"]
    assert dados["agent_active"] is False
    assert "entre etapas" in dados["summary"]
    assert "codex" in dados["summary"]


def test_primeira_etapa_nao_inventa_agente(project: Path) -> None:
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("x")
    svc._ctx(task).current_agent = None

    svc._emit_loop_progress(task.id, pid=os.getpid(), elapsed_s=1)

    dados = _loop_events(svc, task.id)[0]["data"]
    assert dados["agent_active"] is False
    assert "primeira etapa" in dados["summary"]
    assert dados.get("agent") is None


def test_agente_no_ar_aparece_com_pid(project: Path) -> None:
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("x")
    svc._ctx(task).current_agent = ("executor", "claude")
    svc.executor._active_pids.add(4242)
    try:
        svc._emit_loop_progress(task.id, pid=os.getpid(), elapsed_s=5)
    finally:
        svc.executor._active_pids.discard(4242)

    dados = _loop_events(svc, task.id)[0]["data"]
    assert dados["agent_active"] is True
    assert "claude/executor" in dados["summary"]
    assert "4242" in dados["summary"]


def test_run_agent_registra_quem_esta_no_ar(project: Path) -> None:
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("x")

    svc._register_heartbeat(task, role="validator", agent_id="claude")

    assert svc._ctx(task).current_agent == ("validator", "claude")


def test_etapa_corrente_nao_vaza_entre_tasks(project: Path) -> None:
    """0.4.74 — duas tasks no mesmo processo nao podem trocar de etapa.

    Antes `_current_agent` era do SERVICO: a segunda task a despachar um agente
    reescrevia o nome que o heartbeat da primeira ia reportar.
    """
    svc = build_service(project, fake_agents=True)
    a = svc.create_task("a")
    b = svc.create_task("b")

    svc._register_heartbeat(a, role="executor", agent_id="codex")
    svc._register_heartbeat(b, role="validator", agent_id="claude")

    assert svc._ctx(a).current_agent == ("executor", "codex")
    assert svc._ctx(b).current_agent == ("validator", "claude")


# --------------------------------------------------------------------------
# a thread: bate durante o loop, para quando ele acaba
# --------------------------------------------------------------------------


def _cadencia_curta(svc, monkeypatch) -> None:
    """1s e o menor valor que a cadencia aceita: `heartbeat_s or 30` trata 0
    como ausente, e o piso do modulo so entra se o perfil for menor que ele."""
    monkeypatch.setattr(service_mod, "LOOP_HEARTBEAT_MIN_S", 0.05)
    monkeypatch.setattr(
        svc, "caller_profile", replace(svc.caller_profile, heartbeat_s=1)
    )


def test_cadencia_tem_piso(project: Path) -> None:
    """Perfil agressivo nao transforma sinal de vida em enchente de eventos."""
    assert service_mod.LOOP_HEARTBEAT_MIN_S >= 10


def test_contextmanager_bate_e_para(project: Path, monkeypatch) -> None:
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("x")
    _cadencia_curta(svc, monkeypatch)

    with svc._loop_heartbeat(task):
        limite = time.monotonic() + 5
        while not _loop_events(svc, task.id) and time.monotonic() < limite:
            time.sleep(0.05)
        assert _loop_events(svc, task.id), "loop ficou mudo dentro do proprio loop"

    batidas = len(_loop_events(svc, task.id))
    time.sleep(1.5)  # mais de uma cadencia depois do fim
    assert len(_loop_events(svc, task.id)) == batidas, (
        "thread continuou batendo depois do loop terminar"
    )


def test_batida_quebrada_nao_derruba_o_loop(project: Path, monkeypatch) -> None:
    """Observabilidade nunca mata a task."""
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("x")
    _cadencia_curta(svc, monkeypatch)

    def _explode(*_a, **_k):
        raise RuntimeError("db fora do ar")

    monkeypatch.setattr(svc, "_emit_loop_progress", _explode)

    with svc._loop_heartbeat(task):
        time.sleep(1.3)  # tempo de a batida falhar de verdade
    assert not _loop_events(svc, task.id)


# --------------------------------------------------------------------------
# o reaper tem que continuar cego para esta batida
# --------------------------------------------------------------------------


def test_reaper_ignora_a_batida_do_loop(project: Path) -> None:
    """A garantia central. Loop travado num lock ainda bate — se isso contasse
    como progresso, a task ficaria em EXECUTING para sempre e a fila atras dela
    junto (bug-090)."""
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("x")
    # instante fixo: a comparacao tem que ser exata, nao "quase igual"
    agora = datetime.now(timezone.utc)
    antes = svc._idle_seconds(svc.get(task.id), agora)

    svc._emit_loop_progress(task.id, pid=os.getpid(), elapsed_s=1)

    depois = svc._idle_seconds(svc.get(task.id), agora)
    assert depois == antes, (
        "heartbeat do loop nao pode reduzir o silencio aos olhos do reaper"
    )


def test_reaper_continua_vendo_o_heartbeat_do_agente(project: Path) -> None:
    """bug-096 permanece corrigido: CLI no ar E progresso de verdade.

    O filtro do reaper tem que descartar o sinal do loop e manter o do agente,
    mesmo com o do loop sendo o mais recente dos dois.
    """
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("x")
    svc._register_heartbeat(task, role="executor", agent_id="codex")
    svc.executor.on_heartbeat(30, os.getpid())
    svc._emit_loop_progress(task.id, pid=os.getpid(), elapsed_s=1)

    assert svc.repo.last_event(task.id)["type"] == EventType.LOOP_PROGRESS.value
    sobreviveu = svc.repo.last_event(
        task.id, exclude_types=(EventType.LOOP_PROGRESS.value,)
    )
    assert sobreviveu["type"] == EventType.AGENT_PROGRESS.value


def test_last_event_at_filtra_por_tipo(project: Path) -> None:
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("x")
    com_tudo = svc.repo.last_event_at(task.id)
    svc._emit_loop_progress(task.id, pid=os.getpid(), elapsed_s=1)

    assert svc.repo.last_event_at(task.id) != com_tudo
    assert (
        svc.repo.last_event_at(
            task.id, exclude_types=(EventType.LOOP_PROGRESS.value,)
        )
        == com_tudo
    )


# --------------------------------------------------------------------------
# `status` responde "travou?" sem exigir leitura do log
# --------------------------------------------------------------------------


def test_status_traz_o_sinal_de_vida(project: Path) -> None:
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("x")
    svc._ctx(task).current_agent = ("executor", "codex")
    svc._emit_loop_progress(task.id, pid=os.getpid(), elapsed_s=7)

    live = svc.status(task.id).get("live")
    assert live, "status sem sinal de vida obriga a ler `task logs` inteiro"
    assert live["signal"] == EventType.LOOP_PROGRESS.value
    assert live["pid_alive"] is True  # este processo esta rodando o teste
    assert live["agent_active"] is False
    assert live["signal_age_s"] is not None and live["signal_age_s"] < 60


def test_status_marca_pid_morto(project: Path) -> None:
    """A resposta que interessa quando travou de verdade."""
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("x")
    svc._emit_loop_progress(task.id, pid=os.getpid(), elapsed_s=1)
    # reescreve o evento com um PID que nao existe
    eventos = svc.repo.list_events(task.id)
    assert eventos
    svc.repo.add_event(
        service_mod.RuntimeEvent(
            task_id=task.id,
            type=EventType.LOOP_PROGRESS,
            data={"phase": "EXECUTING", "pid": 999_999_999, "agent_active": False},
        )
    )

    assert svc.status(task.id)["live"]["pid_alive"] is False


def test_status_de_task_sem_sinal_nao_inventa(project: Path) -> None:
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("x")

    assert "live" not in svc.status(task.id)


def test_task_terminal_nao_ganha_sinal_de_vida(project: Path) -> None:
    """Task concluida nao esta "viva"; a linha so confundiria."""
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("x")
    svc._emit_loop_progress(task.id, pid=os.getpid(), elapsed_s=1)
    fresh = svc.get(task.id)
    svc.repo.transition(fresh, TaskState.COMPLETED, reason="fim", agent="runtime")

    assert "live" not in svc.status(task.id)


def test_mcp_status_traz_o_sinal_e_a_mensagem(project: Path) -> None:
    """Quem poll o MCP e um agente decidindo entre esperar e cancelar: a
    resposta "travou?" tem que estar na `message`, nao so num campo."""
    from orchestrator_runtime.mcp.tools import OrchestratorMcpTools

    tools = OrchestratorMcpTools(
        default_workspace=project, fake_agents=True, verbose=False
    )
    svc = tools._service()
    task = svc.create_task("x")
    svc._ctx(task).current_agent = ("executor", "codex")
    svc._emit_loop_progress(task.id, pid=os.getpid(), elapsed_s=7)

    out = tools.status({"task_id": task.id})
    assert out["live"]["pid_alive"] is True
    assert out["live"]["agent_active"] is False
    assert "pid vivo" in out["message"]
    assert "entre etapas" in out["message"]
    # 0.4.74 — sem repetir o resumo: ele ja vem de `last_data["summary"]`
    assert out["message"].count("entre etapas") == 1


def test_mcp_status_terminal_nao_traz_sinal(project: Path) -> None:
    from orchestrator_runtime.mcp.tools import OrchestratorMcpTools

    tools = OrchestratorMcpTools(
        default_workspace=project, fake_agents=True, verbose=False
    )
    svc = tools._service()
    task = svc.create_task("x")
    svc._emit_loop_progress(task.id, pid=os.getpid(), elapsed_s=1)
    svc.repo.transition(svc.get(task.id), TaskState.COMPLETED, reason="fim", agent="runtime")

    assert tools.status({"task_id": task.id})["live"] == {}


def test_agent_progress_serve_de_sinal_quando_e_o_mais_recente(project: Path) -> None:
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("x")
    svc._emit_loop_progress(task.id, pid=os.getpid(), elapsed_s=1)
    svc._register_heartbeat(task, role="executor", agent_id="codex")
    svc.executor.on_heartbeat(30, os.getpid())

    live = svc.status(task.id)["live"]
    assert live["signal"] == EventType.AGENT_PROGRESS.value
    assert live["agent"] == "codex"
