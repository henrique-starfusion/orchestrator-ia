"""Erros da camada MCP (transporte)."""

from orchestrator_runtime.errors import OrchestratorError


class McpError(OrchestratorError):
    """Erro de transporte/validação MCP."""


class McpSecurityError(McpError):
    """Violação de segurança MCP (path, agent, role)."""


class McpUnavailableError(McpError):
    """Runtime/MCP indisponível."""
