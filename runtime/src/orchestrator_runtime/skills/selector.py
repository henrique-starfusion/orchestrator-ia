"""Skill selector — picks relevant installed skills before calling heavy models.

A fast-tier model (haiku) is the preferred selector. If the CLI call fails,
select_skills_heuristic() provides a deterministic keyword-match fallback.
Only IDs that exist in the provided catalog are returned; invented IDs are
discarded at parse_and_validate time.
"""

from __future__ import annotations

import json
import re

from orchestrator_runtime.skills.discovery import SkillEntry

# Matches first JSON object containing a "skills" array key
_JSON_RE = re.compile(r"\{[^{}]*\"skills\"\s*:\s*\[[^\]]*\][^{}]*\}", re.DOTALL)


def build_selector_prompt(
    objective: str,
    catalog: list[SkillEntry],
    max_skills: int,
) -> str:
    """Build the prompt sent to the fast selector model."""
    lines = "\n".join(f"- {e.skill_id}: {e.description}" for e in catalog)
    return (
        f"Objetivo: {objective}\n\n"
        "Selecione as skills INSTALADAS mais relevantes para este objetivo.\n"
        "APENAS skills da lista abaixo (não invente IDs).\n\n"
        f"Skills disponíveis:\n{lines}\n\n"
        f"Responda SOMENTE com JSON:\n"
        f'  {{"skills":["id1","id2"], "rationale":"..."}}\n'
        f"Máximo {max_skills} skills. "
        'Se nenhuma aplicar, retorne {"skills":[]}.'
    )


def parse_and_validate(
    raw_output: str | None,
    catalog: list[SkillEntry],
    max_skills: int,
) -> list[str]:
    """Extract and validate skill IDs from selector LLM output.

    Discards any ID that does not exist in the catalog.
    """
    if not raw_output:
        return []
    valid_ids = {e.skill_id for e in catalog}
    m = _JSON_RE.search(raw_output)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    raw = data.get("skills") or []
    chosen = [s for s in raw if isinstance(s, str) and s in valid_ids]
    return chosen[:max_skills]


def select_skills_heuristic(
    catalog: list[SkillEntry],
    prompt: str,
    task_type: str | None,
    *,
    max_skills: int = 5,
) -> list[str]:
    """Deterministic fallback: keyword match between prompt+task_type and skill metadata.

    Scores each skill by the number of distinct prompt words (len>=3) that
    appear in the skill's id+description. Returns top-N by score.
    """
    search_text = (prompt + " " + (task_type or "")).lower()
    words = set(re.findall(r"\w{3,}", search_text))
    scored: list[tuple[int, str]] = []
    for entry in catalog:
        combined = (entry.skill_id + " " + entry.description).lower()
        score = sum(1 for w in words if w in combined)
        if score > 0:
            scored.append((score, entry.skill_id))
    scored.sort(key=lambda x: -x[0])
    return [sid for _, sid in scored[:max_skills]]
