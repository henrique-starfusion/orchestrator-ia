from __future__ import annotations

import os
from pathlib import Path

from orchestrator_runtime.config import resolve_default_workspace


def test_resolve_default_workspace_explicit(tmp_path: Path) -> None:
    orch = tmp_path / ".orchestrator"
    orch.mkdir()
    assert resolve_default_workspace(tmp_path) == tmp_path.resolve()


def test_resolve_default_workspace_env(tmp_path: Path, monkeypatch) -> None:
    orch = tmp_path / ".orchestrator"
    orch.mkdir()
    monkeypatch.setenv("ORCHESTRATOR_PROJECT", str(tmp_path))
    monkeypatch.delenv("WORKSPACE_FOLDER_PATHS", raising=False)
    assert resolve_default_workspace(None) == tmp_path.resolve()


def test_resolve_default_workspace_cursor_paths(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    (project / ".orchestrator").mkdir()
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.delenv("ORCHESTRATOR_PROJECT", raising=False)
    monkeypatch.delenv("ORCHESTRATOR_WORKSPACE", raising=False)
    monkeypatch.setenv(
        "WORKSPACE_FOLDER_PATHS",
        f"{other}{os.pathsep}{project}",
    )
    assert resolve_default_workspace(None) == project.resolve()
