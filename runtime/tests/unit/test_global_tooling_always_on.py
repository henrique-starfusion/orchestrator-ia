"""0.4.12: OpenWolf, Graphify, Superpowers e Caveman sempre ativos nos prompts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator_runtime.config import RuntimeLimits, load_config
from orchestrator_runtime.tasks.models import AcceptanceCriterion, CriterionKind, TaskRecord  # noqa: E501
from orchestrator_runtime.tasks.service import TaskService


# ---------------------------------------------------------------- defaults


def test_caveman_enabled_default_true():
    """RuntimeLimits deve ter caveman_enabled=True por padrão (0.4.12)."""
    limits = RuntimeLimits()
    assert limits.caveman_enabled is True


def test_load_config_caveman_true_when_no_key(project: Path):
    """load_config sem chave token_economy.caveman_enabled usa default True."""
    policies_path = project / ".orchestrator" / "config" / "policies.json"
    # Remove a chave completamente
    policies = json.loads(policies_path.read_text(encoding="utf-8"))
    policies.pop("token_economy", None)
    policies_path.write_text(json.dumps(policies), encoding="utf-8")

    config = load_config(project)
    assert config.limits.caveman_enabled is True


def test_load_config_caveman_false_when_explicit(project: Path):
    """load_config respeita caveman_enabled=false explícito no JSON."""
    config = load_config(project)
    # conftest.py seta caveman_enabled=False
    assert config.limits.caveman_enabled is False


# ---------------------------------------------------------------- tooling block


def _make_service(project: Path, *, caveman: bool) -> TaskService:
    policies_path = project / ".orchestrator" / "config" / "policies.json"
    policies = json.loads(policies_path.read_text(encoding="utf-8"))
    te = policies.setdefault("token_economy", {})
    te["caveman_enabled"] = caveman
    policies_path.write_text(json.dumps(policies), encoding="utf-8")
    config = load_config(project, fake_agents=True)
    return TaskService(config, verbose=False)


def test_required_tooling_block_present_when_caveman_on(project: Path):
    svc = _make_service(project, caveman=True)
    block = svc._required_tooling_block()
    assert "OpenWolf" in block
    assert "Graphify" in block
    assert "Superpowers" in block
    assert "Caveman" in block


def test_required_tooling_block_empty_when_caveman_off(project: Path):
    svc = _make_service(project, caveman=False)
    assert svc._required_tooling_block() == ""


def _make_task(project: Path) -> TaskRecord:
    return TaskRecord(
        prompt="Implemente X",
        project_path=str(project),
        acceptance_criteria=[
            AcceptanceCriterion(
                id="AC-001",
                description="Mudança presente no workspace",
                kind=CriterionKind.WORKSPACE_CHANGES,
            )
        ],
    )


def test_executor_prompt_contains_tooling_when_caveman_on(project: Path):
    svc = _make_service(project, caveman=True)
    task = _make_task(project)
    prompt = svc._build_executor_prompt(task, {}, [])
    assert "OpenWolf" in prompt
    assert "Graphify" in prompt
    assert "Superpowers" in prompt
    assert "Caveman" in prompt


def test_executor_prompt_no_tooling_when_caveman_off(project: Path):
    svc = _make_service(project, caveman=False)
    task = _make_task(project)
    prompt = svc._build_executor_prompt(task, {}, [])
    assert "OpenWolf" not in prompt
    assert "Graphify" not in prompt
    assert "Superpowers" not in prompt


def test_validator_prompt_contains_tooling_when_caveman_on(project: Path):
    svc = _make_service(project, caveman=True)
    task = _make_task(project)
    prompt = svc._build_validator_prompt(task, {}, [], [])
    assert "OpenWolf" in prompt
    assert "Graphify" in prompt
    assert "Superpowers" in prompt
    assert "Caveman" in prompt


def test_validator_prompt_no_tooling_when_caveman_off(project: Path):
    svc = _make_service(project, caveman=False)
    task = _make_task(project)
    prompt = svc._build_validator_prompt(task, {}, [], [])
    assert "OpenWolf" not in prompt
    assert "Graphify" not in prompt
    assert "Superpowers" not in prompt


# ---------------------------------------------------------------- live policies.json


def test_live_policies_caveman_enabled():
    """O policies.json live do projeto deve ter caveman_enabled=true (0.4.12)."""
    repo_root = Path(__file__).resolve().parents[3]
    policies_path = repo_root / ".orchestrator" / "config" / "policies.json"
    if not policies_path.is_file():
        pytest.skip("policies.json live ausente")
    policies = json.loads(policies_path.read_text(encoding="utf-8"))
    te = policies.get("token_economy", {})
    assert te.get("caveman_enabled") is True, (
        f"policies.json deve ter caveman_enabled=true mas encontrou: {te.get('caveman_enabled')}"
    )


def test_live_policies_caveman_default_full():
    """O policies.json live deve ter caveman_default='full'."""
    repo_root = Path(__file__).resolve().parents[3]
    policies_path = repo_root / ".orchestrator" / "config" / "policies.json"
    if not policies_path.is_file():
        pytest.skip("policies.json live ausente")
    policies = json.loads(policies_path.read_text(encoding="utf-8"))
    te = policies.get("token_economy", {})
    assert te.get("caveman_default") == "full"


def test_live_policies_required_tooling_block():
    """O policies.json live deve ter required_agent_tooling com as 4 ferramentas."""
    repo_root = Path(__file__).resolve().parents[3]
    policies_path = repo_root / ".orchestrator" / "config" / "policies.json"
    if not policies_path.is_file():
        pytest.skip("policies.json live ausente")
    policies = json.loads(policies_path.read_text(encoding="utf-8"))
    tooling = (policies.get("token_economy") or {}).get("required_agent_tooling", {})
    for tool in ("openwolf", "graphify", "superpowers", "caveman"):
        assert tool in tooling, f"required_agent_tooling deve conter '{tool}'"
        assert tooling[tool].get("always_on") is True, f"{tool}.always_on deve ser true"
