"""Análise, critérios e planejamento determinísticos."""

from __future__ import annotations

import re
from typing import Any, Iterable

from orchestrator_runtime.execution.scopes import infer_scope
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
        # Menção a segurança em QUALQUER lugar do prompt não faz a tarefa ser uma
        # revisão de segurança: uma implementação de 10k chars que explica "isso
        # causa falha de seguranca" continua sendo implementação. Exige-se INTENÇÃO
        # (verbo de revisão ligado ao termo, ou trabalho de segurança nomeado).
        mentions_security = bool(_SECURITY_MENTION_RE.search(lowered))
        # Ordem: auditoria/análise antes de "doc" (substring em "documentação").
        if _SECURITY_INTENT_RE.search(lowered):
            task_type = "security_review"
        elif _ARCHITECTURE_RE.search(lowered):
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
        # Verbo de implementação vence a keyword de classificação — inclusive
        # para security_review/architecture, que antes eram imunes ao override
        # e faziam bug fix virar revisão de segurança.
        if (
            task_type in ("complex_analysis", "docs", "security_review", "architecture")
            and has_impl_intent
        ):
            task_type = "implementation"

        complexity = "medium"
        if len(prompt) > 400 or task_type in {"architecture", "complex_analysis"}:
            complexity = "high"
        elif len(prompt) < 80 and task_type == "docs":
            complexity = "low"

        # Risco alto acompanha a MENÇÃO a segurança, não a classificação: um bug
        # fix que corrige vazamento continua sendo trabalho de risco alto mesmo
        # classificado como implementation.
        risk = "medium"
        if task_type == "security_review" or mentions_security:
            risk = "high"

        requirements = extract_requirements(prompt)

        # 0.4.27 — loop de execução por pedido. O loop define o task_type quando
        # ele é mais específico que a heurística de keyword (ex.: "auditar a
        # landing" é complex_analysis, "corrigir o bug" é implementation).
        loop_id = detect_loop(prompt)
        loop = get_loop(loop_id)
        # O loop REFINA o padrão; nunca derruba classificação explícita. Sem esta
        # guarda, "security review of the checkout flow" virava complex_analysis
        # só porque "checkout" é palavra-chave do loop de landing.
        if loop is not None and not has_impl_intent and task_type == "implementation":
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
            # 0.4.74 — escopo de arquivos lido do que o pedido NOMEIA, conferido
            # contra as pastas de topo do projeto. Prompt sem caminho devolve
            # vazio, e vazio serializa a task (execution/scopes.py).
            scope=list(infer_scope(prompt, project_files)),
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

_NON_CODE_TASK_TYPES = _AUDIT_TASK_TYPES | frozenset({"docs", "review"})
_CODE_GATE_KINDS = frozenset(
    {CriterionKind.WORKSPACE_CHANGES, CriterionKind.TESTS_PASS}
)


def _loop_is_compatible(loop: Any, task_type: str) -> bool:
    """Loop de implementação não governa task classificada como não-código."""
    return not (
        task_type in _NON_CODE_TASK_TYPES and loop.task_type == "implementation"
    )


def _safe_loop_criteria(loop: Any, task_type: str) -> list[AcceptanceCriterion]:
    """Remove gates determinísticos de código herdados por tasks não-código."""
    criteria = loop.to_criteria()
    if task_type not in _NON_CODE_TASK_TYPES:
        return criteria

    if not _loop_is_compatible(loop, task_type):
        return [
            AcceptanceCriterion(
                id="AC-001",
                description=(
                    "Entregável solicitado apresentado com evidência verificável"
                ),
                kind=CriterionKind.EVIDENCE,
                check=CriterionCheck(kind=CriterionKind.EVIDENCE, params={}),
                required=True,
            )
        ]

    safe: list[AcceptanceCriterion] = []
    for criterion in criteria:
        if criterion.kind not in _CODE_GATE_KINDS:
            safe.append(criterion)
            continue
        if criterion.kind == CriterionKind.TESTS_PASS:
            continue
        criterion = criterion.model_copy(
            update={
                "kind": CriterionKind.EVIDENCE,
                "check": CriterionCheck(
                    kind=CriterionKind.EVIDENCE, params={}
                ),
            }
        )
        safe.append(criterion)
    return safe


def _criteria_are_raw_loop_criteria(
    criteria: list[AcceptanceCriterion], loop: Any
) -> bool:
    """Reconhece critérios copiados do loop sem confundir ACs do usuário."""
    raw = loop.to_criteria()
    if len(criteria) != len(raw):
        return False
    return all(
        (current.id, current.description, current.kind)
        == (expected.id, expected.description, expected.kind)
        for current, expected in zip(criteria, raw)
    )

# Qualquer citação a segurança — usada só para elevar o RISCO, nunca para
# classificar a tarefa.
_SECURITY_MENTION_RE = re.compile(
    r"\b(security|seguran[çc]a|vulnerabilidad\w*|vulnerabilit\w*|cve-\d)", re.IGNORECASE
)

# INTENÇÃO de trabalho de segurança: verbo de revisão ligado ao termo, termo
# seguido de review/audit, ou trabalho de segurança nomeado.
_SECURITY_INTENT_RE = re.compile(
    r"(?:"
    r"\b(?:revis\w*|audit\w*|auditor\w*|analis\w*|avali\w*|verific\w*|review\w*|assess\w*|"
    r"scan\w*|threat\s*model\w*)\s+(?:a\s+|as\s+|o\s+|os\s+|de\s+|da\s+|do\s+|the\s+)*"
    r"(?:security|seguran[çc]a|vulnerabilidad\w*|vulnerabilit\w*)"
    r"|(?:security|seguran[çc]a)\s+(?:review|audit\w*|assessment|scan\w*)"
    r"|\b(?:pentest\w*|owasp|hardening|threat\s*model\w*)\b"
    r")",
    re.IGNORECASE,
)

# Arquitetura com fronteira de palavra: 'design' cru casava em 'designer',
# 'design system' e 'redesign' de qualquer pedido de UI.
_ARCHITECTURE_RE = re.compile(
    r"\b(?:arquitet\w*|architecture|architectural|"
    r"(?:design|desenho)\s+(?:de\s+|da\s+|do\s+|the\s+)?"
    r"(?:sistema|system|solu[çc][ãa]o|solution|arquitetura))",
    re.IGNORECASE,
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
        kind = _infer_declared_kind(text)
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


def _infer_declared_kind(text: str) -> CriterionKind:
    """Unico kind deterministico seguro de inferir: "suite de testes passa".

    Todo o resto vira EVIDENCE (julgamento do validador), que e o
    comportamento correto para criterio escrito em linguagem natural.
    """
    low = text.lower()
    if ("suite" in low or "exit code" in low) and (
        "test" in low or "teste" in low
    ):
        return CriterionKind.TESTS_PASS
    return CriterionKind.EVIDENCE


# bug-046 — usuarios escrevem criterios como prosa ("Criterios: a; b; c.") ou
# lista, nao no formato AC-001:. O parser rigido ignorava esses criterios e o
# template do loop vencia — a task nascia com ACs inatendiveis (GuardLine:
# task de colecao Postman julgada por "Defeito reproduzido com evidencia").
_CRITERIA_HEADER_RE = re.compile(
    r"\b(?:crit[eé]rios?(?:\s+de\s+aceita[çc][aã]o)?|acceptance\s+criteria)\s*:[ \t]*",
    re.IGNORECASE,
)
_CRITERIA_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)]|\(\d+\))\s*(\S.*?)\s*$")
_MIN_SECTION_ITEM_LEN = 8


def parse_criteria_section(prompt: str) -> list[AcceptanceCriterion]:
    """ACs de uma secao "Criterios:" em prosa ou lista de bullets.

    Inline: itens separados por ";" ate o fim da frase (primeiro ". " encerra
    a secao — pontos internos como "docs/postman.md" nao encerram). Ceiling
    conhecido: item com ". " no meio e truncado ali.
    Bloco: header sozinho na linha, itens nas linhas-bullet seguintes.
    """
    match = _CRITERIA_HEADER_RE.search(prompt or "")
    if not match:
        return []
    tail = prompt[match.end():]
    inline = tail.split("\n", 1)[0].strip()

    items: list[str] = []
    if inline:
        sentence_end = re.search(r"\.(?=\s|$)", inline)
        if sentence_end:
            inline = inline[: sentence_end.start()]
        items = [part.strip(" .\t") for part in inline.split(";")]
    else:
        for line in tail.split("\n")[1:]:
            bullet = _CRITERIA_BULLET_RE.match(line)
            if not bullet:
                break
            items.append(bullet.group(1).strip(" ."))

    out: list[AcceptanceCriterion] = []
    for text in items:
        if len(text) < _MIN_SECTION_ITEM_LEN or text.lower() in VAGUE:
            continue
        kind = _infer_declared_kind(text)
        out.append(
            AcceptanceCriterion(
                id=f"AC-{len(out) + 1:03d}",
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
        # Precedência: ACs escritos pelo usuário (formato AC-001: ou seção
        # "Critérios:") > critérios do loop > heurística. bug-046: o loop nunca
        # pode vencer critérios que o usuário escreveu no prompt.
        declared = parse_declared_criteria(prompt) or parse_criteria_section(prompt)
        if declared:
            return declared

        loop = get_loop(getattr(analysis, "loop", None))
        if loop is not None:
            return _safe_loop_criteria(loop, analysis.task_type)

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
        plan_criteria = list(task.acceptance_criteria)
        if (
            loop is not None
            and _criteria_are_raw_loop_criteria(plan_criteria, loop)
        ):
            plan_criteria = _safe_loop_criteria(loop, analysis.task_type)
        loop_block: dict = {}
        if loop is not None and _loop_is_compatible(loop, analysis.task_type):
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
                c.model_dump(mode="json") for c in plan_criteria
            ],
            "maximum_iterations": roles.maximum_iterations,
            "fallbacks": roles.fallbacks,
        }
