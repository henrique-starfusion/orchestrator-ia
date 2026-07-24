"""0.4.13: Skill discovery, selector, and prompt injection tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator_runtime.config import RuntimeLimits, load_config
from orchestrator_runtime.skills.discovery import SkillEntry, clear_cache, discover_skills
from orchestrator_runtime.skills.selector import (
    build_selector_prompt,
    parse_and_validate,
    select_skills_heuristic,
)
from orchestrator_runtime.tasks.models import AcceptanceCriterion, CriterionKind, TaskRecord
from orchestrator_runtime.tasks.service import TaskService


# ---------------------------------------------------------------- fixtures


def _write_skill(base: Path, rel_path: str, name: str, description: str) -> Path:
    """Helper: create a SKILL.md at base/rel_path."""
    skill_dir = base / rel_path
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\nContent.\n",
        encoding="utf-8",
    )
    return skill_md


@pytest.fixture(autouse=True)
def _clear_skill_cache():
    """Ensure discovery cache doesn't bleed between tests."""
    clear_cache()
    yield
    clear_cache()


# ---------------------------------------------------------------- discovery


def test_discover_returns_only_disk_skills(tmp_path: Path):
    """discover_skills only returns skills that exist on disk."""
    _write_skill(tmp_path, ".claude/skills/my-skill", "my-skill", "A real skill")
    entries = discover_skills(tmp_path, include_user_global=False)
    ids = {e.skill_id for e in entries}
    assert "my-skill" in ids


def test_discover_no_invented_skills(tmp_path: Path):
    """discover_skills returns nothing when no SKILL.md exists."""
    entries = discover_skills(tmp_path, include_user_global=False)
    assert entries == []


def test_discover_extracts_description_from_frontmatter(tmp_path: Path):
    """description field from frontmatter is used as SkillEntry.description."""
    _write_skill(tmp_path, ".orchestrator/skills/foo", "foo", "Helps with foo tasks")
    entries = discover_skills(tmp_path, include_user_global=False)
    assert any(e.description == "Helps with foo tasks" for e in entries)


def test_discover_nested_skill_id(tmp_path: Path):
    """Nested skill paths produce plugin:skill IDs (e.g. superpowers:brainstorming)."""
    _write_skill(
        tmp_path,
        ".claude/skills/superpowers/brainstorming",
        "superpowers:brainstorming",
        "Brainstorm solutions",
    )
    entries = discover_skills(tmp_path, include_user_global=False)
    ids = {e.skill_id for e in entries}
    assert "superpowers:brainstorming" in ids


def test_discover_deduplicates_same_id(tmp_path: Path):
    """Skills with the same ID from different base dirs are deduplicated."""
    _write_skill(tmp_path, ".claude/skills/dup", "dup", "First")
    _write_skill(tmp_path, ".codex/skills/dup", "dup", "Second")
    entries = discover_skills(tmp_path, include_user_global=False)
    ids = [e.skill_id for e in entries]
    assert ids.count("dup") == 1


def test_discover_cache_hit(tmp_path: Path):
    """Second call with same args returns cached result (same list object)."""
    _write_skill(tmp_path, ".claude/skills/cached", "cached", "Cache test")
    first = discover_skills(tmp_path, include_user_global=False)
    second = discover_skills(tmp_path, include_user_global=False)
    assert first is second


# ---------------------------------------------------------------- selector


def _make_catalog(*skills: tuple[str, str]) -> list[SkillEntry]:
    return [
        SkillEntry(skill_id=sid, description=desc, path=Path("/fake"))
        for sid, desc in skills
    ]


def test_parse_and_validate_discards_invented_ids():
    """parse_and_validate must discard IDs not in the catalog."""
    catalog = _make_catalog(("real-skill", "A real skill"), ("other", "Another"))
    raw = '{"skills": ["real-skill", "invented-fake-skill"], "rationale": "x"}'
    result = parse_and_validate(raw, catalog, max_skills=5)
    assert "invented-fake-skill" not in result
    assert "real-skill" in result


def test_parse_and_validate_empty_on_no_match():
    """parse_and_validate returns [] when no valid IDs found."""
    catalog = _make_catalog(("real", "Real"))
    result = parse_and_validate('{"skills": ["nonexistent"]}', catalog, max_skills=5)
    assert result == []


def test_parse_and_validate_respects_max_skills():
    """parse_and_validate caps output at max_skills."""
    catalog = _make_catalog(*[(f"skill-{i}", f"desc {i}") for i in range(10)])
    ids = [f"skill-{i}" for i in range(10)]
    raw = json.dumps({"skills": ids})
    result = parse_and_validate(raw, catalog, max_skills=3)
    assert len(result) <= 3


def test_parse_and_validate_returns_empty_on_invalid_json():
    catalog = _make_catalog(("x", "y"))
    assert parse_and_validate("not json at all", catalog, max_skills=5) == []


def test_heuristic_keyword_match():
    """Heuristic selects skills whose text matches prompt keywords."""
    catalog = _make_catalog(
        ("brainstorming", "Ideate and plan solutions systematically"),
        ("security-audit", "Review code for security vulnerabilities"),
        ("unrelated", "Something completely different"),
    )
    result = select_skills_heuristic(
        catalog, "I need to brainstorm and plan the solution", None, max_skills=5
    )
    assert "brainstorming" in result
    assert "unrelated" not in result


def test_heuristic_returns_empty_on_no_match():
    catalog = _make_catalog(("totally-unrelated", "XYZ ABC 123"))
    result = select_skills_heuristic(catalog, "quantum physics", None, max_skills=5)
    assert result == []


def test_build_selector_prompt_contains_catalog_ids():
    catalog = _make_catalog(("skill-a", "Desc A"), ("skill-b", "Desc B"))
    prompt = build_selector_prompt("Do something", catalog, max_skills=5)
    assert "skill-a" in prompt
    assert "skill-b" in prompt
    assert "não invente" in prompt.lower() or "nao invente" in prompt.lower()


# ---------------------------------------------------------------- prompt injection


def _make_service(project: Path, *, skill_selection: bool = True) -> TaskService:
    policies_path = project / ".orchestrator" / "config" / "policies.json"
    policies = json.loads(policies_path.read_text(encoding="utf-8"))
    policies["skill_selection"] = {"enabled": skill_selection, "max_skills": 5, "timeout_s": 30}
    policies_path.write_text(json.dumps(policies), encoding="utf-8")
    config = load_config(project, fake_agents=True)
    return TaskService(config, verbose=False)


def _make_task(project: Path, selected_skills: list[str] | None = None) -> TaskRecord:
    analysis = {}
    if selected_skills is not None:
        analysis["selected_skills"] = selected_skills
    task = TaskRecord(
        prompt="Implemente X",
        project_path=str(project),
        acceptance_criteria=[
            AcceptanceCriterion(
                id="AC-001",
                description="Feature presente",
                kind=CriterionKind.WORKSPACE_CHANGES,
            )
        ],
    )
    if analysis:
        task.analysis = analysis
    return task


def test_executor_prompt_contains_skills_block_when_selected(project: Path):
    """_build_executor_prompt includes skills block when task.analysis has selected_skills."""
    _write_skill(project, ".claude/skills/my-skill", "my-skill", "My skill desc")
    svc = _make_service(project)
    task = _make_task(project, selected_skills=["my-skill"])
    prompt = svc._build_executor_prompt(task, {}, [])
    assert "my-skill" in prompt
    assert "Skills selecionadas" in prompt


def test_executor_prompt_no_skills_block_when_empty(project: Path):
    """_build_executor_prompt has no skills section when no skills selected."""
    svc = _make_service(project)
    task = _make_task(project, selected_skills=[])
    prompt = svc._build_executor_prompt(task, {}, [])
    assert "Skills selecionadas" not in prompt


def test_validator_prompt_contains_skills_block(project: Path):
    """_build_validator_prompt includes skills when selected."""
    _write_skill(project, ".claude/skills/val-skill", "val-skill", "Validator skill")
    svc = _make_service(project)
    task = _make_task(project, selected_skills=["val-skill"])
    prompt = svc._build_validator_prompt(task, {}, [], [])
    assert "val-skill" in prompt
    assert "Skills selecionadas" in prompt


def test_skills_block_empty_when_no_skills_in_analysis(project: Path):
    """_skills_block returns '' when task.analysis has no selected_skills."""
    svc = _make_service(project)
    task = _make_task(project)
    assert svc._skills_block(task) == ""


# ---------------------------------------------------------------- config


def test_runtime_limits_skill_selection_defaults():
    """RuntimeLimits defaults enable skill selection (0.4.13)."""
    limits = RuntimeLimits()
    assert limits.skill_selection_enabled is True
    assert limits.skill_selection_max_skills == 5
    assert limits.skill_selection_timeout_s == 120
    assert limits.skill_selection_include_user_global is True


def test_load_config_reads_skill_selection(project: Path):
    """load_config reads skill_selection block from policies.json."""
    policies_path = project / ".orchestrator" / "config" / "policies.json"
    policies = json.loads(policies_path.read_text(encoding="utf-8"))
    policies["skill_selection"] = {
        "enabled": False,
        "max_skills": 3,
        "timeout_s": 60,
        "include_user_global": False,
    }
    policies_path.write_text(json.dumps(policies), encoding="utf-8")
    config = load_config(project)
    assert config.limits.skill_selection_enabled is False
    assert config.limits.skill_selection_max_skills == 3
    assert config.limits.skill_selection_timeout_s == 60
    assert config.limits.skill_selection_include_user_global is False


def test_live_policies_has_skill_selection_block():
    """Live policies.json has the skill_selection block (0.4.13)."""
    repo_root = Path(__file__).resolve().parents[3]
    policies_path = repo_root / ".orchestrator" / "config" / "policies.json"
    if not policies_path.is_file():
        pytest.skip("policies.json live ausente")
    policies = json.loads(policies_path.read_text(encoding="utf-8"))
    ss = policies.get("skill_selection")
    assert ss is not None, "policies.json deve ter bloco skill_selection (0.4.13)"
    assert ss.get("enabled") is True
    assert "max_skills" in ss
    assert "timeout_s" in ss


def test_live_models_has_skill_selector_role():
    """Live models.json has skill_selector in role_model_preferences (0.4.13)."""
    repo_root = Path(__file__).resolve().parents[3]
    models_path = repo_root / ".orchestrator" / "config" / "models.json"
    if not models_path.is_file():
        pytest.skip("models.json live ausente")
    models = json.loads(models_path.read_text(encoding="utf-8"))
    prefs = models.get("role_model_preferences") or {}
    assert "skill_selector" in prefs, (
        "models.json deve ter role_model_preferences.skill_selector (0.4.13)"
    )
    assert "claude" in prefs["skill_selector"]
