"""0.4.70 — falha do SERVICO do provedor deixa de virar reinstalacao (bug-106).

Os tres `opencode` da frota em 09/08 (printbee 1, trustsafe 2) sairam `exit=1`
em ~2s com 165 bytes:

    Error: {"name":"UnknownError","data":{"message":"Unexpected server error.
    Check server logs for details.","ref":"err_da9ff4ff"}}

CLI intacto, credencial intacta: quem falhou foi o servidor do outro lado. Sem
uma categoria para isso, a regra do fast-fail mudo (stdout vazio + duracao curta)
classificava `install`, e o auto-reparo da 0.4.63 gastou uma REINSTALACAO
COMPLETA — que terminou `repair_ok: true` — para o agente falhar igual na
chamada seguinte.

O remedio de `service` e nao ter remedio local: outro agente assume.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from orchestrator_runtime.agents.health import classify_agent_failure
from orchestrator_runtime.tasks.service import build_service


OPENCODE_STDERR = (
    'Error: {   "name": "UnknownError",   "data": {     "message": '
    '"Unexpected server error. Check server logs for details.",     '
    '"ref": "err_da9ff4ff"   } }'
)


def _run(stdout: str = "", stderr: str = "", *, duration_s: float = 2.0, status="failed"):
    return SimpleNamespace(
        stdout=stdout, stderr=stderr, duration_s=duration_s, status=status, timed_out=False
    )


def test_erro_de_servidor_do_opencode_nao_e_install() -> None:
    """A regressao exata: 2s, stdout vazio, erro de servidor."""
    assert classify_agent_failure(_run(stderr=OPENCODE_STDERR)) == "service"


def test_service_vence_o_fast_fail_mudo() -> None:
    """Sem o marcador, este mesmo run cairia em `install` — e caia."""
    assert classify_agent_failure(_run(stderr="morreu calado")) == "install"


def test_service_vence_auth_e_install_na_mesma_saida() -> None:
    """CLI que loga 'npm error' ao morrer por 503 nao deve ser reinstalado."""
    misto = "npm error\nunauthorized\n503 Service Unavailable"
    assert classify_agent_failure(_run(stderr=misto)) == "service"


def test_marcador_de_servico_em_saida_grande_nao_conta() -> None:
    """bug-097 continua valendo: saida grande e conteudo, nao diagnostico."""
    grande = "x" * 9000 + "unexpected server error"
    assert classify_agent_failure(_run(stdout=grande, duration_s=600.0)) is None


def test_timeout_continua_fora_da_classificacao() -> None:
    r = _run(stderr=OPENCODE_STDERR)
    r.timed_out = True
    assert classify_agent_failure(r) is None


def test_sucesso_nunca_classifica() -> None:
    assert classify_agent_failure(_run(stderr=OPENCODE_STDERR, status="completed")) is None


def test_service_vira_degradacao_com_acao_honesta(project: Path) -> None:
    """Nao ha o que digitar — e a degradacao tem que dizer isso."""
    from orchestrator_runtime.events import EventType, RuntimeEvent

    svc = build_service(project, fake_agents=True)
    task = svc.create_task("task que pegou provedor fora do ar")
    svc.repo.add_event(
        RuntimeEvent(
            task_id=task.id,
            type=EventType.AGENT_REPAIR,
            role="validator",
            agent="opencode",
            data={"failure_kind": "service", "summary": "provedor respondeu erro"},
        )
    )

    paradas = svc.service_outages(task.id)
    assert [p["agent"] for p in paradas] == ["opencode"]

    degradacao = [d for d in svc.degradations(task.id) if d["kind"] == "agent_service_down"]
    assert degradacao, "degradacao aceita tem que aparecer no resultado"
    assert "instalar" in degradacao[0]["action"] and "logar" in degradacao[0]["action"]


def test_service_nao_polui_os_blockers_de_credencial(project: Path) -> None:
    """Login num CLI ja autenticado e a pior orientacao possivel."""
    from orchestrator_runtime.events import EventType, RuntimeEvent

    svc = build_service(project, fake_agents=True)
    task = svc.create_task("x")
    svc.repo.add_event(
        RuntimeEvent(
            task_id=task.id,
            type=EventType.AGENT_REPAIR,
            role="validator",
            agent="opencode",
            data={"failure_kind": "service"},
        )
    )

    assert svc.auth_blockers(task.id) == []


def test_opencode_deixa_de_ganhar_de_agente_desconhecido() -> None:
    """0/3 em producao depois de reinstalado com sucesso: o prior estava errado."""
    from orchestrator_runtime.planning.analyzer import TaskAnalysis
    from orchestrator_runtime.routing.manager import CapabilityScorer

    scorer = CapabilityScorer()
    analise = TaskAnalysis(task_type="implementation")
    assert scorer.score("opencode", "validator", analise) < scorer.score(
        "agente-desconhecido", "validator", analise
    )
