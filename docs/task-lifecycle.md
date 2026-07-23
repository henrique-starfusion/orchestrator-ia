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

## Repair loop (`execute_review_repair`)

Em cada iteração (até `policies.json` → `maximum_iterations`, padrão 3):

1. **EXECUTING** — `executor` (iter 1) ou **corrector** (iter ≥ 2)
2. **TESTING** — suite determinística do runtime
3. **VALIDATING** — checklist determinístico + validator CLI independente
4. Se aprovado **e** testes ok → sai do loop (docs → COMPLETED)
5. Se rejeitado, testes falharam, ou spawn do CLI falhou → **CORRECTING** e volta ao passo 1

Notas de resiliência:

- Falha ao iniciar o CLI do executor (`FileNotFoundError` / exit 127) **não** termina em `FAILED` imediato: tenta fallback e reentra no loop.
- `TimeoutError` do WriteLock / double-start MCP **não** marca a tarefa em andamento como `FAILED`.
- Issue `TEST-FAIL` é injetado no prompt do corrector quando a suite falha.
