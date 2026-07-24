"""Máquina de estados da tarefa."""

from __future__ import annotations

from enum import Enum

from orchestrator_runtime.errors import InvalidTransitionError


class TaskState(str, Enum):
    RECEIVED = "RECEIVED"
    ANALYZING = "ANALYZING"
    RETRIEVING_MEMORY = "RETRIEVING_MEMORY"
    PLANNING = "PLANNING"
    SELECTING_AGENTS = "SELECTING_AGENTS"
    EXECUTING = "EXECUTING"
    TESTING = "TESTING"
    VALIDATING = "VALIDATING"
    CORRECTING = "CORRECTING"
    UPDATING_DOCUMENTATION = "UPDATING_DOCUMENTATION"
    CONSOLIDATING = "CONSOLIDATING"
    COMPLETED = "COMPLETED"
    INCOMPLETE = "INCOMPLETE"
    FAILED = "FAILED"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    CANCELLED = "CANCELLED"


TERMINAL_STATES = {
    TaskState.COMPLETED,
    TaskState.INCOMPLETE,
    TaskState.FAILED,
    TaskState.CANCELLED,
}

ALLOWED_TRANSITIONS: dict[TaskState, set[TaskState]] = {
    TaskState.RECEIVED: {
        TaskState.ANALYZING,
        TaskState.CANCELLED,
        TaskState.FAILED,
        # delegate (single-role) finaliza direto, sem passar pelo workflow —
        # sem isso a task delegada fica órfã em RECEIVED para sempre.
        TaskState.COMPLETED,
        TaskState.INCOMPLETE,
    },
    TaskState.ANALYZING: {
        TaskState.RETRIEVING_MEMORY,
        TaskState.CANCELLED,
        TaskState.FAILED,
    },
    TaskState.RETRIEVING_MEMORY: {
        TaskState.PLANNING,
        TaskState.CANCELLED,
        TaskState.FAILED,
    },
    TaskState.PLANNING: {
        TaskState.SELECTING_AGENTS,
        TaskState.CANCELLED,
        TaskState.FAILED,
        TaskState.WAITING_FOR_USER,
    },
    TaskState.SELECTING_AGENTS: {
        TaskState.EXECUTING,
        TaskState.CANCELLED,
        TaskState.FAILED,
        TaskState.INCOMPLETE,
    },
    TaskState.EXECUTING: {
        TaskState.TESTING,
        TaskState.CORRECTING,
        TaskState.CANCELLED,
        TaskState.FAILED,
        TaskState.INCOMPLETE,
    },
    TaskState.TESTING: {
        TaskState.VALIDATING,
        TaskState.CORRECTING,
        TaskState.CANCELLED,
        TaskState.FAILED,
        TaskState.INCOMPLETE,
    },
    TaskState.VALIDATING: {
        TaskState.CORRECTING,
        TaskState.UPDATING_DOCUMENTATION,
        TaskState.CANCELLED,
        TaskState.FAILED,
        TaskState.INCOMPLETE,
        TaskState.WAITING_FOR_USER,
    },
    TaskState.CORRECTING: {
        TaskState.EXECUTING,
        TaskState.TESTING,
        TaskState.CANCELLED,
        TaskState.FAILED,
        TaskState.INCOMPLETE,
    },
    TaskState.UPDATING_DOCUMENTATION: {
        TaskState.CONSOLIDATING,
        TaskState.CANCELLED,
        TaskState.FAILED,
        TaskState.INCOMPLETE,
    },
    TaskState.CONSOLIDATING: {
        TaskState.COMPLETED,
        TaskState.INCOMPLETE,
        TaskState.FAILED,
    },
    TaskState.WAITING_FOR_USER: {
        TaskState.PLANNING,
        TaskState.EXECUTING,
        TaskState.CANCELLED,
        TaskState.INCOMPLETE,
    },
    TaskState.COMPLETED: set(),
    TaskState.INCOMPLETE: set(),
    TaskState.FAILED: set(),
    TaskState.CANCELLED: set(),
}


def assert_transition(current: TaskState, new: TaskState) -> None:
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    if new not in allowed:
        raise InvalidTransitionError(
            f"Transição inválida: {current.value} -> {new.value}"
        )


def can_resume(state: TaskState) -> bool:
    return state not in TERMINAL_STATES
