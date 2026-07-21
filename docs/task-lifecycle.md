# Task lifecycle

Estados:

```text
RECEIVED → ANALYZING → RETRIEVING_MEMORY → PLANNING → SELECTING_AGENTS
→ EXECUTING → TESTING → VALIDATING ⇄ CORRECTING
→ UPDATING_DOCUMENTATION → CONSOLIDATING → COMPLETED
```

Terminais: `COMPLETED`, `INCOMPLETE`, `FAILED`, `CANCELLED`, `WAITING_FOR_USER`.

## Completion

COMPLETED somente se:

- testes obrigatórios passaram
- critérios obrigatórios ok
- sem blocking issues
- score ≥ threshold
- revisão documental registrada e `validation=passed`

Limite de iterações / same-issue / timeout → `INCOMPLETE` (não `COMPLETED`).
