"""Fixtures and helpers for runtime tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_child_agent_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """Suite roda tambem dentro de dispatch (Invoke-RoutedAgent seta
    ORCHESTRATOR_CHILD_AGENT=1); o guard anti-recursao de mcp/tools.py
    nao pode vazar para os testes."""
    monkeypatch.delenv("ORCHESTRATOR_CHILD_AGENT", raising=False)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    orch = tmp_path / ".orchestrator"
    (orch / "config").mkdir(parents=True)
    (orch / "agents" / "profiles").mkdir(parents=True)
    (orch / "runtime" / "locks").mkdir(parents=True)
    (orch / "data").mkdir(parents=True)
    (orch / "memory").mkdir(parents=True)

    (orch / "VERSION").write_text("0.2.0\n", encoding="utf-8")
    (orch / "config" / "policies.json").write_text(
        json.dumps(
            {
                "maximum_iterations": 3,
                "same_issue_repeat_limit": 2,
                "minimum_validation_score": 0.9,
                "minimum_score_improvement": 0.03,
                "require_independent_validation": True,
                "require_deterministic_validation": True,
                "require_documentation_review": True,
                "token_economy": {"caveman_enabled": False},
            }
        ),
        encoding="utf-8",
    )
    (orch / "config" / "models.json").write_text(
        json.dumps(
            {
                "clients": {
                    "claude": {
                        "model_flag": "--model",
                        "prefer_aliases": True,
                        "aliases": {"balanced": "sonnet"},
                        "task_map": {"implementation": "sonnet", "docs": "sonnet"},
                    },
                    "codex": {
                        "model_flag": "-m",
                        "prefer_aliases": False,
                        "models": {"balanced": "gpt-5.6-sol-medium"},
                        "task_map": {"implementation": "gpt-5.6-sol-medium"},
                    },
                },
                "task_classes": {"implementation": {"tier": "balanced"}},
            }
        ),
        encoding="utf-8",
    )
    (orch / "config" / "manager_model.json").write_text(
        json.dumps({"provider": "rules", "enabled": False}),
        encoding="utf-8",
    )
    for name, verified in (("claude", True), ("codex", True)):
        (orch / "agents" / "profiles" / f"{name}.json").write_text(
            json.dumps(
                {
                    "id": name,
                    "kind": "cli",
                    "verified": verified,
                    "invoke": {
                        "subcommand": ["exec"] if name == "codex" else [],
                        "prompt_flag": None if name == "codex" else "-p",
                    },
                    "timeout_default_s": 60,
                    "exit_codes": {"success": 0},
                }
            ),
            encoding="utf-8",
        )
    (orch / "agents" / "profiles" / "cursor.json").write_text(
        json.dumps(
            {
                "id": "cursor",
                "kind": "ide-client",
                "executable": False,
                "worker_roles": [],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("# Fixture\n", encoding="utf-8")
    return tmp_path
