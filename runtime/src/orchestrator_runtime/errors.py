"""Erros do runtime."""


class OrchestratorError(Exception):
    """Erro base do runtime."""


class InvalidTransitionError(OrchestratorError):
    """Transição de estado inválida."""


class TaskNotFoundError(OrchestratorError):
    """Tarefa inexistente."""


class AgentUnavailableError(OrchestratorError):
    """Agente CLI indisponível."""


class CompletionGateError(OrchestratorError):
    """Completion gate não satisfeito."""


class RecursionBlockedError(OrchestratorError):
    """ORCHESTRATOR_CHILD_AGENT impede nova delegação."""


class PathEscapeError(OrchestratorError):
    """Caminho fora do projeto."""


class CancelledError(OrchestratorError):
    """Tarefa cancelada."""
