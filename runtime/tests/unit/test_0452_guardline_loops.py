"""0.4.52 — loops ui-probe e review portados dos prompts GuardLine."""

from __future__ import annotations

import pytest

from orchestrator_runtime.planning.analyzer import TaskAnalyzer
from orchestrator_runtime.planning.loops import LOOPS, detect_loop
from orchestrator_runtime.tasks.models import CriterionKind


def test_ui_probe_tem_contrato_completo_de_sonda_segura() -> None:
    probe = LOOPS["ui-probe"]

    assert probe.id == "ui-probe"
    assert probe.task_type == "complex_analysis"
    assert len(probe.stages) >= 4
    assert len(probe.criteria) >= 3
    assert set(probe.keywords) >= {
        "sonda",
        "probe",
        "ui",
        "playwright",
        "navegador",
        "browser",
    }
    assert all(kind == CriterionKind.EVIDENCE for _texto, kind in probe.criteria)

    etapas = " ".join(probe.stages)
    assert "~/.cache/ms-playwright" in etapas
    assert "NUNCA" in etapas
    assert "getByRole/getByLabel" in etapas
    assert "ANTES do clique" in etapas
    assert "Top 3 must-fix" in etapas


def test_review_tem_papeis_temas_e_evidencias_obrigatorias() -> None:
    review = LOOPS["review"]

    assert review.id == "review"
    assert review.task_type == "complex_analysis"
    assert len(review.stages) >= 4
    assert len(review.criteria) >= 3
    assert set(review.keywords) >= {
        "review",
        "revisão",
        "revisao",
        "adversarial",
        "deep dive",
        "caçar bugs",
        "cacar bugs",
    }
    assert {kind for _texto, kind in review.criteria} == {
        CriterionKind.EVIDENCE,
        CriterionKind.WORKSPACE_CHANGES,
    }

    etapas = " ".join(review.stages)
    for papel in ("SRE", "segurança/privacidade", "arquiteto", "júnior"):
        assert papel in etapas
    for tema in (
        "correção/races/ordenação",
        "Edge cases",
        "Pontos cegos de operação",
        "Fragilidades",
        "Melhorias",
    ):
        assert tema in etapas
    assert "sem achados porque <razão>" in etapas
    assert "file:line" in etapas
    assert "Top 5" in etapas
    assert "tabela vai NO FIM" in etapas


@pytest.mark.parametrize(
    ("prompt", "esperado"),
    [
        ("Executar sonda Playwright visual no navegador da UI", "ui-probe"),
        ("Fazer revisão adversarial e deep dive do código entregue", "review"),
    ],
)
def test_analyzer_roteia_novos_loops_por_keyword(prompt: str, esperado: str) -> None:
    analysis = TaskAnalyzer().analyze(prompt)

    assert analysis.loop == esperado
    assert analysis.task_type == "complex_analysis"


@pytest.mark.parametrize(
    "prompt",
    [
        "Ajustar o build do pacote",
        "Escrever um guide de instalação",
    ],
)
def test_ui_respeita_fronteira_de_palavra(prompt: str) -> None:
    assert detect_loop(prompt) != "ui-probe"


def test_correcao_de_erro_vence_review_adversarial() -> None:
    prompt = (
        "Fazer review adversarial e revisão profunda, mas corrigir o erro "
        "de ordenação no processamento"
    )

    assert detect_loop(prompt) == "bug"
