# Ciclo 5 — MCP security + DX (2026-07-21)

Continuidade pós-0.4.1.

## Achados atacados

| Gap | Fix |
|-----|-----|
| Geradores MCP divergentes | `cursor_config.stdio_server_entry` = cmd + `${workspaceFolder}` |
| Echo live sem redact | `process.py` `_reader` / `[exec]` |
| validator==executor | router raise + service hard reject |
| fake_agents via MCP | `McpSecurityError` no payload |
| CLI `agents` ausente | `orchestrator agents` + bin route |
| Docs scope default | `mcp-integration.md` + log install |

## Testes

Rodar `python -m pytest -q` no runtime.

## Próximo ciclo

Itens 2–3 foram parcialmente cobertos depois; follow-up do `analyze` em
`docs/audits/2026-07-21-cycle-6-analyze-behavior.md`.

1. Fila/worker fora do stdio MCP
2. ~~Permissões `0o700` em `.orchestrator/data`~~
3. ~~Bloquear write roles / `fake_agents` no MCP~~ (ver tabela acima)
4. Smoke e2e `orchestrator_run` com agentes reais
5. ~~Parse de requirements semver + ACs de auditoria~~ (ciclo 6)
