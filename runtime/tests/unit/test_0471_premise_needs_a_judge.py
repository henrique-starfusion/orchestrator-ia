"""0.4.71 — `premise_mismatch` deixa de fabricar sucesso perfeito (bug-107).

O executor pode declarar que a premissa da tarefa esta errada (0.4.53) e isso e
um outcome legitimo: nao ha o que entregar. Mas era o EXECUTOR declarando o
proprio resultado, sem validator nenhum, com `require_independent_validation`
ligado em toda a frota — e o runtime gravava:

    task.last_score = 1.0
    _persist_episode(success=True)
    -> COMPLETED

Dois problemas medidos no printbee:

1. O 1.0 era FABRICADO. Ninguem validou nada, e o numero chega ao dono
   (`task status`, `orchestrator_result`, learnings) e entra em
   `strategy_performance`. A tabela do printbee virou
   `19 runs / 19 successes / 0 failures / avg_score 0.9968` num projeto com 4
   CANCELLED e 1 FAILED.

2. A alegacao era honrada DEPOIS de uma rejeicao gravada. A `efeaee6fd306`
   fechou COMPLETED com `rejected score=0.1` e issues bloqueantes em disco: o
   escape hatch lavou o veredito do validator.

Tres COMPLETED do printbee eram na verdade este caminho (`efeaee6fd306`,
`d9f8383c7760`, `06d74af53ee0`).
"""

from __future__ import annotations

import json
from pathlib import Path

from orchestrator_runtime.tasks.service import build_service


def _com_rodada(svc, task_id: str, status: str, score: float) -> None:
    svc.repo.add_validation_round(
        task_id=task_id,
        iteration=1,
        status=status,
        score=score,
        payload_json=json.dumps({"status": status, "score": score}),
    )


def test_rejeicao_gravada_e_detectada(project: Path) -> None:
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("x")
    _com_rodada(svc, task.id, "rejected", 0.1)

    assert svc._prior_rejection(task.id) is not None


def test_aprovacao_nao_conta_como_rejeicao(project: Path) -> None:
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("x")
    _com_rodada(svc, task.id, "approved", 1.0)

    assert svc._prior_rejection(task.id) is None


def test_sem_rodada_nao_ha_rejeicao(project: Path) -> None:
    """Primeira iteracao: alegacao de premissa nao contradiz nada."""
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("x")

    assert svc._prior_rejection(task.id) is None


def test_premissa_declarada_vira_degradacao(project: Path) -> None:
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("task que o executor recusou por premissa")
    fresh = svc.get(task.id)
    fresh.analysis = {
        "premise_mismatch": "o arquivo citado no prompt nao existe neste repo",
        "premise_verified": False,
    }
    svc.repo.save(fresh)

    degradacao = [
        d for d in svc.degradations(task.id) if d["kind"] == "premise_declared_unverified"
    ]
    assert degradacao, "COMPLETED sem juiz tem que aparecer no resultado"
    assert "nada foi entregue" in degradacao[0]["detail"]
    assert "EXECUTOR" in degradacao[0]["impact"]


def test_premissa_verificada_nao_degrada(project: Path) -> None:
    """Deixa a porta aberta para quando um juiz confirmar a alegacao."""
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("x")
    fresh = svc.get(task.id)
    fresh.analysis = {"premise_mismatch": "confirmado", "premise_verified": True}
    svc.repo.save(fresh)

    assert not [
        d for d in svc.degradations(task.id) if d["kind"] == "premise_declared_unverified"
    ]


def test_task_normal_nao_ganha_a_degradacao(project: Path) -> None:
    svc = build_service(project, fake_agents=True)
    task = svc.create_task("task comum")

    assert not [
        d for d in svc.degradations(task.id) if d["kind"] == "premise_declared_unverified"
    ]


def test_alegacao_apos_rejeicao_nao_fecha_como_sucesso(project: Path) -> None:
    """Laundering de veredito, ponta a ponta.

    Reproduz a `efeaee6fd306`: o validator rejeita com issues bloqueantes, a
    iteracao 2 comeca, e o executor alega premissa incorreta. Antes isso fechava
    COMPLETED com score 1.0 — a alegacao apagava o veredito em disco.
    """
    import asyncio

    from orchestrator_runtime.config import load_config
    from orchestrator_runtime.tasks.service import TaskService
    from orchestrator_runtime.tasks.state_machine import TaskState
    from test_0453_premise_mismatch import PremiseMismatchExecutor

    svc = TaskService(load_config(project, fake_agents=True), verbose=False)
    for nome in ("claude", "codex", "opencode"):
        svc.registry._adapters[nome] = PremiseMismatchExecutor(nome, project)

    task = svc.create_task("tarefa que ja foi rejeitada uma vez", max_iterations=3)
    _com_rodada(svc, task.id, "rejected", 0.1)

    done = asyncio.run(svc.run_task(task.id))

    assert done.status == TaskState.INCOMPLETE, (
        "alegacao do executor apagou uma rejeicao gravada"
    )
    assert done.last_score is None
    assert "contradiz o veredito" in (done.error or "")


def test_primeira_passada_continua_fechando_como_antes(project: Path) -> None:
    """Sem rejeicao em disco, o outcome legitimo da 0.4.53 segue valendo."""
    import asyncio

    from orchestrator_runtime.config import load_config
    from orchestrator_runtime.tasks.service import TaskService
    from orchestrator_runtime.tasks.state_machine import TaskState
    from test_0453_premise_mismatch import PremiseMismatchExecutor

    svc = TaskService(load_config(project, fake_agents=True), verbose=False)
    for nome in ("claude", "codex", "opencode"):
        svc.registry._adapters[nome] = PremiseMismatchExecutor(nome, project)

    task = svc.create_task("tarefa com premissa errada de saida", max_iterations=3)
    done = asyncio.run(svc.run_task(task.id))

    assert done.status == TaskState.COMPLETED
    assert done.last_score is None, "sucesso sem juiz nao carrega score inventado"
    assert [
        d for d in svc.degradations(task.id) if d["kind"] == "premise_declared_unverified"
    ], "o dono precisa ver que ninguem julgou"
