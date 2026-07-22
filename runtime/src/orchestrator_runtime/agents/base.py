"""Contrato comum dos agentes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class AgentCapabilities(BaseModel):
    roles: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    can_write: bool = True
    can_test: bool = False
    can_validate: bool = True
    experimental: bool = False
    executable: bool = True


class AgentStatus(BaseModel):
    id: str
    available: bool
    path: str | None = None
    version: str | None = None
    kind: str = "cli"
    verified: bool = False
    notes: str = ""


class AgentRequest(BaseModel):
    role: str
    prompt: str
    model: str | None = None
    model_flag: str | None = None
    cwd: str
    timeout_s: int = 600
    env: dict[str, str] = Field(default_factory=dict)
    extra_args: list[str] = Field(default_factory=list)


class AgentSession(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    agent_id: str
    role: str
    started_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    meta: dict[str, Any] = Field(default_factory=dict)


class AgentResult(BaseModel):
    session_id: str
    agent_id: str
    role: str
    status: str
    exit_code: int | None = None
    timed_out: bool = False
    stdout: str = ""
    stderr: str = ""
    model: str | None = None
    command: list[str] = Field(default_factory=list)
    cwd: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    changed_files: list[str] = Field(default_factory=list)
    duration_s: float = 0.0


class AgentAdapter:
    id: str = "base"
    kind: str = "cli"

    def detect(self) -> AgentStatus:
        raise NotImplementedError

    def capabilities(self) -> AgentCapabilities:
        raise NotImplementedError

    async def start(self, request: AgentRequest) -> AgentSession:
        raise NotImplementedError

    async def continue_session(
        self, session: AgentSession, request: AgentRequest
    ) -> AgentResult:
        raise NotImplementedError

    async def cancel(self, session: AgentSession) -> None:
        return None

    async def run(self, request: AgentRequest) -> AgentResult:
        session = await self.start(request)
        return await self.continue_session(session, request)
