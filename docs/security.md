# Security

Status: **implementado** (MCP local) · auth remota: **experimental/planejado**

## MCP

- Bind padrão `127.0.0.1` apenas
- Workspace allowlist (cwd / projeto com `.orchestrator/`)
- Sem tool de shell genérica
- Roles/agents só do registry
- Cursor não é worker
- Prompts limitados em tamanho
- Logs/resultados com redact de secrets
- Rede/install de deps bloqueados por padrão nas tools
- `ORCHESTRATOR_CHILD_AGENT` impede recursão

## Políticas

Tools MCP **não** podem sobrescrever `config/policies.json` (limites do runtime).
