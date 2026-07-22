# Security

Status: **implementado** (MCP local) · auth remota: **experimental/planejado**

## MCP

- Bind padrão `127.0.0.1` apenas
- Workspace allowlist **estrita**: apenas o `default_workspace` do MCP (e subpaths); path absoluto externo é rejeitado mesmo com `.orchestrator/`
- Sem tool de shell genérica
- Roles/agents só do registry
- Cursor não é worker
- `read_only=true` em `orchestrator_delegate` bloqueia roles de escrita
- Prompts limitados em tamanho
- Logs/resultados com redact de secrets
- `allow_network` / install de deps **rejeitados** (não são no-op)
- `ORCHESTRATOR_CHILD_AGENT` impede recursão
- Overrides explícitos de `planner`/`executor`/`validator` têm precedência sobre `routing=automatic`
- `fake_agents` **bloqueado** na superfície MCP (só CLI/`ORCHESTRATOR_ALLOW_FAKE_AGENTS` em CI)
- `require_independent_validation`: falha se não houver validator ≠ executor
- Echo live de subprocess passa por `redact()`
- `.orchestrator/data` tenta `chmod 0o700` (Unix; best-effort no Windows)

## Políticas

Tools MCP **não** podem sobrescrever `config/policies.json` (limites do runtime).
