"""Quem chamou o orquestrador — e como isso muda o tratamento.

O runtime e chamado de superficies com contratos bem diferentes:

- **claude-code**: sessao bloqueante. Se o CLI nao imprime nada, o operador ve
  silencio e conclui que travou (medido: 13 min sem evento no printbee).
- **cursor**: chama por MCP e faz polling; sobrevive ao silencio, mas depende
  dos EVENTOS estarem no banco.
- **mcp**: sem console nenhum — eco no stdout e desperdicio, evento e tudo.
- **cli**: terminal do usuario; eco ao vivo e o canal principal.

Alem do eco, o chamador importa na ESCOLHA DE AGENTE: mandar o executor ser o
mesmo CLI que ja esta ocupado atendendo o usuario disputa cota e rate limit do
mesmo provedor. Quando ha alternativa, o orquestrador prefere outro.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Setado pelo servidor MCP antes de atender qualquer tool call.
MCP_ENV = "ORCHESTRATOR_CALLER_MCP"

# Override explicito, util em automacao e nos testes.
OVERRIDE_ENV = "ORCHESTRATOR_CALLER"

KNOWN = ("claude-code", "cursor", "codex", "mcp", "cli")

# Agente equivalente a cada superficie: usado para NAO escolher como executor o
# mesmo CLI que ja esta ocupado atendendo o usuario.
CALLER_AGENT = {
    "claude-code": "claude",
    "cursor": "cursor",
    "codex": "codex",
}


@dataclass(frozen=True)
class CallerProfile:
    id: str
    echo: bool          # imprimir saida do CLI filho no stdout
    heartbeat_s: int    # frequencia do sinal de vida
    busy_agent: str | None  # agente ja ocupado com o usuario (evitar como executor)

    @property
    def polls(self) -> bool:
        """Superficie que consulta status por conta propria."""
        return self.id in {"cursor", "mcp"}


_PROFILES = {
    # Bloqueante e sem polling: eco ao vivo + heartbeat curto.
    "claude-code": CallerProfile("claude-code", True, 20, "claude"),
    "codex": CallerProfile("codex", True, 20, "codex"),
    # Faz polling: evento e o que importa; console nao existe.
    "cursor": CallerProfile("cursor", False, 30, "cursor"),
    "mcp": CallerProfile("mcp", False, 30, None),
    # Terminal do usuario.
    "cli": CallerProfile("cli", True, 30, None),
}


def detect_caller(env: dict[str, str] | None = None) -> str:
    """Superficie que originou a chamada.

    Ordem: override explicito > MCP (marcado pelo servidor) > marcadores de
    ambiente do cliente > cli.
    """
    src = os.environ if env is None else env

    override = (src.get(OVERRIDE_ENV) or "").strip().lower()
    if override in KNOWN:
        return override

    if (src.get(MCP_ENV) or "").strip():
        return "mcp"

    # Claude Code exporta CLAUDECODE=1 nas sessoes que ele controla.
    if (src.get("CLAUDECODE") or "").strip() not in ("", "0"):
        return "claude-code"
    if (src.get("CLAUDE_PROJECT_DIR") or "").strip():
        return "claude-code"

    if any(k.startswith("CURSOR_") for k in src):
        return "cursor"
    if (src.get("TERM_PROGRAM") or "").strip().lower() == "cursor":
        return "cursor"

    if (src.get("CODEX_HOME") or "").strip():
        return "codex"

    return "cli"


def caller_profile(caller_id: str | None = None) -> CallerProfile:
    if caller_id is None:
        caller_id = detect_caller()
    return _PROFILES.get(str(caller_id).lower(), _PROFILES["cli"])
