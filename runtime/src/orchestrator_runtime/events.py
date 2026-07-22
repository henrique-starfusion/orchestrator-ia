"""Eventos estruturados do runtime."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EventType(str, Enum):
    TASK_CREATED = "task_created"
    STATE_CHANGED = "state_changed"
    PLAN_CREATED = "plan_created"
    ROUTING_DECIDED = "routing_decided"
    AGENT_STARTED = "agent_started"
    AGENT_OUTPUT = "agent_output"
    AGENT_COMPLETED = "agent_completed"
    TEST_STARTED = "test_started"
    TEST_COMPLETED = "test_completed"
    VALIDATION_STARTED = "validation_started"
    VALIDATION_COMPLETED = "validation_completed"
    CORRECTION_REQUESTED = "correction_requested"
    DOCUMENTATION_STARTED = "documentation_started"
    DOCUMENTATION_COMPLETED = "documentation_completed"
    MEMORY_UPDATED = "memory_updated"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_INCOMPLETE = "task_incomplete"
    TASK_CANCELLED = "task_cancelled"


class RuntimeEvent(BaseModel):
    task_id: str
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    type: EventType
    role: str | None = None
    agent: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class EventBus:
    """Emite eventos para stdout e callbacks."""

    def __init__(self, verbose: bool = True) -> None:
        self.verbose = verbose
        self._handlers: list = []
        self.history: list[RuntimeEvent] = []

    def on(self, handler) -> None:
        self._handlers.append(handler)

    def emit(self, event: RuntimeEvent) -> RuntimeEvent:
        self.history.append(event)
        if self.verbose:
            role = f" role={event.role}" if event.role else ""
            agent = f" agent={event.agent}" if event.agent else ""
            extra = ""
            if event.data:
                summary = event.data.get("summary") or event.data.get("to") or ""
                if summary:
                    extra = f" {summary}"
            # stderr: nunca poluir stdout (MCP stdio = JSON-RPC)
            print(f"[{event.type.value}]{role}{agent}{extra}", file=sys.stderr, flush=True)
        for handler in self._handlers:
            handler(event)
        return event
