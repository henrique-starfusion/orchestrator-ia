# Cursor integration

Status: **implementado** (MCP + rules)

Cursor é **cliente IDE** / front controller — não worker CLI.

## Preferido (MCP)

```bash
orchestrator cursor configure
orchestrator mcp serve --transport stdio
```

No chat (qualquer modelo): tools `orchestrator_run`, `orchestrator_delegate`, `orchestrator_status`, …

Docs: [`mcp-integration.md`](mcp-integration.md) · [`cursor-front-controller.md`](cursor-front-controller.md)

## CLI direta

```bash
orchestrator run --prompt "..."
orchestrator task status <id>
```

## Rules

- `.cursor/rules/multiagent-orchestrator.mdc` — front controller
- `.cursor/rules/runtime.mdc` — runtime gates

Não selecionar Cursor como planner/executor/tester/validator.
`dispatch --client cursor` está deprecado.
