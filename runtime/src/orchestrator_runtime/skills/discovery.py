"""Skill catalog discovery — only installed skills, never invented.

Scans well-known skill directories (project-local and user-global) for
SKILL.md files and builds a catalog. Only IDs/paths that exist on disk
are returned; nothing is fabricated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SkillEntry:
    skill_id: str
    description: str
    path: Path


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)
_FIELD_RE = re.compile(r"^([\w-]+)\s*:\s*(.+)$", re.MULTILINE)

# In-memory cache: (project_path_str, include_user_global) -> list[SkillEntry]
_cache: dict[tuple[str, bool], list[SkillEntry]] = {}


def _parse_frontmatter(text: str) -> dict[str, str]:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    return dict(_FIELD_RE.findall(m.group(1)))


def _first_content_line(text: str) -> str:
    """First non-frontmatter, non-heading, non-empty line as fallback description."""
    in_front = True
    fence_count = 0
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "---":
            fence_count += 1
            if fence_count >= 2:
                in_front = False
            continue
        if in_front:
            continue
        if stripped and not stripped.startswith("#"):
            return stripped[:120]
    return ""


def _skill_dirs(project_path: Path, *, include_user_global: bool) -> list[Path]:
    dirs: list[Path] = [
        # project-local: installer-managed skills first
        project_path / ".orchestrator" / "skills",
        project_path / ".claude" / "skills",
        project_path / ".codex" / "skills",
        project_path / ".agents" / "skills",
    ]
    if not include_user_global:
        return dirs
    home = Path.home()
    dirs += [
        home / ".agents" / "skills",
        home / ".claude" / "skills",
        home / ".codex" / "skills",
        # Windows %USERPROFILE% is home on modern Python — no extra lookup needed
    ]
    return dirs


def _skill_id_from_path(skill_md: Path, base_dir: Path, frontmatter: dict[str, str]) -> str:
    """Derive a canonical skill ID.

    For a path like ~/.claude/skills/superpowers/brainstorming/SKILL.md
    under base_dir ~/.claude/skills, return 'superpowers:brainstorming'.
    For a single-level path like ~/.claude/skills/graphify/SKILL.md, return 'graphify'.
    Frontmatter 'name:' field takes precedence if present.
    """
    fm_name = (frontmatter.get("name") or "").strip()
    if fm_name:
        return fm_name
    try:
        rel_parts = skill_md.parent.relative_to(base_dir).parts
    except ValueError:
        return skill_md.parent.name
    if not rel_parts:
        return skill_md.parent.name
    if len(rel_parts) == 1:
        return rel_parts[0]
    # Multi-level: plugin:skill (last 2 segments; skip intermediate cache/version dirs)
    # e.g. plugins/cache/superpowers/6.1.1/skills/brainstorming → superpowers:brainstorming
    # Heuristic: use first and last part
    return f"{rel_parts[0]}:{rel_parts[-1]}"


def discover_skills(
    project_path: Path,
    *,
    include_user_global: bool = True,
) -> list[SkillEntry]:
    """Scan installed skill directories and return SkillEntry list.

    Results are cached per (project_path, include_user_global) for the
    duration of the Python process (one orchestrator run). Call
    clear_cache() to invalidate between runs.
    """
    cache_key = (str(project_path.resolve()), include_user_global)
    if cache_key in _cache:
        return _cache[cache_key]

    seen_ids: set[str] = set()
    entries: list[SkillEntry] = []

    for base_dir in _skill_dirs(project_path, include_user_global=include_user_global):
        if not base_dir.is_dir():
            continue
        for skill_md in sorted(base_dir.rglob("SKILL.md")):
            try:
                text = skill_md.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            fm = _parse_frontmatter(text)
            skill_id = _skill_id_from_path(skill_md, base_dir, fm)
            if skill_id in seen_ids:
                continue
            seen_ids.add(skill_id)
            description = (fm.get("description") or "").strip() or _first_content_line(text)
            entries.append(
                SkillEntry(
                    skill_id=skill_id,
                    description=description[:120],
                    path=skill_md,
                )
            )

    _cache[cache_key] = entries
    return entries


def clear_cache() -> None:
    """Invalidate the skill catalog cache (call between independent runs)."""
    _cache.clear()
