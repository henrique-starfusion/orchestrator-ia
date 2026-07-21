"""Configuração do runtime a partir de .orchestrator/."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class RuntimeLimits(BaseModel):
    maximum_iterations: int = 3
    same_issue_repeat_limit: int = 2
    minimum_validation_score: float = 0.9
    minimum_score_improvement: float = 0.03
    maximum_duration_seconds: int = 3600
    require_independent_validation: bool = True
    require_deterministic_validation: bool = True
    require_documentation_review: bool = True
    allow_parallel_read_only_analysis: bool = True
    allow_parallel_workspace_writes: bool = False
    caveman_enabled: bool = False


class ManagerModelConfig(BaseModel):
    provider: str = "rules"
    enabled: bool = False
    base_url: str = "http://localhost:8000/v1"
    model: str = ""
    api_key_env: str = "ORCHESTRATOR_MANAGER_API_KEY"


class RuntimeConfig(BaseModel):
    project_path: Path
    orchestrator_root: Path
    db_path: Path
    limits: RuntimeLimits = Field(default_factory=RuntimeLimits)
    manager: ManagerModelConfig = Field(default_factory=ManagerModelConfig)
    models: dict[str, Any] = Field(default_factory=dict)
    policies: dict[str, Any] = Field(default_factory=dict)
    profiles_dir: Path | None = None
    fake_agents: bool = False

    @property
    def data_dir(self) -> Path:
        return self.db_path.parent


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_orchestrator_root(project_path: Path) -> Path:
    root = project_path / ".orchestrator"
    if not root.is_dir():
        raise FileNotFoundError(
            f".orchestrator/ ausente em {project_path}. Rode 'orchestrator install' primeiro."
        )
    return root


def load_config(
    project_path: Path | str | None = None,
    *,
    fake_agents: bool = False,
    manager_provider: str | None = None,
) -> RuntimeConfig:
    project = Path(project_path or Path.cwd()).resolve()
    orch = resolve_orchestrator_root(project)
    data_dir = orch / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    policies = _load_json(orch / "config" / "policies.json")
    models = _load_json(orch / "config" / "models.json")
    manager_raw = _load_json(orch / "config" / "manager_model.json")
    limits = RuntimeLimits(
        maximum_iterations=int(policies.get("maximum_iterations", 3)),
        same_issue_repeat_limit=int(policies.get("same_issue_repeat_limit", 2)),
        minimum_validation_score=float(policies.get("minimum_validation_score", 0.9)),
        minimum_score_improvement=float(policies.get("minimum_score_improvement", 0.03)),
        maximum_duration_seconds=int(
            policies.get("maximum_duration_seconds", 3600)
        ),
        require_independent_validation=bool(
            policies.get("require_independent_validation", True)
        ),
        require_deterministic_validation=bool(
            policies.get("require_deterministic_validation", True)
        ),
        require_documentation_review=bool(
            policies.get("require_documentation_review", True)
        ),
        allow_parallel_read_only_analysis=bool(
            policies.get("allow_parallel_read_only_analysis", True)
        ),
        allow_parallel_workspace_writes=bool(
            policies.get("allow_parallel_workspace_writes", False)
        ),
        caveman_enabled=bool(
            (policies.get("token_economy") or {}).get("caveman_enabled", False)
        ),
    )
    manager = ManagerModelConfig(
        provider=manager_raw.get("provider", "rules"),
        enabled=bool(manager_raw.get("enabled", False)),
        base_url=manager_raw.get("base_url", "http://localhost:8000/v1"),
        model=manager_raw.get("model", ""),
        api_key_env=manager_raw.get("api_key_env", "ORCHESTRATOR_MANAGER_API_KEY"),
    )
    if manager_provider:
        manager.provider = manager_provider
        if manager_provider != "rules":
            manager.enabled = True
    return RuntimeConfig(
        project_path=project,
        orchestrator_root=orch,
        db_path=data_dir / "orchestrator.db",
        limits=limits,
        manager=manager,
        models=models,
        policies=policies,
        profiles_dir=orch / "agents" / "profiles",
        fake_agents=fake_agents,
    )
