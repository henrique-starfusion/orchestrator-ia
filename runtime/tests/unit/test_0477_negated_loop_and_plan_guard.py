"""0.4.77 — negação e compatibilidade entre loop e tipo da task."""

from __future__ import annotations

import pytest

from orchestrator_runtime.planning.analyzer import CriteriaBuilder, Planner
from orchestrator_runtime.planning.loops import detect_loop, get_loop
from orchestrator_runtime.tasks.models import (
    CriterionKind,
    OrchestrationPlan,
    TaskAnalysis,
    TaskRecord,
)


REAL_REVIEW_PROMPT = (
    "Revisao independente da branch feature/TS-110-ambiente-odin, repositorio "
    "X, commits 76d6e7e e c7074bd. NAO e correcao de bug: e conferencia de "
    "entrega pronta. NAO reescreva a entrega; aponte arquivo e linha se achar "
    "problema. O ambiente local deixou de subir por erro de conexao e a falha "
    "aparecia no log."
)


def test_revisao_real_com_negacao_nao_cai_no_loop_bug() -> None:
    assert detect_loop(REAL_REVIEW_PROMPT) == "review"


@pytest.mark.parametrize(
    "negacao",
    [
        "nao e correcao de bug",
        "não é correção de bug",
        "nao se trata de correcao de bug",
        "isto nao e um pedido de correcao de bug",
        "this is not a bug fix",
        "nao reescreva a entrega",
    ],
)
def test_clausulas_negadas_nao_contam_como_intencao_de_bug(negacao: str) -> None:
    prompt = (
        f"Revisao independente da entrega pronta. {negacao}. "
        "Conferir se algum erro ou falha ficou no resultado."
    )
    assert detect_loop(prompt) == "review"


def test_correcao_explicita_apontada_por_revisao_continua_loop_bug() -> None:
    assert (
        detect_loop("corrigir os dois defeitos que a revisao independente apontou")
        == "bug"
    )


def test_loop_de_codigo_nao_impoe_gates_de_codigo_a_task_docs(tmp_path) -> None:
    analysis = TaskAnalysis(
        task_type="docs",
        languages=["python"],
        requirements=["Produzir o relatório solicitado"],
        loop="bug",
    )

    built = CriteriaBuilder().build(
        "Documentar o estorno PIX sem alterar codigo-fonte", analysis
    )
    assert built
    assert {criterion.kind for criterion in built}.isdisjoint(
        {CriterionKind.WORKSPACE_CHANGES, CriterionKind.TESTS_PASS}
    )

    task = TaskRecord(
        prompt="Documentar o estorno PIX sem alterar codigo-fonte",
        project_path=str(tmp_path),
        task_type="docs",
        acceptance_criteria=get_loop("bug").to_criteria(),
    )
    roles = OrchestrationPlan(
        strategy="execute_review_repair",
        planner="claude",
        executor="codex",
        validator="claude",
    )

    plan = Planner().plan(task, analysis, roles)
    kinds = {
        criterion["kind"] for criterion in plan["acceptance_criteria"]
    }
    assert "loop" not in plan
    assert kinds.isdisjoint(
        {
            CriterionKind.WORKSPACE_CHANGES.value,
            CriterionKind.TESTS_PASS.value,
        }
    )
