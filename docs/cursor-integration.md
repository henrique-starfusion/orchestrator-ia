# Cursor integration

Cursor é **cliente** do runtime.

```bash
orchestrator run --prompt "..."
orchestrator task status <id>
```

Rule: `.cursor/rules/runtime.mdc`.

Não selecionar Cursor como planner/executor/tester/validator.
`dispatch --client cursor` está deprecado.
`Task model=` permanece apenas como fallback legado — não é o workflow principal.
