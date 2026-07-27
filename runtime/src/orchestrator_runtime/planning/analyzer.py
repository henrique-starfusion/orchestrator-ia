"""Análise, critérios e planejamento determinísticos."""

from __future__ import annotations

import re
from typing import Any, Iterable

from orchestrator_runtime.planning.loops import detect_loop, get_loop
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


_IMPLEMENTATION_INTENT = (
    "implement",
    "implemente",
    "implementar",
    "criar",
    "crie",
    "corrig",
    "conserte",
    "mudar",
    "mude",
    "mudanç",
    "mudanc",
    "alterar",
    "altere",
    "adicionar",
    "adicione",
    "remover",
    "remova",
    "refator",
    "refactor",
    "aplicar",
    "aplique",
    "ajustar",
    "ajuste",
    "escrever",
    "escreva",
)


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
        elif re.search(r"\bdoc|\breadme\b|\bchangelog\b", lowered):
            task_type = "docs"

        # Pedido de implementação que também cita "analisar"/"doc" não pode virar
        # complex_analysis/docs (ACs de auditoria em vez de workspace_changes) —
        # verbo de implementação vence a keyword de análise/docs.
        # Negações não contam como intenção ("não criar módulo soma").
        cleaned = _NEGATED_CLAUSE_RE.sub(" ", lowered)
        has_impl_intent = any(w in cleaned for w in _IMPLEMENTATION_INTENT) or re.search(
            r"\bfix(es|ed|ing)?\b", cleaned
        )
        if task_type in ("complex_analysis", "docs") and has_impl_intent:
            task_type = "implementation"

        complexity = "medium"
        if len(prompt) > 400 or task_type in {"architecture", "complex_analysis"}:
            complexity = "high"
        elif len(prompt) < 80 and task_type == "docs":
            complexity = "low"

        risk = "medium"
        if task_type == "security_review":
            risk = "high"

        requirements = extract_requirements(prompt)

        # 0.4.27 — loop de execução por pedido. O loop define o task_type quando
        # ele é mais específico que a heurística de keyword (ex.: "auditar a
        # landing" é complex_analysis, "corrigir o bug" é implementation).
        loop_id = detect_loop(prompt)
        loop = get_loop(loop_id)
        if loop is not None and not has_impl_intent:
            task_type = loop.task_type

        return TaskAnalysis(
            task_type=task_type,
            languages=languages,
            risk=risk,
            complexity=complexity,
            requirements=requirements,
            acceptance_criteria=[],
            summary=prompt.strip()[:240],
            loop=loop_id,
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

# Remove cláusulas negadas / meta-instruções antes do match positivo
# ("não criar módulo soma", "IGNORAR template de função soma", "avoid soma(a,b)")
_NEGATED_CLAUSE_RE = re.compile(
    r"\b("
    r"n[aã]o|not|never|nunca|sem|"
    r"ignorar|ignore|ignores|ignored|"
    r"evitar|evite|avoid|avoids|avoiding|"
    r"skip|skipping"
    r")\b[^.!?;:\n—–-]{0,120}",
    re.IGNORECASE,
)

_AUDIT_TASK_TYPES = frozenset(
    {"complex_analysis", "security_review", "architecture"}
)


def wants_soma_module(prompt: str) -> bool:
    """True só para intent positivo de módulo/função soma|sum.

    Ignora substring em resume/summary e menções sob negação/meta
    (ex.: "não criar módulo soma", "IGNORAR template de função soma").
    """
    cleaned = _NEGATED_CLAUSE_RE.sub(" ", prompt or "")
    return bool(_SOMA_MODULE_RE.search(cleaned))


# ACs declarados pelo usuario no proprio prompt: "AC-001: <descricao>",
# tolerando marcador de lista e qualificador entre parenteses.
_DECLARED_AC_RE = re.compile(
    r"^[ \t]*[-*•]?[ \t]*AC[-_ ]?(\d{1,3})[ \t]*(?:\([^)\n]{0,80}\))?[ \t]*[:–-][ \t]*(\S.*?)[ \t]*$",
    re.MULTILINE,
)
_MAX_DECLARED_AC = 10


def parse_declared_criteria(prompt: str) -> list[AcceptanceCriterion]:
    """ACs escritos no prompt vencem a inferencia por palavra-chave.

    Sem isto, uma auditoria read-only que declara "AC-001: criar relatorio X"
    era julgada pelos ACs genericos (tests_pass / docs_example em README.md) e
    reprovava por falha de suite alheia ao trabalho (bug-031/bug-032).
    """
    out: list[AcceptanceCriterion] = []
    seen: set[str] = set()
    for num, desc in _DECLARED_AC_RE.findall(prompt or ""):
        text = desc.strip().rstrip(".")
        if len(text) < 8 or text.lower() in VAGUE:
            continue
        cid = f"AC-{int(num):03d}"
        if cid in seen:
            continue
        seen.add(cid)
        low = text.lower()
        # Unico kind deterministico seguro de inferir: "suite de testes passa".
        # Todo o resto vira EVIDENCE (julgamento do validador), que e o
        # comportamento correto para criterio escrito em linguagem natural.
        if ("suite" in low or "exit code" in low) and (
            "test" in low or "teste" in low
        ):
            kind = CriterionKind.TESTS_PASS
        else:
            kind = CriterionKind.EVIDENCE
        out.append(
            AcceptanceCriterion(
                id=cid,
                description=text,
                kind=kind,
                check=CriterionCheck(kind=kind, params={}),
                required=True,
            )
        )
        if len(out) >= _MAX_DECLARED_AC:
            break
    return out


class CriteriaBuilder:
    def build(self, prompt: str, analysis: TaskAnalysis) -> list[AcceptanceCriterion]:
        # Precedência: ACs escritos pelo usuário > critérios do loop > heurística.
        declared = parse_declared_criteria(prompt)
        if declared:
            return declared

        loop = get_loop(getattr(analysis, "loop", None))
        if loop is not None:
            return loop.to_criteria()

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
            if re.search(r"\b(docs?|document\w*|readme)\b", lowered):
                add(
                    "README ou docs descrevem uso com exemplo executável",
                    CriterionKind.DOCS_EXAMPLE,
                    params={"path": "README.md", "must_contain": ["soma"]},
                )
            return criteria

        if analysis.task_type in _AUDIT_TASK_TYPES:
            # Auditorias/reviews: não deixar "testes"/"docs" no prompt
            # trocarem ACs de evidência por README/suite de produto.
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
            return criteria

        # Implementation / docs: workspace sempre; testes/docs por keyword ou fallback
        add(
            "Alterações solicitadas no prompt estão presentes no workspace",
            CriterionKind.WORKSPACE_CHANGES,
        )
        if re.search(r"\b(test|pytest|teste|testes)\b", lowered):
            add(
                "Suite de testes determinística passa com exit code 0",
                CriterionKind.TESTS_PASS,
            )
        if re.search(r"\b(docs?|document\w*|readme)\b", lowered):
            add(
                "README ou docs descrevem uso com exemplo executável",
                CriterionKind.DOCS_EXAMPLE,
                params={"path": "README.md"},
            )
        if len(criteria) == 1:
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
        loop = get_loop(getattr(analysis, "loop", None))
        loop_block: dict = {}
        if loop is not None:
            loop_block = {
                "loop": loop.id,
                "loop_title": loop.title,
                "loop_stages": list(loop.stages),
                "loop_done_when": loop.done_when,
            }
        return {
            **loop_block,
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
