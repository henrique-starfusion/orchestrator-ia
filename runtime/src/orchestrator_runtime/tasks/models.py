"""Modelos de domínio da tarefa."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from orchestrator_runtime.tasks.state_machine import TaskState

VAGUE_CRITERIA = {
    "código bom",
    "codigo bom",
    "solução adequada",
    "solucao adequada",
    "funciona corretamente",
    "works correctly",
    "good code",
}


def new_task_id() -> str:
    return uuid4().hex[:12]


class CriterionKind(str, Enum):
    """Verificadores tipados — o validator despacha por kind, não por substring."""

    SOMA_MODULE = "soma_module"
    TESTS_PASS = "tests_pass"
    DOCS_EXAMPLE = "docs_example"
    WORKSPACE_CHANGES = "workspace_changes"
    EVIDENCE = "evidence"
    CUSTOM = "custom"


class CriterionCheck(BaseModel):
    kind: CriterionKind
    params: dict[str, Any] = Field(default_factory=dict)


class AcceptanceCriterion(BaseModel):
    id: str
    description: str
    kind: CriterionKind = CriterionKind.EVIDENCE
    check: CriterionCheck | None = None
    verifiable: bool = True
    required: bool = True
    satisfied: bool | None = None

    @field_validator("description")
    @classmethod
    def reject_vague(cls, value: str) -> str:
        lowered = value.strip().lower()
        if lowered in VAGUE_CRITERIA or len(lowered) < 8:
            raise ValueError(f"Critério vago ou curto demais: {value!r}")
        return value

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_kind(cls, data: Any) -> Any:
        if isinstance(data, dict) and "kind" not in data and "check" not in data:
            kind = cls.infer_kind_from_description(str(data.get("description") or ""))
            data = {
                **data,
                "kind": kind,
                "check": {"kind": kind, "params": {}},
            }
        return data

    @model_validator(mode="after")
    def ensure_check(self) -> AcceptanceCriterion:
        if self.check is None:
            self.check = CriterionCheck(kind=self.kind)
        elif self.check.kind != self.kind:
            # check.kind is source of truth when both present
            self.kind = self.check.kind
        return self

    @classmethod
    def infer_kind_from_description(cls, description: str) -> CriterionKind:
        """Migração de critérios legados persistidos sem kind."""
        desc = (description or "").lower()
        if "soma" in desc and (
            "função" in desc or "funcao" in desc or "def " in desc or "(a, b)" in desc
        ):
            return CriterionKind.SOMA_MODULE
        if "suite de testes" in desc or (
            ("teste" in desc or "test" in desc) and "passa" in desc
        ):
            return CriterionKind.TESTS_PASS
        if "readme" in desc or "document" in desc or "docs" in desc:
            return CriterionKind.DOCS_EXAMPLE
        if "alterações solicitadas" in desc or "alteracoes solicitadas" in desc:
            return CriterionKind.WORKSPACE_CHANGES
        return CriterionKind.EVIDENCE


class TaskConstraints(BaseModel):
    maximum_iterations: int = 3
    maximum_duration_seconds: int = 3600
    maximum_cost: float | None = None
    profile: str = "balanced"
    planner: str | None = None
    executor: str | None = None
    validator: str | None = None
    dry_run: bool = False


class TaskRecord(BaseModel):
    id: str = Field(default_factory=new_task_id)
    prompt: str
    project_path: str
    task_type: str = "implementation"
    languages: list[str] = Field(default_factory=list)
    risk: str = "medium"
    complexity: str = "medium"
    requirements: list[str] = Field(default_factory=list)
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    constraints: TaskConstraints = Field(default_factory=TaskConstraints)
    status: TaskState = TaskState.RECEIVED
    plan: dict[str, Any] | None = None
    analysis: dict[str, Any] | None = None
    documentation_review: dict[str, Any] | None = None
    iteration: int = 0
    last_score: float | None = None
    cancel_requested: bool = False
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    error: str | None = None


class OrchestrationPlan(BaseModel):
    strategy: str = "execute_review_repair"
    planner: str
    executor: str
    tester: str = "runtime"
    validator: str
    fallbacks: dict[str, list[str]] = Field(default_factory=dict)
    maximum_iterations: int = 3
    roles: dict[str, str] = Field(default_factory=dict)


class TaskAnalysis(BaseModel):
    task_type: str
    languages: list[str] = Field(default_factory=list)
    risk: str = "medium"
    complexity: str = "medium"
    requirements: list[str] = Field(default_factory=list)
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    summary: str = ""
