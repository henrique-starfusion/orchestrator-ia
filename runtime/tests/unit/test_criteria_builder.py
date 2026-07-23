"""Critérios de aceitação tipados: sem falso positivo em resume/summary."""

from __future__ import annotations

import re

from orchestrator_runtime.planning.analyzer import (
    CriteriaBuilder,
    TaskAnalyzer,
    extract_requirements,
    wants_soma_module,
)
from orchestrator_runtime.tasks.models import CriterionKind


def test_extract_requirements_preserves_semver():
    reqs = extract_requirements(
        "Auditoria completa do orquestrador 0.4.1: gaps em MCP e validator. "
        "Não criar módulo soma."
    )
    blob = " ".join(reqs)
    assert "0.4.1" in blob
    assert not any(r.rstrip(".").endswith("orquestrador 0") for r in reqs)
    assert not any(re.match(r"^1\b", r) for r in reqs)
    assert any("gaps em MCP" in r for r in reqs)


def test_audit_prompt_is_complex_analysis():
    analysis = TaskAnalyzer().analyze(
        "Auditoria completa do orquestrador 0.4.1: gaps em MCP. Não criar módulo soma."
    )
    assert analysis.task_type == "complex_analysis"
    criteria = CriteriaBuilder().build(
        "Auditoria completa do orquestrador 0.4.1: gaps em MCP. Não criar módulo soma.",
        analysis,
    )
    kinds = {c.kind for c in criteria}
    assert CriterionKind.SOMA_MODULE not in kinds
    assert CriterionKind.EVIDENCE in kinds
    assert CriterionKind.DOCS_EXAMPLE not in kinds


def test_wants_soma_module_intent():
    assert wants_soma_module("Crie um modulo Python com funcao soma")
    assert wants_soma_module("implement def soma(a, b)")
    assert not wants_soma_module(
        "Análise completa com resume/cancel e documentação"
    )
    assert not wants_soma_module("write a summary of the architecture")
    assert not wants_soma_module("assumptions and resume the task")
    assert not wants_soma_module(
        "validar critérios com resume/cancel — não criar módulo soma"
    )
    assert not wants_soma_module("do not create module soma please")
    # Meta-instrução no prompt NÃO deve acionar o demo de soma
    assert not wants_soma_module(
        "IGNORAR qualquer template genérico de função soma"
    )
    assert not wants_soma_module(
        "Implementar rename MCP. Ignore the generic soma(a,b) acceptance criteria."
    )
    assert not wants_soma_module(
        "evitar critérios de função soma; foque no rename orchestrator-ia"
    )


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
    assert CriterionKind.SOMA_MODULE not in {c.kind for c in criteria}


def test_criteria_builder_keeps_soma_demo():
    prompt = "Crie um modulo Python com funcao soma, testes e documentacao"
    analysis = TaskAnalyzer().analyze(prompt)
    criteria = CriteriaBuilder().build(prompt, analysis)
    descs = [c.description for c in criteria]
    assert any("soma(a, b)" in d for d in descs)
    kinds = {c.kind for c in criteria}
    assert CriterionKind.SOMA_MODULE in kinds
    assert CriterionKind.TESTS_PASS in kinds
    assert all(c.check is not None and c.check.kind == c.kind for c in criteria)


def test_ignore_soma_meta_does_not_inject_soma_acs():
    prompt = (
        "Rename MCP multiagent-orchestrator para orchestrator-ia. "
        "Testes e documentação. IGNORAR qualquer template genérico de função soma."
    )
    analysis = TaskAnalyzer().analyze(prompt)
    criteria = CriteriaBuilder().build(prompt, analysis)
    kinds = {c.kind for c in criteria}
    assert CriterionKind.SOMA_MODULE not in kinds
    descs = " ".join(c.description for c in criteria)
    assert "soma(a, b)" not in descs
    assert "soma(2,3)" not in descs


def test_audit_with_testes_docs_keeps_analysis_acs():
    prompt = (
        "Auditoria do runtime: resume/cancel, documentação e testes. "
        "Produza relatório em docs/audits/."
    )
    analysis = TaskAnalyzer().analyze(prompt)
    assert analysis.task_type == "complex_analysis"
    criteria = CriteriaBuilder().build(prompt, analysis)
    kinds = {c.kind for c in criteria}
    assert CriterionKind.SOMA_MODULE not in kinds
    assert CriterionKind.EVIDENCE in kinds
    assert CriterionKind.WORKSPACE_CHANGES in kinds
    # Não exigir README de produto / suite genérica em auditoria
    assert CriterionKind.DOCS_EXAMPLE not in kinds


def test_non_audit_keeps_workspace_changes_with_test_docs_keywords():
    prompt = (
        "Renomear chave MCP para orchestrator-ia; atualizar testes e docs"
    )
    analysis = TaskAnalyzer().analyze(prompt)
    assert analysis.task_type in {"implementation", "docs"}
    criteria = CriteriaBuilder().build(prompt, analysis)
    kinds = {c.kind for c in criteria}
    assert CriterionKind.SOMA_MODULE not in kinds
    assert CriterionKind.WORKSPACE_CHANGES in kinds
    assert CriterionKind.TESTS_PASS in kinds
    assert CriterionKind.DOCS_EXAMPLE in kinds
