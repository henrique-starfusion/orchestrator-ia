# Pre-cleanup inventory

**Branch:** `feature/call-agent-profiles`  
**Commit base:** `1171835`  
**Versão antes:** 0.3.0  
**Data:** 2026-07-21

## Arquitetura confirmada

```text
Cursor (front controller / MCP) → Runtime → Manager → Adapters CLI → testes → validação → docs → memória
Fonte canônica: .orchestrator/
```

## Baseline testes

| Suite | Resultado |
|---|---|
| Runtime pytest | 34/34 PASS |
| Instalador npm test | 14/14 PASS |

## Classes de itens

Ver `reference-analysis.md` e `removal-plan.md`.
