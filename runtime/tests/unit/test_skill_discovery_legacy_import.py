"""0.4.23: skills sob legacy-import/** entram no catálogo (rglob)."""

from pathlib import Path

from orchestrator_runtime.skills.discovery import clear_cache, discover_skills


def test_discover_skills_finds_legacy_import(tmp_path: Path):
    skill_md = (
        tmp_path
        / ".orchestrator"
        / "skills"
        / "legacy-import"
        / "claude"
        / "bar"
        / "SKILL.md"
    )
    skill_md.parent.mkdir(parents=True)
    skill_md.write_text(
        "---\nname: bar\ndescription: imported skill\n---\n# bar\n",
        encoding="utf-8",
    )

    clear_cache()
    entries = discover_skills(tmp_path, include_user_global=False)
    ids = {e.skill_id for e in entries}
    assert "bar" in ids
    match = next(e for e in entries if e.skill_id == "bar")
    assert match.path == skill_md
