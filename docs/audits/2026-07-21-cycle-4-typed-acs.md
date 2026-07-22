# Ciclo 4 — schema tipado de acceptance criteria (2026-07-21)

## Smoke pós-reload Cursor

| Check | Resultado |
|-------|-----------|
| `orchestrator_health` | `healthy` (v0.4.0, agentes claude/codex/opencode/kimi) |
| `orchestrator_analyze` | falhou com `asyncio.run` no loop MCP → **corrigido** neste ciclo |

## Entregue

| Item | Detalhe |
|------|---------|
| `CriterionKind` | `soma_module`, `tests_pass`, `docs_example`, `workspace_changes`, `evidence`, `custom` |
| `CriterionCheck` | `{kind, params}` — ex.: path/symbol para soma |
| `CriteriaBuilder` | emite kind+check tipados |
| `DeterministicValidator` | despacha por kind (não substring da description) |
| Migração | critérios antigos sem kind inferidos em `model_validate` / repository |
| MCP | `analyze` via `_run_coro` |

## Testes

```
49 passed (runtime pytest)
```

## Nota

Recarregue o Cursor novamente para o processo MCP carregar o runtime atualizado (analyze + kinds).
