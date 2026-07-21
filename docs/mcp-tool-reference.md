# MCP tool reference

Status: **implementado**

| Tool | Papel |
|---|---|
| `orchestrator_health` | Saúde runtime/agentes |
| `orchestrator_analyze` | Análise read-only |
| `orchestrator_delegate` | Um papel em um CLI |
| `orchestrator_run` | Workflow completo (`routing=automatic` padrão) |
| `orchestrator_status` | Estado + polling hint |
| `orchestrator_events` | Eventos paginados |
| `orchestrator_result` | Resultado compacto |
| `orchestrator_cancel` | Cancelar |
| `orchestrator_resume` | Retomar |
| `orchestrator_message` | Resposta humana |
| `orchestrator_agents` | Registry |
| `orchestrator_memory_search` | Memória (sanitizada) |

Resources: `orchestrator://health`, `orchestrator://agents`, `orchestrator://tasks/{id}/…`

Prompts: `orchestrate_complex_task`, `delegate_planning`, `delegate_code_review`, `validate_implementation`, `investigate_failure`
