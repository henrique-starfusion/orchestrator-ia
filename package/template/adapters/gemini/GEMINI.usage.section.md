<!-- orchestrator:how-to-use -->
## Como usar o Orquestrador (vale para TODO agente: Claude, Codex, Gemini, Kimi, OpenCode, Cursor)

Este projeto tem o Orquestrador Multiagente instalado. Ele é o modo **padrão** de
trabalho para qualquer tarefa não-trivial — o usuário não precisa pedir.

### Antes de tudo: você é filho ou principal?

Se a variável de ambiente `ORCHESTRATOR_CHILD_AGENT` estiver definida, você **é**
um agente delegado: faça o trabalho INLINE e **nunca** delegue de novo (nem
orquestrador, nem subagentes) — delegar aninhado trava a execução.
Caso contrário, você é o agente principal e vale o resto deste bloco.

### Quando orquestrar (qualquer gatilho abaixo)

- Alterar código-fonte, mesmo 1 linha de lógica
- Corrigir bug (bug fix NUNCA é "trivial demais")
- Criar/alterar testes, build ou configuração
- Tarefa com critérios de aceitação, validação ou múltiplos arquivos

Resposta direta é permitida só para: dúvida conceitual, leitura de arquivo sem
edição, typo/comentário/formatação sem mudança de lógica.

### Como chamar

**Via MCP** (preferido quando as tools `orchestrator_*` estiverem disponíveis):
`orchestrator_run` → guarde `task_id` → `orchestrator_status` no intervalo de
`next_poll_after_seconds` → `orchestrator_events` se parecer parado →
`orchestrator_result` no fim. Só declare sucesso/fracasso após o `result`.

**Via CLI** (sempre funciona; use quando não houver MCP):

```bash
orchestrator run --prompt "<atividade com critérios de aceitação>"
orchestrator task list                  # tasks recentes e seus estados
orchestrator task status <task_id>      # estado, iteração, score, blockers
orchestrator task logs <task_id>        # saída dos agentes
orchestrator task resume <task_id>      # retomar task não-terminal
orchestrator version --json             # versão + code_fingerprint (detecta MCP stale)
```

Overrides úteis: `--executor <agente> --validator <agente> --max-iterations N`.
No Windows, **não** use `codex` como validator (trava por sandbox; use `claude`).

### Loops de execução

O pedido escolhe sozinho um roteiro com etapas obrigatórias e critérios próprios
— um prompt termina numa resposta, um loop termina num resultado verificado:

| Loop | Para quê | Etapas |
|---|---|---|
| `/loop-bug` | defeito | reproduzir → diagnosticar → teste que falha → corrigir na raiz → validar |
| `/loop-mvp` | ideia → app | planejar → construir → executar → corrigir → repetir até abrir |
| `/loop-landing` | página | oferta, copy, clareza, mobile, conversão → priorizar |
| `/loop-conteudo` | texto | ângulos → 3 variações → criticar → melhorar → escolher |
| `/loop-saas` | entrega ampla | produto → dev → marketing → validação → revisão final |

Para forçar um loop, comece o prompt com `/loop-<id>` (ou use `--loop <id>`).
Sem palavra-chave que case, nenhum loop é imposto.

O executor recebe automaticamente as **skills** e as **regras do projeto**
(`.cursor/rules/`, `.orchestrator/rules/`) mais relevantes ao pedido — mantenha
`description` no frontmatter das suas regras para que a seleção funcione.

### Acompanhe até o fim — não cancele por impaciência

Estados normais e o que esperar: `SELECTING_AGENTS` (~2 min), `EXECUTING`
(5–10 min, pode chegar a 30), `VALIDATING` (~7 min). Ficar minutos parado no
mesmo estado é **esperado**, não é travamento.

Antes de cancelar: rode `task status` e `task logs`. Se houver progresso, espere.
Cancelar e refazer inline desperdiça o trabalho já pago e é a maior causa de
tarefas perdidas nesta frota. Se cancelar mesmo assim, registre o motivo no
prompt da próxima task.

### O que NÃO vasculhar

`.orchestrator/backups/`, `.orchestrator/runtime/results/` e `.orchestrator/data/`
são artefatos gerados (dezenas de pastas) — ignore-os em buscas. A configuração
real está em `.orchestrator/config/`, `.orchestrator/agents/profiles/` e
`.orchestrator/skills/`.
