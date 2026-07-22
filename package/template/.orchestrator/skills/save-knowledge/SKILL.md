# Save Knowledge

Persist durable findings to shared memory for future tasks.

## When to use

- After every task terminal state (COMPLETED, INCOMPLETE, FAILED)
- When decisions or architecture change
- After documentation review

## Hard rules

- Runtime writes episodes/metrics to SQLite (`.orchestrator/data/orchestrator.db`)
- Also export human-readable notes under `memory/` when useful
- Include documentation review outcome in the episode
- Ao final de cada tarefa, revisar e atualizar a documentação afetada antes da conclusão

## Outputs

- SQLite `memories`, `agent_performance`, `strategy_performance`
- Entries under `memory/` subdirectories (export)
- Updated `memory/index.json` when applicable
