"""0.4.70 — o teto da task cabe o percurso que o runtime pretende fazer (bug-104).

Os proprios numeros do runtime se contradiziam. Uma volta com correcao soma:

    planner 900 + executor 2400 + tester 600 + validator 1200
                 + corrector 2400 + validator 1200 = 8700s

contra um `maximum_duration_seconds` de 3600. Toda task que realmente usava o
orcamento dos papeis morria no meio — sempre antes do validator, porque o
validator e o ULTIMO a ser chamado. Nao era azar, era aritmetica: quanto maior a
task, mais certa a morte.

Como aparecia para o dono (printbee, task b259e8f0c168):

    FAILED — Orcamento de tempo insuficiente para validator (timeout_s=0)

Trabalho possivelmente pronto, reprovado por relogio, com texto de falha de
merito. O dono do printbee teve que subir o teto para 10800 na mao.

Tres defesas, da raiz para a borda:
  1. piso derivado dos tetos dos papeis — o teto nunca fica abaixo do percurso;
  2. reserva do veredito — executor/corrector nao levam o orcamento inteiro;
  3. degradacao honesta — sem orcamento, o veredito deterministico assume e o
     resultado DIZ que ninguem julgou o merito, em vez de estourar.
"""

from __future__ import annotations

import json
from pathlib import Path

from orchestrator_runtime.config import RuntimeLimits, load_config
from orchestrator_runtime.execution.timeouts import (
    MIN_AGENT_TIMEOUT_S,
    VERDICT_RESERVE_S,
    minimum_task_budget_s,
    resolve_agent_timeout,
)
from orchestrator_runtime.tasks.service import build_service


# --------------------------------------------------------------------------
# 1. o piso
# --------------------------------------------------------------------------


def test_piso_e_a_conta_que_matou_o_pb69() -> None:
    assert minimum_task_budget_s() == 8700


def test_piso_acompanha_os_tetos_configurados() -> None:
    """Piso derivado, nao constante: mexeu no papel, o piso mexe junto."""
    piso = minimum_task_budget_s({"executor": 1200, "corrector": 1200})
    assert piso == 900 + 1200 + 600 + 1200 + 1200 + 1200


def test_teto_padrao_deixa_de_contradizer_os_papeis() -> None:
    limits = RuntimeLimits()
    assert limits.maximum_duration_seconds == 8700
    assert limits.duration_floor_raised_from == 3600, (
        "o valor pedido tem que ficar registrado — o dono precisa saber que o "
        "numero dele nao valia"
    )


def test_teto_abaixo_do_piso_sobe() -> None:
    limits = RuntimeLimits(maximum_duration_seconds=600)
    assert limits.maximum_duration_seconds == 8700
    assert limits.duration_floor_raised_from == 600


def test_teto_acima_do_piso_e_respeitado() -> None:
    """Piso, nao teto: quem pediu mais continua com mais."""
    limits = RuntimeLimits(maximum_duration_seconds=20000)
    assert limits.maximum_duration_seconds == 20000
    assert limits.duration_floor_raised_from is None


def test_policies_json_com_3600_sobe_no_load(project: Path) -> None:
    """O caminho real: projeto com o valor antigo no disco (toda a frota tinha)."""
    policies = project / ".orchestrator" / "config" / "policies.json"
    dados = json.loads(policies.read_text(encoding="utf-8"))
    dados["maximum_duration_seconds"] = 3600
    policies.write_text(json.dumps(dados), encoding="utf-8")

    config = load_config(project, fake_agents=True)

    assert config.limits.maximum_duration_seconds == 8700
    assert config.limits.duration_floor_raised_from == 3600


# --------------------------------------------------------------------------
# 2. a reserva do veredito
# --------------------------------------------------------------------------


def test_executor_nao_leva_o_orcamento_inteiro() -> None:
    """CONTRATO NOVO (bug-104): antes o executor recebia `remaining` cheio.

    Com 2000s restantes ele pegava 2000 e o validator ficava com 0 — que era
    exatamente o `timeout_s=0` do PB-69. Agora para em 1400 e sobram os 600 da
    reserva para o veredito.
    """
    assert resolve_agent_timeout("executor", remaining_s=2000) == 2000 - VERDICT_RESERVE_S


def test_corrector_tambem_reserva() -> None:
    """Corrector gasta tanto quanto o executor e roda ainda mais perto do fim."""
    assert resolve_agent_timeout("corrector", remaining_s=2000) == 2000 - VERDICT_RESERVE_S


def test_reserva_nao_empurra_o_executor_abaixo_do_piso() -> None:
    """Reserva limita teto; nao inventa orcamento onde nao ha."""
    assert resolve_agent_timeout("executor", remaining_s=300) == MIN_AGENT_TIMEOUT_S


def test_teto_do_papel_ainda_manda_quando_sobra_orcamento() -> None:
    """Com folga, quem limita e o papel — a reserva nao encurta o trabalho."""
    assert resolve_agent_timeout("executor", remaining_s=8700) == 2400


def test_validator_nao_reserva_de_si_mesmo() -> None:
    assert resolve_agent_timeout("validator", remaining_s=600) == 600


def test_planner_e_tester_ficam_intactos() -> None:
    assert resolve_agent_timeout("planner", remaining_s=1000) == 900
    assert resolve_agent_timeout("tester", remaining_s=1000) == 600


def test_reserva_garante_que_o_veredito_cabe() -> None:
    """A propriedade que importa, encadeada como no loop real."""
    restante = 3000
    gasto_executor = resolve_agent_timeout("executor", remaining_s=restante)
    sobra = restante - gasto_executor
    assert resolve_agent_timeout("validator", remaining_s=sobra) >= MIN_AGENT_TIMEOUT_S


# --------------------------------------------------------------------------
# 3. a degradacao honesta
# --------------------------------------------------------------------------


def _com_rodada(project: Path, payload: dict):
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("task que ficou sem relogio")
    svc.repo.add_validation_round(
        task_id=task.id,
        iteration=1,
        status=payload.get("status", "rejected"),
        score=payload.get("score", 0.0),
        payload_json=json.dumps(payload),
    )
    return svc, task


def test_validator_sem_orcamento_vira_degradacao_e_nao_excecao(project: Path) -> None:
    svc, task = _com_rodada(
        project,
        {
            "status": "rejected",
            "score": 0.5,
            "validator_infra_failure": True,
            "validation_skipped": "budget",
        },
    )

    registro = svc.degradations(task.id)
    validacao = [d for d in registro if d["kind"] == "validation_not_independent"]
    assert validacao, "degradacao aceita tem que aparecer no resultado"
    assert "orçamento" in validacao[0]["detail"]
    assert "maximum_duration_seconds" in validacao[0]["action"], (
        "remedio errado manda o dono cacar um agente quebrado que nao existe"
    )


def test_falha_de_infra_mantem_o_remedio_antigo(project: Path) -> None:
    """Mesma degradacao, causa diferente: aqui o agente falhou de verdade."""
    svc, task = _com_rodada(
        project,
        {"status": "approved", "score": 1.0, "validator_infra_failure": True},
    )

    validacao = [
        d for d in svc.degradations(task.id) if d["kind"] == "validation_not_independent"
    ]
    assert validacao
    assert "validator vivo" in validacao[0]["action"]


def test_validacao_normal_nao_gera_degradacao(project: Path) -> None:
    svc, task = _com_rodada(project, {"status": "approved", "score": 1.0})

    assert not [
        d for d in svc.degradations(task.id) if d["kind"] == "validation_not_independent"
    ]


# --------------------------------------------------------------------------
# 4. o reaper para de mentir sobre o relogio e sobre o que se perdeu (bug-105)
# --------------------------------------------------------------------------


def test_mensagem_do_reaper_nao_afirma_tempo_de_fase() -> None:
    """`total_s` conta desde `created_at`, nao desde a entrada no estado.

    trustsafe `529cc0476c4e`: a mensagem dizia "VALIDATING ha 4525s" — 4525s era
    a IDADE DA TASK; em VALIDATING ela estava ha 2963s. Terceira vez que uma
    mensagem deste reaper aponta o relogio errado.
    """
    import inspect

    import orchestrator_runtime.tasks.service as svc_mod

    fonte = inspect.getsource(svc_mod)
    assert "criada há " in fonte
    assert '{task.status.value} há {int(total_s)}s' not in fonte


def test_veredito_aprovado_perdido_aparece_no_cancelamento(project: Path) -> None:
    svc, task = _com_rodada(project, {"status": "approved", "score": 1.0})

    nota = svc._verdict_lost_note(task.id)

    assert "APROVADO" in nota and "1.0" in str(nota)


def test_veredito_rejeitado_nao_vira_alarme(project: Path) -> None:
    """So avisa o que o dono perderia: rejeicao nao e trabalho aprovado."""
    svc, task = _com_rodada(project, {"status": "rejected", "score": 0.4})

    assert svc._verdict_lost_note(task.id) == ""


def test_sem_rodada_de_validacao_nao_inventa_nota(project: Path) -> None:
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("nunca chegou a validar")

    assert svc._verdict_lost_note(task.id) == ""


def test_loop_nao_chama_validator_sem_orcamento() -> None:
    """O guard tem que existir ANTES do `_run_agent` do validator.

    Sem ele o `_run_agent` levanta RuntimeError e a task termina FAILED — foi
    literalmente a mensagem que o dono viu no PB-69.
    """
    import inspect

    import orchestrator_runtime.tasks.service as svc_mod

    fonte = inspect.getsource(svc_mod)
    guard = fonte.index('if self._remaining_duration_s(task) < MIN_AGENT_TIMEOUT_S:')
    chamada = fonte.index('val_agent, "validator", val_prompt, task')
    assert guard < chamada
