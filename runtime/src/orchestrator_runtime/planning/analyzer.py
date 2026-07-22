"""Análise, critérios e planejamento determinísticos."""

from __future__ import annotations

import re
from typing import Any, Iterable

from orchestrator_runtime.tasks.models import (
    AcceptanceCriterion,
    CriterionCheck,
    CriterionKind,
    OrchestrationPlan,
    TaskAnalysis,
    TaskRecord,
)

VAGUE = {
    "código bom",
    "codigo bom",
    "solução adequada",
    "solucao adequada",
    "funciona corretamente",
}


def detect_languages(prompt: str, project_files: Iterable[str] | None = None) -> list[str]:
    text = prompt.lower()
    langs = []
    mapping = {
        "python": ["python", "pytest", "pyproject", ".py"],
        "typescript": ["typescript", "tsx", "npm", "package.json"],
        "javascript": ["javascript", "node"],
        "go": ["golang", " go ", "go.mod"],
        "rust": ["rust", "cargo"],
        "csharp": ["c#", "dotnet", ".csproj"],
    }
    blob = text + " " + " ".join(project_files or []).lower()
    for lang, keys in mapping.items():
        if any(k in blob for k in keys):
            langs.append(lang)
    return langs or ["python"]


def extract_requirements(prompt: str) -> list[str]:
    """Separa requisitos sem partir versões semver (ex.: 0.4.1)."""
    parts = re.split(r"(?<!\d)\.(?!\d)|\n+|;+", prompt or "")
    requirements = [s.strip() for s in parts if len(s.strip()) > 12][:8]
    return requirements or [prompt.strip()]


class TaskAnalyzer:
    def analyze(self, prompt: str, project_files: list[str] | None = None) -> TaskAnalysis:
        languages = detect_languages(prompt, project_files)
        lowered = prompt.lower()
        task_type = "implementation"
        # Ordem: auditoria/análise antes de "doc" (substring em "documentação").
        if any(w in lowered for w in ("security", "segurança", "seguranca")):
            task_type = "security_review"
        elif any(w in lowered for w in ("arquitet", "architecture", "design")):
            task_type = "architecture"
        elif any(
            w in lowered
            for w in ("analis", "diagnos", "investig", "auditor", "audit", "gap")
        ):
            task_type = "complex_analysis"
        elif any(w in lowered for w in ("doc", "readme", "changelog")):
            task_type = "docs"

        complexity = "medium"
        if len(prompt) > 400 or task_type in {"architecture", "complex_analysis"}:
            complexity = "high"
        elif len(prompt) < 80 and task_type == "docs":
            complexity = "low"

        risk = "medium"
        if task_type == "security_review":
            risk = "high"

        requirements = extract_requirements(prompt)

        return TaskAnalysis(
            task_type=task_type,
            languages=languages,
            risk=risk,
            complexity=complexity,
            requirements=requirements,
            acceptance_criteria=[],
            summary=prompt.strip()[:240],
        )


_SOMA_MODULE_RE = re.compile(
    r"(?:"
    r"\b(?:fun[cç][aã]o|function|m[oó]dulo|module|def)\s+soma\b"
    r"|\bsoma\s*\(\s*[a-z_]"
    r"|\b(?:function|module|def)\s+sum\b"
    r"|\bsum\s*\(\s*[a-z_]"
    r")",
    re.IGNORECASE,
)

# Remove cláusulas negadas ("não criar módulo soma") antes do match positivo
_NEGATED_CLAUSE_RE = re.compile(
    r"\b(n[aã]o|not|never|nunca|sem)\b[^.!?;:\n—–-]{0,100}",
    re.IGNORECASE,
)


def wants_soma_module(prompt: str) -> bool:
    """True só para intent positivo de módulo/função soma|sum.

    Ignora substring em resume/summary e menções sob negação
    (ex.: "não criar módulo soma").
    """
    cleaned = _NEGATED_CLAUSE_RE.sub(" ", prompt or "")
    return bool(_SOMA_MODULE_RE.search(cleaned))


class CriteriaBuilder:
    def build(self, prompt: str, analysis: TaskAnalysis) -> list[AcceptanceCriterion]:
        criteria: list[AcceptanceCriterion] = []
        idx = 1
        lowered = prompt.lower()

        def add(
            desc: str,
            kind: CriterionKind,
            *,
            required: bool = True,
            params: dict[str, Any] | None = None,
        ) -> None:
            nonlocal idx
            if desc.strip().lower() in VAGUE:
                return
            criteria.append(
                AcceptanceCriterion(
                    id=f"AC-{idx:03d}",
                    description=desc,
                    kind=kind,
                    check=CriterionCheck(kind=kind, params=params or {}),
                    required=required,
                )
            )
            idx += 1

        if wants_soma_module(prompt):
            add(
                "Existe função soma(a, b) retornando a soma numérica",
                CriterionKind.SOMA_MODULE,
                params={"path": "soma/core.py", "symbol": "soma"},
            )
            add(
                "Há teste automatizado cobrindo soma(2,3)==5",
                CriterionKind.TESTS_PASS,
                params={"mention": "soma"},
            )
        if re.search(r"\b(test|pytest|teste|testes)\b", lowered):
            add(
                "Suite de testes determinística passa com exit code 0",
                CriterionKind.TESTS_PASS,
            )
        if re.search(r"\b(docs?|document\w*|readme)\b", lowered):
            params: dict[str, Any] = {"path": "README.md"}
            if wants_soma_module(prompt):
                params["must_contain"] = ["soma"]
            add(
                "README ou docs descrevem uso com exemplo executável",
                CriterionKind.DOCS_EXAMPLE,
                params=params,
            )
        if not criteria:
            if analysis.task_type in {
                "complex_analysis",
                "security_review",
                "architecture",
            }:
                # Auditorias/reviews: não exigir README de produto nem suite de testes
                add(
                    "Entregável da análise presente no workspace (relatório/docs)",
                    CriterionKind.WORKSPACE_CHANGES,
                )
                add(
                    "Achados com evidência verificável no workspace",
                    CriterionKind.EVIDENCE,
                )
                add(
                    "Recomendações priorizadas documentadas",
                    CriterionKind.EVIDENCE,
                )
            else:
                add(
                    "Alterações solicitadas no prompt estão presentes no workspace",
                    CriterionKind.WORKSPACE_CHANGES,
                )
                add(
                    "Testes determinísticos relevantes passam ou estão justificados",
                    CriterionKind.TESTS_PASS,
                )
                add(
                    "Documentação afetada foi revisada e atualizada se necessário",
                    CriterionKind.DOCS_EXAMPLE,
                    params={"path": "README.md"},
                )
        return criteria


class Planner:
    def plan(
        self, task: TaskRecord, analysis: TaskAnalysis, roles: OrchestrationPlan
    ) -> dict:
        return {
            "strategy": roles.strategy,
            "steps": [
                {"role": "planner", "agent": roles.planner, "action": "refine_plan"},
                {"role": "executor", "agent": roles.executor, "action": "implement"},
                {"role": "tester", "agent": "runtime", "action": "run_tests"},
                {"role": "validator", "agent": roles.validator, "action": "validate"},
                {"role": "documentation", "agent": "runtime", "action": "update_docs"},
            ],
            "acceptance_criteria": [
                c.model_dump(mode="json") for c in task.acceptance_criteria
            ],
            "maximum_iterations": roles.maximum_iterations,
            "fallbacks": roles.fallbacks,
        }
