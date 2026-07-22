"""Análise, critérios e planejamento determinísticos."""

from __future__ import annotations

import re
from typing import Iterable

from orchestrator_runtime.tasks.models import (
    AcceptanceCriterion,
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


class TaskAnalyzer:
    def analyze(self, prompt: str, project_files: list[str] | None = None) -> TaskAnalysis:
        languages = detect_languages(prompt, project_files)
        lowered = prompt.lower()
        task_type = "implementation"
        if any(w in lowered for w in ("doc", "readme", "changelog")):
            task_type = "docs"
        elif any(w in lowered for w in ("arquitet", "architecture", "design")):
            task_type = "architecture"
        elif any(w in lowered for w in ("security", "segurança", "seguranca")):
            task_type = "security_review"
        elif any(w in lowered for w in ("analis", "diagnos", "investig")):
            task_type = "complex_analysis"

        complexity = "medium"
        if len(prompt) > 400 or task_type in {"architecture", "complex_analysis"}:
            complexity = "high"
        elif len(prompt) < 80 and task_type == "docs":
            complexity = "low"

        risk = "medium"
        if task_type == "security_review":
            risk = "high"

        requirements = [
            s.strip()
            for s in re.split(r"[.\n;]", prompt)
            if len(s.strip()) > 12
        ][:8]
        if not requirements:
            requirements = [prompt.strip()]

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


def wants_soma_module(prompt: str) -> bool:
    """True só para intent de módulo/função soma|sum — não substring em resume/summary."""
    return bool(_SOMA_MODULE_RE.search(prompt or ""))


class CriteriaBuilder:
    def build(self, prompt: str, analysis: TaskAnalysis) -> list[AcceptanceCriterion]:
        criteria: list[AcceptanceCriterion] = []
        idx = 1
        lowered = prompt.lower()

        def add(desc: str, required: bool = True) -> None:
            nonlocal idx
            if desc.strip().lower() in VAGUE:
                return
            criteria.append(
                AcceptanceCriterion(
                    id=f"AC-{idx:03d}",
                    description=desc,
                    required=required,
                )
            )
            idx += 1

        if wants_soma_module(prompt):
            add("Existe função soma(a, b) retornando a soma numérica")
            add("Há teste automatizado cobrindo soma(2,3)==5")
        if re.search(r"\b(test|pytest|teste|testes)\b", lowered):
            add("Suite de testes determinística passa com exit code 0")
        if re.search(r"\b(docs?|document\w*|readme)\b", lowered):
            add("README ou docs descrevem uso com exemplo executável")
        if not criteria:
            add("Alterações solicitadas no prompt estão presentes no workspace")
            add("Testes determinísticos relevantes passam ou estão justificados")
            add("Documentação afetada foi revisada e atualizada se necessário")
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
            "acceptance_criteria": [c.model_dump() for c in task.acceptance_criteria],
            "maximum_iterations": roles.maximum_iterations,
            "fallbacks": roles.fallbacks,
        }
