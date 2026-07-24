# Cursor front controller

Status: **implementado**

O modelo ativo no chat do Cursor (Grok, Claude, Gemini, …) é o **front controller**.

O Orquestrador (RulesManager / Qwen opcional) é o **manager interno** do workflow.

```mermaid
flowchart TB
  subgraph cursor [Cursor chat]
    FC[Modelo ativo]
  end
  subgraph orch [Runtime]
    Mgr[Manager Rules/Qwen]
    Plan[Planner CLI]
    Exec[Executor CLI]
    Val[Validator CLI]
  end
  FC -->|orchestrator_run / delegate| Mgr
  Mgr --> Plan --> Exec --> Val
  Val -->|result| FC
```

## Decisão

| Situação | Ação |
|---|---|
| Dúvida conceitual / typo sem lógica (exceções em multiagent-orchestrator.mdc) | Resposta direta |
| Bug fix / mudança de lógica (qualquer tamanho) | `orchestrator_run` (default, sem pedir) |
| Plano / review pontual | `orchestrator_delegate` |
| Multi-arquivo, testes, validação | `orchestrator_run` |

Não simular CLIs. Não declarar sucesso sem `orchestrator_result`.
