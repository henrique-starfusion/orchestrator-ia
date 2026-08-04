"""Regras do projeto: descoberta + seleção por relevância.

O executor já recebia as skills selecionadas, mas não as REGRAS do projeto —
então o agente reimplementava padrões que o time já tinha escrito (.NET/DDD,
Angular, Postgres, git-workflow...). Aqui as regras são descobertas pelo
frontmatter (`description`, `globs`, `alwaysApply`) e as mais relevantes para
o pedido entram no prompt.

Injetamos caminho + descrição, não o corpo: o agente lê o arquivo quando for
mexer naquela área. Isso mantém o custo de token baixo e a regra autoritativa.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
_FIELD_RE = re.compile(r"^([\w-]+)\s*:\s*(.+)$", re.MULTILINE)
_WORD_RE = re.compile(r"[a-zà-ú0-9_]{4,}", re.IGNORECASE)

# Diretórios de regras, em ordem de precedência. `legacy-import` é cópia do
# vendor e entra por último — a deduplicação por nome de arquivo evita repetir.
# bug-081 — o executor herdava só .cursor/.orchestrator: as rules DO MODELO
# (`.codex/rules` existem e são citadas pelos agents codex do printbee) nunca
# chegavam ao agente chamado pelo orquestrador.
_RULE_DIRS = (
    Path(".cursor") / "rules",
    Path(".orchestrator") / "rules",
    Path(".codex") / "rules",
    Path(".claude") / "rules",
    Path(".kimi-code") / "rules",
)

_MAX_RULES = 6

# Palavras genéricas demais para indicar relevância.
_STOPWORDS = frozenset(
    {
        "para", "como", "sobre", "todos", "todas", "quando", "porque", "projeto",
        "arquivo", "arquivos", "usar", "deve", "esse", "essa", "isso", "mais",
        "pode", "fazer", "regra", "regras", "padrao", "padrão", "padroes",
        "padrões", "with", "that", "this", "from", "your", "have", "will",
    }
)


@dataclass(frozen=True)
class RuleEntry:
    rule_id: str
    description: str
    path: Path
    always_apply: bool
    globs: tuple[str, ...]


def _parse_frontmatter(text: str) -> dict[str, str]:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}
    return {
        k.strip().lower(): v.strip()
        for k, v in _FIELD_RE.findall(match.group(1))
    }


def _parse_globs(raw: str) -> tuple[str, ...]:
    if not raw:
        return ()
    cleaned = raw.strip().strip("[]")
    parts = [p.strip().strip("\"'") for p in cleaned.split(",")]
    return tuple(p for p in parts if p)


def discover_rules(project_path: Path) -> list[RuleEntry]:
    """Todas as regras do projeto, deduplicadas por nome de arquivo."""
    found: dict[str, RuleEntry] = {}
    for rel in _RULE_DIRS:
        base = project_path / rel
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.suffix.lower() not in {".mdc", ".md"}:
                continue
            if not path.is_file():
                continue
            key = path.stem.lower()
            if key in found:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            meta = _parse_frontmatter(text)
            description = meta.get("description", "").strip()
            if not description:
                # Sem frontmatter: primeira linha não vazia que não seja título.
                for line in text.splitlines():
                    stripped = line.strip().lstrip("#").strip()
                    if stripped and not stripped.startswith("---"):
                        description = stripped[:200]
                        break
            found[key] = RuleEntry(
                rule_id=path.stem,
                description=description,
                path=path,
                always_apply=meta.get("alwaysapply", "").lower() == "true",
                globs=_parse_globs(meta.get("globs", "")),
            )
    return list(found.values())


def _tokens(text: str) -> set[str]:
    return {
        w.lower()
        for w in _WORD_RE.findall(text or "")
        if w.lower() not in _STOPWORDS
    }


def select_rules(
    project_path: Path,
    prompt: str,
    *,
    languages: list[str] | None = None,
    limit: int = _MAX_RULES,
) -> list[RuleEntry]:
    """Regras aplicáveis ao pedido: alwaysApply + as mais relevantes."""
    rules = discover_rules(project_path)
    if not rules:
        return []

    prompt_tokens = _tokens(prompt)
    lang_tokens = {str(x).lower() for x in (languages or [])}

    always = [r for r in rules if r.always_apply]
    scored: list[tuple[int, RuleEntry]] = []
    for rule in rules:
        if rule.always_apply:
            continue
        haystack = _tokens(f"{rule.rule_id.replace('_', ' ').replace('-', ' ')} {rule.description}")
        score = len(prompt_tokens & haystack)
        # Glob casando com a linguagem do pedido conta como sinal forte.
        for glob in rule.globs:
            ext = glob.rsplit(".", 1)[-1].lower() if "." in glob else ""
            if ext and ext in lang_tokens:
                score += 2
        if score > 0:
            scored.append((score, rule))

    scored.sort(key=lambda pair: (-pair[0], pair[1].rule_id))
    selected = always + [r for _, r in scored]
    return selected[:limit]
