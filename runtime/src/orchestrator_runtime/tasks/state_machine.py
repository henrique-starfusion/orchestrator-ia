"""Máquina de estados da tarefa."""

from __future__ import annotations

from enum import Enum

from orchestrator_runtime.errors import InvalidTransitionError


class TaskState(str, Enum):
    RECEIVED = "RECEIVED"
    QUEUED = "QUEUED"
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
        TaskState.QUEUED,
        TaskState.ANALYZING,
        TaskState.CANCELLED,
        TaskState.FAILED,
        # delegate (single-role) finaliza direto, sem passar pelo workflow —
        # sem isso a task delegada fica órfã em RECEIVED para sempre.
        TaskState.COMPLETED,
        TaskState.INCOMPLETE,
    },
    # 0.4.19 — workspace task queue: fila FIFO por project_path
    TaskState.QUEUED: {
        TaskState.ANALYZING,
        TaskState.RECEIVED,
        TaskState.CANCELLED,
        TaskState.FAILED,
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
    # As arestas de RE-ENTRADA para ANALYZING são adicionadas logo abaixo, uma
    # para cada estado de meio de pipeline (bug-110).
    TaskState.EXECUTING: {
        # Premissa factual incorreta encerra com sucesso sem gates artificiais.
        TaskState.COMPLETED,
        TaskState.TESTING,
        TaskState.CORRECTING,
        TaskState.CANCELLED,
        TaskState.FAILED,
        TaskState.INCOMPLETE,
        # executor emitiu REQUIRES_INPUT estruturado — pausa sem queimar iteração
        TaskState.WAITING_FOR_USER,
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
        # resume após resposta do usuário reentra o pipeline completo
        TaskState.ANALYZING,
    },
    TaskState.COMPLETED: set(),
    TaskState.INCOMPLETE: set(),
    TaskState.FAILED: set(),
    TaskState.CANCELLED: set(),
}

# bug-110 — task ÓRFÃ retomada reinicia o pipeline pelo ANALYZING.
#
# Medido no printbee (task e9803cf77a43, 10/08 19:50): o processo dono morreu
# com a task em VALIDATING; `can_resume` aceita qualquer estado não-terminal,
# então o resume entrou, mas o loop só transicionava para ANALYZING vindo de
# RECEIVED/WAITING_FOR_USER. Pulou a re-entrada, seguiu o fluxo e bateu em
# `VALIDATING -> RETRIEVING_MEMORY`, aresta que não existe:
#
#     status=FAILED  error='Transição inválida: VALIDATING -> RETRIEVING_MEMORY'
#
# Texto que parece mérito e é infra. Retomar de qualquer ponto do meio tem que
# REINICIAR pelo começo — quem estava no meio não tem contexto de agente vivo
# para continuar de onde parou.
MID_PIPELINE_STATES: frozenset[TaskState] = frozenset(
    {
        TaskState.RETRIEVING_MEMORY,
        TaskState.PLANNING,
        TaskState.SELECTING_AGENTS,
        TaskState.EXECUTING,
        TaskState.TESTING,
        TaskState.VALIDATING,
        TaskState.CORRECTING,
        TaskState.UPDATING_DOCUMENTATION,
        TaskState.CONSOLIDATING,
    }
)

for _mid in MID_PIPELINE_STATES:
    # Só esta aresta. As demais continuam exatamente como estavam, e estado
    # terminal segue com o conjunto VAZIO — daqui não sai nada.
    ALLOWED_TRANSITIONS[_mid].add(TaskState.ANALYZING)
del _mid


def assert_transition(current: TaskState, new: TaskState) -> None:
    if current == new:  # ponytail: same-state is a no-op — prevents FAILED on double-resume/MCP retry
        return
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    if new not in allowed:
        raise InvalidTransitionError(
            f"Transição inválida: {current.value} -> {new.value}"
        )


def can_resume(state: TaskState) -> bool:
    return state not in TERMINAL_STATES
