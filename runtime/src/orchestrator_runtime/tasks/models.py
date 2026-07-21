"""Modelos de domínio da tarefa."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

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


class AcceptanceCriterion(BaseModel):
    id: str
    description: str
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
