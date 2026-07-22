# Ciclo 2 — hardening runtime/MCP (2026-07-21)

Continuidade de `2026-07-21-project-analysis.md`.

## Objetivo

Corrigir gaps que impediam o orquestrador de se auto-melhorar via chat MCP.

## Entregue

| Achado | Fix |
|-------|-----|
| C2 AC soma via `sum⊆resume` | `wants_soma_module()` + testes |
| A1 WriteLock | stale PID + reentrancy |
| A9 delegate asyncio | `_run_coro` |
| C1 allowlist | só `default_workspace` |
| A4 read_only | bloqueia WRITE_ROLES |
| A7 overrides | precedência mesmo com automatic |
| Comunicação status | `error`, message rica, poll_hint |
| Regras Cursor | contrato de poll |

## Testes

```
47 passed (runtime pytest)
```

## Próximo ciclo (backlog)

1. CI GitHub Actions
2. Default `CursorMcpScope=project`
3. Unificar geradores `.cursor/mcp.json`
4. Generalizar `DeterministicValidator` (default fail)
5. Fila de tasks fora do processo MCP stdio
6. Redact live stdout
