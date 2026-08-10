# Task lifecycle

Estados:

```text
RECEIVED → ANALYZING → RETRIEVING_MEMORY → PLANNING → SELECTING_AGENTS
→ EXECUTING → TESTING → VALIDATING ⇄ CORRECTING
→ UPDATING_DOCUMENTATION → CONSOLIDATING → COMPLETED
```

Terminais: `COMPLETED`, `INCOMPLETE`, `FAILED`, `CANCELLED`, `WAITING_FOR_USER`.

## Resume de task órfã (0.4.76+)

`can_resume` aceita qualquer estado **não-terminal** — inclusive os do meio do
pipeline, onde a task fica quando o processo dono morre. Retomar de qualquer um
deles **reinicia** o pipeline pelo `ANALYZING`:

```text
RETRIEVING_MEMORY | PLANNING | SELECTING_AGENTS | EXECUTING | TESTING
| VALIDATING | CORRECTING | UPDATING_DOCUMENTATION | CONSOLIDATING  →  ANALYZING
```

O motivo aparece no histórico como `restart after orphan (<estado>)`, distinto
de `start analysis` (task nova) e `resume after user input` (voltou de
`WAITING_FOR_USER`).

Recomeçar, e não continuar de onde parou, é a única retomada honesta: quem estava
no meio não tem sessão de agente viva para retomar.

> **Estado terminal continua imutável.** `COMPLETED`, `INCOMPLETE`, `FAILED` e
> `CANCELLED` têm conjunto de saída **vazio** — a re-entrada nova é só do meio do
> pipeline. Até a 0.4.75 retomar de `VALIDATING` terminava
> `FAILED: Transição inválida: VALIDATING -> RETRIEVING_MEMORY` (bug-110,
> printbee `e9803cf77a43`).

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
