"""Fallback de changed_files via git status --porcelain."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from orchestrator_runtime.agents.base import AgentResult
from orchestrator_runtime.config import load_config
from orchestrator_runtime.execution.git_workspace import (
    GitBaseline,
    capture_baseline,
    changed_files_since,
)
from orchestrator_runtime.tasks.service import TaskService


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(project: Path) -> None:
    _git(project, "init")
    _git(project, "config", "user.email", "test@example.com")
    _git(project, "config", "user.name", "Test")
    (project / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(project, "add", "seed.txt")
    _git(project, "commit", "-m", "seed")


def test_changed_files_since_detects_new_file(project: Path):
    _init_repo(project)
    baseline = capture_baseline(project)
    assert baseline.available
    (project / "new_feature.py").write_text("x = 1\n", encoding="utf-8")
    changed = changed_files_since(project, baseline)
    assert "new_feature.py" in changed


def test_changed_files_since_ignores_preexisting_dirt(project: Path):
    _init_repo(project)
    (project / "pre.txt").write_text("pre\n", encoding="utf-8")
    baseline = capture_baseline(project)
    assert "pre.txt" in baseline.porcelain
    (project / "post.txt").write_text("post\n", encoding="utf-8")
    changed = changed_files_since(project, baseline)
    assert "post.txt" in changed
    assert "pre.txt" not in changed


def test_changed_files_since_detects_second_edit_of_preexisting_modified_file(
    project: Path,
):
    _init_repo(project)
    tracked = project / "seed.txt"
    tracked.write_text("dirty before task\n", encoding="utf-8")
    baseline = capture_baseline(project)

    tracked.write_text("dirty by task\n", encoding="utf-8")

    assert changed_files_since(project, baseline) == ["seed.txt"]


def test_changed_files_since_detects_restore_of_preexisting_modified_file(
    project: Path,
):
    _init_repo(project)
    tracked = project / "seed.txt"
    tracked.write_text("dirty before task\n", encoding="utf-8")
    baseline = capture_baseline(project)

    tracked.write_text("seed\n", encoding="utf-8")

    assert changed_files_since(project, baseline) == ["seed.txt"]


def test_changed_files_since_ignores_untouched_preexisting_modified_file(
    project: Path,
):
    _init_repo(project)
    tracked = project / "seed.txt"
    tracked.write_text("dirty before task\n", encoding="utf-8")
    baseline = capture_baseline(project)

    assert changed_files_since(project, baseline) == []


@pytest.mark.parametrize(
    ("operation", "expected"),
    [
        ("create", "created.txt"),
        ("modify", "seed.txt"),
        ("delete", "seed.txt"),
    ],
)
def test_changed_files_since_preserves_clean_baseline_detection(
    project: Path, operation: str, expected: str
):
    _init_repo(project)
    baseline = capture_baseline(project)

    if operation == "create":
        (project / expected).write_text("created by task\n", encoding="utf-8")
    elif operation == "modify":
        (project / expected).write_text("modified by task\n", encoding="utf-8")
    else:
        (project / expected).unlink()

    assert changed_files_since(project, baseline) == [expected]


def _nested_dirty_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, GitBaseline]:
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    root = tmp_path / "workspace"
    child = root / "nested"
    child.mkdir(parents=True)
    _init_repo(child)
    tracked = child / "seed.txt"
    tracked.write_text("dirty before task\n", encoding="utf-8")
    return root, tracked, capture_baseline(root)


def test_nested_repo_detects_second_edit_of_preexisting_modified_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, tracked, baseline = _nested_dirty_baseline(tmp_path, monkeypatch)

    tracked.write_text("dirty by task\n", encoding="utf-8")

    assert changed_files_since(root, baseline) == ["nested/seed.txt"]


def test_nested_repo_detects_restore_of_preexisting_modified_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, tracked, baseline = _nested_dirty_baseline(tmp_path, monkeypatch)

    tracked.write_text("seed\n", encoding="utf-8")

    assert changed_files_since(root, baseline) == ["nested/seed.txt"]


def test_nested_repo_ignores_untouched_preexisting_modified_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, _, baseline = _nested_dirty_baseline(tmp_path, monkeypatch)

    assert changed_files_since(root, baseline) == []


def test_enrich_changed_files_fills_empty_result(project: Path):
    _init_repo(project)
    config = load_config(project, fake_agents=True)
    service = TaskService(config, verbose=False)
    # 0.4.74 — o baseline e POR TASK: era atributo do servico e a segunda task a
    # comecar reatribuia o da primeira, atribuindo arquivos ao run errado.
    task = service.create_task("x")
    service._ctx(task).git_baseline = capture_baseline(project)
    (project / "via_agent.py").write_text("ok\n", encoding="utf-8")
    result = AgentResult(
        session_id="s",
        agent_id="codex",
        role="executor",
        status="completed",
        exit_code=0,
        changed_files=[],
    )
    enriched = service._enrich_changed_files(result, task)
    assert "via_agent.py" in enriched.changed_files


def test_capture_baseline_unavailable_outside_git(tmp_path: Path):
    baseline = capture_baseline(tmp_path)
    assert baseline.available is False
    assert changed_files_since(tmp_path, baseline) == []


def test_git_hang_returns_unavailable_baseline(tmp_path: Path, monkeypatch):
    """git status pendurado (Windows) não pode travar RECEIVED→ANALYZING."""
    import orchestrator_runtime.execution.git_workspace as gw

    def _hang(command, **kwargs):
        raise subprocess.TimeoutExpired(cmd=command, timeout=kwargs.get("timeout", 30))

    monkeypatch.setattr(gw.subprocess, "run", _hang)
    baseline = capture_baseline(tmp_path)
    assert baseline.available is False
    assert changed_files_since(tmp_path, GitBaseline(available=True)) == []
