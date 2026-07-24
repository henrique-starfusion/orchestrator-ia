"""Configuração do runtime a partir de .orchestrator/."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class RuntimeLimits(BaseModel):
    maximum_iterations: int = 3
    same_issue_repeat_limit: int = 2
    minimum_validation_score: float = 0.9
    minimum_score_improvement: float = 0.03
    maximum_duration_seconds: int = 3600
    agent_timeout_default_s: int = 1800
    agent_timeout_by_role: dict[str, int] = Field(
        default_factory=lambda: {
            "planner": 900,
            "executor": 2400,
            "corrector": 2400,
            "validator": 1200,
            "tester": 600,
            "skill_selector": 120,
        }
    )
    require_independent_validation: bool = True
    require_deterministic_validation: bool = True
    require_documentation_review: bool = True
    allow_parallel_read_only_analysis: bool = True
    allow_parallel_workspace_writes: bool = False
    caveman_enabled: bool = True
    skill_selection_enabled: bool = True
    skill_selection_max_skills: int = 5
    skill_selection_timeout_s: int = 120
    skill_selection_include_user_global: bool = True
    # 0.4.14 — learn-then-compact context
    context_compaction_enabled: bool = True
    save_learning_before_compact: bool = True
    digest_max_chars: int = 1500
    truncate_result_artifacts_chars: int = 20000
    update_wolf_status: bool = True


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


def _has_orchestrator(path: Path) -> bool:
    try:
        return path.is_dir() and (path / ".orchestrator").is_dir()
    except OSError:
        return False


def resolve_default_workspace(explicit: Path | str | None = None) -> Path:
    """Resolve workspace para CLI/MCP (cwd do Cursor costuma ser o home).

    Ordem:
    1. argumento explicito
    2. ORCHESTRATOR_PROJECT / ORCHESTRATOR_WORKSPACE
    3. WORKSPACE_FOLDER_PATHS (Cursor)
    4. cwd se tiver .orchestrator/
    5. sobe pais a partir do cwd
    6. cwd (fallback)
    """
    if explicit is not None and str(explicit).strip():
        return Path(explicit).expanduser().resolve()

    for env_name in ("ORCHESTRATOR_PROJECT", "ORCHESTRATOR_WORKSPACE"):
        raw = (os.environ.get(env_name) or "").strip()
        if raw:
            candidate = Path(raw).expanduser().resolve()
            if _has_orchestrator(candidate):
                return candidate

    workspace_paths = (os.environ.get("WORKSPACE_FOLDER_PATHS") or "").strip()
    if workspace_paths:
        # Cursor pode enviar varios paths separados por pathsep ou ;
        parts = [p for p in workspace_paths.replace(";", os.pathsep).split(os.pathsep) if p.strip()]
        for part in parts:
            candidate = Path(part.strip()).expanduser().resolve()
            if _has_orchestrator(candidate):
                return candidate
        if parts:
            return Path(parts[0].strip()).expanduser().resolve()

    cwd = Path.cwd().resolve()
    if _has_orchestrator(cwd):
        return cwd

    for parent in cwd.parents:
        if _has_orchestrator(parent):
            return parent

    return cwd


def _skill_selection_limits(policies: dict[str, Any]) -> dict[str, Any]:
    """Extract skill_selection overrides from policies.json (0.4.13)."""
    ss = policies.get("skill_selection") or {}
    out: dict[str, Any] = {}
    if "enabled" in ss:
        out["skill_selection_enabled"] = bool(ss["enabled"])
    if "max_skills" in ss:
        try:
            out["skill_selection_max_skills"] = int(ss["max_skills"])
        except (TypeError, ValueError):
            pass
    if "timeout_s" in ss:
        try:
            out["skill_selection_timeout_s"] = int(ss["timeout_s"])
        except (TypeError, ValueError):
            pass
    if "include_user_global" in ss:
        out["skill_selection_include_user_global"] = bool(ss["include_user_global"])
    return out


def _context_compaction_limits(policies: dict[str, Any]) -> dict[str, Any]:
    """Extract context_compaction overrides from policies.json (0.4.14)."""
    cc = policies.get("context_compaction") or {}
    out: dict[str, Any] = {}
    if "enabled" in cc:
        out["context_compaction_enabled"] = bool(cc["enabled"])
    if "save_learning_before_compact" in cc:
        out["save_learning_before_compact"] = bool(cc["save_learning_before_compact"])
    if "update_wolf_status" in cc:
        out["update_wolf_status"] = bool(cc["update_wolf_status"])
    for key, field in (
        ("digest_max_chars", "digest_max_chars"),
        ("truncate_result_artifacts_chars", "truncate_result_artifacts_chars"),
    ):
        if key in cc:
            try:
                out[field] = int(cc[key])
            except (TypeError, ValueError):
                pass
    return out


def load_config(
    project_path: Path | str | None = None,
    *,
    fake_agents: bool = False,
    manager_provider: str | None = None,
) -> RuntimeConfig:
    project = resolve_default_workspace(project_path)
    orch = resolve_orchestrator_root(project)
    data_dir = orch / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    try:
        # Unix: restringe leitura do DB/prompts; no Windows é best-effort.
        os.chmod(data_dir, 0o700)
    except OSError:
        pass
    policies = _load_json(orch / "config" / "policies.json")
    models = _load_json(orch / "config" / "models.json")
    manager_raw = _load_json(orch / "config" / "manager_model.json")
    default_by_role = {
        "planner": 900,
        "executor": 2400,
        "corrector": 2400,
        "validator": 1200,
        "tester": 600,
        "skill_selector": 120,
    }
    raw_by_role = policies.get("agent_timeout_by_role") or {}
    by_role: dict[str, int] = dict(default_by_role)
    if isinstance(raw_by_role, dict):
        for key, value in raw_by_role.items():
            try:
                by_role[str(key)] = int(value)
            except (TypeError, ValueError):
                continue
    limits = RuntimeLimits(
        maximum_iterations=int(policies.get("maximum_iterations", 3)),
        same_issue_repeat_limit=int(policies.get("same_issue_repeat_limit", 2)),
        minimum_validation_score=float(policies.get("minimum_validation_score", 0.9)),
        minimum_score_improvement=float(policies.get("minimum_score_improvement", 0.03)),
        maximum_duration_seconds=int(
            policies.get("maximum_duration_seconds", 3600)
        ),
        agent_timeout_default_s=int(
            policies.get("agent_timeout_default_s", 1800)
        ),
        agent_timeout_by_role=by_role,
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
            (policies.get("token_economy") or {}).get("caveman_enabled", True)
        ),
        **_skill_selection_limits(policies),
        **_context_compaction_limits(policies),
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
