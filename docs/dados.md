# Dados

## Onde fica

Banco SQLite único por projeto, em `.orchestrator/data/orchestrator.db`
(`runtime/src/orchestrator_runtime/config.py:295`). O diretório é criado no
carregamento da configuração e recebe permissão `0700` em Unix, best-effort em
Windows (`config.py:208-214`).

O schema é declarado com SQLAlchemy em
`runtime/src/orchestrator_runtime/memory/database.py` e criado por
`Base.metadata.create_all` na primeira sessão
(`create_session_factory`, `memory/database.py:216-219`). **Não há ferramenta de
migração de schema**: alteração de coluna em base já existente não é aplicada
automaticamente. Registrado em `limitacoes.md`.

## Quem escreve

Todo acesso ao banco passa por `TaskRepository`
(`runtime/src/orchestrator_runtime/tasks/repository.py:39`). Nenhum outro módulo
instancia as classes `*Row` — verificado por varredura de cada classe do schema
em todo o pacote. Portanto, a coluna "quem escreve" abaixo cita o método do
repositório e o chamador real.

## Tabelas

### tasks

Uma linha por task. Chave primária: id de 12 caracteres hex
(`new_task_id`, `tasks/models.py:25`).

| Coluna | Tipo | Registra |
|---|---|---|
| `id` | String(32) | Identificador da task |
| `prompt` | Text | Pedido original, já reparado de mojibake |
| `project_path` | Text | Workspace; é a chave da fila |
| `task_type` | String(64) | Classificação (`implementation`, `docs`, `complex_analysis`, ...) |
| `languages_json` | Text | Linguagens detectadas |
| `risk`, `complexity` | String(32) | Risco e complexidade estimados |
| `requirements_json` | Text | Requisitos extraídos do prompt |
| `acceptance_criteria_json` | Text | ACs serializados, com `kind` e `check` |
| `constraints_json` | Text | Iterações, timeout, perfil, agentes forçados, `dry_run` |
| `status` | String(64) | Estado atual |
| `plan_json` | Text | Plano determinístico, com passos e fallbacks |
| `analysis_json` | Text | Análise, skills selecionadas, caller, digest, contexto de `requires_input` |
| `documentation_review_json` | Text | Resultado do gate documental |
| `iteration` | Integer | Iteração corrente |
| `last_score` | Float | Último score de validação |
| `cancel_requested` | Integer | Flag de cancelamento pedido |
| `error` | Text | Último erro, ou marcador `queued_behind:<id>|pos=N` |
| `created_at`, `updated_at` | DateTime | Timestamps |

Escrita por `create` (linha 124), `save` (linha 185) e `transition`
(linha 235). `save` tem duas guardas: não ressuscita task terminal a partir de
objeto stale em memória e nunca desfaz `cancel_requested`
(`tasks/repository.py:192-204`).

### task_events

Trilha completa do que aconteceu. Uma linha por evento, em ordem de id.

| Coluna | Registra |
|---|---|
| `task_id` | Task (indexado) |
| `timestamp` | ISO 8601 UTC |
| `type` | Um dos vinte valores de `EventType` (`events.py:13-35`) |
| `role`, `agent` | Papel e agente envolvidos, quando aplicável |
| `data_json` | Carga do evento: `summary`, `to`, `model`, `elapsed_s`, ... |

Escrita por `add_event` (linha 298), chamada por `transition` para
`state_changed` e diretamente pelo serviço para heartbeat
(`tasks/service.py:2778`) e eventos de dedup, fila e cancelamento.

Atenção operacional: **nem todo evento emitido no barramento é persistido.**
`EventBus.emit` só ecoa em stderr e chama handlers (`events.py:60-74`); a
gravação é uma chamada separada a `repo.add_event`. Vários pontos do serviço
emitem sem persistir. Registrado em `limitacoes.md`.

### task_iterations

Uma linha por iteração encerrada, com a decisão do manager.

| Coluna | Registra |
|---|---|
| `task_id`, `iteration` | Task e número da volta |
| `score` | Score da rodada |
| `status` | Ação decidida: `approve`, `correct`, `stop_incomplete`, `fail` |
| `notes_json` | Motivo, issues, ou o id da issue de infra |

Escrita por `add_iteration` (linha 424), chamada em três pontos:
falha de execução (`tasks/service.py:1065`), rejeição por infra
(`tasks/service.py:2414`) e fim normal da rodada (`tasks/service.py:1594`).

### agent_runs

Uma linha por invocação de CLI.

| Coluna | Registra |
|---|---|
| `task_id`, `role`, `agent`, `model` | Contexto da chamada |
| `command_json` | Argv completo executado |
| `cwd` | Diretório de trabalho |
| `started_at`, `finished_at` | Timestamps ISO |
| `exit_code`, `timed_out` | Desfecho do processo |
| `stdout`, `stderr` | Últimos 20000 caracteres de cada |
| `status` | `completed`, `failed` ou `timeout` |
| `changed_files_json` | Arquivos alterados, já enriquecidos pelo git |

Escrita por `add_agent_run` (linha 330), chamada em `_run_agent`
(`tasks/service.py:2889-2904`). Lida por `list_recent_agent_runs` (linha 335)
para o circuito de quarentena de agente (`tasks/service.py:2343-2362`).

### test_runs

Uma linha por comando de teste executado, incluindo a baseline.

| Coluna | Registra |
|---|---|
| `task_id` | Task |
| `command` | Comando executado |
| `category` | Categoria da descoberta (`unit`) |
| `exit_code`, `duration_s` | Desfecho |
| `stdout`, `stderr` | Saída |
| `status` | `passed`, `failed`, `skipped`, ... |
| `discovery_source` | Como o comando foi descoberto; a baseline entra com o prefixo `baseline:` (`tasks/service.py:992`) |
| `failure_kind` | `preexisting` quando a falha já existia antes da task |

Escrita por `add_test_run` (linha 398), chamada na baseline
(`tasks/service.py:988`) e após a execução (`tasks/service.py:1375`).

### validation_rounds

Uma linha por rodada de validação.

| Coluna | Registra |
|---|---|
| `task_id`, `iteration` | Contexto |
| `status` | `approved` ou `rejected` |
| `score` | Nota final da rodada, já aplicada a regra do mais rígido |
| `payload_json` | Validação inteira, incluindo `criteria`, `test_assessment` e `input_hashes` |

Escrita por `add_validation_round` (linha 403), chamada em
`tasks/service.py:1540`. O campo `input_hashes` traz sha256 por arquivo
alterado (até 20, ignorando ausentes e maiores que 2 MB) e o `HEAD` do git
(`_collect_input_hashes`, `tasks/service.py:80-114`) — é o que permite
reauditar exatamente o estado medido.

### validation_issues

Uma linha por issue bloqueante de cada rodada.

| Coluna | Registra |
|---|---|
| `task_id` | Task |
| `issue_id` | `VAL-00N`, `TEST-FAIL`, `AGENT-TIMEOUT`, `EXEC-SPAWN`, `AGENT-EMPTY-OUTPUT`, `AGENT-FAILED-NO-OUTPUT`, `VAL-IND`, ... |
| `severity` | Sempre `blocking` no caminho atual |
| `description` | Texto da issue |
| `resolved` | Default 0; **nenhum código atualiza esta coluna** |

Escrita por `add_validation_issue` (linha 408), chamada em
`tasks/service.py:1550`.

### routing_decisions

Uma linha por task, com o plano de papéis escolhido.

| Coluna | Registra |
|---|---|
| `task_id` | Task |
| `strategy` | Sempre `execute_review_repair` no roteador atual (`routing/manager.py:87`) |
| `decision_json` | Plano completo: papéis, agentes, fallbacks, teto de iterações |

Escrita por `add_routing_decision` (linha 413), chamada em
`tasks/service.py:844`.

### artifacts

Uma linha por artefato gravado em disco.

| Coluna | Registra |
|---|---|
| `task_id` | Task |
| `kind` | Hoje sempre `agent_output` (`tasks/service.py:2909`) |
| `path` | Caminho do `.txt` em `.orchestrator/runtime/results/<task_id>/` |
| `meta_json` | Metadados, vazio no caminho atual |

Escrita por `add_artifact` (linha 437). Lida por `list_artifacts` (linha 449),
que atende `orchestrator task artifacts`.

### memories

Memória do projeto, em duas espécies.

| Coluna | Registra |
|---|---|
| `task_id` | Task de origem, quando houver |
| `kind` | `episode` (resumo do desfecho) ou `learning` (aprendizado enriquecido) |
| `content` | Texto pesquisável |
| `meta_json` | Metadados; para `learning`, inclui `session_digest` |
| `created_at` | Timestamp |

Escrita por `save_memory` (linha 474), chamada por `_persist_episode`
(`tasks/service.py:3003`) e por `_learn_then_compact`
(`tasks/service.py:3054`). Lida por `search_memories` (linha 486) na fase
`RETRIEVING_MEMORY` (`tasks/service.py:823-825`) e pela tool MCP
`orchestrator_memory_search`.

A busca é um ranqueamento simples por contagem de termos sobre as 100 memórias
mais recentes (`tasks/repository.py:489-511`) — não é índice de texto completo.

### agent_performance

Uma linha por agente, acumulada ao longo do tempo (`agent` é único).

| Coluna | Registra |
|---|---|
| `agent` | Id do agente |
| `runs`, `successes`, `failures` | Contadores |
| `avg_duration_s` | Média móvel da duração |
| `last_score` | Último score da task em que participou |

Escrita por `update_agent_performance` (linha 513), chamada em
`_run_agent` (`tasks/service.py:2910-2915`). **Nenhum código lê esta tabela**:
o roteador não consulta desempenho histórico para escolher agente. A quarentena
usa `agent_runs`, não esta tabela.

### strategy_performance

Uma linha por estratégia (`strategy` é único), com contadores e score médio.

Escrita por `update_strategy_performance` (linha 532), chamada por
`_persist_episode` quando a estratégia é conhecida
(`tasks/service.py:3013-3016`). **Nenhum código lê esta tabela.** Como o
roteador só produz `execute_review_repair`, ela tende a ter uma única linha.

### documentation_updates

Uma linha por passagem pelo gate documental.

| Coluna | Registra |
|---|---|
| `task_id` | Task |
| `required` | Se a revisão era exigida |
| `reason` | Justificativa textual |
| `files_updated_json`, `files_reviewed_json` | Arquivos tocados e revisados |
| `validation` | `passed` ou `failed` |
| `payload_json` | Revisão completa |

Escrita por `save_documentation_update` (linha 459), chamada em
`tasks/service.py:1652`. **Nenhum código lê esta tabela**; o gate final consulta
`task.documentation_review`, que fica na tabela `tasks`.

### subtasks

Uma linha por subtarefa do fan-out.

| Coluna | Registra |
|---|---|
| `task_id` | Task-mãe |
| `role` | Sempre `executor` (`tasks/service.py:2746`) |
| `description` | Título da subtarefa |
| `status` | `merged`, `conflict`, `empty` ou `failed` |
| `payload_json` | Escopo, arquivos, erro e caminho do patch |

Escrita por `add_subtask` (linha 360) através de `_record_subtask`
(`tasks/service.py:2740`). **Só recebe linha quando o fan-out roda**, isto é,
com `allow_parallel_workspace_writes: true`. O comentário no repositório
registra que a tabela existia desde o primeiro schema e nunca recebeu uma linha
até a 0.4.61 (`tasks/repository.py:356-359`).

## Resumo: quem escreve e quem lê

| Tabela | Escrita quando | Lida por |
|---|---|---|
| `tasks` | Sempre | Todo o serviço, CLI e MCP |
| `task_events` | Transições e eventos selecionados | `task logs`, `orchestrator_events`, `orchestrator_status` |
| `task_iterations` | Fim de cada iteração | Ninguém no código atual |
| `agent_runs` | Cada invocação de CLI | Quarentena de agente (`list_recent_agent_runs`) |
| `test_runs` | Baseline e cada rodada de testes | Ninguém no código atual |
| `validation_rounds` | Cada validação | Ninguém no código atual |
| `validation_issues` | Cada issue bloqueante | Ninguém no código atual |
| `routing_decisions` | Uma vez por task, no PLANNING | Ninguém no código atual |
| `artifacts` | Cada saída de agente gravada | `task artifacts` |
| `memories` | Fim de task (episode e learning) | `RETRIEVING_MEMORY` e `orchestrator_memory_search` |
| `agent_performance` | Cada invocação de CLI | **Ninguém** |
| `strategy_performance` | Fim de task com estratégia | **Ninguém** |
| `documentation_updates` | Gate documental | **Ninguém** |
| `subtasks` | **Só com fan-out ligado** | `list_subtasks`, sem chamador no serviço |

Tabelas escritas e nunca lidas são material de auditoria: quem investiga uma
execução consulta direto o SQLite. Isso é registro, não defeito — mas é bom
saber que o runtime não toma nenhuma decisão a partir delas.

## Dados fora do banco

| Caminho | Conteúdo | Escrito por |
|---|---|---|
| `.orchestrator/runtime/results/<task_id>/<papel>-<agente>.txt` | stdout mais stderr do agente | `tasks/service.py:2905-2908` |
| `.orchestrator/runtime/patches/<task_id>/<sub>.patch` | Patch de subtarefa do fan-out, inclusive os que conflitaram | `tasks/service.py:2650-2673` |
| `.orchestrator/runtime/locks/workspace.write.lock` | PID e timestamp do dono do lock | `execution/locks.py:91-93` |
| `.orchestrator/memory/episodes/<task_id>.md` | Resumo legível do episódio | `_export_memory_markdown`, `tasks/service.py:3094` |
| `.orchestrator/memory/learnings/` e `index.json` | Aprendizado durável por task | `memory/learnings.py` via `tasks/service.py:3062-3063` |
| `.orchestrator/memory/legacy-import/INDEX.md` | Índice de skills e regras importadas, marcado como requires-review | `_write_legacy_import_index`, `tasks/service.py:323` |
| `.wolf/STATUS.md` e `.wolf/cerebrum.md` | Estado e Do-Not-Repeat do projeto | `memory/learnings.py` via `tasks/service.py:3066-3068` |

Os `.txt` de `results/` são truncados em `truncate_result_artifacts_chars`
depois — e nunca antes — de o learning estar em disco
(`tasks/service.py:3076-3084`).

## Privacidade dos registros

`stdout` e `stderr` gravados em `agent_runs` e nos `.txt` passam por `redact`
(`agents/process.py:68-77`): linha contendo `API_KEY`, `TOKEN`, `SECRET`,
`PASSWORD` ou `AUTHORIZATION` junto de `=` ou `:` vira `[REDACTED]`. É um filtro
por padrão textual, não uma garantia formal: segredo em formato diferente passa.
Registrado em `limitacoes.md`.
