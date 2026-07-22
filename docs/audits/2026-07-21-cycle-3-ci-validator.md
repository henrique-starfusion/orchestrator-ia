# Ciclo 3 — CI, validator e MCP scope (2026-07-21)

## Entregue

| Item | Mudança |
|------|---------|
| CI | `.github/workflows/ci.yml` — pytest (Ubuntu) + `Run-AllTests.ps1` (Windows) |
| Validator | critérios sem verificador exigem `changed_files` ou testes passed |
| MCP Cursor | default `CursorMcpScope=project` |
| Docs | `cli-reference.md`, CHANGELOG Unreleased |

## Testes

```
48 passed (runtime pytest)
```

## Próximo ciclo (backlog)

1. Unificar geradores `.cursor/mcp.json` (Python vs PS)
2. Redact live stdout de subprocess
3. Fila de tasks / worker fora do stdio MCP
4. Schema tipado de acceptance criteria
5. Smoke `orchestrator_run` e2e com agentes reais pós-reload MCP
