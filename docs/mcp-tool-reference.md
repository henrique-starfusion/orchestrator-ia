# MCP tool reference

Status: **implementado**

| Tool | Papel |
|---|---|
| `orchestrator_health` | Saúde + `runtime.code_fingerprint`/`features` (detectar MCP stale) |
| `orchestrator_analyze` | Análise read-only |
| `orchestrator_delegate` | Um papel em um CLI |
| `orchestrator_run` | Workflow completo; overrides `planner`/`executor`/`validator` têm precedência; resposta inclui `poll_hint` |
| `orchestrator_status` | Estado + `error` + `message` rica + `active_agent`/`active_role` + `blocking_issues` + `next_poll_after_seconds` |
| `orchestrator_events` | Eventos paginados (use se status parecer parado) |
| `orchestrator_result` | Resultado compacto (única fonte para declarar sucesso) |
| `orchestrator_cancel` | Cancelar |
| `orchestrator_resume` | Retomar |
| `orchestrator_message` | Resposta humana |
| `orchestrator_agents` | Registry |
| `orchestrator_memory_search` | Memória (sanitizada) |

Resources: `orchestrator://health`, `orchestrator://agents`, `orchestrator://tasks/{id}/…`

Prompts: `orchestrate_complex_task`, `delegate_planning`, `delegate_code_review`, `validate_implementation`, `investigate_failure`
