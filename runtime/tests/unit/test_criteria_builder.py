"""Critérios de aceitação: sem falso positivo em resume/summary."""

from __future__ import annotations

from orchestrator_runtime.planning.analyzer import (
    CriteriaBuilder,
    TaskAnalyzer,
    wants_soma_module,
)


def test_wants_soma_module_intent():
    assert wants_soma_module("Crie um modulo Python com funcao soma")
    assert wants_soma_module("implement def soma(a, b)")
    assert not wants_soma_module(
        "Análise completa com resume/cancel e documentação"
    )
    assert not wants_soma_module("write a summary of the architecture")
    assert not wants_soma_module("assumptions and resume the task")


def test_criteria_builder_skips_resume_false_positive():
    analysis = TaskAnalyzer().analyze(
        "Auditoria do runtime: resume/cancel, documentação e testes"
    )
    criteria = CriteriaBuilder().build(
        "Auditoria do runtime: resume/cancel, documentação e testes", analysis
    )
    descs = " ".join(c.description for c in criteria)
    assert "função soma" not in descs
    assert "soma(2,3)" not in descs


def test_criteria_builder_keeps_soma_demo():
    prompt = "Crie um modulo Python com funcao soma, testes e documentacao"
    analysis = TaskAnalyzer().analyze(prompt)
    criteria = CriteriaBuilder().build(prompt, analysis)
    descs = [c.description for c in criteria]
    assert any("soma(a, b)" in d for d in descs)
