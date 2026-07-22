"""Schemas Pydantic das tools MCP."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AnalyzeInput(BaseModel):
    objective: str
    workspace: str | None = None
    constraints: dict[str, Any] = Field(default_factory=dict)
    include_research: bool = False


class DelegateInput(BaseModel):
    agent: str
    role: str
    objective: str
    workspace: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    read_only: bool = True
    timeout_seconds: int = 600
    model: str | None = None


class RunConstraints(BaseModel):
    maximum_iterations: int = 3
    maximum_duration_seconds: int = 3600
    maximum_cost_usd: float | None = None
    allow_network: bool = False
    allow_dependency_install: bool = False


class RunInput(BaseModel):
    objective: str
    workspace: str | None = None
    profile: str = "balanced"
    routing: str = "automatic"
    planner: str | None = None
    executor: str | None = None
    validator: str | None = None
    constraints: RunConstraints = Field(default_factory=RunConstraints)
    wait: bool = False
    fake_agents: bool = False


class TaskIdInput(BaseModel):
    task_id: str


class EventsInput(BaseModel):
    task_id: str
    after_event_id: int | None = None
    limit: int = 100


class CancelInput(BaseModel):
    task_id: str
    reason: str = ""


class ResumeInput(BaseModel):
    task_id: str
    instruction: str | None = None


class MessageInput(BaseModel):
    task_id: str
    message: str


class MemorySearchInput(BaseModel):
    query: str
    workspace: str | None = None
    types: list[str] = Field(default_factory=list)
    limit: int = 10
