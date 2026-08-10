<!-- orchestrator:how-to-use -->
## Como usar o Orquestrador (vale para TODO agente: Claude, Codex, Gemini, Kimi, OpenCode, Cursor)

Este projeto tem o Orquestrador Multiagente instalado. Ele é o modo **padrão** de
trabalho para qualquer tarefa não-trivial — o usuário não precisa pedir.

### Antes de tudo: você é filho ou principal?

Se a variável de ambiente `ORCHESTRATOR_CHILD_AGENT` tiver **valor não-vazio e
diferente de `0`** (o runtime seta `1` nos filhos), você **é** um agente
delegado: faça o trabalho INLINE e **nunca** delegue de novo (nem
orquestrador, nem subagentes) — delegar aninhado trava a execução.
Vazia ou `0` — mesmo presente no ambiente — NÃO conta: você é o agente
principal e vale o resto deste bloco.

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
orchestrator task watch <task_id>       # ACOMPANHA ao vivo até terminar
orchestrator task resume <task_id>      # retomar task não-terminal
orchestrator version --json             # versão + code_fingerprint (detecta MCP stale)
```

Overrides úteis: `--executor <agente> --validator <agente> --max-iterations N`.
No Windows, **não** use `codex` como validator (trava por sandbox; use `claude`).

### Para ACOMPANHAR uma task, use `task watch` — não invente vigia

Existe **um** jeito padrão de seguir uma task rodando:

```bash
orchestrator task watch <task_id>
```

Ele transmite cada evento na hora, sai sozinho quando a task chega a estado
terminal e devolve código diferente de 0 se ela não terminou `COMPLETED` — mesmo
contrato do `run`. Opções: `--verbose` (inclui cada batida de heartbeat), `--all`
(reproduz o histórico), `--json` (uma linha JSON por evento, para outro agente
consumir), `--timeout N` (desiste de olhar; **não** cancela a task).

**NÃO escreva laço de shell para isso.** Nada de `until orchestrator task status`
com `sleep` dentro, nada de canalizar em `grep -q`, nada de `watch`. Isso já custou
caro: no trustsafe três tarefas de segundo plano ficaram vigiando a MESMA task
(`c210252e2c58`), cada uma com um `sleep` diferente, porque o pipe engolia a saída,
o painel ficava mudo entre os ciclos e a sessão recriava o vigia achando que tinha
travado. Um `task watch` resolve, e resolve uma vez.

Antes de criar QUALQUER acompanhamento, veja se já existe um rodando. Vigia
duplicado não duplica trabalho (é leitura), mas torna o painel ilegível — que foi
exatamente o problema.

`task status` continua sendo a foto pontual; `task watch` é o filme. Se só quer
saber se travou, `task status --text` já traz a linha `[VIVO]` com a idade do sinal
e se o PID dono está vivo.

### No Claude Code: dispare como TAREFA EM SEGUNDO PLANO

Uma task do orquestrador leva de 5 a 30 min. Em primeiro plano ela prende a
conversa inteira e o usuário fica sem ver nada acontecer. Rode o Bash com
`run_in_background: true`: o comando vira uma **tarefa em segundo plano** que o
usuário acompanha em `/tasks`, com a saída ao vivo gravada em arquivo, e você é
notificado quando termina — enquanto isso você continua trabalhando.

```
Bash({ command: 'orchestrator run --prompt "<atividade com critérios>"',
       run_in_background: true })
```

Regras que fazem a diferença entre acompanhar e ficar no escuro:

- **Não canalize a saída** (`| tail`, `| head`, `| Select-Object`, `> arquivo`):
  o pipe segura tudo até o fim e o painel fica mudo. Deixe transmitir e filtre
  o arquivo de saída depois.
- O retorno traz o caminho do arquivo de saída — leia esse arquivo para
  acompanhar o progresso, em vez de recriar a task.
- Só declare sucesso ou fracasso depois do estado terminal. `orchestrator run`
  sai com código ≠ 0 quando a task não termina `COMPLETED`.

Via MCP o `orchestrator_run` já volta na hora com o `task_id` (`wait=false` é o
padrão) — mas ele **não** cria a tarefa em segundo plano que aparece em
`/tasks`. Quando o usuário quiser ver o trabalho rodando, prefira o CLI em
background.

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

### Ao rodar comandos de terminal, mostre o que está acontecendo

Comando longo em segundo plano **sem saída visível** é indistinguível de travado —
foi o que fez tasks vivas parecerem congeladas nesta frota.

- **Não** encadeie a saída em `| tail`, `| head` ou `> arquivo` num comando longo:
  o pipe segura tudo até o fim e o painel fica mudo. Deixe transmitir e filtre depois.
- Reporte o que está rodando e o resultado — silêncio nunca é sucesso.
- Acompanhe até o fim: um processo em background sem ninguém olhando é trabalho perdido.

### O que NÃO vasculhar

`.orchestrator/backups/`, `.orchestrator/runtime/results/` e `.orchestrator/data/`
são artefatos gerados (dezenas de pastas) — ignore-os em buscas. A configuração
real está em `.orchestrator/config/`, `.orchestrator/agents/profiles/` e
`.orchestrator/skills/`.
