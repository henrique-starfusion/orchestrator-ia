"""0.4.26 — bug-031: ACs declarados no prompt vencem a inferencia generica.

Antes: prompt de auditoria read-only com AC-001..003 explicitos recebia os ACs
genericos (workspace_changes / tests_pass / docs_example em README.md). Como
`npm test` tinha falhas pre-existentes (bug-032), TODA task era reprovada por
motivo alheio ao trabalho — task ca2c5142e0ae terminou INCOMPLETE score=0.4 com
o entregavel de 489 linhas corretamente produzido.
"""

from __future__ import annotations

from orchestrator_runtime.planning.analyzer import (
    CriteriaBuilder,
    parse_declared_criteria,
)
from orchestrator_runtime.tasks.models import CriterionKind, TaskAnalysis

AUDIT_PROMPT = """AUDITORIA DE USO DA FROTA + ONBOARDING.

Analise os projetos e produza um relatorio. Nao rodar npm test nem pytest.
Documentar os achados em docs/.

CRITERIOS DE ACEITACAO:
- AC-001: criar o arquivo NOVO docs/audits/2026-07-26-fleet.md
- AC-002: cada achado com evidencia verificavel (caminho de arquivo ou linha)
- AC-003: secao final com o texto integral do bloco canonico
"""


def _analysis(task_type: str = "implementation") -> TaskAnalysis:
    return TaskAnalysis(
        task_type=task_type,
        languages=["python"],
        complexity="medium",
        requirements=[],
    )


def test_declared_criteria_win_over_generic() -> None:
    criteria = CriteriaBuilder().build(AUDIT_PROMPT, _analysis())

    assert [c.id for c in criteria] == ["AC-001", "AC-002", "AC-003"]
    # o prompt cita "npm test" e "docs/" — antes isso injetava tests_pass +
    # docs_example; agora nenhum criterio deterministico alheio sobrevive.
    assert all(c.kind == CriterionKind.EVIDENCE for c in criteria)
    assert "docs/audits/2026-07-26-fleet.md" in criteria[0].description


def test_tests_pass_still_inferred_when_user_asks_for_it() -> None:
    prompt = "Implementar X.\n- AC-001: a suite de testes passa com exit code 0\n"
    criteria = parse_declared_criteria(prompt)

    assert len(criteria) == 1
    assert criteria[0].kind == CriterionKind.TESTS_PASS


def test_no_declared_criteria_keeps_legacy_inference() -> None:
    prompt = "Implementar modulo com testes automatizados e atualizar o README."
    criteria = CriteriaBuilder().build(prompt, _analysis())

    assert criteria, "sem ACs declarados o builder legado deve continuar agindo"
    kinds = {c.kind for c in criteria}
    assert CriterionKind.TESTS_PASS in kinds
    assert CriterionKind.DOCS_EXAMPLE in kinds


def test_vague_and_short_declarations_are_ignored() -> None:
    prompt = "- AC-001: codigo bom\n- AC-002: ok\n- AC-003: entregar relatorio completo\n"
    criteria = parse_declared_criteria(prompt)

    assert [c.id for c in criteria] == ["AC-003"]


def test_duplicate_ids_collapse() -> None:
    prompt = (
        "- AC-001: entregar o relatorio final\n"
        "- AC-001: entregar o relatorio final de novo\n"
    )
    assert len(parse_declared_criteria(prompt)) == 1
