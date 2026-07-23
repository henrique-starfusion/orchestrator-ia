# Orchestrator adapter for Cursor
#
# Canonical project configuration lives in `.orchestrator/`.
#
# Cursor is an IDE **client** of the runtime — not a CLI worker.

## Runtime + MCP (preferred)

```bash
orchestrator cursor configure
orchestrator mcp serve --transport stdio
orchestrator run --prompt "<atividade>"
orchestrator task status <id>
```

No chat, use MCP tools `orchestrator_run` / `orchestrator_delegate` (any model can be front controller).

Non-trivial tasks DEFAULT to `orchestrator_run` — the user does not need to
ask. Inline edits are limited to the exceptions in
`.cursor/rules/multiagent-orchestrator.mdc`.

Do **not** select Cursor as planner/executor/tester/validator.
Do **not** rely on `Task model=` for the main multi-agent workflow.

## Documentation gate

Ao final de cada tarefa, revisar e atualizar a documentação afetada antes da conclusão.

## Token economy + models (legacy Task fallback only)

- Rules: `.cursor/rules/` + `.orchestrator/config/models.json`.
- Caveman is **off** by default for runtime/logs; optional for presentation replies.
- If you must use Task, always pass `model=` (never inherit parent).
