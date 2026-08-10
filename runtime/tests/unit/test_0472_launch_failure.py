"""0.4.72 — processo que NAO NASCEU deixa de virar reinstalacao (bug-109).

Medido no trustsafe, task 22a07ed7e2de, 09/08 14:47:

    corrector/codex     exit=3221225794  0s  stdout=0  stderr=0
    corrector/opencode  exit=3221225794  0s  stdout=0  stderr=0

3221225794 = 0xC0000142 = STATUS_DLL_INIT_FAILED: o processo nao conseguiu nem
inicializar. Sem saida nenhuma, o classificador caiu na regra do fast-fail mudo
e devolveu `install`. O auto-reparo tentou reinstalar os dois — e a PROPRIA
reinstalacao falhou com o mesmo codigo:

    codex:    reinstalacao falhou (exit=3221225794)  repair_ok: false
    opencode: reinstalacao falhou (exit=3221225794)  repair_ok: false

Quatro lancamentos de processo falharam em ~1 segundo. O sinal era da maquina,
nao do CLI — e quando o proprio reparo nao nasce, insistir e desperdicio certo.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestrator_runtime.agents.health import (
    LAUNCH_FAILURE_MAX_S,
    classify_agent_failure,
    is_launch_failure,
)
from orchestrator_runtime.tasks.service import build_service

DLL_INIT_FAILED = 0xC0000142  # 3221225794


def _run(**kw):
    base = dict(
        stdout="", stderr="", duration_s=0.0, status="failed",
        timed_out=False, exit_code=DLL_INIT_FAILED,
    )
    base.update(kw)
    return SimpleNamespace(**base)


# --------------------------------------------------------------------------
# o predicado
# --------------------------------------------------------------------------


def test_a_assinatura_exata_do_trustsafe() -> None:
    assert is_launch_failure(3221225794, duration_s=0.0, produced=False) is True


def test_windows_reportando_como_negativo() -> None:
    """O mesmo NTSTATUS chega como complemento de dois em alguns caminhos."""
    assert is_launch_failure(-1073741502, duration_s=0.0, produced=False) is True


@pytest.mark.parametrize("codigo", [0xC0000017, 0xC000012D, 0xC0000018])
def test_familia_de_falta_de_recurso(codigo: int) -> None:
    assert is_launch_failure(codigo, duration_s=0.0, produced=False) is True


@pytest.mark.parametrize("codigo", [0xC0000005, 0xC0000409, 1, 0, 127])
def test_crash_de_binario_fica_fora(codigo: int) -> None:
    """Access violation e stack overrun sao crash: reinstalar PODE resolver."""
    assert is_launch_failure(codigo, duration_s=0.0, produced=False) is False


def test_processo_que_trabalhou_nao_e_falha_de_lancamento() -> None:
    """So o codigo nao basta — morte tardia e outra historia."""
    assert (
        is_launch_failure(
            DLL_INIT_FAILED, duration_s=LAUNCH_FAILURE_MAX_S + 1, produced=False
        )
        is False
    )


def test_processo_que_falou_nao_e_falha_de_lancamento() -> None:
    assert is_launch_failure(DLL_INIT_FAILED, duration_s=0.0, produced=True) is False


def test_exit_code_ilegivel_nao_explode() -> None:
    assert is_launch_failure(None, duration_s=0.0, produced=False) is False
    assert is_launch_failure("nao-numero", duration_s=0.0, produced=False) is False


# --------------------------------------------------------------------------
# a classificacao
# --------------------------------------------------------------------------


def test_nao_nascer_classifica_launch_e_nao_install() -> None:
    assert classify_agent_failure(_run()) == "launch"


def test_sem_o_codigo_ainda_cai_em_install() -> None:
    """Contraste: e a regra do fast-fail mudo que este bug atropelava."""
    assert classify_agent_failure(_run(exit_code=1)) == "install"


def test_launch_vence_marcador_de_install_na_saida() -> None:
    """Processo que nao nasceu nao tem diagnostico de CLI a oferecer."""
    r = _run(stderr="npm error something", exit_code=DLL_INIT_FAILED)
    # com saida, o predicado nao aceita: volta a valer o marcador
    assert classify_agent_failure(r) == "install"


def test_timeout_continua_fora() -> None:
    r = _run()
    r.timed_out = True
    assert classify_agent_failure(r) is None


def test_sucesso_nunca_classifica() -> None:
    assert classify_agent_failure(_run(status="completed")) is None


# --------------------------------------------------------------------------
# o que o dono ve
# --------------------------------------------------------------------------


def test_launch_vira_degradacao_com_acao_de_maquina(project: Path) -> None:
    from orchestrator_runtime.events import EventType, RuntimeEvent

    svc = build_service(project, fake_agents=True)
    task = svc.create_task("task que pegou a maquina sem recurso")
    svc.repo.add_event(
        RuntimeEvent(
            task_id=task.id,
            type=EventType.AGENT_REPAIR,
            role="corrector",
            agent="codex",
            data={"failure_kind": "launch", "exit_code": DLL_INIT_FAILED},
        )
    )

    assert [f["agent"] for f in svc.launch_failures(task.id)] == ["codex"]

    deg = [d for d in svc.degradations(task.id) if d["kind"] == "agent_launch_failed"]
    assert deg, "degradacao aceita tem que aparecer no resultado"
    assert "não do CLI" in deg[0]["detail"]
    assert "instalar" in deg[0]["action"] and "logar" in deg[0]["action"]


def test_launch_nao_polui_auth_nem_service(project: Path) -> None:
    from orchestrator_runtime.events import EventType, RuntimeEvent

    svc = build_service(project, fake_agents=True)
    task = svc.create_task("x")
    svc.repo.add_event(
        RuntimeEvent(
            task_id=task.id,
            type=EventType.AGENT_REPAIR,
            role="corrector",
            agent="codex",
            data={"failure_kind": "launch", "exit_code": DLL_INIT_FAILED},
        )
    )

    assert svc.auth_blockers(task.id) == []
    assert svc.service_outages(task.id) == []
