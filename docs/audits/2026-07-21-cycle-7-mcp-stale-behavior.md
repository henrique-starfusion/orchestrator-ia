# Ciclo 7 — comportamento do agente vs MCP stale (2026-07-21)

## O que a última conversa mostrou

1. Código e pytest locais corretos (`extract_requirements`, ACs de auditoria).
2. `orchestrator update --force` concluiu OK.
3. Commit/push feitos.
4. **Mas** `orchestrator_analyze` via MCP ainda devolveu requirements partidos e
   ACs antigos — o processo MCP do Cursor mantém módulos Python já importados.
5. O agente avisou “reload Cursor”, porém já tinha declarado o ciclo fechado
   sem probe MCP verde na sessão.

`VERSION` sozinha não detecta isso: stale e novo ambos reportam `0.4.1`.

## Ajustes

| Gap | Fix |
|-----|-----|
| Sem sinal de código carregado | `runtime.code_fingerprint` + `features` em `orchestrator_health` |
| `orchestrator --version` quebrava (ia pro installer) | `version` / `-V` / `--version` no `bin/orchestrator.js` |
| CLI sem fingerprint | `orchestrator version --json` / `orchestrator-runtime version --json` |
| Regra Cursor omissa | seção anti-MCP-stale em `multiagent-orchestrator.mdc` |
| planner==validator silencioso | warning `validator_equals_planner` no analyze |

## Contrato para o agente Cursor

Após alterar runtime: fingerprint CLI == fingerprint MCP **e** probe analyze OK,
senão pedir reload e **não** afirmar MCP verificado.
