# Changelog

## Unreleased

## 0.4.85 - 2026-08-12

### Added

- **Issue #15 — boundaries internas do Engine sem reorganização física.**
  `engine.core`, `engine.agents`, `engine.memory`, `engine.persistence`,
  `engine.server`, `engine.cli` e `engine.mcp` passam a ter consumidores
  autorizados explícitos, preservando todos os caminhos atuais
- As 18 arestas legadas que já contrariavam a tabela permanecem numa lista
  exata e justificada; exceção sem motivo ou que deixou de representar uma
  violação também quebra o teste

### Tests

- `runtime/tests/unit/test_0485_engine_internal_boundaries.py` percorre todos os
  módulos Python com `ast`, monta o grafo de imports internos e informa arquivo,
  linha e regra em cada violação

## 0.4.84 - 2026-08-11

### Added

- **Issue #9 — publicação derivada da documentação na Wiki.**
  `scripts/Publish-Wiki.ps1` transforma cada Markdown de `docs/` em página,
  gera `Home` a partir do índice, separa material-base de histórico e converte
  links de documentos para a Wiki e links do repositório para URLs `blob`
- A publicação clona a Wiki em diretório temporário e só cria commit/push quando
  há mudança real; execução consecutiva idêntica não produz commit
- `.github/wiki-sync.yml.disabled` preserva a automação futura fora de
  `.github/workflows/`, pois Actions segue indisponível na conta
- `docs/documentation-policy.md` formaliza `docs/` como fonte da verdade, a Wiki
  como derivada e a sobrescrita de edições manuais

### Tests

- `tests/Test-WikiPublishing.ps1` cobre link relativo entre documentos, caminho
  `docs/...`, arquivo de código, URL externa, página histórica e geração da Home

## 0.4.83 - 2026-08-11

### Added

- **Issue #12 — regra de desenvolvimento "nunca supor".** Afirmações técnicas
  passam a exigir verificação no código, medição ou consulta à fonte oficial,
  com evidência citada junto da conclusão e números no lugar de adjetivos
- A regra canônica `.orchestrator/rules/nunca-supor.md` é selecionada por termos
  distintivos da `description`; o template e o manifest a propagam como arquivo
  `managed` para projetos novos e existentes

### Tests

- `runtime/tests/unit/test_0483_never_assume_rule.py` prova descoberta,
  frontmatter distintivo e seleção por pedido que exige evidência

## 0.4.82 - 2026-08-11

### Fixed

- **bug-119 — CLI de agente órfão sobrevivia ao runtime que o lançou.** Os PIDs
  dos CLIs ficavam num set em memória (`CliExecutor._active_pids`), lido por um
  único consumidor: `kill_active()`, chamado só de `TaskService.cancel`. O
  rastreador existia enquanto existisse o processo que o criou — então ele cobria
  exatamente o caso em que o runtime está vivo, e órfão é por definição o caso em
  que ele já não está. Crash, `taskkill`, restart do editor ou fim abrupto do
  terminal deixavam os CLIs vivos sem que nenhum código do orquestrador soubesse
  que existiam. `agent_runs` não ajudava: a linha só nasce quando o processo
  termina e a tabela nunca teve coluna de PID
- Nova tabela `agent_processes` registra, no instante do lançamento, a
  identidade recuperável de cada CLI: `pid`, `image`, `create_time`, `owner_pid`,
  `task_id` e `started_at`. A linha sobrevive à morte do runtime, que é o ponto
  todo
- `TaskService._reap_orphan_agents` ceifa a sobra a partir dos pontos de poll que
  já existiam (`status`, `list_tasks`, `follow_events`, `create_task`) — o mesmo
  padrão da adoção de task órfã do bug-085 e do bug-113. **Sem daemon, sem
  processo novo, sem thread de poll periódico**
- **Proteção contra reuso de PID.** Windows recicla número de processo, então
  matar por número é destrutivo. Antes de qualquer kill a identidade ATUAL do PID
  é lida do próprio sistema operacional (Windows: `GetProcessTimes` +
  `QueryFullProcessImageNameW`; Linux: `/proc/<pid>/stat`) e precisa conferir nos
  DOIS campos — nome da imagem e instante de criação. Identidade divergente, ou
  ilegível, encerra o assunto: ninguém morre
- Só é ceifado o que satisfaz tudo junto: PID registrado pelo orquestrador,
  identidade conferida, task dona terminal **ou** runtime dono morto, e
  `orphan_agent_reap_after_s` (120s, negativo desliga) vencido desde o lançamento
- A ceifa é idempotente entre pollers concorrentes: a reivindicação grava
  `reaped_at` numa transação única, sob gate de thread e lock de arquivo curto
- `kill_active()` no cancelamento segue exatamente como estava — a ceifa é
  adição, e cobre o caminho que ele nunca pôde cobrir
- O registro passa a valer em **todo** ponto que fabrica executor, não só no
  despacho comum: o fan-out cria um `CliExecutor` novo por subtarefa
  (`_subtask_executor`) e executor novo nasce sem `on_launch`, então os CLIs mais
  numerosos — N subtarefas em paralelo, o cenário dos 338 processos — ficavam
  fora do registro e, por consequência, fora da ceifa

### Tests

- `runtime/tests/unit/test_0482_orphan_agent_reaper.py` — 16 casos com
  **processos reais**: órfão de runtime morto é ceifado; PID reciclado por outro
  programa **não** é morto (divergência de instante de criação e, em teste
  separado, de nome de imagem); agente de task em execução com dono vivo é
  intocado; limiar de tempo protege lançamento recente; a ceifa é idempotente
  entre dois serviços sobre o mesmo banco; o poll de `status` dispara a ceifa; o
  lançamento persiste identidade e a saída fecha o registro; o executor de
  subtarefa do fan-out persiste o lançamento e seu CLI órfão é ceifado;
  `kill_active()` sem regressão

## 0.4.81 - 2026-08-11

### Fixed

- **bug-117 — sync do pacote truncava a história do clone do dono.**
  `Sync-PackageSource` executava `fetch --depth 1` em todo `PackageRoot`, mesmo
  quando ele era um clone completo de desenvolvimento. O Git criava
  `.git/shallow`, `rev-list` passava a enxergar só o tip e o `merge --ff-only`
  seguinte podia recusar histórias sem ancestral comum
- O sync consulta `rev-parse --is-shallow-repository` antes do fetch. Clone
  completo usa fetch sem limite de profundidade e mantém `merge --ff-only`;
  clone já shallow conserva `--depth 1`, avança para `FETCH_HEAD` sem aprofundar
  e imprime aviso com `git fetch --unshallow origin`
- O cache existente de `get.ps1` aplica a mesma decisão pelo estado real. Clone
  novo e descartável continua usando `clone --depth 1`

### Tests

- `Test-PackageSyncHistory.ps1` cria origin e clones reais descartáveis para
  provar preservação de história completa, avanço ff-only, atualização shallow,
  aviso de recuperação e economia de banda na instalação nova

## 0.4.80 - 2026-08-11

### Fixed

- **bug-116 — entregável invisível em árvore já suja.** `GitBaseline` guardava
  apenas `path -> código XY` do `git status --porcelain`. Se o arquivo já estava
  ` M` e a task o editava de novo, o rótulo continuava ` M`; se a task restaurava
  o conteúdo original, o path sumia do status. Os dois casos devolviam
  `changed_files=[]`, alimentando falsos `AGENT-EMPTY-OUTPUT`,
  `AGENT-FAILED-NO-OUTPUT` e reprovação de `workspace_changes`
- O baseline agora guarda SHA-256 **somente dos paths já sujos** e o comparador
  comum combina mudança de XY com mudança de conteúdo. O mesmo helper atende
  raiz e repos aninhados; path sujo intocado não é creditado à task

### Performance

- Nenhuma árvore inteira é hasheada. Paths limpos no baseline continuam
  detectados pelo porcelain; só entradas que já aparecem sujas recebem hash,
  inclusive dentro de repos filhos imediatos

### Tests

- Nove regressões cobrem segunda edição, restauração e arquivo intocado em raiz
  e repo aninhado, além de preservar criação, modificação e exclusão após
  baseline limpo

## 0.4.79 - 2026-08-11

Duas mudanças na mesma área — o controle de execução do agente —, ambas
adotadas do LangGraph depois de ler o código (`libs/langgraph/langgraph/types.py`:
`TimeoutPolicy` e `RetryPolicy`).

O orçamento do agente era um número só por papel, teto de relógio puro: um
agente que morreu mudo no segundo 5 e um agente que produz saída sem parar eram
tratados igual. E o backoff do retry de lançamento tinha intervalos fixos, o que
faz processos que falharam juntos voltarem juntos, contra o mesmo recurso
escasso.

### Fixed

- **bug-114 — política de execução em DOIS EIXOS por papel.**
  `agent_timeout_by_role` aceita agora `{"run_timeout": N, "idle_timeout": M}`
  além do inteiro de sempre. `run_timeout` é o teto de relógio da tentativa e
  **nunca** é renovado por sinal nenhum; `idle_timeout` é o tempo máximo sem
  progresso observável, renovado pelo sinal que o runtime já emite (byte lido no
  stream, ou mudança no workspace pela sonda). Ponto único de decisão em
  `execution/timeouts.resolve_agent_timeout_policy`; o eixo duro alimenta o
  `proc.wait` do CLI e o ocioso alimenta o watchdog de silêncio (bug-086)
- Encerramento por ociosidade entra no fluxo de **infra** que já existia
  (`AGENT-NO-OUTPUT-HANG` → `_reject_iteration_infra`), nunca como rejeição de
  mérito, e o texto passa a dizer *sem sinal de vida (idle_timeout=Ns) … falta de
  sinal — infra, não qualidade do trabalho*
- **bug-115 — jitter no backoff do retry de lançamento.** `_LAUNCH_RETRY_BACKOFF_S`
  continua `(3, 8, 15)`, mas a espera final é `base × (1 + 0,5 × sorteio)` — fica
  em `[base, base×1,5)`, nunca encurta e nunca estica sem teto (26 s no total
  viram no máximo 39 s). A fonte de aleatoriedade é injetável
  (`_launch_retry_rand`) para o teste ser determinístico. A guarda de orçamento
  compara contra a espera **já com jitter**: comparar contra a base e dormir o
  sorteado furaria o `maximum_duration_seconds` da task

### Changed

- `policies.json` (template) passa a declarar `executor` e `corrector` com
  `idle_timeout: 1200`. O número é folgado de propósito: a referência é o
  `agent_no_output_timeout_s` global de 900 s (bug-086), o único valor desta
  frota medido em produção sem matar trabalho legítimo, e estes são os dois
  únicos papéis com teto duro de 2400 s que passam trechos longos lendo sem
  imprimir. Enterrar um agente morto 300 s depois custa 12 % do teto dele; matar
  um agente vivo custa a task inteira

### Unchanged

- **Retrocompatível.** Papel declarado como inteiro puro vira `run_timeout` com
  `idle_timeout` nulo, e nulo cai no `agent_no_output_timeout_s` global —
  comportamento idêntico ao da 0.4.78. O merge do template é aditivo, então
  `policies.json` já existente não é reescrito
- `minimum_task_budget_s` e a aritmética do bug-104 seguem derivados dos tetos
  **duros**: o eixo ocioso não gasta orçamento, só interrompe mais cedo quem
  parou de dar sinal
- Nada mudou no laço de validação, em `same_issue_repeat_limit`, em
  `maximum_iterations` nem na detecção de loop. Nenhum daemon, thread de poll
  periódico ou processo de background novo

## 0.4.78 - 2026-08-10

Uma task podia permanecer `QUEUED` para sempre quando o processo que a
enfileirou saía e o dono do workspace morria antes de executar o handoff. Não
havia recuperação: `_maybe_start_next` dependia do `finally` de outro
`run_task`, enquanto a adoção do bug-085 examinava somente `RECEIVED`.

### Fixed

- **bug-113 — adoção de órfã cobre `QUEUED`.** `status`, `list_tasks`,
  `follow_events` (`task watch`) e `create_task` tentam recuperar a cabeça FIFO
  depois de `orphan_queued_adopt_after_s` (padrão 120 s)
- A recuperação exige, em conjunto: bloqueador registrado terminal ou nenhuma
  task ativa; admissão normal por `_blocking_task_id` (teto + escopo); e a
  candidata ser a primeira da fila. Cabeça bloqueada nunca é pulada pelo
  adotador, ainda que uma task posterior tenha escopo disjunto
- Uma lease em `updated_at`, gravada sob `queue.adopt.lock`, e o set local
  `_adopted` tornam polls concorrentes idempotentes. O estado continua `QUEUED`
  até a thread existente entrar em `run_task`; se o processo morrer antes, a
  lease expira e outro poll pode tentar novamente

### Unchanged

- Nenhum daemon, processo ou thread periódica foi criado. A execução reutiliza
  `_start_background`; o contrato de código de saída de `orchestrator run` não
  mudou. A adoção de `RECEIVED` do bug-085 permanece ativa

## 0.4.77 - 2026-08-10

Dez tasks de revisão/documentação morreram `INCOMPLETE` em produção porque
vocabulário negado ou descritivo de defeito impôs o loop de bug e seus gates de
código a entregas que não alteravam código.

### Fixed

- **bug-112 — detecção de loop respeita negação.** A pontuação ignora cláusulas
  estreitas iniciadas por `não`/`nao`/`not`, incluindo `não é`, `não se trata
  de`, `this is not` e `não reescreva`, no mesmo estágio que já ignora
  condicionais desde o bug-045
- **Review não vira bug por vocabulário adversarial.** Quando `review` e `bug`
  coexistem, `bug` só prevalece com intenção explícita verbo+defeito, como
  `corrigir os dois defeitos que a revisão apontou`; citar `erro` e `falha` no
  que deve ser conferido preserva o loop `review`
- **Rede de segurança loop×task type.** Tasks `docs`, `complex_analysis`,
  `security_review`, `architecture` e `review` não recebem gates bloqueantes
  `workspace_changes`/`tests_pass` herdados de loop de código. Loop incompatível
  não entra no plano; o entregável real fica sob critério `evidence`. Critérios
  declarados pelo usuário continuam com precedência

### Unchanged

- `same_issue_repeat_limit` e `maximum_iterations` não mudaram: encerravam a
  repetição corretamente; o defeito era o critério impossível que se repetia

## 0.4.76 - 2026-08-10

Dois defeitos de runtime confirmados em produção na 0.4.75 — os dois matavam a
task com um texto que **parece mérito** e era infra.

### Fixed

- **bug-110 — retomar uma task órfã deixa de matá-la.** No printbee (task
  `e9803cf77a43`, 10/08 19:50) o processo dono morreu com a task em `VALIDATING`;
  o resume terminou `FAILED` com
  `Transição inválida: VALIDATING -> RETRIEVING_MEMORY`. `can_resume` aceita
  qualquer estado não-terminal, mas o loop só transicionava para `ANALYZING`
  vindo de `RECEIVED`/`WAITING_FOR_USER` — retomando do meio ele pulava a
  re-entrada, seguia o fluxo e batia numa aresta que não existe. Agora retomar de
  **qualquer** estado de meio de pipeline (`RETRIEVING_MEMORY`, `PLANNING`,
  `SELECTING_AGENTS`, `EXECUTING`, `TESTING`, `VALIDATING`, `CORRECTING`,
  `UPDATING_DOCUMENTATION`, `CONSOLIDATING`) **reinicia** o pipeline pelo
  `ANALYZING`. Quem estava no meio não tem agente vivo para continuar de onde
  parou — recomeçar é a única retomada honesta
- **bug-111 — falha de lançamento de processo para de queimar iteração.** No
  trustsafe, 5 tasks morreram `INCOMPLETE` em 10/08 (`86b3abcb5cfa`,
  `517010995d91`, `22a07ed7e2de`, `c0e98dde9f27`, `e89063f15776`) com
  `AGENT-FAILED-NO-OUTPUT: corrector/codex exit=3221225794 sem mudancas` — e uma
  com `opencode`, **mesmo exit code**. `3221225794` = `0xC0000142`
  (STATUS_DLL_INIT_FAILED): o processo **não nasceu**, com ~132 processos `node`
  vivos na máquina. Desde a 0.4.72 isso já era classificado como `launch`, mas o
  serviço só emitia o evento e devolvia a mesma falha: ela caía no guard
  `failed_no_output`, **queimava uma iteração** e disparava fallback para outro
  agente — que também não nascia, porque a falta de recurso era da **máquina**.
  `same_issue_repeat_limit` estourava e a task morria sem nenhum julgamento de
  mérito. Agora falha de lançamento **espera e reexecuta o MESMO agente** com
  backoff (3 s, 8 s, 15 s), respeitando o orçamento restante da task

### Changed

- Cada tentativa de reexecução emite `AGENT_REPAIR` com `retry_attempt`,
  `backoff_s` e o desfecho (`retry_ok`, `retry_exhausted` ou
  `retry_skipped: budget`) — aparece em `task logs`, que é onde se investiga
  depois que o processo morreu

### Known

- **Nada é reinstalado** no caminho de lançamento, de propósito: a reinstalação
  já foi medida falhando com o **mesmo** exit code. Se o próprio reparo não
  nasce, insistir é desperdício certo
- Esgotadas as três tentativas, o resultado devolvido continua sendo a falha —
  **infra, nunca mérito**. A task ainda termina `INCOMPLETE`, mas dizendo que foi
  a máquina
- Estado terminal segue **imutável**: `COMPLETED`/`INCOMPLETE`/`FAILED`/
  `CANCELLED` continuam com conjunto de saída vazio. A re-entrada nova é só do
  meio do pipeline para `ANALYZING`

## 0.4.75 - 2026-08-10

Pedido do dono: *"precisamos padronizar para as coisas não serem inventadas e sim
planejadas"*. O gatilho foi concreto — no trustsafe apareceram **três** tarefas de
segundo plano vigiando a **mesma** task (`c210252e2c58`), cada uma com um
`until … sleep` escrito à mão e com intervalo diferente (120 s, 150 s, 150 s). Não
era task duplicada: era o **vigia** duplicado. O `| grep -qE` engolia a saída, o
painel ficava mudo entre os `sleep`, e a sessão recriava o vigia achando que a task
tinha travado.

### Added

- **`orchestrator task watch <id>`** — acompanha ao vivo até terminar. Transmite
  cada evento na hora (sem pipe, sem `sleep` do chamador), sai sozinho no estado
  terminal e devolve código ≠ 0 se não terminou `COMPLETED`, mesmo contrato do
  `run`. Uma tarefa de segundo plano precisa disparar isso **uma vez**
- `--verbose` inclui cada batida de heartbeat; `--all` reproduz o histórico;
  `--json` emite **JSONL** (uma linha por evento) para outro agente consumir;
  `--timeout N` desiste de olhar e diz explicitamente que a task **não** foi
  cancelada
- `TaskService.follow_events()` e `TaskRepository.list_events_since()`: o cursor de
  eventos que faltava. `list_events` devolvia a task inteira e sem id, então não
  havia como pedir "só o que chegou depois" — e era essa falta que empurrava cada
  sessão para o laço de shell
- `watch.py` com a formatação testável (linha por evento, linha `[VIVO]`, filtro do
  heartbeat repetitivo)

### Changed

- **As regras dos seis adaptadores** (claude, codex, gemini, kimi, opencode,
  cursor) passam a mandar usar `task watch` e a **proibir** laço de shell para
  acompanhar, citando o incidente. A padronização é o ponto: sem uma instrução
  escrita onde o agente lê, cada sessão inventa a sua

### Known

- O heartbeat fica fora da saída por padrão: ele repete a mesma frase a cada
  20-30 s e, sozinho, é o ruído que faz o dono parar de ler a tela. `--verbose`
  traz tudo
- `task watch` é **somente leitura**. Sair dele (Ctrl-C, `--timeout`) nunca toca na
  task — as duas saídas dizem isso na tela, porque "desisti de olhar" e "cancelei"
  são fáceis de confundir e a confusão custaria o trabalho

## 0.4.74 - 2026-08-10

Pedido do dono: *"quero que o orquestrador execute mais de 1 tarefa no mesmo
projeto; o que temos que garantir é que 2 agentes não mexam no mesmo código"*.

### Added

- **`max_parallel_tasks`** (3 no template, **1 restaura a 0.4.73**). Até agora o
  projeto era serializado por inteiro — uma task ativa, as outras em QUEUED, e a
  segunda esperando 25 a 40 min. O que precisa ser exclusivo não é o projeto, é o
  **código**: duas tasks em pastas diferentes nunca se atrapalham
- **Escopo de arquivos por task** (`execution/scopes.py`). Duas tasks só rodam
  juntas com escopos **comprovadamente disjuntos**. Comparação por segmentos de
  caminho, nunca textual: `src/auth` não colide com `src/authz`
- `orchestrator run --scope src/api --scope tests/api` (repetível). Sem `--scope`,
  o escopo sai dos caminhos que o **próprio pedido nomeia** e que existem no
  projeto; pedido sem caminho nenhum fica sem escopo
- Degradação **`scope_violation`** no `status`/`result`: agente que escreveu fora
  do escopo declarado
- Lock próprio para o **`TESTING`**. Escopo disjunto separa código, não recurso de
  máquina — duas suítes no mesmo diretório disputam build dir, cache e porta, e a
  falha resultante não existe no código de nenhuma das duas
- Features de diagnóstico: `parallel_tasks_per_project`, `file_scope_admission`,
  `scope_violation_reported`, `per_task_run_context`, `sqlite_wal_multi_writer`

### Fixed

- **Estado do run vivia no serviço.** `_run_ctx`, `_git_baseline`,
  `_loop_started_monotonic`, `_exhausted_models` e `_current_agent` eram atributos
  de `TaskService`, e `_execute_loop` reatribuía os quatro primeiros no topo. Como
  o servidor MCP roda todas as tasks no mesmo processo, a task B **zerava** o
  relógio, o baseline git e o contexto da A — arquivo mudado atribuído à task
  errada, orçamento contado do início errado, learning gravado com contexto de
  outra. Sem erro nenhum. Agora `TaskRunContext` por task
- **SQLite sem WAL.** O default (`journal_mode=delete`) trava o arquivo inteiro
  por escrita: o segundo escritor levaria `database is locked` na hora. Agora WAL
  + `busy_timeout=15s` + `synchronous=NORMAL`. Efeito colateral medido: a suíte
  caiu de 154 s para 88 s
- **Executor era compartilhado.** `on_heartbeat` e `progress_probe` são atributos
  do executor: a segunda task a despachar um agente reescrevia o callback da
  primeira e trocava a sonda de silêncio dela — e a sonda é o que decide se um
  agente calado está morto (bug-086). Executor por task quando há concorrência;
  com teto 1 segue o compartilhado, intocado
- **Sonda do watchdog e `changed_files` por escopo.** A sonda olhava a árvore
  inteira: com duas tasks, a A veria a escrita da B e concluiria que o próprio
  agente pendurado está trabalhando — a prova do bug-086 virada do avesso
- **Reaper com pid por task.** `owner_alive` vinha do pid no write lock,
  calculado **uma vez** e aplicado a todas as tasks. Agora vem do
  `loop_progress`, cuja primeira batida passou a sair no instante em que o loop
  começa; o lock continua como ponte para processos ainda na 0.4.73
- Rota de `TimeoutError` girava para sempre: a task era enfileirada e o `finally`
  a desenfileirava na mesma hora. Até a 0.4.73 o `held_lock` protegia disso por
  acidente

### Changed

- **O loop não segura mais o write lock do workspace.** Segurá-lo por 25-40 min
  *era* a serialização do projeto. Quem usava a existência daquele arquivo de lock
  como "alguém está trabalhando" precisa passar a olhar `loop_progress`
- Dequeue puxa **tudo que couber**, não uma por vez, e não pára na primeira
  recusa: FIFO estrito deixaria vaga ociosa por causa de uma task que não pode
  entrar

### Known

- **A garantia é admissão + detecção, não impossibilidade.** Com tudo na branch
  local, o runtime impede duas tasks de escopos sobrepostos serem admitidas
  juntas, mas não impede o agente de escrever fora do escopo depois de admitido —
  isso é medido (`scope_violation`), não bloqueado. A disciplina de
  `_git_hygiene_block()` (bug-077: seis quase-arrastões num dia no printbee) deixa
  de ser precaução e passa a ser condição de funcionamento
- **Escopo vazio serializa.** É a regra que sustenta o resto: sem prova de
  disjunção não há vaga. Na prática, task cujo pedido não nomeia caminho nenhum se
  comporta como na 0.4.73 — quem quer paralelismo garantido passa `--scope`
- A inferência de escopo é **deliberadamente burra**: só caminho que aparece
  literalmente no pedido e cuja pasta de topo existe. Adivinhar aqui não é
  cosmético — o escopo é o que AUTORIZA duas tasks a rodarem juntas, e um escopo
  inventado com confiança liberaria exatamente o par que não podia
- Teto 3 é máximo, não promessa: cada task gasta ~6 invocações de CLI, e foi
  exaustão de recurso que produziu o `0xC0000142` do bug-109

## 0.4.73 - 2026-08-10

Pedido do dono depois de três investigações manuais para concluir "não travou":
*"quero poder saber o que está ocorrendo, acompanhar o processamento do agente"*.

### Added

- **Heartbeat do loop** (`loop_progress`). O `agent_progress` da 0.4.28 só existe
  enquanto um CLI está no ar. Nos vãos — escolha de agentes, consolidação,
  gravação de memória, gate de documentação, a troca de uma etapa para a seguinte
  — **nada** era emitido, e `updated_at` só muda em transição de estado. Quem
  olhava `task status` nesses vãos via a mesma linha por minutos, sem como
  distinguir fase legítima de processo morto: printbee `8e4329205f01` e trustsafe
  `e89063f15776` pareceram travadas enquanto trabalhavam, e a resposta exigiu ler
  o log inteiro e conferir o PID à mão. Agora uma thread daemon bate durante toda
  a execução com `phase`, `phase_elapsed_s`, `elapsed_s`, `iteration`, `pid` e
  `agent_active` — e diz **quem** está no ar (ou quem acabou de sair)
- Bloco `live` no `status` (e no `orchestrator_status`): sinal usado, idade do
  sinal, fase, idade da fase, se há agente no ar e se o **PID dono está vivo**.
  `task status --text` imprime a linha `[VIVO] ...`
- `TaskRepository.last_event()`, com filtro por tipo — o `status` é o evento mais
  frequente da frota e não pode ler a task inteira para olhar o último sinal
- Features de diagnóstico: `loop_heartbeat_between_agents`,
  `status_answers_is_it_alive`

### Changed

- Cadência do heartbeat do loop = a do perfil do chamador (20 s bloqueante, 30 s
  polling), com piso de 10 s (`LOOP_HEARTBEAT_MIN_S`)

### Known

- **O reaper ignora `loop_progress` de propósito.** A batida nasce de uma thread
  do processo dono e continuaria batendo com o loop travado num lock — contá-la
  como progresso trocaria a fila parada de 11 h do bug-090 por uma eterna. Ela
  prova que o **processo** vive, não que o trabalho anda. A decisão do reaper
  fica exatamente como estava na 0.4.72
- Corolário: uma fase longa e legítima **sem agente no ar** continua sujeita ao
  reaper como antes. O ganho aqui é o dono ver o que está acontecendo, não o
  runtime tolerar mais silêncio
- `_current_agent` guarda a última etapa despachada, não a etapa ativa: quando
  nenhum agente está no ar a batida diz "entre etapas (última: X)". Distinguir
  isso de "X ainda rodando" vem de `agent_active`, que lê os PIDs vivos do
  executor

## 0.4.72 - 2026-08-10

Achado observando a frota rodando, não lendo código.

### Fixed

- **bug-109** — processo que **não nasceu** era tratado como CLI quebrado. No
  trustsafe (task `22a07ed7e2de`) `corrector/codex` e `corrector/opencode`
  saíram `exit=3221225794` (`0xC0000142` STATUS_DLL_INIT_FAILED) em **0 s** com
  zero byte nos dois streams. Sem saída nenhuma, o classificador caiu na regra
  do fast-fail mudo e devolveu `install`; o auto-reparo tentou reinstalar os dois
  — e **a própria reinstalação falhou com o mesmo exit code**
  (`repair_ok: false`). Quatro lançamentos de processo falharam em ~1 s: o sinal
  era da máquina, não do CLI. Quarta categoria `launch`, avaliada **antes de
  qualquer marcador** (é justamente a ausência de saída que empurrava isto para
  `install`), exigindo as três condições juntas: NTSTATUS da família de falta de
  recurso, morte em ≤ 15 s e nenhuma saída. Não reinstala e sobe como degradação
  `agent_launch_failed`, cuja ação fala de **máquina**, não de CLI
- Feature de diagnóstico: `launch_failure_not_reinstall`

### Changed

- `failure_kind` do evento `agent_repair` ganha um quarto valor, `launch`, agora
  acompanhado de `exit_code`
- `service_outages()` e a nova `launch_failures()` passam a compartilhar
  `_repair_events_by_kind()`; ambas devolvem também `exit_code`

### Known

- Escopo estreito de propósito: access violation (`0xC0000005`) e stack overrun
  (`0xC0000409`) ficam **fora** de `LAUNCH_FAILURE_EXIT_CODES` — aqueles são
  crash de binário, onde reinstalar pode de fato resolver
- A exaustão de recurso observada foi provavelmente causada pela carga da própria
  sessão (suítes completas + propagação + monitor em paralelo). A classificação
  está errada independentemente da causa, mas o episódio **não** é evidência de
  que a frota sofra disso em operação normal

## 0.4.71 - 2026-08-10

Auditoria das tasks `COMPLETED` da frota. O modo de falha mais documentado de
agente de código é **declarar sucesso independente do que aconteceu** — e o
runtime tinha um caminho que fazia exatamente isso.

### Fixed

- **bug-108** — `orchestrator run` estava **quebrado em toda a frota** desde a
  0.4.66. O helper `_drain_queue` (bug-098) foi inserido logo abaixo do
  `@app.command("run")` e **engoliu o decorator**: o typer registrou o helper
  como o comando `run` e o `run_cmd` real ficou órfão. O sintoma era
  `Usage: run [OPTIONS] {service} {json_out}` / `No such option: --prompt`.
  Duas releases saíram assim, e **nenhum dos 555 testes pegou** — a suíte
  exercitava `TaskService` direto e nunca perguntava ao typer quais comandos
  existem nem quais opções cada um aceita. O conserto que importa é
  `test_0471_cli_commands_registered.py`, que faz essa pergunta (inclusive um
  caso que falha se `service` voltar a aparecer como parâmetro do `run`)
- **bug-107** — `premise_mismatch` **fabricava sucesso perfeito**. O executor
  pode declarar que a premissa da tarefa está incorreta (0.4.53) e isso é um
  outcome legítimo: não há o que entregar. Mas era o **executor declarando o
  próprio resultado**, sem validator nenhum, com
  `require_independent_validation` ligado em toda a frota — e o runtime gravava
  `last_score = 1.0` e `_persist_episode(success=True)`. Dois danos medidos no
  printbee:
  1. o `1.0` era **inventado**. Chega ao dono (`task status`,
     `orchestrator_result`, learnings) e entra em `strategy_performance`, cuja
     tabela virou `19 runs / 19 successes / 0 failures / avg_score 0.9968` num
     projeto com 4 `CANCELLED` e 1 `FAILED`;
  2. a alegação era honrada **depois de uma rejeição gravada** — a
     `efeaee6fd306` fechou `COMPLETED score=1.0` com `rejected score=0.1` e
     issues bloqueantes em disco. O escape hatch **lavava** o veredito.

  Agora o score fica **nulo** (o campo é nullable e serve só para relatório —
  inventar 1.0 é pior que não ter), alegação que contradiz rejeição gravada
  encerra em `INCOMPLETE` com os dois fatos no `error`, e o caminho legítimo
  sobe a degradação `premise_declared_unverified` dizendo que **nada foi
  entregue** e que ninguém julgou. Três `COMPLETED` do printbee eram este
  caminho: `efeaee6fd306`, `d9f8383c7760`, `06d74af53ee0`
- Features de diagnóstico: `premise_score_not_fabricated`,
  `premise_never_overrides_rejection`

### Changed

- **Contrato**: no caminho `premise_mismatch`, `last_score` era `1.0` e agora é
  `None`. Cliente que assume score numérico em task `COMPLETED` precisa tratar
  nulo. `analysis.premise_verified` (`false`) passa a acompanhar
  `analysis.premise_mismatch`

### Known

- `strategy_performance` é **write-only** — nenhum módulo a lê. Nenhuma decisão
  de roteamento foi corrompida pelo score fabricado, mas a tabela ainda carrega
  os números inflados das execuções anteriores à 0.4.71
- O caminho legítimo continua fechando como `COMPLETED`, que para quem varre
  `task list` é indistinguível de entrega. Um estado terminal próprio
  (`DECLINED`/`NOT_APPLICABLE`) é decisão do dono: mexe na state machine e nos
  clientes

## 0.4.70 - 2026-08-09

### Fixed

- **bug-104** — o teto da task **não cabia o trabalho que o runtime pretende
  fazer**. Uma volta com correção soma
  `planner 900 + executor 2400 + tester 600 + validator 1200 + corrector 2400 +
  validator 1200 = 8700 s`, contra um `maximum_duration_seconds` de **3600**.
  Os próprios números do runtime se contradiziam: toda task que realmente usasse
  o orçamento dos papéis morria no meio — e sempre **antes do validator**, que é
  o último a ser chamado. Não era azar, era aritmética: quanto maior a task,
  mais certa a morte. O dono via
  `FAILED — Orçamento de tempo insuficiente para validator (timeout_s=0)`
  (printbee, `b259e8f0c168`), isto é, trabalho possivelmente pronto reprovado
  por relógio com texto de falha de mérito. No printbee o teto teve de ser subido
  para 10800 **na mão**. Três defesas, da raiz para a borda:
  1. **piso derivado** — `maximum_duration_seconds` nunca fica abaixo da soma dos
     tetos dos papéis nesse percurso (`minimum_task_budget_s`). Elevar é correção,
     não preferência: abaixo do piso o teto não reprova nada, só interrompe — e
     teto é limite de paciência, subir não faz task nenhuma demorar mais;
  2. **reserva do veredito** — `executor` e `corrector` devolvem
     `VERDICT_RESERVE_S` (600 s) do restante, para o julgamento sempre caber;
  3. **degradação honesta** — sem orçamento, o veredito determinístico assume e
     o resultado **diz** que ninguém julgou o mérito, com o remédio certo
     (aumentar `maximum_duration_seconds`), em vez de estourar `RuntimeError`
- **bug-105** — o reaper mentia sobre o relógio **e** jogava fora trabalho
  aprovado sem dizer. A mensagem escrevia `VALIDATING há 4525s`, mas 4525 s era
  a **idade da task**, não o tempo na fase (2963 s) — terceira vez que uma
  mensagem deste reaper aponta o relógio errado (bug-093, bug-096), e custou uma
  leitura errada na própria sessão que a corrigiu. Pior: no trustsafe
  (`529cc0476c4e`) a task foi cancelada **com o veredito na mão** — o validator
  respondera `accepted score=1.0` 40 min antes, gravado em `validation_rounds`,
  e o dono lia só "auto-cancel". Agora a mensagem nomeia o relógio
  (`em VALIDATING, criada há Ns e sem sinal de vida há Ms`) e anexa
  `a última validação já havia APROVADO (score=X)`. A **decisão** não muda —
  sem processo vivo não dá para consolidar com honestidade
- **bug-106** — falha do **serviço do provedor** era tratada como CLI quebrado.
  `classify_agent_failure` só tinha `install` e `auth`; erro de servidor não casa
  com marcador nenhum e caía na regra final (stdout vazio + morte rápida) como
  `install`. Os três `opencode` da frota em 09/08 saíram `exit=1` em **2 s** com
  165 bytes de `{"name":"UnknownError","message":"Unexpected server error"}` —
  CLI intacto, credencial intacta — e o auto-reparo gastou uma **reinstalação
  completa** (`repair_ok: true`) para o agente falhar igual na chamada seguinte.
  Nova categoria `service`, avaliada antes de `auth`/`install` e sujeita ao mesmo
  teto de evidência do bug-097: registra, **não** reinstala, e sobe como
  degradação `agent_service_down` com a única ação honesta — não há o que
  digitar, espere ou troque o agente
- Features de diagnóstico: `task_budget_fits_correction_round`,
  `verdict_time_reserved`, `validation_skipped_not_failed`,
  `reaper_names_the_clock`, `provider_outage_not_reinstall`

### Changed

- Prior do `opencode` no `CapabilityScorer`: **0.6 → 0.3**, abaixo do 0.4 de
  agente desconhecido. Medição da frota: **0/3**, depois de o auto-reparo tê-lo
  reinstalado com sucesso. Desconhecido ainda pode funcionar; este já provou que
  não. Continua disponível quando escolhido explicitamente

### Known

- Entre um agente e outro o runtime **não emite sinal de vida** — o heartbeat de
  30 s existe só enquanto um CLI roda. Morte de processo e fase longa sem agente
  ficam indistinguíveis para o reaper. Foi o que deixou a `529cc0476c4e` 40 min
  em silêncio depois de um validator que terminou `exit=0`

### Changed

- `maximum_duration_seconds` do template passa de **3600 → 8700**. Projetos já
  instalados **não precisam editar nada**: o piso é aplicado ao carregar a
  configuração, e o valor pedido fica registrado em `duration_floor_raised_from`
- **Contrato de `resolve_agent_timeout` para `executor`/`corrector`**: com
  `remaining_s=1000` devolvia 1000, agora devolve 400. Quem lê esse valor para
  prever duração precisa contar a reserva

## 0.4.69 - 2026-08-09

### Fixed

- **bug-103** — task nascida com o workspace **ocupado** ficava em `RECEIVED`,
  fora da fila. `_enqueue_task` só acontecia dentro do `run_task`; quem cria por
  MCP (`orchestrator_run`, `wait=false`) ou por `task create` nunca chama
  `run_task`, então a task nascia `RECEIVED` — e `RECEIVED` está **fora de
  `list_queued`**, ou seja, a cadeia de dequeue (corrigida no bug-098) nem
  olhava para ela. Sobrava a adoção de órfã: **uma por vez**, só com o workspace
  livre e só se alguém fizesse poll. Medido no printbee em 09/08:
  `edeee9684e66` passou **9899 s (2 h45)** entre o `task_created` e o primeiro
  estado; `2d933db18554` passou **2 h47 com um único evento** — nunca começou.
  Agora `create_task` enfileira quando o workspace está ocupado, e a fila drena
  em FIFO sem depender de ninguém observar. `run_task` já promovia
  `QUEUED → RECEIVED` ao liberar, então o caminho de execução não muda
- Feature de diagnóstico: `create_enqueues_when_busy`

## 0.4.68 - 2026-08-09

Honestidade do resultado e uma porta de entrada para skills externas.

### Added

- **Detecção de enfraquecimento de teste.** O executor escreve o código **e** os
  testes, e o gate só verifica se a suíte fica verde — nada impedia baixar uma
  asserção, marcar `skip` ou apagar um caso para passar, e o resultado sairia
  `COMPLETED score=1.0` igual a trabalho honesto. `validation/test_integrity.py`
  lê o **diff de verdade** (git, não a narrativa do agente) dos arquivos de
  teste e sinaliza três padrões mecânicos: asserções removidas, testes
  desligados, casos apagados. Severidade **não-bloqueante** de propósito —
  refator legítimo também remove asserção, e esta frota já pagou caro por
  heurística de texto confiante demais (bug-097). Vira `blocking` só se o
  validador confirmar
- **O validador julga por observação.** O prompt passa a dizer explicitamente
  que as afirmações do executor são hipóteses **falsificáveis**, que o diff e a
  saída dos testes são a verdade, que ele deve reexecutar o que puder em vez de
  inferir do código, e que o não verificável vira `UNVERIFIABLE` em vez de
  aceitação por omissão
- **Registro único de degradação.** Três releases criaram três avisos ad-hoc
  para a mesma ideia: `independent_validation` (0.4.62), `agent_auth_required`
  (0.4.64), `plan_refined` (0.4.67). A quarta degradação seria um quarto campo
  solto. Agora `status` e `orchestrator_result` trazem `degradations` — uma
  lista com `kind`, `impact`, `detail` e `action`. Os campos antigos continuam
  saindo; cliente que já os consome não quebra
- **Pacotes de skills curados.** `orchestrator skills list` e
  `orchestrator skills install <pacote> --project <projeto>` instalam coleções
  externas em `.orchestrator/skills/<pacote>/`, com `SKILLPACK.json` de
  procedência (origem, licença, data, contagem). O mapa é **curado no script** —
  nunca URL livre, mesma regra do mapa de agentes. Primeiro pacote: `marketing`,
  49 skills MIT de Corey Haines. Instalação é **por projeto**: o seletor recebe
  a lista inteira a cada task e descrições demais encarecem também as tasks de
  código
- Features de diagnóstico: `test_weakening_detection`,
  `validator_claims_are_falsifiable`, `degradation_ledger`, `curated_skill_packs`

### Créditos

A heurística de integridade de teste (*"um teste alterado é culpado até a
justificativa remontar a uma spec"*) e a postura de tratar afirmações como
falsificáveis foram **reimplementadas** a partir do
[fable-method](https://github.com/Sahir619/fable-method) (MIT). Nenhum texto ou
prompt foi copiado. As skills de marketing são de
[coreyhaines31/marketingskills](https://github.com/coreyhaines31/marketingskills)
(MIT), instaladas na íntegra.

## 0.4.67 - 2026-08-09

Três defeitos que a análise das falhas do printbee expôs. Nenhum era agente
quebrado — os três eram o runtime cobrando o preço errado.

### Fixed

- **bug-101** — `SELECTING_AGENTS_CAP_S` era **180**, menor que o próprio
  `PLANNER_REFINE_CAP_S` (**300**). Como o teto efetivo do refino é
  `min(300, 180 - decorrido)`, os 300 s prometidos ao planner **nunca eram
  alcançáveis**: ele tinha ~180 s reais. E `role_model_preferences.planner`
  começa por `fable`, o modelo mais deliberativo — o menor orçamento da pipeline
  entregue ao agente mais lento. Medido no printbee: 4 refinos, 2 concluíram em
  57 s e 81 s, **2 morreram em 180 s cravados com ZERO byte** (`claude -p` só
  imprime no fim, então o kill não deixa nem saída parcial). 50 % de perda. O
  teto da fase agora é `skill_selection_timeout_s + PLANNER_REFINE_CAP_S`, por
  construção — mexer num não deixa mais o outro inalcançável
- **bug-102** — refino perdido era **invisível**. Ele é advisory de propósito, e
  a task segue com o plano determinístico — mas terminava `COMPLETED score=1.0`,
  indistinguível de uma que foi refinada. Duas das quatro tasks do printbee
  rodaram com plano cru e nada no resultado dizia. Agora `status` traz
  `plan_refined: false` + `plan_warning`, persistidos em `analysis` para
  sobreviver ao processo. Mesma família de `independent_validation` (0.4.62) e
  `agent_auth_required` (0.4.64): o runtime decide certo, mas tem que contar
- **bug-100** — `pytest` sai **5** (`EXIT_NOTESTSCOLLECTED`) quando não há teste
  para rodar, e isso virava `failed/introduced`. O printbee é .NET + Angular; a
  descoberta propunha `pytest -q`, ele saía 5 em **toda** task e a task era
  cobrada por não ter quebrado nada. Agora é `skipped/no_tests_collected` —
  mesma família de `tool_missing` e `deps_missing`: ambiente, não mérito. Exit 5
  de qualquer outro comando continua falha
- Features de diagnóstico: `selecting_cap_fits_planner_refine`,
  `plan_refined_flag`, `pytest_no_tests_not_a_failure`

## 0.4.66 - 2026-08-09

### Fixed

- **bug-098** — a fila entregava a task e matava quem ia executá-la. Ao terminar
  uma task, `_maybe_start_next` desenfileira a próxima e a inicia numa thread
  **daemon**. Só que quem dispara isso é o `finally` do `run_task` — no CLI, o
  processo sai no instante seguinte e leva a thread junto. A task já tinha sido
  transicionada de `QUEUED` para `RECEIVED`, então sai de `list_queued` e
  ninguém mais a enxerga pela fila; sobra só a adoção de órfã, que depende de
  alguém fazer poll. Medido no printbee: `06d74af53ee0` terminou 17:35:53 e
  `a0a588e6937b` foi para `RECEIVED` **no mesmo segundo**, ficando 11,5 min
  parada até o dono cancelar e recriar a mesma task à mão. Em 07/08 a sequência
  idêntica durou **47 horas**, até o auto-cancel de 6h. Agora
  `TaskService.join_background()` espera as tasks que o processo tirou da fila,
  e o CLI (`run` e `task run`) drena antes de sair. O servidor MCP segue vivo e
  não chama — só quem morreria
- **bug-099** — `Update-Agents.ps1` substituía o binário de um CLI **em
  execução**. No Windows isso não é "update pulado": o npm baixa o pacote, falha
  o move final com `EBUSY` e faz rollback **parcial** — o pacote principal fica,
  o de plataforma não chega. O CLI não fica desatualizado, fica **destruído**.
  Foi exatamente o que aconteceu com o `codex` em 07/08, durante um
  `orchestrator update` com codex rodando como executor: 340 MB presos num
  staging órfão, `@openai/codex-win32-x64` ausente e `exit=1` com zero byte em
  toda a frota por dois dias — e o script tratou como simples aviso. Agora
  agente com processo vivo é reportado como **`deferred_running`**, com linha
  `[ACAO]` dizendo para rodar de novo depois. Consequência esperada: rodar
  `orchestrator update` de dentro do Claude Code adia o update do próprio
  `claude` — correto, o binário dele também está em uso
- Features de diagnóstico: `queue_handoff_joined`,
  `agent_update_defers_running_cli`

## 0.4.65 - 2026-08-07

### Fixed

- **bug-096** — o reaper da 0.4.63 media o silêncio pelo campo errado.
  `updated_at` só muda em **transição de estado**; um executor legítimo passa 40
  min em `EXECUTING` sem tocá-lo, enquanto o heartbeat de 30s é **evento**.
  Flagrado no printbee (task `25ea69c8324a`): o registro de cancelamento diz
  *"parada há 1643s"* de uma task que emitia heartbeat até **87 s antes**. A
  decisão até acertou — o processo dono havia mesmo morrido, e o reaper limpou
  ~1,5 min depois, que é exatamente o que ele existe para fazer — mas o critério
  ficou inteiramente apoiado no arquivo de lock. Consequência séria: apagar um
  `workspace.write.lock` à mão (procedimento normal de desentupimento até
  ontem) passaria a **cancelar execução saudável**. Agora o relógio é o sinal de
  vida mais recente entre transição e evento (`TaskRepository.last_event_at`), e
  o teto de duração é medido sobre a vida da task, não sobre `updated_at`.
  Heartbeat recente segura o reaper sozinho, independente do lock
- A mensagem de cancelamento passa a dizer **"sem sinal de vida há Ns"** — a
  anterior afirmava que a task estava parada quando ela estava trabalhando, e
  quem lesse o histórico chegaria à conclusão errada
- **bug-097** — `classify_agent_failure` lia a saída do agente como diagnóstico
  mesmo quando ela era **conteúdo**. Nas falhas de `codex` de 2026-08-07 o stderr
  trazia 20 KB do `tasks/service.py` *deste pacote*, que contém as strings
  `"codex login"`, `"not logged in"` e `"unauthorized"` porque é onde elas são
  **definidas**. O classificador leu a documentação do próprio recurso e devolveu
  `auth`. Consequência real e medida na frota: o problema verdadeiro era
  `install` (`Missing optional dependency @openai/codex-win32-x64. Reinstall
  Codex: npm install -g @openai/codex@latest`), o auto-reparo que teria
  consertado **não rodou**, e o dono recebeu um pedido de login que não resolvia
  nada. Agora marcador só vale em saída de até `EVIDENCE_CAP_BYTES` (8 KB): um
  CLI que não consegue nascer imprime centenas de bytes e morre; quem imprime
  milhares rodou. A assinatura exata do codex quebrado entrou em
  `INSTALL_MARKERS`. Custo aceito: `rate limit` que só apareça depois de 8 KB de
  trabalho real deixa de ser classificado — é indistinguível de um agente citando
  a expressão, e classificar errado é pior que não classificar

## 0.4.64 - 2026-08-07

### Fixed

- **bug-095** — agente sem credencial não chegava a quem pode resolver. A 0.4.63
  já classificava `auth` e emitia `agent_repair` com o comando de login, mas
  evento mora no `task logs` — e quem precisa agir é o **dono**, que está olhando
  o chat. Na primeira execução real da 0.4.63 (task `b0b9f6cadb7a`) o `codex`
  caiu por `auth` **duas vezes**, a task terminou `COMPLETED score=1.0` e nem o
  resultado nem a saída do `run` disseram uma palavra. Reinstalar não resolve
  credencial: só a pessoa pode fazer login, então o silêncio custava rodadas
  inteiras de fallback a cada task. Agora o bloqueio sobe por três caminhos:
  - `orchestrator_status` / `task status` ganham `agent_auth_required` (agente,
    papel, comando) e `action_required` — a cada poll, não só no fim
  - `orchestrator_result` leva o mesmo par, popula `remaining_issues` (que era
    **sempre** `[]`) e prefixa `message`, para cliente de chat que só exibe ela
  - `orchestrator run` / `task run` imprimem uma linha `[ACAO]` por agente

  Deduplicado por agente: o mesmo CLI falha em vários papéis e o dono só precisa
  rodar o comando uma vez. Falha `install` **não** vira pedido ao dono — essa o
  runtime resolve sozinho.
- Feature de diagnóstico: `agent_auth_blocker_surfaced`

### Changed

- **Claude Code dispara o orquestrador em segundo plano por padrão.** Uma task
  leva de 5 a 30 min; em primeiro plano ela prende a conversa e o usuário fica
  sem ver nada. O adaptador (`CLAUDE.usage.section.md`) e o subagente
  `orquestrador` agora mandam usar `Bash` com `run_in_background: true` — o
  comando vira tarefa em segundo plano visível em `/tasks`, com saída ao vivo em
  arquivo e notificação no fim. Com o aviso explícito de **não canalizar** a
  saída (`| tail`, `| Select-Object`, `> arquivo`): o pipe segura tudo até o fim
  e o painel fica mudo. Via MCP o `orchestrator_run` já volta na hora, mas não
  cria a tarefa de `/tasks`
- O subagente `orquestrador` passa a levar `action_required` ao usuário mesmo
  quando a task termina `COMPLETED` — sem o login, toda task seguinte repaga o
  fallback

## 0.4.63 - 2026-08-07

O runtime parava de vez em quando e ninguém sabia por quê. Era um deadlock de
pipe — e, na volta, a fila ficava barrada para sempre por uma task que nunca
terminava. Esta versão corrige a causa e três camadas de defesa em volta dela.

### Fixed

- **bug-090 (causa raiz)** — `CliExecutor.run` escrevia o `stdin` **antes** de
  subir as threads leitoras de `stdout`/`stderr`. Com prompt grande (acima do
  teto de argv o prompt vai por stdin, `base_adapters:172`) travava dos dois
  lados: o pai enchia o buffer de entrada (~64 KB no Windows) e esperava o filho
  consumir; o filho enchia o de saída e esperava alguém ler — e as leitoras
  ainda não existiam. Como `proc.wait(timeout=...)` só vem depois, **nenhum
  timeout se aplicava**: nem o do papel, nem o watchdog de silêncio da 0.4.60.
  Medido na task `2ffb76eb16df`: 40+ min parada entre `skill_selector` e
  `planner`, segurando o `workspace.write.lock`. Agora a escrita é uma thread
  própria, iniciada **depois** das leitoras
- **bug-093** — não havia reaper de task **não-terminal**.
  `_cancel_stale_received` só varre `RECEIVED`; task presa em
  `PLANNING`/`EXECUTING` ficava para sempre, `_busy_task_id` seguia devolvendo
  ela e toda task nova entrava em `QUEUED` atrás de uma que nunca terminaria —
  ~11 h de fila parada no printbee. `_cancel_stale_execution()` cancela quando
  `updated_at` passa de `maximum_duration_seconds + stale_execution_grace_s`
  **ou** quando nenhum processo vivo segura o lock do workspace (o lock já
  carrega o pid do dono, então não foi preciso campo novo na task). Task deste
  processo nunca é ceifada; `QUEUED` fica de fora de propósito
- **bug-094 (a)** — `_npm_global_bins_nt()` usava
  `subprocess.run(capture_output=True, timeout=15)`. No Windows, quando o
  timeout estoura, o `communicate()` pós-kill espera **todo neto** que herdou o
  handle do pipe: é o bug-059, corrigido em `git_workspace._run_git` e nunca
  aplicado aqui. Esse caminho roda dentro de `which()` → `detect()`, que
  `orchestrator_run` chama **depois** de já ter disparado a task — por isso a
  chamada MCP ficava 1800 s sem responder com a task rodando. Agora usa o novo
  `run_capture_file()` (Popen + arquivo temporário + `taskkill /T`)
- **bug-091** — `Set-DefaultAgentKey` gravava `"agent": "orquestrador"` também
  no repositório **do próprio pacote**. Esse subagente é read-only por design
  (sem `Write`/`Edit`) e só sabe delegar — e, com o runtime quebrado, delegar
  trava. A sessão capaz de consertar o orquestrador ficava impedida de escrever,
  e cada `orchestrator update` recolocava a chave. Agora o script detecta o repo
  do pacote (`runtime/src/orchestrator_runtime/` na raiz) e pula a chave
- **bug-092** — `redact()` era **quadrático** em linha longa sem segredo:
  `[\w.\-\[\]]*` antes da alternação consome a linha inteira em cada posição
  inicial e retrocede um char por vez. Medido: 2,4 MB de saída de agente (linhas
  de 4 KB) = ~100 s de CPU a 100% só redigindo — e `redact()` roda no fim de
  **toda** execução. Pré-filtro barato decide se a linha sequer menciona um
  marcador; prefixo/sufixo da chave limitados a 64 chars

### Added

- **Auto-reparo de CLI de agente quebrado.** `codex` e `opencode` saíam `exit=1`
  com **zero byte** como executor *e* como validator (task `143e8b2ca47b`; quem
  salvou foi o corrector `claude/opus`). O bug-070 só colocava em quarentena —
  esconde em vez de resolver. `agents/health.py` classifica a falha em
  `install` / `auth` / `None`, e `agents/repair.py` reinstala **uma vez por
  agente por processo** delegando a `scripts/Update-Agents.ps1 -Only <agente>`,
  que já tem os mapas curados (npm/chocolatey/scoop/instalador nativo).
  Falta de credencial **não** reinstala: emite o comando de login.
  `timed_out` nunca é CLI quebrado, e sem marcador só classifica `install`
  quando o agente morreu mudo **e** rápido — o corrector da GuardLine, com 17
  min e 20 KB de stderr, é mérito, não CLI quebrado
- **`.gitignore` na instalação.** `Configure-GitIgnore.ps1` escreve um bloco
  delimitado com o estado local de agentes (`.claude/`, `.codex/`, `.cursor/`,
  `.orchestrator/`, `.wolf/`, `graphify-out/`, `.mcp.json`…). Sem isso o estado
  local vai para o commit e o próximo checkout **regride a versão instalada** —
  foi o que aconteceu em printbee, adzora e trustsafe. Linhas do usuário fora do
  bloco nunca são tocadas; adaptadores em markdown (`AGENTS.md`, `CLAUDE.md`)
  ficam de fora de propósito, são instruções de projeto. Arquivo já rastreado
  não é afetado por `.gitignore`: o script avisa e sugere `git rm -r --cached`.
  O repositório do **próprio pacote** é exceção (mesma regra do bug-091): lá
  `.cursor/rules/` e `.orchestrator/` são conteúdo versionado — é o que o pacote
  distribui
- Chaves novas em `policies.json`: `stale_execution_grace_s` (900),
  `agent_auto_repair` (true), `agent_repair_timeout_s` (300)
- Features de diagnóstico: `stdin_written_after_readers`,
  `stale_execution_reaper`, `agent_broken_cli_detection`, `agent_auto_repair`

## 0.4.62 - 2026-08-07

Dois defeitos que a primeira execução real do fan-out expôs.

### Fixed

- **bug-088** — a redação de segredos apagava a **linha inteira** sempre que
  ela citasse "secret"/"token"/"password" e tivesse `:` ou `=`. Na primeira
  execução real do fan-out (task `143e8b2ca47b`, documentação deste projeto) o
  JSON do decompositor mencionava *"NAO exponha secrets"* e voltou como
  `{"subtasks":[ [REDACTED] [REDACTED] ]}`: o parse achou zero subtarefas e o
  runtime caiu no sequencial **sem ninguém perceber**. E não é só log —
  `CliExecutor.run` devolve o texto redigido, então o runtime **parseia** o que
  sobrou; tarefa de documentação, de segurança ou de config fala dessas
  palavras o tempo todo. Agora some o **valor**, não a linha, e só quando a
  forma é de atribuição (chave sem espaços contendo o marcador, separador,
  valor colado). Prosa sobrevive; JSON continua parseável mesmo quando um valor
  é redigido
- Escolha deliberada no filtro: exigir "forma de segredo" (comprimento,
  dígito) deixava passar `API_KEY=supersecret`, que é segredo de verdade. Como
  agora some só o valor, redigir demais custa uma palavra ilegível e redigir de
  menos vaza credencial — o desempate é óbvio. Placeholders (`<sua-chave>`,
  `${VAR}`, `nome`, `obrigatorio`) seguem intactos
- **bug-089** — na mesma task, os **dois** validators (codex e opencode)
  saíram `exit=1` com zero byte e o resultado veio `COMPLETED score=1.0`. A
  política de não transformar falha de infra em rejeição de mérito está certa;
  o silêncio sobre ela, não — `1.0` lia-se como "revisado e aprovado".
  `orchestrator_status` passa a trazer `independent_validation` e, quando
  falso, `validation_warning` dizendo que o score não reflete revisão de
  mérito. **Não muda gate nem score**: só para de esconder

### Notes

- Testes: `test_0462_redact.py` (12 — env dump, JSON com token, bearer, senha
  curta, valor sem dígito, prosa intacta, o JSON exato do decompositor que
  quebrou, placeholders, preservação do resto da linha) e
  `test_0462_independence.py` (4). Runtime: 446 passed / 3 skipped
- A missão de documentação do próprio orquestrador rodou e entregou os dez
  documentos em `/docs` (task `143e8b2ca47b`, 22 min, nada fora de `/docs`
  tocado) — mas **sequencialmente**, por causa do bug-088. O fan-out com
  agentes reais segue sem prova de campo; com agentes fake está coberto por
  `test_0461_fanout_service.py`

## 0.4.61 - 2026-08-07

Fan-out: subtarefas em paralelo, cada uma no seu worktree, fundidas por patch.

### Added

- **Escrita paralela de verdade.** Até aqui o runtime era **estritamente
  sequencial** — um executor por workspace, serializado pelo `WriteLock`. As
  chaves `allow_parallel_read_only_analysis` e
  `allow_parallel_workspace_writes` existiam na config desde o começo e
  **nenhum código as lia**; a tabela `subtasks` existia e nunca recebeu uma
  linha. Agora `allow_parallel_workspace_writes: true` liga o fan-out: o
  planner divide a tarefa em subtarefas de escopo disjunto, cada uma roda num
  `git worktree` próprio, e o runtime funde os patches na árvore real
- `execution/worktrees.py` — criação/coleta/fusão/limpeza de worktree.
  **Fusão é tudo-ou-nada**: `git apply --check` antes de escrever. `--3way`
  resolveria mais casos, mas em conflito deixa marcadores no working tree — um
  merge pela metade na árvore real, justamente onde pode haver trabalho de
  outros agentes (bug-077). Patch que não passa vira subtarefa `conflict` com o
  `.patch` preservado em `.orchestrator/runtime/patches/<task>/`
- `execution/fanout.py` — decomposição e a regra de sobreposição. Escopos que
  colidem (mesmo arquivo, pasta contendo arquivo, ou escopo **não declarado**)
  são **fundidos** numa subtarefa só antes de gastar agente: fundir preserva o
  trabalho declarado, descartar perderia requisito. Menos de duas subtarefas
  úteis ⇒ caminho sequencial de sempre
- `max_parallel_subtasks` (padrão 4) em `policies.json`
- Tabela `subtasks` finalmente escrita: `merged` / `conflict` / `empty` /
  `failed`, com escopo, arquivos e caminho do patch; eventos
  `agent_started`/`agent_completed` ganham `mode=parallel_subtasks`

### Notes

- **Executor próprio por subtarefa** não é preciosismo: o watchdog de silêncio
  (0.4.60) sonda o workspace para decidir se o agente está vivo, e uma sonda
  apontada para a árvore principal veria "nada mudou" enquanto a subtarefa
  escreve no worktree — mataria agentes vivos. Cada subtarefa também roda em
  thread própria porque `adapter.run` é `async` mas o `CliExecutor` por baixo é
  bloqueante: um `gather` direto serializaria tudo e travaria o event loop
- **Só na primeira passada.** Correção existe para fechar issue específica do
  validator; dividir isso entre agentes cegos uns aos outros multiplica o
  conflito, não o trabalho
- Requisitos: repo git com pelo menos um commit. Sem HEAD não há base para
  worktree nem diff — o runtime segue sequencial em vez de falhar
- Continua **desligado por padrão**: escrita paralela só compensa em tarefa que
  se divide de verdade em escopos disjuntos
- Testes: `test_0461_worktrees.py` (10 — isolamento, patch com arquivo novo,
  fusão de disjuntas, conflito que **não** suja a árvore, limpeza, recriação),
  `test_0461_fanout_split.py` (10 — JSON cercado de prosa, teto, indivisível,
  fusão de escopo sobreposto, pasta×arquivo, escopo vazio, normalização de
  separador), `test_0461_fanout_service.py` (9 — gate, exigência de git, fusão
  na árvore real, limpeza de worktree, registro em `subtasks`, subtarefa que
  falha sem derrubar as outras). Runtime: 428 passed / 3 skipped

## 0.4.60 - 2026-08-07

Uma hora de orçamento, nada entregue: o agente mudo comia o tempo do agente
que trabalhava.

### Fixed

- **bug-086** — GuardLine `e0457603df65`: executor `claude/opus` ficou **40
  min com ZERO byte** em stdout E stderr e só morreu no timeout do papel
  (2400s). O corrector que entrou depois estava produzindo de verdade (20KB de
  stderr, arquivos sendo escritos) e foi morto 17 min depois pelo
  `maximum_duration_seconds` da task. Uma hora gasta, INCOMPLETE, e o agente
  sacrificado foi justamente o que trabalhava. Novo **watchdog de silêncio**
  (`agent_no_output_timeout_s`, padrão 900s): mata o agente que passa a janela
  inteira sem NENHUMA saída **e** sem tocar no workspace. As duas condições
  importam — `claude -p` só imprime no fim, então silêncio sozinho não prova
  travamento; silêncio com zero arquivo alterado prova. Sonda de progresso que
  falhe (git lento/indisponível) **nunca** mata o agente: sem prova, sem kill
- **bug-085** — trustsafe `c4b7a1d12d6b`: criada 23:02, primeiro agente só às
  23:33 — 30 min parada com o workspace **livre** e nenhuma outra task na
  frente. `_maybe_start_next` só olhava a fila `QUEUED`; task `RECEIVED` cujo
  processo criador morreu antes de rodar o loop (cliente MCP recém-instalado
  que ainda não recarregou, CLI interrompido no meio do create) ficava órfã até
  o auto-cancel de 6h — que resolvia o zumbi e jogava o trabalho fora. Agora
  qualquer processo vivo do orquestrador **adota** a órfã, inclusive no poll de
  `status`/`list`. Janela `orphan_received_adopt_after_s` (padrão 120s) evita
  roubar a task de quem acabou de criá-la
- **bug-087** — três mortes diferentes saíam com o mesmo rótulo
  `AGENT-TIMEOUT-NO-OUTPUT`, inclusive para um corrector com 20KB de stderr: o
  log mandava procurar o defeito no lugar errado. Agora o rótulo vem da
  evidência — `AGENT-NO-OUTPUT-HANG` (pendurado, morto pelo watchdog),
  `TASK-BUDGET-EXHAUSTED` (cortado pelo teto da task, não pelo timeout do
  papel), `AGENT-TIMEOUT-NO-CHANGES` (falou mas não entregou) e
  `AGENT-TIMEOUT-NO-OUTPUT` (o caso real de silêncio). Os remédios são
  opostos: trocar de agente, aumentar o teto da task, ou tratar como mérito
### Notes

- Testes: `test_0460_hang_and_orphan.py` (15 casos — watchdog mata mudo, não
  encosta em quem fala, respeita progresso no workspace, sonda quebrada não
  mata, desligado por padrão; rótulo por evidência nos 4 cenários; adoção de
  órfã, janela que protege a task recém-criada, uma thread por órfã e não uma
  por poll, workspace ocupado não adota). Runtime: 399 passed / 3 skipped

## 0.4.59 - 2026-08-06

O orquestrador vira o agente PADRAO da sessao, nao so um agente disponivel.

### Added

- **bug-083** — instalar o subagente `orquestrador` (0.4.53–0.4.56) so o
  tornava DISPONIVEL: a thread principal seguia sendo o agente generico, que
  decidia sozinho se delegava — e frequentemente nao delegava. Os dois CLIs
  que expoem "rodar a sessao COMO um agente nomeado" passam a ser
  configurados em todo install/update/propagate:
  - **claude code**: `.claude/settings.json` → `"agent": "orquestrador"`.
    A doc oficial descreve a chave como *"Run the main thread as a named
    subagent... Applies that subagent's system prompt, tool restrictions, and
    model"* — a thread principal herda as tools restritas (sem write/edit) e
    o system prompt do operador do runtime
  - **opencode**: `opencode.json` (raiz, precedencia maxima) →
    `"default_agent": "orquestrador"`. A doc exige agente **primary**:
    subagent puro cai no fallback `build` com warning, entao o template do
    subagente opencode passou de `mode: subagent` para `mode: all` (serve
    como primary E subagent)
- Chave gerenciada com respeito ao usuario: gravada quando ausente ou ja
  nossa; valor DIFERENTE definido pelo usuario e **preservado com aviso**.
  Merge nao-destrutivo (hooks/permissions/enabledPlugins intactos) e UTF-8
  sem BOM (mesmo motivo do bug-074)

### Notes

- Sem equivalente na doc oficial (verificado 08/2026): **gemini CLI** (so
  `experimental.enableAgents` e `agents.overrides`), **codex** (`[agents]`
  tem apenas `max_threads`/`max_depth`) e **kimi code** (`config.toml` e de
  provider/modelo). Nesses tres o desvio segue pelo subagente instalado +
  `AGENTS.md` gerado — que ja e o mecanismo atual
- `Test-DefaultAgent`: criacao, idempotencia, merge preservando conteudo do
  usuario, respeito a valor customizado, settings.json invalido sem derrubar
  o install, ausencia de BOM e `mode: all` no subagente opencode
- **bug-084** — `Test-Hooks` ficou vermelho contra um guard CORRETO: as
  assercoes cobravam `exit 2` (guard bloqueante), mas o **bug-080** (0.4.57)
  tornou o guard de codigo-fonte consultivo — `exit 0` com o aviso em
  `systemMessage` no stdout. O teste passa a assertar o TEXTO do aviso e o
  silencio dentro da janela de rearme, que e o comportamento observavel
  agora; ganhou tambem os casos de "nao avisa" (doc isenta e executor
  delegado). Suite: 30/30

## 0.4.58 - 2026-08-05

O bug que escondia o orquestrador de todos os clientes MCP.

### Fixed

- **bug-082** — causa raiz da não-adoção do subagente (investigação pedida
  pelo dono após 2 ciclos com zero invocações): o launcher `findPython()`
  escolhia qualquer `python` do PATH, e clientes MCP (claude/kimi) que
  spawnam o servidor com o ambiente DELES caíam num python sem as deps —
  o servidor MCP **morria no boot** com `ModuleNotFoundError: typer`,
  reproduzido com o spawn exato do `.mcp.json`. Resultado: ZERO tools
  `orchestrator_*` disponíveis nas sessões (24 projetos com MCP
  "habilitado" mas morto). O launcher agora prefere o **venv do runtime**
  (`runtime/.venv`, que tem todas as deps) antes de qualquer python do PATH.
  Handshake re-testado pós-fix: initialize OK, `serverInfo orchestrator-ia
  1.28.1`, `tools/list` respondendo

### Notes

- Cadeia completa da adoção, agora destravada de ponta a ponta: MCP
  registrado (0.4.49) → habilitado (0.4.57) → **vivo no boot (0.4.58)** →
  subagente carregado (0.4.53) → invocação espontânea (a observar)

## 0.4.57 - 2026-08-04

O guard que não impede, o MCP que aparece, e o spawn que herda tudo.

### Fixed

- **bug-080** — o guard estava BARRANDO trabalho legítimo no printbee
  (reportado pelo dono: "não podemos impedir o agente de fazer edições e
  correções"). Dois erros de desenho: (1) Write/Edit bloqueava com exit 2 em
  vez de avisar; (2) `git reset --hard` cego bloqueava o fluxo canônico de
  sync do prompts.md Type 6 (`git reset --hard origin/<base>`). Agora:
  Write/Edit e git em lote (add -A/commit -a/stash) são **consultivos**
  (systemMessage ao modelo, exit 0 — o trabalho sempre passa); bloqueio
  de uma-vez só para destrutivo real sem volta (`git clean`,
  `reset --hard` SEM alvo, `checkout/restore .`); `reset --hard <ref>`
  explícito liberado. Verificado nos 5 cenários
- **bug-079** — causa raiz de "o claude não chamou o orquestrador": o MCP
  estava REGISTRADO no `.mcp.json` mas não HABILITADO — claude exige
  aprovação para servers de projeto e o printbee tinha
  `enabledMcpjsonServers: []` (sessão de 56k linhas com 1.385 Edits e ZERO
  chamadas orchestrator_*). O Repair-ClaudeTrust agora também pré-habilita
  `orchestrator-ia` em enabledMcpjsonServers por projeto (só o nosso
  server; demais seguem ask-on-first-use). Verificado ao vivo
- **bug-081** — o agente chamado pelo orquestrador não herdava as surfaces
  do PRÓPRIO runtime de IA: rules descobria só `.cursor/.orchestrator`
  (`.codex/rules` — citadas pelos agents codex do printbee — ficavam fora),
  skills ignorava `.kimi-code`/`.gemini`, e as personas de agents
  (.claude/.codex/.kimi-code/.opencode) nunca chegavam ao prompt. Agora:
  rules cobre `.codex/.claude/.kimi-code/rules`; skills cobre
  `.kimi-code/.gemini/skills` (projeto e home); e o prompt do executor lista
  os agentes definidos no projeto como **guia de escopo** (personas — NÃO
  delegação; delegação aninhada segue proibida)

## 0.4.56 - 2026-08-04

O subagente orquestrador em TODOS os CLIs instalados.

### Added

- **Espelho codex** — `orquestrador.toml` em `.codex/agents/` de todos os
  projetos (formato nativo confirmado: name + description +
  developer_instructions, igual aos 15 agents existentes nos projetos).
  Mesma persona operador-do-runtime, adaptada ao contexto codex (sem
  spawn_agent, shell só para o CLI orchestrator)
- **Espelho opencode** — `orquestrador.md` em `.opencode/agent/` com
  frontmatter nativo (`mode: subagent`, tools com write/edit desligados)

### Notes

- Cobertura final por CLI neste host: claude (.claude/agents ✓ 0.4.53),
  kimi (.kimi-code/agents ✓ 0.4.54), **codex (.codex/agents ✓)**,
  **opencode (.opencode/agent ✓)**. Gemini fica fora: CLI não instalado
  nesta máquina. Cursor segue como front controller via MCP (não é worker,
  não tem mecanismo de subagente)

## 0.4.55 - 2026-08-03

Pesquisa na internet para qualquer agente — e disciplina Karpathy no template.

### Added

- **`/loop-research`** — padrão Lead→Researchers→Analyst→Writer do demo
  `research-agent` da Anthropic (Claude Agent SDK), adaptado para UM executor
  sequencial de **qualquer CLI** (não só claude). O executor decompõe o
  tópico em 2-4 subtemas, pesquisa com a busca web do SEU CLI
  (WebSearch/web.run/google_search — com saída honesta "sem busca disponível"
  em vez de simulação), grava notas com URLs em
  `.orchestrator/runtime/results/research/notes/`, extrai dados/gráficos em
  `data/` e `charts/`, e redige o relatório final em `reports/` com citações
  por afirmação. Etapa obrigatória de REVISÃO DE HONESTIDADE: todo número
  rastreia para nota com URL; lacunas marcadas ("não encontrado"), nunca
  preenchidas com conhecimento interno
- **Skill `karpathy-guidelines`** — os 4 princípios anti-pitfall de LLM do
  andrej-karpathy-skills (MIT, com atribuição), adaptados agent-agnostic:
  Pense antes de codar (pergunte em vez de assumir), Simplicidade primeiro
  (50 linhas em vez de 200), Mudanças cirúrgicas (cada linha rastreia para o
  pedido; código morto alheio só se menciona), Execução dirigida por objetivo
  (critérios verificáveis + loop até passar). Registrada no template e
  propagada a todos os projetos — menos reescritas, diffs menores, menos
  suposições erradas em toda a frota

## 0.4.54 - 2026-07-31

Um arquivo, dois runtimes: o orquestrador-agente também no kimi.

### Added

- **Espelho do subagente `orquestrador` para o kimi code** — o mesmo
  Markdown agora é instalado também em `.kimi-code/agents/` de todos os
  projetos (diretório de discovery do kimi, por docs oficiais). O frontmatter
  ganhou `whenToUse` (dica de delegação do kimi; o claude ignora campo
  desconhecido). Compatibilidade confirmada na documentação: kimi carrega
  agent files claude-style (tools comma-separated, campos estrangeiros
  ignorados). Smoke ao vivo: `kimi --agent-file orquestrador.md -p` respondeu
  com a persona exata do operador ("NUNCA implemento, NUNCA spawno
  subagentes, NUNCA valido por conta própria"). Sem `override`: nosso nome
  não colide com built-ins e não tomamos o prompt de ninguém

## 0.4.53 - 2026-07-31

O subagente que não consegue editar — só orquestrar.

### Added

- **Subagente `orquestrador` para Claude Code** (`.claude/agents/orquestrador.md`,
  propagado a todos os projetos no install/update). Ideia do dono com dois
  ajustes: subagentes vivem em `.claude/agents/` (não no settings.json), e a
  persona é **operador do runtime**, não "orquestrador roleplay" — o system
  prompt proíbe implementar, spawnar Task/Agent e autovalidar. Três camadas
  de valor:
  - **auto-seleção**: a description cobre "qualquer tarefa não-trivial", e o
    claude escolhe o subagente sozinho nesses casos — a regra "orquestrar é
    o padrão" deixa de depender só de AGENTS.md ser lido
  - **tools restritas**: Read/Grep/Glob/Bash(orchestrator CLI)/MCP
    `orchestrator_*` — sem Write/Edit, o subagente fisicamente não edita
    código direto (enforcement de harness, acima do guard de uma-bloqueada)
  - **fluxo com paciência embutida**: run → status no intervalo → events →
    result; nunca cancelar por impaciência; interpreta COMPLETED,
    premise_mismatch, INCOMPLETE e falhas de infra com o próximo passo

## 0.4.52 - 2026-07-31

O orquestrador implementando a si mesmo — e a revisão que pegou a mentira.

Rodada completa de dogfooding: as 5 melhorias portadas do `prompts.md` da
GuardLine foram implementadas POR TASKS do próprio orquestrador no repo do
pacote (3 tasks, executor codex, validador claude).

### Added

- **`/loop-ui-probe`** (task A) — sonda Playwright portada dos Types 10/11:
  boundary mutante/não-mutante, locators por role, listeners (HTTP 4xx/5xx,
  console, WebSocket) como entregável, roadmap com tags fixas. Responde à
  falha que matou a task 8193684389b1 do printbee
- **`/loop-review`** (task A) — revisão adversarial portada do Type 8:
  identity priming (SRE-3h/segurança/arquiteto/júnior), 5 temas fixos,
  "do NOT pad findings", tabela ranqueada por severidade NO FIM
- **Outcome terminal `PREMISE_MISMATCH:`** (task B) — executor declara a
  premissa factualmente errada (já corrigido/já existe/já entregue) e a
  task encerra **COMPLETED sem gates** (sem teste, sem workspace_changes):
  honestidade deixa de grindar iterações. Parser tolerante a markdown,
  transição EXECUTING→COMPLETED na state machine, `analysis.premise_mismatch`
- **Cap de 3 commits por iteração** (C1) — prompt do executor/corrector
  (Rule 17: pare nos 3, sub-slices sequenciais na MESMA branch) + juiz
  orientado a sinalizar >3 commits como non-blocking
- **`input_hashes` nas validation_rounds** (C2) — sha256 por arquivo
  alterado (máx 20, ≤2MB) + `git rev-parse HEAD` no payload: re-auditoria
  futura reproduz o estado exato medido (Type 7)

### Fixed

- **bug-078** — falso fechamento: task C da própria rodada teve executor E
  corrector codex falhando exit 1 com `changed=[]` e a iteração SEGUIA
  para validação; o juiz aprovou 1.0 confundindo o diff de OUTRA task no
  mesmo arquivo (o iter 1 havia rejeitado corretamente: "diffs são de
  outras tasks"). A revisão humana da rodada pegou zero código entregue.
  Agora `failed` + sem changed_files (mesmo após fallback git) é
  infra-reject (`AGENT-FAILED-NO-OUTPUT`), nunca mérito a validar —
  guard irmão do AGENT-EMPTY-OUTPUT

### Notes

- Dogfooding em números: 3 tasks, 3 COMPLETED, 2× iter 1 score 1.0 — e a
  única falha da rodada foi detectada exatamente pelo tipo de revisão que
  o `prompts.md` prega (verify-then-trust). codex segue instável editando
  service.py (2 mortes exit 1); guard bug-078 cobre a consequência

## 0.4.51 - 2026-07-31

O trust que pendurava o claude — e o fim do arrastão por disciplina.

### Fixed

- **bug-076** — claude CLI pendurava >15min sem heartbeat em workspace sem
  trust aceito (validador do smoke kimi; backlog "planner timeout ~9% com
  stdout vazio"). Novo `Repair-ClaudeTrust.ps1` (todo install/update)
  pré-aquece `projects["<path>"].hasTrustDialogAccepted` no `~/.claude.json`
  nos DOIS formatos de path que o claude grava. Cirurgia de TEXTO, não
  round-trip JSON: o arquivo real tem chaves duplicadas por caixa que
  quebram o ConvertFrom-Json do PS 5.1 e seriam perdidas. Testado:
  idempotente, arquivo íntegro
- **bug-077** — higiene git em árvore compartilhada. printbee, 30/07: SEIS
  quase-arrastões num dia evitados só por disciplina do agente (patch
  isolado de 1 arquivo/2 linhas em vez de `git add -A` sobre trabalho não
  commitado de outro agente). Três camadas: (1) guard hook intercepta
  **Bash** e bloqueia uma vez por classe `git add -A/--all/-u/.`,
  `commit -a/-am`, `stash`, `clean`, `reset --hard`, `checkout/restore .` —
  vale MESMO para o executor (verificado: perigoso exit 2, repetição passa,
  `git add <path>` livre); (2) matcher do guard em todos os projetos vira
  `Write|Edit|MultiEdit|Bash` (atualização in-place); (3) prompt do
  executor/corrector traz sempre o bloco "Higiene git"

### Added

- **Skills de operação de agentes** (pedido do dono): refresh do
  `call-agent` (kimi na tabela de comandos, quirks Windows: teto .CMD,
  stdin vs `-p`, sandbox 740, aliases reais, trust) e nova skill
  **`choose-model`** — decisão de agente/modelo por task_class: tiers,
  task_map, o que cada agente faz bem (medido na frota), cadeia de
  recuperação (rotação → quarentena → correction-loop → exaustão de cota)

### Notes

- Análise pedida — adzora: sessão claude de 29/07 com 3.246 linhas e
  **219 Edits diretos vs 3 menções ao orquestrador**; tasks do orquestrador
  paradas desde 22/07. É o padrão que bug-072 (.mcp.json) + guard + skills
  atacam: agente trabalhando direto porque não tinha o orquestrador à mão

## 0.4.50 - 2026-07-30

O kimi rodando — e o BOM que o derrubava no boot.

### Fixed

- **bug-074** — o `.mcp.json` do bug-072 era gravado por `Set-Content
  -Encoding UTF8` (PS 5.1) **com BOM**, e o parser do kimi rejeita BOM no
  primeiro byte: `kimi -p` morria no boot em qualquer projeto registrado
  ("Invalid JSON in .mcp.json"). Descoberto no primeiro smoke test real.
  Escrita agora via `WriteAllText` UTF8 sem BOM; idempotente — o update
  regrava os 12 projetos já corrigidos. Cursor tolera BOM, kimi não
- **kimi models** — `models.json` tinha o alias fictício `kimi-latest` em
  todos os tiers: toda run com `-m kimi-latest` falharia. Mapeado para os
  aliases REAIS do `~/.kimi-code/config.toml` (CLI 0.31):
  fast=`kimi-code/kimi-for-coding-highspeed`, demais=`kimi-code/k3`
  (flagship, 1M ctx; `default_model` da máquina já é k3). E mais: o
  manifest aplica models.json com `mode=merge` que PRESERVA o valor do
  projeto — o alias obsoleto ficou congelado nos 12 projetos. Novo
  `Repair-ModelsJson.ps1` (roda em todo install/update) faz o patch
  cirúrgico `kimi-latest` → aliases reais, idempotente, com backup

- **bug-075** — a propagação SKIPava projetos já na versão corrente e com
  isso pulava TODOS os reparos idempotentes: o `kimi-latest` ficou
  congelado nos 12 projetos (merge do manifest preserva o valor do
  projeto) e só saiu com o Repair rodado à mão. O branch
  `already current` da propagação agora executa os reparos de conteúdo
  (Repair-ModelsJson) mesmo sem bump — reparo passa a ser auto-curativo,
  não refém de versão nova

### Notes

- **Smoke end-to-end do kimi PROVADO** (sandbox dentro do pacote, adapters
  reais): `kimi -p` responde OK; task completa com `executor=kimi` —
  executor E corrector kimi **completed exit 0** em duas rodadas (segunda
  rodada em curso normal de validação quando o processo de smoke expirou)
- Achado colateral: validador claude pendurou >15min SEM heartbeat no
  sandbox recém-criado — consistente com trust dialog de workspace novo
  ("Run Claude Code interactively here once and accept the trust dialog")
  e com o backlog "planner claude timeout ~9% (stdout vazio)". Candidato a
  bug-075: pré-aquecer trust do claude no install/update

## 0.4.49 - 2026-07-30

Dois "por quês" do dono: os agentes que não chamavam — e o kimi invisível.

### Fixed

- **bug-072** — claude code e kimi code NUNCA chamavam o orquestrador: o
  MCP `orchestrator-ia` só era registrado no Cursor (`.cursor/mcp.json`).
  Os dois leem `.mcp.json` na raiz do projeto (mesma convenção `mcpServers`
  — verificado no dist do @moonshot-ai/kimi-code 0.31; ausência confirmada
  no `~/.claude.json` global e em todos os projetos). Novo
  `Configure-AgentMcp.ps1` escreve/ mescla `.mcp.json` por projeto (entry
  `orchestrator-ia` via stdio, projeto resolvido pelo cwd do spawn),
  preserva servidores existentes e roda em todo install/update
- **bug-073** — "orquestrador não usa o kimi k3 mesmo instalado": o CLI
  `@moonshot-ai/kimi-code` 0.31 estava instalado num prefix npm fora do
  PATH do processo MCP (`npm-global` do desktop); `which()` = shutil.which
  puro → `detect()` marcava kimi indisponível para sempre e o roteador o
  pulava em silêncio. `which()` agora faz fallback para bins globais npm
  conhecidos (`%APPDATA%\npm` e `npm prefix -g`, com cache por processo).
  Detectado ao vivo: `kimi.CMD` resolvido; profile `kimi -p` já estava
  verificado (0.29.2) e o teto cmd.exe do bug-061 cobre o shim .CMD

### Notes

- Cenário completo das 3 perguntas do dono nesta sessão: (1) Cursor era o
  único cliente com MCP registrado; (2) kimi CLI instalado mas fora do
  PATH; (3) models.json já tinha client kimi com task_map — o bloqueio era
  puramente detecção, nunca roteamento

## 0.4.48 - 2026-07-30

A regra de permissão que o claude ignorava em toda run.

### Fixed

- **bug-071** — o `.claude/settings.json` global tinha `Write(**)` no allow,
  regra que o claude atual IGNORA ("only Edit(path) rules are matched") —
  60-90% das agent_runs da frota carregavam o aviso no stderr (medido:
  GuardLine.BR 27/31, printbee 62/113, bootstrap-agents 13/46 das runs
  completadas). O `Repair-AgentHooks.ps1` (rodado em todo install/update)
  agora migra `Write(**)` → `Edit(**)` nos buckets allow/deny/ask das
  settings do projeto E da global do usuário, com dedup quando ambas
  coexistem, backup único (`.bak-bug071`) e idempotência

## 0.4.47 - 2026-07-30

O agente com pulso e sem serviço — toda rotação caía nele.

### Fixed

- **bug-070** — circuit breaker de agente. opencode tinha o binário
  instalado (`detect()` = disponível) mas o **servidor** morto: 15
  agent_runs consecutivas falhando em ~8s com "Unexpected server error"
  (printbee: agent_performance 3 runs / 0 sucessos; frota: 12 falhas de
  validator). Toda rotação de fallback — validator E executor — escolhia o
  mesmo agente morto e queimava a iteração. Agora: 3 falhas rápidas (<30s)
  consecutivas dentro de uma janela de 6h (qualquer task, lido de
  agent_runs) colocam o agente em **quarentena**; os dois pontos de escolha
  de fallback (`_next_validator_fallback` e a rotação de executor pós-infra)
  pulam para o próximo candidato. Cooldown de 6h: falha velha não condena
  para sempre. Sucesso recente ou falha lenta (trabalho real) quebram a
  quarentena

### Notes

- Medição pós-0.4.43 (bug-061): executor/corrector **8/8 completed** na
  frota (claude 7, codex 1) vs era pré-fix: codex 25 ok / 43 failed / 4
  timeout. Amostra pequena mas zero falhas de spawn desde o fix de stdin

## 0.4.46 - 2026-07-30

A versão que regredia sozinha — e o bug impossível de provar.

### Fixed

- **bug-068** — printbee regrediu 0.4.44 → 0.4.42 entre propagações e
  ninguém viu. Causa raiz: o `.orchestrator/` do printbee é **versionado no
  git do próprio projeto** (commit 849379b0b congelou a 0.4.42 no repo);
  checkout/restore derruba a working tree para a versão commitada. As três
  guardas anti-downgrade do CLI (install exit 6, update exit 6, propagate
  SKIP) protegem o orquestrador, não o git alheio. A propagação agora
  detecta `.orchestrator/VERSION` rastreado pelo git do projeto e emite
  `[AVISO]` + nota no relatório: commitar ou o update pode regredir
- **bug-069** — task 8193684389b1 (printbee, "/loop-bug BUG CONFIRMADO no
  navegador"): defeito de renderização; nem executor nem validador CLI
  abrem browser, e o critério "Defeito reproduzido com evidência registrada"
  foi lido como reprodução visual — rejeitado 2x idêntico até o
  repeat-limit. Template do loop-bug agora escopa a evidência de UI: teste
  que falha, DOM/snapshot do HTML gerado ou análise estática — screenshot
  de navegador explicitamente NÃO exigido de agentes CLI

### Notes

- Observação do ciclo: frota quieta, zero tasks RECEIVED/QUEUED vivas em
  todos os 12 projetos — watchdog do bug-064 confirmado em campo

## 0.4.45 - 2026-07-30

Aprovado 1.0 pelo juiz, executado pelo gate documental — por um link válido.

### Fixed

- **bug-066** — a task c003522e25e2 (printbee) passou no determinístico e no
  juiz LLM com **1.0** e morreu em CONSOLIDATING: "validação documental não
  passou". Causa: o link checker do `DocumentationValidator` tratava
  `/openapi/diagrams/<arquivo>.svg` — caminho de URL do dev server (dir
  public do frontend) com placeholder, escrito PELA própria task — como
  path de filesystem; resolvia para fora do projeto e retornava "failed".
  O checker agora ignora alvos não-verificáveis em disco (rota
  site-absolute `/...`, placeholder `<...>`, âncora pura) e normaliza
  fragmento `#secao`, query `?...` e `%20` antes do `exists()`. Links
  relativos quebrados e escapes para fora do projeto continuam reprovando
- **bug-067** — o juiz LLM roda `git status` com as próprias ferramentas e
  via os arquivos de INFRA do orquestrador (`.orchestrator/`, `.cursor/`,
  `.wolf/`, `AGENTS.md`..., sujos por update/propagação/adapters) como
  "alteração fora de escopo" — VAL-002 reprovou a iter 1 da mesma task
  mesmo com o changed_files do executor limpo. O prompt do validador agora
  lista explicitamente a infra do orquestrador como NUNCA-escopo

### Notes

- Varredura da frota (últimas 40h): 6 tasks — printbee 3 COMPLETED 1.0
  (feature, ajuste visual) + GuardLine.BR 1 COMPLETED 1.0; a única morte
  injusta era o par bug-066/067. A INCOMPLETE 8193684389b1 (/loop-bug UI)
  parou por same_issue_repeat_limit com a mesma issue legítima 2x —
  comportamento correto: bug de browser que nem executor nem validador
  conseguem evidenciar via CLI

## 0.4.44 - 2026-07-30

A suite quebrada que condenava a task — antes de ela começar.

### Fixed

- **bug-065** — baseline de testes pré-executor. Suite já quebrada na entrada
  (corehub: restore NuGet falho no CLI — `Value cannot be null (path1)` em
  qualquer SDK; printbee: suite da raiz quebrada, INCOMPLETE 1d63d2a5cb28,
  pendência assumida na 0.4.41) era classificada `failure_kind="introduced"`
  e a task estava condenada a INCOMPLETE por mérito alheio. Agora:
  - o runtime captura uma **baseline** (`run_all`) ANTES de o executor tocar
    a árvore, persistida em `test_runs` com `discovery_source=baseline:*`
  - falha na iteração com a mesma assinatura (comando + exit code) da
    baseline vira `"preexisting"` — o determinístico já a honrava como
    não-bloqueante, mas o **segundo gate** (`TEST-FAIL`, "testes falhos
    sempre forçam correção") ainda contava pré-existente como falha:
    `tests_passed` e a descrição do issue agora ignoram `preexisting`
  - prompt do corretor separa "corrija até passarem" (introduced) de
    "pré-existentes — NÃO é exigido corrigir"; prompt do validador carrega
    `failure_kind` com a regra explícita
  - falha da baseline que PASSA após o trabalho conta como passed (melhoria
    real, não isenção)
  - e2e: suite pré-quebrada + entrega real → COMPLETED 0.95 iter 1 (antes:
    INCOMPLETE 0.4 com TEST-FAIL)

## 0.4.43 - 2026-07-29

A task que nascia morta no spawn — e os testes que cobravam ambiente como
mérito. Dissecado na primeira task real do corehub pós-0.4.40
(`b6c4e9ba0a15`, LGPD backend .NET): INCOMPLETE score 0.25 com executor E
corrector zerados e 20 min queimados em teste que nunca terminaria.

### Fixed

- **bug-061** — cmd.exe processa `.CMD`/`.BAT` com teto próprio de **8191
  chars** por linha, muito abaixo dos 32767 do CreateProcess que o
  `ARGV_LIMIT` (30000) assumia. Prompt de 9.635 chars para `codex.CMD`
  morria no spawn com "Linha de comando muito longa." (exit 1, 29 bytes)
  ANTES de o agente iniciar — reproduzido na máquina: 8.100 passa, 8.200
  falha. Era a causa oculta do padrão da frota "codex executor: 30 failed /
  17 ok". O teto agora é calculado pelo executável resolvido
  (`_effective_argv_limit`) sobre a linha COM quoting (`list2cmdline`);
  CLI sem suporte a stdin e linha acima do teto falha pré-spawn com
  `[argv-overflow]` (exit 126) em vez do erro críptico do cmd.exe
- **bug-062** — .NET 10 preview (10.0.400) recusa `dotnet test` sem argumento
  mesmo com UM `.sln` na pasta quando há `.csproj` em subdirs (MSB1011,
  reproduzido no corehub). Discovery emite o alvo explícito
  (`.sln` > `.slnx` > `.csproj`) — e passa a reconhecer o formato `.slnx`
  também no marcador de subdirs
- **bug-063** — efeito colateral do bug-056: a discovery mais ampla passou a
  achar testes não-executáveis. `npm test` sem `node_modules` ("'stencil'
  não é reconhecido", cobrado como mérito com `failure_kind=introduced`)
  agora vira `skipped/deps_missing` — mesmo tratamento "ambiente ≠ mérito"
  do bug-050. E `ng test` sem `--watch=false` (Karma em modo watch) travou
  601s até timeout, 2x por task; o runner anexa `-- --watch=false`,
  convertendo hang em falha rápida e honesta
- **bug-064** — double-submit (2 `create_task` em 16s via MCP) gerava tasks
  gêmeas e uma travava RECEIVED sem dono. `create_task` ficou idempotente
  (mesmo prompt + mesmo dry_run em 120s devolve a existente, com evento de
  auditoria) e o sweep de RECEIVED velhas também roda no `status()`/
  `list_tasks()` — antes só rodava ao criar task nova. Bônus: o roundtrip
  SQLite perdia o tzinfo do `created_at`, o `except` engolia o TypeError e
  **a varredura nunca cancelava nada lido do DB** — corrigido assumindo UTC
  em timestamp naïve

### Notes

- Teste do bug-041 (`test_cli_sem_stdin_nao_perde_o_texto`) atualizado para o
  novo contrato: sem stdin + overflow = falha pré-spawn `[argv-overflow]`,
  não spawn condenado
- corehub continua com pendência de PROJETO (não do orquestrador): restore
  NuGet quebrado (`Value cannot be null. (Parameter 'path1')`) e tsconfig de
  specs do frontend sem inputs (TS18003)

## 0.4.42 - 2026-07-29

A fila presa atrás de uma task cancelada.

### Fixed

- **bug-059** — "fila presa de novo → cancelei e rodei inline" (GuardLine,
  6 tasks canceladas em 1 dia por fila). Cadeia medida no DB + lock:
  (1) coroutine do pré-loop congelou num `git status` — `subprocess.run`
  com PIPE pendura para SEMPRE no pós-kill do timeout quando um neto do git
  (ex.: `fsmonitor--daemon`) herda os handles de saída; (2) a coroutine
  congelada nunca chega ao `finally`, então a task cancelada fica em
  `_running_tasks` segurando o `WriteLock` (lock de 21:16 UTC ainda vivo
  1h depois, pid do MCP); (3) `_busy_task_id` apontava para essa task
  terminal e toda task nova virava `QUEUED behind <CANCELLED>`, sem dequeue
  nunca. Quatro correções:
  - `_run_git` captura em ARQUIVO (nunca PIPE — deadlock de EOF impossível),
    roda com `core.fsmonitor=false` (sem daemon-neto) e no timeout mata a
    ÁRVORE (`taskkill /T`), não só o git
  - `_busy_task_id` ignora task em estado terminal presente em
    `_running_tasks` — zumbi cancelada não ocupa o workspace nem vira
    "behind" de ninguém
  - `_execute_loop` valida cancel/terminal ANTES do pré-loop (baseline git):
    cancel no intervalo aborta na hora, solta lock e destrava a fila
  - `cancel()` dispara `_maybe_start_next` — cancelar quem encabeçava a fila
    desfila quem estava atrás imediatamente

### Notes

- Lock órfão da GuardLine removido na intervenção; reload do Cursor/MCP na
  GuardLine ainda recomendado (o processo antigo pode manter a coroutine
  congelada até reiniciar)

## 0.4.41 - 2026-07-29

O agente que se achava filho — e o wrapper que nao achava o PowerShell.

### Fixed

- **bug-057** — `ORCHESTRATOR_CHILD_AGENT` era tratado como **presenca**, nao
  valor: a var chegava VAZIA (herdada de shell/wrapper) e o agente principal
  se considerava delegado — recusava orquestrar e fazia tudo inline
  (registrado no Do-Not-Repeat da GuardLine: *"is presence-based, even when
  its value is blank... do the task inline and never call orchestrator
  dispatch"*). Agora vazio/`0` NAO e filho em TODOS os pontos:
  `is_child_agent()` no runtime (CliExecutor + guard do
  `orchestrator_delegate` MCP), `orchestrator-guard.js`,
  `Invoke-RoutedAgent.ps1`, e os textos dos 5 adapters + skill call-agent
  dizem explicitamente que so valor nao-vazio ≠ `0` (runtime seta `1`)
  identifica o filho
- **bug-058** — `findPowerShell` so procurava `powershell.exe`/`pwsh.exe` no
  PATH; shells de agente chegam com PATH sem System32 e o wrapper morria sem
  PowerShell (GuardLine contornou na mao prependando
  `C:\Windows\System32\WindowsPowerShell\v1.0` ao PATH). Fallback por caminho
  absoluto (`%SystemRoot%\System32\...\powershell.exe` e `Sysnative` para
  processo 32-bit) entra na lista de candidatos

### Notes

- Frota sem tasks presas: varredura 29/07 — 0 tasks nao-terminais nos 10
  projetos. GuardLine 2bd9da5de2dd COMPLETED 1.0 confirma o pipeline pos
  0.4.35–0.4.40. printbee 1d63d2a5cb28 INCOMPLETE por suite pre-existente
  quebrada na raiz (pytest failed + npm test timeout) — pendencia conhecida:
  baseline de testes pre-task para distinguir falha introduzida de
  pre-existente

## 0.4.40 - 2026-07-28

Auditoria de uso da frota — descoberta de testes cega a stack em subdiretórios.

### Fixed

- **bug-056** — projetos com a stack fora da raiz e sem repos git filhos
  (printbee: `src/backend` .NET + `src/frontend` Angular) rodavam 100% das
  tasks com teste `<none>/skipped`: o bug-048 cobriu repos aninhados
  (GuardLine), mas subdiretórios comuns ficaram de fora. Quando raiz +
  extra_dirs não acham stack, o `TestRunner.run_all` varre subdiretórios até
  profundidade 2 (`TestDiscovery.discover_subdirs`), pulando
  node_modules/bin/obj/ocultos e repos filhos com `.git` (estes seguem via
  extra_dirs). Comportamento inalterado quando a raiz já tem stack.

### Notes

- Testes: runtime 297 passed / 3 skipped (5 novos em
  `test_0440_discovery_subdirs.py`).
- Achados da auditoria fleet (2026-07-28): 4 projetos com DB de tasks
  (GuardLine.BR, printbee, bootstrap-agents, adzora); os demais 6 só têm o
  orquestrador instalado, sem uso. GuardLine pós-0.4.38: primeira task
  COMPLETED 1.0 genuína (2bd9da5de2dd). 0.4.39 (bug-055, graphify
  anti-janela) estava commitada local sem push — vai neste push.

## 0.4.39 - 2026-07-28

## 0.4.39 - 2026-07-28

O commit que piscava janela — reparo do graphify vira etapa do update.

### Fixed

- **bug-055** — a cada `git commit`/`git checkout`, o hook do graphify
  relancava o rebuild do grafo via `python.exe` (subsistema de CONSOLE do
  Windows: todo processo aloca janela ao nascer) destacado e **sem supressao
  de janela** — console piscando na tela a cada commit. O fix manual validado
  no PrintBee (preferir `pythonw.exe` no interpretador pinado +
  `CREATE_NO_WINDOW`/0x08000000 nas creationflags do Popen) vivia em
  `.git/hooks`, que nao e versionado — `graphify hook install` sobrescrevia e
  desfazia o reparo. Novo `Repair-GraphifyHooks.ps1` roda em **todo
  install/update/propagate**: patch idempotente nos `post-commit`/
  `post-checkout` do repo raiz **e dos repos git filhos imediatos** (layout
  pasta-mae, GuardLine.BR), derivando o caminho do `pythonw.exe` do proprio
  `_PINNED` gravado no hook (sem hardcode de usuario), com backup ao lado
  (`*.bak-orchestrator-*`), preservando LF e tocando apenas arquivos com o
  marcador do graphify

### Notes

- `Test-GraphifyHookRepair`: patch raiz + filho, fallback `python.exe`
  preservado como `elif`, idempotencia (2a rodada no-op, sem novo backup),
  hook sem graphify intocado, e re-aplicacao apos `graphify hook install`
  sobrescrever. Validado ao vivo: PrintBee (fix manual) reporta "fix ja
  aplicado" — a deteccao casa com o reparo feito a mao

## 0.4.38 - 2026-07-28

Terceira rodada GuardLine.BR (parte 2) — a task que o validador aprovava e o
sistema reprovava. Todas medidas na task ff270e3ff814.

### Fixed

- **bug-051** — o validador determinístico reprovava critérios EVIDENCE/CUSTOM
  sem parâmetros (inverificáveis por definição) quando `changed=[]` e testes
  skipped — caso de task re-executada sobre entrega já existente — e o
  "prefer stricter" vetava a aprovação 1.0 do validador LLM que leu os
  arquivos. Agora EVIDENCE/CUSTOM sem evidência objetiva fica
  `satisfied=None` (indeterminado, marcado `unverifiable`) e nunca bloqueia;
  kinds verificáveis (workspace_changes, tests_pass, soma_module,
  docs_example) seguem reprovando sem evidência.
- **bug-052** — `same_issue_repeat_limit` contava por id posicional
  (`VAL-001` = 1ª issue da rodada): problemas diferentes com o mesmo id entre
  iterações ("Critério não atendido: coleção Postman..." → "Teste falhou: go
  test") encerravam a task por coincidência de posição. Identidade da issue
  agora é `id + descrição normalizada`.
- **bug-053** — validator==executor após rotação de infra (executor girou
  para o agente do validator pós-EXEC-SPAWN, ou validator caiu no agente do
  executor por quota/ENOTFOUND) virava `VAL-IND` bloqueante em toda iteração
  — aprovação impossível por infra. Antes de bloquear, o validator gira para
  um fallback disponível ≠ executor; `VAL-IND` só resta sem alternativa.
- **bug-054** — `go test ./...` executava testes live (rede + certs mTLS)
  que falham offline (`TestLive_OAuthMTLS_DES`) e bloqueavam o portão para
  sempre. Descoberta Go agora roda `go test -short ./...` — `testing.Short()`
  é o idiom padrão Go para pular live/integração.

### Notes

- Testes: runtime 292 passed / 3 skipped (6 novos em
  `test_0438_guardline_round3.py`; `test_unknown_criterion_requires_evidence`
  atualizado para o contrato do bug-051).
- O bug-050 (0.4.37) segurou o `make test` inexistente como
  `skipped/tool_missing` nesta mesma task — confirmado em produção.

## 0.4.37 - 2026-07-28

Terceira rodada GuardLine.BR — ferramenta ausente não é teste falho.

### Fixed

- **bug-050** — o fix do bug-048 passou a descobrir `go test ./...` e
  `make test` dentro dos repos filhos, mas ferramenta fora do PATH (ou
  inexistente na máquina) voltava exit 127 (WinError 2) do CliExecutor e era
  classificada como teste falho (`failure_kind: introduced`) → `TEST-FAIL`
  bloqueante → task INCOMPLETE por ambiente, mesmo com o validador aprovando
  1.0 e os 4 ACs satisfeitos (medido na task 3b56b92278e9: `make` não existe
  na máquina, `go` fora do PATH do processo). O `TestRunner.run_all` agora faz
  pre-flight `which()` do executável e reporta `skipped` +
  `failure_kind: tool_missing` — o portão `tests_passed` não bloqueia e o
  validador vê a causa honesta no prompt. Falha real de suite (exit != 0 com
  ferramenta presente) segue bloqueante.

### Notes

- Testes: runtime 286 passed / 3 skipped (4 novos em
  `test_0437_tool_missing.py`; `test_run_all_extra_dirs_roda_no_repo_filho`
  passou a mockar `which` para seguir hermético em máquina sem `go`).

## 0.4.36 - 2026-07-28

Segunda rodada GuardLine.BR — testes cegos e prompt corrompido.

### Fixed

- **bug-048** — em workspace pasta-mae de repos aninhados, a descoberta de
  testes so olhava a raiz — que nao tem marcador de stack nenhum — e devolvia
  `<none>/skipped`. O validador reprovava `tests_pass` por falta de evidencia
  em toda iteracao, mesmo com `go test` verde dentro do repo filho. Agora o
  `TestRunner.run_all` recebe os repos filhos tocados pelos `changed_files` da
  iteracao (derivados pelo fix do bug-047) e roda a descoberta/execucao dentro
  deles, com `discovery_source` prefixado (`travelex-api/go.mod`)
- **bug-049** — prompt criado via terminal com codepage CP1252 (caller
  `cursor`) era persistido com mojibake UTF-8 ("exigÃªncia" em vez de
  "exigência") — medido na task 117c69f1e4b2 da GuardLine; o texto corrompido
  seguia para analyzer, executor e validator. `repair_mojibake` na ingestao
  (`create_task`): assinatura `Ã/Â + U+00A0..U+00BF` dispara o round-trip
  cp1252→utf-8, com contagem de marcadores decrescente como guarda — "NÃO"/
  "SÃO" legitimos nao casam a assinatura e passam intactos; mojibake duplo e
  desfeito em duas rodadas

### Notes

- Task 117c69f1e4b2 (12:03 UTC) nasceu 3 min antes da propagacao da 0.4.35 e
  rodou num processo com modulos antigos — criterios de template e
  `changed=[]` esperados. Processos MCP/CLI persistentes precisam de reload
  apos update (o proprio runtime recusa `orchestrator_run` com
  `mcp_modules_stale` quando detecta)

## 0.4.35 - 2026-07-28

A task que nascia reprovada — auditoria GuardLine.BR.

### Fixed

- **bug-045** — `detect_loop` casava substring **sem fronteira de palavra** e
  qualquer hit incidental sequestrava os criterios da task. Medido na
  GuardLine: "erro" casou dentro de **"errors"** (ingles), "mvp" casou em *"O
  MVP **ja existe**"* e *"**se** gap for bug, corrigir"* (clausula condicional)
  ligou o loop de bug numa task de publicacao Postman — 4 tasks julgadas por
  criterios de template errado ("Defeito reproduzido com evidencia" numa task
  de colecao de API). Agora: palavra inteira (radical marcado com `*`),
  clausulas condicionais (`se/caso/if ...`) nao contam, e 1 hit isolado num
  prompt longo (>240 chars) nao impoe loop — em prompt curto a palavra-chave e
  o assunto e segue valendo
- **bug-046** — criterios escritos pelo usuario como **"Criterios: a; b; c"**
  (prosa ou bullets) eram ignorados: so o formato `AC-001:` era reconhecido, e
  o template do loop vencia os criterios reais do prompt. Na GuardLine, 3 das
  4 tasks recentes declaravam criterios explicitos — todos descartados; a task
  reprovava por ACs que ninguem pediu ate `same_issue_repeat_limit` →
  INCOMPLETE (38 min queimados). `parse_criteria_section` agora reconhece a
  secao (inline com `;` ate o fim da frase, ou bloco de bullets) e mantem a
  precedencia: ACs do usuario > loop > heuristica
- **bug-047** — `changed_files_since` era **cego a repos git aninhados**.
  GuardLine.BR e uma pasta-mae com ~40 repos filhos (travelex-api/, onp-api/,
  cada um com `.git`); `git status` na raiz nao desce no repo aninhado, entao
  `changed=[]` em 100% dos agent runs — `workspace_changes` nunca passava,
  40 min de trabalho real do codex viraram `AGENT-TIMEOUT-NO-OUTPUT` e o
  corrector repetia as mesmas issues ate o usuario cancelar. O baseline agora
  captura o porcelain de cada repo filho imediato e o diff reporta os paths
  prefixados (`travelex-api/main.go`) — inclusive quando a raiz nem e repo git

### Notes

- O cancel-race *"Transicao invalida: CANCELLED -> TESTING"* visto na task
  85ff56f1f7da (23/07) ja fora corrigido pelo hard-stop do bug-022 — a task
  rodou em versao anterior; nenhuma mudanca adicional
- Heartbeat persistido (bug-040, 0.4.29) confirmado em producao na GuardLine:
  eventos `agent_progress` a cada 30s durante toda a execucao

## 0.4.34 - 2026-07-27

O lembrete que falava uma vez e calava.

### Fixed

- **bug-044** — `orchestrator-guard` avisava **uma unica vez por sessao**. Numa
  sessao de 12h no proprio repo do orquestrador ele disparou as 01:03 e nunca
  mais: 1 interrupcao para dezenas de arquivos de codigo editados direto depois.
  A mensagem ainda ensinava o desvio — *"repita a operacao: este aviso so
  aparece uma vez por sessao"*. Um ponto de interceptacao que fala uma vez e
  cala e uma formalidade, nao um controle
- O aviso agora **rearma** a cada `ORCHESTRATOR_GUARD_REARM_MIN` minutos (padrao
  20) e informa **quantos arquivos** ja foram editados direto na sessao. A
  repeticao imediata segue passando — o objetivo continua sendo forcar a decisao
  consciente, nao travar a sessao. `ORCHESTRATOR_GUARD_REARM_MIN=0` volta ao
  comportamento antigo; `ORCHESTRATOR_GUARD=off` desliga
- O marcador virou JSON (`{edits,last_at}`) e tolera BOM na leitura: uma
  ferramenta que reescrevesse o arquivo no Windows quebrava o `JSON.parse` em
  silencio e a contagem reiniciava
- `Test-Hooks` cobre bloqueio, silencio dentro da janela, rearme apos a janela,
  contador e isencao de documentacao. O teste entrega o payload por **redirect**
  e nao por pipe: o pipe do PowerShell nao chega ao `fs.readFileSync(0)` do node,
  e o hook lia vazio — daria teste verde para um guard que nunca bloqueou

## 0.4.33 - 2026-07-27

O update tambem reconfere — nao so o install.

### Fixed

- O branch `update` do instalador **nunca chamava** `Probe-Agents`: so o
  `install` chamava. A 0.4.32 ligou o probe por padrao, mas isso so valia para
  quem instalava do zero — nos 9 projetos propagados o `probe-results.json`
  seguiu congelado na data da instalacao (medido: **21/07**, seis dias e varias
  versoes atras). Agora o probe roda no update tambem, logo apos o refresh de
  deteccao, com o mesmo opt-out `-SkipAgentProbes`. `Test-AgentUpdates` apaga o
  arquivo, roda um update e exige que ele volte com `skipped != true`

## 0.4.32 - 2026-07-27

Todo update reconfere os agentes da maquina.

### Changed

- `Probe-Agents` volta a rodar **por padrao** em install/update (opt-out:
  `-SkipAgentProbes`). Estava desligado por default: o `probe-results.json`
  desta maquina estava parado em `skipped: true` desde **19/07**, oito dias sem
  reconferir nada
- O probe passou a **conferir o profile contra o CLI instalado**, nao so a rodar
  `--help`. Pede o help do comando que o profile realmente invoca — as flags do
  codex (`--sandbox`, `--skip-git-repo-check`) so aparecem em
  `codex exec --help`, e pedir o help de topo gerava falso "flag ausente" — e
  verifica se cada flag existe. Grava versao do CLI, flags esperadas e ausentes
  em `probe-results.json`, e imprime `[ACAO]` para cada profile suspeito

### Fixed

- **bug-043** — o profile do kimi invocava o CLI de um jeito que ele recusa.
  `prompt_flag: null` mandava o prompt como argumento nu e o kimi respondia
  `unknown command 'Responda apenas: ok'`. Agora usa `-p`, o modo nao-interativo
  documentado, conferido contra o CLI 0.29.2. O kimi era **fallback em 80
  planos** da frota — nunca chegou a ser acionado, e teria falhado 100% das
  vezes. `sandbox_flags` fica vazio de proposito: o CLI recusa `--auto` e
  `--yolo` junto com `-p`. `model_flag: "-m"` adicionado em `models.json`, que
  nao tinha nenhum — o modelo resolvido nunca chegava ao kimi
- `invoke.prompt_stdin: false` no profile do kimi e respeitado pelo adapter:
  `-p` exige valor, entao o fallback de stdin da 0.4.30 deixaria um `-p` vazio.
  Prompt grande demais para argv falha com erro explicito em vez de comando
  invalido

## 0.4.31 - 2026-07-27

Atualizacao de agente que nao mente.

### Added

- Estrategia `native-installer` no `Update-Agents`: agente cuja instalacao
  nativa nao se auto-atualiza (kimi no Windows) passa a ser atualizado pelo
  **instalador oficial do proprio agente**, em vez de so reportar o comando.
  A URL vem de `Get-AgentNativeInstallerMap` — mapa curado no codigo, nunca o
  comando lido da saida do CLI: executar texto vindo de stdout seria injecao.
  O script e baixado para `.orchestrator/runtime/installers/` e so entao
  executado; tamanho e SHA256 vao para o log. `-NoNativeInstaller` desliga e
  volta ao comportamento de so reportar.
  **Implicacao:** com isto, `orchestrator update` baixa e executa um script
  remoto do fornecedor do agente — mesma classe de `npm install -g` e
  `choco upgrade`, que a cadeia ja fazia, mas vale saber

### Fixed

- **bug-042** — `Update-Agents` reportava como **atualizado** um CLI que nao se
  atualizou. O kimi instalado por instalador nativo no Windows nao sabe se
  auto-atualizar: ele imprime o aviso e sai com **exit 0**. Como a decisao
  olhava so o exit code, virava `updated`. Quando a checagem de versao falhava
  por rede, o mesmo agente virava `[AVISO] native:kimi falhou` — dois desfechos
  errados para o mesmo CLI. Agora o que decide e o que o CLI disse: ao anunciar
  "auto-update is not supported", o agente entra em `manual_required`, o comando
  manual que ele mesmo imprime e extraido da saida e repetido no fim do log
  (`[ACAO] kimi: atualize manualmente -> ...`), e os fallbacks npm/choco/scoop
  sao pulados — instalariam uma copia paralela a nativa e o PATH passaria a
  resolver outra versao. Falha transitoria de rede segue como aviso, com
  fallback intacto

## 0.4.30 - 2026-07-27

O agente que nunca nascia.

### Fixed

- **bug-041** — prompt grande estourava o limite de linha de comando do Windows
  e o agente NUNCA rodava. `CreateProcess` corta em 32767 chars; o Popen morria
  com "Linha de comando muito longa" (WinError 206) e o `executor-codex.txt`
  ficava com 30 bytes — zero arquivo tocado — mas a task seguia para validacao
  como se tivesse executado e terminava INCOMPLETE com score 0.8. Parecia
  trabalho ruim do agente; era processo que nunca nasceu. Passou a estourar na
  0.4.27, quando o prompt do executor passou a carregar skills + rules + loop:
  prompt de usuario de ~6KB ja bastava. Medido no printbee: 2 tasks, executor E
  corrector. Agora, quando argv passaria de 30000 chars, o prompt vai por stdin
  — caminho nativo dos dois CLIs (`codex exec` e `claude -p` leem stdin quando
  nao recebem o texto). `invoke.prompt_via: "stdin"` forca o modo. WinError 206
  residual agora retorna erro explicado em vez de 30 bytes crus
- Testes `test_0429_prompt_via_stdin.py` (6 casos, codex e claude)

## 0.4.29 - 2026-07-27

O orquestrador sabe quem o chamou — e o sinal de vida finalmente chega em quem
esta olhando.

### Added

- `callers.py`: deteccao da superficie que originou a chamada (`claude-code`,
  `cursor`, `codex`, `mcp`, `cli`), com override por `ORCHESTRATOR_CALLER`. Cada
  uma tem contrato diferente: sessao bloqueante fica muda sem eco no console;
  quem faz polling nao ganha nada com stdout e depende dos eventos
- Perfil por chamador aplicado em tres pontos: eco do CLI filho, cadencia do
  heartbeat (20s em sessao bloqueante, 30s em quem faz polling) e escolha de
  executor — o CLI que ja esta ocupado atendendo o usuario deixa de ser a
  primeira escolha (preferencia, nao restricao: se for o unico, e usado)
- Campo `caller` gravado na analise da task, para relatorio e auditoria
- Testes `test_0429_caller_awareness.py` (11 casos) e
  `test_0429_heartbeat_persisted.py` (3 casos)

### Fixed

- **bug-040** — `agent_progress` nunca chegava ao banco. A 0.4.28 fez o
  heartbeat do CLI virar evento, mas emitia so no `EventBus` (stderr + historico
  em memoria); a persistencia vive em `repo.add_event`. Resultado: o publico que
  a correcao existia para atender — quem observa por MCP/DB e via EXECUTING
  parado por 10-30 min — seguia sem ver nada. Medido na frota com GuardLine.BR
  ja na 0.4.28 e uma task VIVA em EXECUTING: zero eventos `agent_progress`.
  A logica saiu de dentro de `_run_agent` para `_register_heartbeat`, que agora
  tem teste

## 0.4.28 - 2026-07-27

Plano executado ate o fim + progresso visivel.

### Added

- Continuacao de plano: quando o executor volta com o plano incompleto, o
  runtime manda CONTINUAR de onde parou em vez de validar trabalho pela metade.
  Contrato explicito `PLAN_STATUS: {"complete": bool, "remaining": [...]}` no
  fim da saida do executor, com fallback por frases de parada ("quer que eu
  continue?", "parte 1 de 3", "shall I continue"). Orcamento
  `max_plan_continuations` (default 5) em policies.json; continuacao NAO gasta
  iteracao de validacao
- Evento `agent_progress`: cada heartbeat do CLI vira evento de task. Sem isso o
  heartbeat so existia no console de quem chamou, e quem observava por MCP/DB
  via a task parada em EXECUTING por 10-30 min e concluia que travou
- Testes `test_0428_plan_continuation.py` (8 casos, 2 e2e)

### Fixed

- `orchestrator-guard`: isencoes de caminho comparavam com `path.sep`, mas o
  Claude Code envia `file_path` com barra normal no Windows — as isencoes
  falhavam em silencio e o guard bloqueava edicao em `.wolf/`, `.claude/` e
  `.cursor/`

## 0.4.27 - 2026-07-27

Loops de execução + regras do projeto no prompt do executor.

Um prompt termina numa resposta; um loop termina num resultado verificado. O
pedido agora escolhe um roteiro nomeado com etapas obrigatórias e critérios
próprios, e o executor passa a receber as regras que o time já escreveu.

### Added

- `planning/loops.py` — 5 loops de execução selecionados pelo pedido:
  - `/loop-bug` — reproduzir → diagnosticar → teste que falha → corrigir na raiz → validar
  - `/loop-mvp` — planejar → construir → executar → corrigir → repetir até abrir
  - `/loop-landing` — auditoria em oferta, copy, clareza, mobile e conversão
  - `/loop-conteudo` — pesquisar ângulos → variações → criticar → melhorar → escolher
  - `/loop-saas` — produto → desenvolvimento → marketing → validação → revisão final
- Seleção automática por palavra-chave; override explícito por prefixo
  (`/loop-bug ...`) ou `orchestrator run --loop bug`. Sem match, nenhum loop é imposto
- Etapas do loop injetadas no prompt do executor (`_loop_block`) e no plano
  (`loop`, `loop_stages`, `loop_done_when`)
- `rules/discovery.py` — descoberta de regras do projeto por frontmatter
  (`description`, `globs`, `alwaysApply`) e seleção por relevância ao pedido;
  injetadas no prompt do executor (`_rules_block`). Antes, as regras existiam em
  `.cursor/rules/` e nunca chegavam ao agente
- Catálogo global: `marketingskills` (41.8k stars, MIT) e `anthropics/skills`
  (164k stars), com mapa `departments` cobrindo os 7 times de skills
- Testes `test_0427_loops_and_rules.py` (13 casos)

### Changed

- `TaskAnalysis.loop` — campo novo com o loop escolhido
- Precedência de critérios: ACs declarados no prompt > critérios do loop > heurística

## 0.4.26 - 2026-07-26

Onboarding vendor-neutro do orquestrador + varredura de bugs abertos.

Auditoria da frota (10 projetos, rodada pelo próprio orquestrador — task
`ca2c5142e0ae`) mostrou 86 tasks com 9,3% de conclusão e 68,6% de cancelamento.
Causa raiz do não-uso: as instruções operacionais viviam só em
`.cursor/rules/multiagent-orchestrator.mdc`, que apenas o Cursor lê.

### Added

- Bloco canônico vendor-neutro `orchestrator:how-to-use` distribuído a
  `CLAUDE.md`, `AGENTS.md`, `GEMINI.md` e `KIMI.md` de todos os projetos:
  comandos essenciais, MCP vs CLI, contrato de poll, anti-recursão, tempos
  normais por estado (para não cancelar por impaciência) e o que não vasculhar
- `scripts/Repair-AgentHooks.ps1` — remove hooks que disparam um processo por
  chamada de ferramenta; roda em todo install/update (bug-033)
- `Merge-JsonFileAdditive` / `Merge-JsonObjectAdditive` — deep-merge aditivo em
  arquivos `mode=merge` (bug-003)
- `parse_declared_criteria` — ACs escritos no prompt vencem a inferência (bug-031)
- Testes: `Test-MergeAdditive.ps1`, `test_0426_declared_acceptance_criteria.py`,
  `test_0426_cancel_race_no_zombie_event.py`, `test_0426_cancel_stops_loop_e2e.py`

### Fixed

- **bug-003** — `mode=merge` só pulava o arquivo existente: chaves novas do
  template (ex.: `model_flag`, `stale_received_ttl_hours`) nunca chegavam a
  projetos instalados. Agora entram preservando os valores do usuário
- **bug-022/bug-029** — após cancel concorrente, `transition()` emitia
  `STATE_CHANGED` de uma transição que `save()` já havia neutralizado e o loop
  seguia (19 eventos zumbis medidos na frota)
- **bug-028** — `Get-Content -Raw` sem `-Encoding UTF8` no `Generate-Adapters`
  gravava dupla codificação nos adapters; 30 arquivos da frota reparados
- **bug-030** — `test_lock_timeout_does_not_mark_task_failed` esperava
  `RECEIVED`; desde 0.4.19 o destino correto é `QUEUED`
- **bug-031** — ACs do prompt eram descartados e o plano injetava `tests_pass` /
  `docs_example`, reprovando auditoria read-only por suíte alheia
- **bug-032** — `docs/superpowers/` rastreado no HEAD contradizia
  `Test-NoLegacyArtifacts`; conteúdo movido para `docs/archive/superpowers/`.
  `Test-ProjectPropagate` falhava porque fixtures de teste eram puladas no
  registro mesmo com registry isolado por `ORCHESTRATOR_PROJECTS_REGISTRY`

## 0.4.25 - 2026-07-25

Planner com Claude: usa o melhor modelo e faz fallback automático se a cota esgotar.

### Added

- `resolve_model_candidates` + detecção de cota/rate-limit (`routing/quota.py`)
- `_run_agent` tenta o próximo modelo da preferência do papel quando a CLI sinaliza esgotamento
- Planner Claude: `fable → opus → sonnet`
- Feature `planner_model_quota_fallback`
- Migration `0.4.24-to-0.4.25`
- Testes `test_planner_quota_fallback.py`

### Changed

- Docs `model-routing.md` — seção de fallback de cota

## 0.4.24 - 2026-07-25

Correções P0–P2 da auditoria multi-projeto: cancel confiável, MCP stale, registry, spawn, fila.

### Fixed

- **bug-022:** `save` não ressuscita task terminal; `transition` relê DB e aborta com `CancelledError` ao sair de CANCELLED/FAILED/…
- Loop checa cancel/`_ensure_runnable` entre fases (incl. TESTING/VALIDATING)
- `cancel(reason=)` persiste motivo em `error`
- MCP `orchestrator_run` **recusa** se `modules_stale` (opt-out: `ORCHESTRATOR_ALLOW_STALE_MCP=1`)
- SELECTING_AGENTS com teto 180s (refine limitado ao restante)
- WinError 2: stderr com path/`which`/command explícitos
- Registry: não registra `Temp/orchestrator-tests-*`; `Prune-OrchestratorProjectRegistry` no propagate

### Added

- Evento `TASK_QUEUED`
- Onboarding no primeiro run (probe agentes + `memory/legacy-import/INDEX.md`)
- `role_model_preferences.planner` no patch de models
- Rules git-workflow: não commit inline com task ativa
- Feature flags: `cancel_terminal_hard_stop`, `mcp_stale_run_reject`, `registry_prune_test_fixtures`, `task_queued_event`
- Migration `0.4.23-to-0.4.24`
- Testes `test_0424_p0_p2_fixes.py`

## 0.4.23 - 2026-07-25

Antes do install/update, importa rules/skills/adapters já presentes no repositório para `legacy-import/` (aditivo; não apaga a origem).

### Added

- Hotspots migrate: `.claude/skills`, `.cursor/rules`, `.codex/skills`, `.gemini/skills`, `.opencode/skills`
- Snapshot de `CLAUDE.md` / `AGENTS.md` / `CURSOR.md` / `CODEX.md` / `GEMINI.md` / `KIMI.md` → `memory/legacy-import/adapters/`
- Exclusão de rules geradas do template Cursor + `openwolf.mdc` na cópia de `.cursor/rules`
- Feature `preinstall_import_existing_config`
- Migration `0.4.22-to-0.4.23` (reexecuta detect+migrate)
- Testes: fixture ampliada em `Test-LegacyMigration`; `test_skill_discovery_legacy_import.py`

### Changed

- `docs/legacy-cleanup.md` + seção no README com exemplo executável

## 0.4.22 - 2026-07-25

Corrige propagação do roteamento de modelos: `models.json` é `mode=merge` e a 0.4.21 era no-op nos consumidores.

### Fixed

- Migration `0.4.20-to-0.4.21` faz patch idempotente de `role_model_preferences` + `task_map` Claude
- Migration `0.4.21-to-0.4.22` reaplica o patch nos projetos já em 0.4.21

## 0.4.21 - 2026-07-25

Roteamento de modelos: executor/corrector usam modelo forte para código; validator fica em tier intermediário.

### Changed

- `models.json` `role_model_preferences`:
  - **executor / corrector:** Claude `opus` (fallback sonnet); Codex `gpt-5.6-sol` / deep; OpenCode deep
  - **validator:** Claude `sonnet` (fallback haiku); Codex/OpenCode `balanced`
- `task_map` Claude `implementation` / `refactor_simple`: `sonnet` → `opus`
- Defaults em `routing/manager.py` alinhados (mesmo sem JSON)

### Added

- Feature `role_model_executor_strong`
- Migration `0.4.20-to-0.4.21`
- Teste `test_executor_prefers_strong_coding_model`

## 0.4.20 - 2026-07-25

Propagação automática: ao atualizar o **pacote** (`@starfusion/orchestrator`), os projetos registrados com orquestrador também são atualizados.

### Added

- Registry `%LOCALAPPDATA%\StarFusion\orchestrator\projects.json` (upsert em install/update)
- `Propagate-OrchestratorUpdate.ps1` — leva FIFO com `-SkipAgentUpdates -NoPropagate`
- Flags `--no-propagate` / `--discover` (JS → `-NoPropagate` / `-Discover`)
- `Find-OrchestratorProjects` para descoberta opcional
- Migration `0.4.19-to-0.4.20` · teste `Test-ProjectPropagate.ps1`

### Behavior

- Propagação **só** quando `ProjectPath` é o workspace do pacote
- Update num consumidor (PrintBee) **não** propaga
- Opt-out: `--no-propagate`; discover: `--discover`

## 0.4.19 - 2026-07-24

Fila FIFO por workspace: se o orquestrador já executa uma task no projeto, novas submissões entram em `QUEUED` e iniciam automaticamente quando a ativa termina/cancela.

### Added

- Estado `TaskState.QUEUED` + transições `RECEIVED↔QUEUED`
- `TaskRepository.list_queued` / `find_active_execution`
- `TaskService`: enqueue em busy/lock TimeoutError; `_maybe_start_next` no finally do lock
- MCP `orchestrator_run` retorna `QUEUED` + `queue_position` + `blocked_by` sem spawnar thread
- Feature `workspace_task_queue`
- Migration `0.4.18-to-0.4.19`

### Changed

- `blocked_by_lock` mudo substituído por fila explícita `queued_behind:<id>|pos=N`

## 0.4.18 - 2026-07-24

Corrige hang do Codex no PrintBee: o executor seguia `printbee-patterns` (mínimo 3 subagentes → `collab: Wait` / timeouts 124s) porque a restrição anti-subagente só entrava no prompt se o **MCP pai** tivesse `ORCHESTRATOR_CHILD_AGENT` — e nunca tem (a env só existe no CLI filho).

### Fixed

- `tasks/service.py`: `_child_agent_restriction_block()` **sempre** injetado no executor/validator/planner (antes das skills); texto proíbe spawn/wait/collab e ignora rito de N subagentes
- `agents/process.py`: fail-fast também em `collab: wait` e `command timed out after 124`

### Added

- Features `child_agent_restriction_always_on`, `codex_collab_wait_failfast`
- Migration `0.4.17-to-0.4.18`

## 0.4.17 - 2026-07-24

Install/update do orquestrador atualiza automaticamente os CLIs dos agentes **já existentes** no PATH (`claude`, `codex`, `kimi`, `opencode`, `gemini`, …). Opt-out: `-SkipAgentUpdates` / `--skip-agent-updates`.

### Added

- `Update-Agents.ps1`: estratégias nativas (`claude|codex|kimi|gemini update`) + fallback npm/chocolatey/scoop conforme `installation_method`; relatório `.orchestrator/runtime/reports/agent-updates.json`
- `Orchestrator.Common.ps1`: `Get-AgentChocolateyPackageMap`, `Get-AgentScoopPackageMap`
- `Install-Orchestrator.ps1`: `-SkipAgentUpdates`; Update-Agents **ON por padrão** em `install` e `update`, seguido de re-`Detect-Agents`
- CLI: `--skip-agent-updates`
- Migration `0.4.16-to-0.4.17`

### Changed

- Update de agentes deixa de ser opt-in (`-UpdateAgents`); a flag permanece aceita por compatibilidade
- `-Force` continua forçando fallback npm/choco/scoop mesmo quando o method detectado difere

## 0.4.16 - 2026-07-24

Fixes de produção baseados na análise ao vivo do PrintBee (2026-07-24): lock reentrante asyncio, classificação falsa como "docs", transição idempotente, TTL de zumbis RECEIVED, restrição de subagentes no prompt child.

### Added

- `execution/locks.py`: `WriteLock` rastreia `_owner_task` (asyncio Task); segunda task ≠ owner → `TimeoutError` imediato (single-flight correto — spinning causaria deadlock no event loop)
- `planning/analyzer.py`: check "doc" usa `\bdoc` (word-boundary) para não cassar em palavras como "produção"; `docs` com intent de implementação é promovido para `implementation` (mesmo padrão de `complex_analysis`)
- `tasks/state_machine.py`: `assert_transition` trata same-state como no-op (não levanta `InvalidTransitionError`)
- `tasks/repository.py`: `transition` retorna task sem salvar/emitir evento quando `current == new_state`
- `config.py`: campo `stale_received_ttl_hours: int = 6` em `RuntimeLimits`; `load_config` lê de `policies.json`
- `policies.json` (live + template): `stale_received_ttl_hours: 6`
- `tasks/service.py`: `_cancel_stale_received()` — auto-cancela tasks RECEIVED com idade > TTL; chamado em `create_task`; bloco ORCHESTRATOR_CHILD_AGENT no prompt do executor (P1-E)
- `diagnostics.py`: features `writelock_asyncio_singleflight`, `produção_not_docs`, `same_state_transition_noop`, `stale_received_ttl_autocancel`, `child_agent_no_subagents_prompt`
- Testes `runtime/tests/unit/test_0416_fixes.py` (12 casos: lock asyncio single-flight, lock mesmo task reentrant, lock não-async OK, análise "produção" = implementation, impl-vence-docs, same-state no-op, terminal same-state, TTL RECEIVED, TTL respeita limite, child prompt block, no block sem env, config TTL)
- Migration `0.4.15-to-0.4.16`

### Changed

- `tasks/service.py`: `create_task` chama `_cancel_stale_received()` antes de criar; import `datetime`/`timezone` adicionado

## 0.4.15 - 2026-07-24

Codex Windows sandbox fix: elimina hang de 10–20 min causado por `CreateProcessAsUserW error 740` quando Codex usa `--sandbox workspace-write` no Windows sem elevação. Dois mecanismos: (1) override automático de sandbox para `danger-full-access` quando `os.name == "nt"`; (2) fail-fast no stream — mata o processo após N ocorrências do marcador 740 (padrão 3, configurável em `policies.json`).

### Added

- `agents/process.py`: constante `INFRA_FAIL_MARKERS` (marcadores 740/sandbox importáveis); `CliExecutor.__init__` aceita `infra_fail_fast_count: int = 3`; `run()` detecta marcadores em tempo real no `_reader`, mata o processo após N ocorrências e adiciona `[INFRA-FAIL-FAST] windows sandbox: runner failed` ao stderr (ativa `_validator_infra_failure` em service.py)
- `agents/base_adapters.py`: `build_command` detecta `os.name == "nt"` e substitui `--sandbox workspace-write` por `--sandbox danger-full-access` no comando Codex; profile JSON mantém `workspace-write` como base documentada
- `config.py`: campo `agent_infra_fail_fast_count: int = 3` em `RuntimeLimits`; `load_config` lê de `policies.json`
- `policies.json` (live + template): `agent_infra_fail_fast_count: 3`
- `agents/profiles/codex.json` (live + template): `notes` documenta override Windows automático
- `diagnostics.py`: features `codex_infra_failfast` + `codex_sandbox_windows_override`
- `docs/troubleshooting.md`: nova seção "Codex trava em VALIDATING / processo fica preso por 10–20 min no Windows" com causa, mecanismos de correção e ajuste de sensibilidade
- Testes `runtime/tests/unit/test_codex_infra_failfast.py` (9 casos: override nt/posix/já-danger/sem-sandbox; fail-fast mata após N/desabilitado/abaixo-do-limiar; config default/policies; service repassa ao executor)
- Migration `0.4.14-to-0.4.15`

### Changed

- `tasks/service.py`: `TaskService.__init__` repassa `agent_infra_fail_fast_count` ao `CliExecutor`

## 0.4.14 - 2026-07-24

Learn-then-compact context: ao terminar cada tarefa (COMPLETED/INCOMPLETE/FAILED/CANCELLED após execução), o runtime PRIMEIRO grava um aprendizado durável e SÓ DEPOIS compacta artefatos. O `orchestrator_result`/`orchestrator_status` devolvem um `session_digest` compacto (≤ 1500 chars) para o cliente IDE reter apenas digest + ponteiro de memória e descartar o histórico verboso de polls. A próxima conversa/tarefa recupera esses aprendizados (memória `kind=learning`) e os injeta nos prompts do planner/executor.

### Added

- `runtime/src/orchestrator_runtime/memory/learnings.py`: novo módulo puro — `extract_learning` (objetivo, decisões, arquivos tocados, testes, blockers, recomendações, skills, status/score), `build_digest` (digest compacto com teto de chars + `[TRUNCATED]`), `render_markdown`/`memory_content`, `write_markdown` + `update_index` (`.orchestrator/memory/learnings/{task_id}.md` + `memory/index.json`), `update_wolf_status` (bloco gerenciado "Last orchestrator task" em `.wolf/STATUS.md`), `append_cerebrum_pitfall` (Do-Not-Repeat em `.wolf/cerebrum.md` quando a task falha com blockers), `compact_result_artifacts` (trunca `results/{id}/*.txt` grandes)
- `TaskService._learn_then_compact`: choke point 0.4.14 — ordem obrigatória save learning → compact; grava SQLite `kind=learning` (meta rico + `session_digest`), markdown, index, `.wolf/`; só então trunca artefatos; falha nunca aborta a task
- `TaskService._learnings_block`: renderiza aprendizados de tarefas anteriores ("use como contexto") para injeção nos prompts de planner/executor
- `TaskRepository.search_memories(kind=...)`: filtro opcional por tipo de memória (`learning` vs `episode`)
- `config.py`: campos `context_compaction_enabled`, `save_learning_before_compact`, `digest_max_chars`, `truncate_result_artifacts_chars`, `update_wolf_status` em `RuntimeLimits`; `_context_compaction_limits()` lê de `policies.json`
- `policies.json` (live + template): bloco `context_compaction` (`enabled`, `save_learning_before_compact`, `digest_max_chars`, `truncate_result_artifacts_chars`, `update_wolf_status`)
- `mcp/tools.py`: `orchestrator_result` expõe `session_digest`, `context_compaction` (keep/discard) e `memory.learning_saved`/`learning_path`; `orchestrator_status` expõe `session_digest` e, em estado terminal, orienta reter só digest + learning_path
- Migration `0.4.13-to-0.4.14`
- Feature `learn_then_compact_context` + fingerprint de `memory/learnings.py` em `diagnostics.py`
- Testes `runtime/tests/unit/test_context_compaction.py` (14 casos: extract/digest/memory_content, compactação de artefatos, index dedupe, `.wolf/` STATUS+cerebrum, ordem save-antes-compact, digest presente no result, retrieval inclui learning, defaults/leitura de config, live policies)

### Changed

- `tasks/service.py`: `_execute_loop` reseta `self._run_ctx` e recupera aprendizados (`kind=learning`) além dos episodes em RETRIEVING_MEMORY; injeta o bloco de aprendizados nos prompts de planner e executor; `_persist_episode` chama `_learn_then_compact` após salvar o episode (aprendizado enriquecido, não substituído); `cancel()` grava learning quando a task já havia iniciado execução
- `docs/orquestrador.md` e `docs/runtime-architecture.md`: seção de learn-then-compact + digest; `.cursor/rules/token-economy.mdc` e `multiagent-orchestrator.mdc`: após tarefa terminal, o chat retém só o digest + ponteiro de memória

## 0.4.13 - 2026-07-24

Skill selection: o orquestrador agora descobre skills instaladas e usa um modelo leve (haiku/fast) para selecionar as mais relevantes antes de chamar modelos pesados (planner/executor/validator). Apenas skills em disco são enviadas; IDs inventados são descartados.

### Added

- `runtime/src/orchestrator_runtime/skills/discovery.py`: varre `{project}/.orchestrator/skills`, `.claude/skills`, `.codex/skills`, `.agents/skills` e equivalentes globais do usuário (`~/.agents/skills`, `~/.claude/skills`, `~/.codex/skills`); extrai `id` + `description` do frontmatter de cada `SKILL.md`; cache em memória por run; nunca fabrica IDs ausentes no disco
- `runtime/src/orchestrator_runtime/skills/selector.py`: `build_selector_prompt` (objetivo + catálogo → prompt JSON), `parse_and_validate` (descarta IDs inventados), `select_skills_heuristic` (fallback keyword-match determinístico)
- `runtime/src/orchestrator_runtime/skills/__init__.py`: re-exports dos símbolos públicos
- `TaskService._select_skills`: nova fase no workflow após RETRIEVING_MEMORY, antes de PLANNING; chama agente com role `skill_selector` (fast/haiku); fallback heurístico quando CLI falha; persiste resultado em `task.analysis["selected_skills"]`
- `TaskService._skills_block`: renderiza skills selecionadas para injeção nos prompts de planner/executor/validator (instrução "use APENAS estas")
- `TaskService._pick_selector_agent`: seleciona primeiro CLI disponível (claude > codex > opencode > gemini > kimi) para a fase de seleção
- `policies.json` (live + template): bloco `skill_selection` (`enabled`, `model_tier`, `max_skills`, `timeout_s`, `include_user_global`); `agent_timeout_by_role.skill_selector: 120`
- `models.json` (live + template): `role_model_preferences.skill_selector` mapeando haiku/fast por CLI
- `config.py`: campos `skill_selection_enabled`, `skill_selection_max_skills`, `skill_selection_timeout_s`, `skill_selection_include_user_global` em `RuntimeLimits`; `_skill_selection_limits()` lê do policies.json; `skill_selector: 120` no `agent_timeout_by_role` padrão
- Migration `0.4.12-to-0.4.13`
- Testes `runtime/tests/unit/test_skill_selection.py` (21 casos: discovery só de disco, deduplicação, cache, parse descarta inventados, heurística, prompts recebem skills, config, live policies/models)
- Feature `skill_selection_fast_model` em `diagnostics.py`

### Changed

- `tasks/service.py`: `_build_executor_prompt` e `_build_validator_prompt` injetam `_skills_block(task)` antes do bloco always-on tooling; planner prompt também recebe skills block; always-on Superpowers ajustado para referenciar as skills selecionadas da sessão (`policies.json`)

## 0.4.12 - 2026-07-24

Always-on tooling: OpenWolf, Graphify, Superpowers e Caveman obrigatórios em todos os prompts do orquestrador.

### Changed

- `policies.json` (live + template): `caveman_enabled` `false→true`, `caveman_default` `"off"→"full"`; novo bloco `required_agent_tooling` documenta as 4 ferramentas obrigatórias (openwolf, graphify, superpowers, caveman) com instrução e condição por ferramenta
- `models.json`: novo bloco `required_agent_tooling` + `always_on_skills` declara obrigatoriedade e scope de cada ferramenta
- `config.py`: `RuntimeLimits.caveman_enabled` default `False→True`; `load_config` default do token_economy `False→True` (sem override explícito no JSON, caveman fica ativo)
- `tasks/service.py`: novo método `_required_tooling_block()` (retorna bloco non-empty quando `caveman_enabled=True`) injetado no início do prompt do planner, antes do bloco de escopo no executor/corrector, e ao final do prompt do validator
- `docs/global-tools.md`: Caveman de "opcional/desabilitado" para "obrigatório por padrão (0.4.12+)"
- `docs/model-routing.md`: seção Caveman atualizada — de opt-in para always-on

### Added

- Migration `0.4.11-to-0.4.12`
- Testes `runtime/tests/unit/test_global_tooling_always_on.py`: caveman_enabled default True, prompts contêm OpenWolf/Graphify/Superpowers/Caveman quando config exige; tooling block ausente quando caveman_enabled=False

## 0.4.11 - 2026-07-24

Auditoria das transcrições reais PrintBee (Cursor 2026-07-24) -> correções P0 do runtime
(`docs/audits/2026-07-24-printbee-transcripts-orchestrator-fixes.md`).

### Fixed

- Executor que pergunta em vez de implementar: prompt proíbe perguntas abertas quando o objetivo já define o escopo; se genuinamente bloqueado, emite linha estruturada `REQUIRES_INPUT: {"question": ..., "options": [...]}` — runtime pausa em WAITING_FOR_USER SEM queimar a iteração (pergunta/opções expostas em `orchestrator_status`); pergunta repetida após resposta vira `AGENT-REQUIRES-INPUT` (infra) com rotação de executor e stop por `same_issue_repeat_limit`
- Classificação: pedido de implementação que também cita "analisar" não vira mais `complex_analysis` com ACs de auditoria — verbo de implementação (implementar/criar/corrigir/mudar/alterar/ajustar/fix...) vence a keyword de análise; negações ("não criar X") continuam ignoradas
- Refino de plano pelo planner (advisory — o plano determinístico já existe) com teto duro de 300s; `SELECTING_AGENTS` não fica mais preso 15 min no fable
- Harness por stack: descoberta de pytest exige marcador Python real (pyproject/setup/requirements ou `.py` em `tests/`); fim do `**/test_*.py` que varria `node_modules` e inventava pytest em projeto Angular; prompts de executor e validator recebem os comandos de teste detectados ("use SOMENTE estes")
- Cancel propaga kill para os CLIs filhos ativos (`CliExecutor.kill_active`); Codex órfão não segue rodando após cancelamento
- Task barrada pelo `workspace.write.lock` grava `error = "blocked_by_lock: ..."` (visível em status/list) em vez de ficar RECEIVED muda; o erro é limpo quando a task finalmente executa
- Timeout do executor sem NENHUM arquivo alterado (padrão Codex/PowerShell no Windows) rejeita como infra `AGENT-TIMEOUT-NO-OUTPUT` com rotação de executor, em vez de mandar "continue do disco" vazio; prompt no Windows orienta evitar heredoc/quoting PowerShell (preferir tools de escrita/`python -c`/arquivo temp)
- `orchestrator_message`: não transiciona mais para PLANNING (transição que quebrava o resume); resume reentra o pipeline via WAITING_FOR_USER -> ANALYZING preservando resposta do usuário na análise

### Added

- `orchestrator_run` avisa (`warnings: ["mcp_modules_stale"]` + mensagem) quando o processo MCP está stale vs disco
- Fingerprint de stale agora cobre `tasks/service.py`, `tasks/state_machine.py`, `testing/discovery.py`, `agents/process.py`; features novas: `requires_input_structured`, `impl_intent_overrides_analysis`, `stack_aware_test_harness`, `cancel_kills_children`, `blocked_by_lock_visible`, `timeout_no_output_rotation`, `planner_refine_cap`
- Migration `0.4.10-to-0.4.11`
- Testes `runtime/tests/unit/test_transcript_p0_fixes.py` (17 casos: classificação, requires_input pause/resume/repeat, discovery Node vs Python, stack hint nos prompts, timeout sem output, lock visível, cancel-kill, teto do planner)

## 0.4.10 - 2026-07-23

Auditoria do processo PrintBee -> correcoes de confiabilidade do runtime
(`docs/audits/2026-07-23-printbee-process-orchestrator-improvements.md`).

### Fixed

- `git status`/`rev-parse` do baseline agora com timeout de 30s (`GIT_TIMEOUT_S`); hang do git no Windows nao trava mais a task em RECEIVED segurando o `workspace.write.lock`
- Executor/corrector que "completa" com stdout vazio e zero arquivos alterados gera issue de infra `AGENT-EMPTY-OUTPUT` com fallback de executor e stop por `same_issue_repeat_limit`, em vez de rejeicao falsa do AC `workspace_changes`
- `LlmReviewValidator.parse`: extracao de JSON tolerante a logs com chaves soltas (`raw_decode` por candidato); so `approved`/`rejected` contam como veredito - `{"status":"validating"}` e ruido de CLI nao rejeitam mais por engano; `score: null` cai no score deterministico
- Validator que falha por infra (ex.: sandbox Windows erro 740 "requer elevacao") nao conta como rejeicao de merito: runtime tenta um validator alternativo e, sem veredito, usa apenas a validacao deterministica marcada com `validator_infra_failure`
- `orchestrator_delegate` finaliza a task criada (COMPLETED/INCOMPLETE/FAILED); fim dos orfaos RECEIVED acumulados no DB (state machine permite RECEIVED->COMPLETED/INCOMPLETE para single-role)
- Suite `npm test` hermetica: `Run-AllTests.ps1` limpa `ORCHESTRATOR_CHILD_AGENT` herdada do runtime (VALIDATING roda testes via `CliExecutor`, que marca o filho com a var); sem isso o golden de dispatch do `Test-AgentProfiles` abortava por anti-recursao em `Invoke-RoutedAgent.ps1` - mesmo isolamento ja aplicado ao pytest em `runtime/tests/conftest.py`

### Added

- Migration `0.4.9-to-0.4.10` (inclui SQL opcional para limpar delegates RECEIVED antigos)
- Testes: hang de git (baseline indisponivel), saida vazia do executor -> INCOMPLETE com `AGENT-EMPTY-OUTPUT`, parse de veredito em log ruidoso, finalizacao de delegate

## 0.4.9 — 2026-07-23

### Fixed

- Auto-dispatch: docstrings MCP de `orchestrator_run`/`delegate`/`analyze` declaram DEFAULT obrigatório (sem o usuário pedir)
- Rule Cursor: primeira tool de trabalho = `orchestrator_run` antes de editar
- Gap documentado em `docs/audits/2026-07-23-cursor-orchestrator-auto-dispatch-gap.md`

### Added

- Migration `0.4.8-to-0.4.9`

## 0.4.8 — 2026-07-23

### Fixed

- `cursor configure` / merge de `.cursor/mcp.json` tolera BOM UTF-8 (`utf-8-sig`)

### Added

- Migration `0.4.7-to-0.4.8`

## 0.4.7 — 2026-07-23

### Fixed

- Windows/Cursor: runtime fixa stdin/stdout/stderr em UTF-8; descrições PT-BR não perdem `ç`, `ã`, `õ` quando Python herda CP1252 em pipe
- Wrapper Node (`bin/orchestrator.js`) exporta `PYTHONUTF8=1` + `PYTHONIOENCODING=utf-8` ao spawnar o runtime Python
- `task list` texto troca `prompt[:60]` por preview de uma linha, word-safe, com `…`; `--json` continua integral
- Regressão cobre CLI argv → SQLite → MCP result → JSON/texto sob `PYTHONIOENCODING=cp1252`

### Changed

- Rules Cursor (`multiagent-orchestrator.mdc`, live + template + rule gerada por `cursor configure`): orquestrador vira **modo padrão obrigatório** ("sem o usuário pedir"), com seções Gatilhos/Exceções/Anti-padrões; proibido inventar preferência de projeto sem citação `arquivo:linha` (auditoria `docs/audits/2026-07-23-cursor-inline-bypass-audit.md`, F1–F8)
- `token-economy.mdc`: seção "Preferência" → "Ordem obrigatória"
- `docs/cursor-front-controller.md` + `CURSOR.md` (raiz e template): bug fix / mudança de lógica → `orchestrator_run` por default; removida a licença "edição trivial → resposta direta"

### Added

- Migration `0.4.6-to-0.4.7` (behavior-only; dados SQLite já estavam íntegros)
- Testes: `runtime/tests/unit/test_cli_encoding.py` (pipeline UTF-8) e `tests/Test-CursorDefaultOrchestration.ps1` (wording default orquestrador live == template == `cursor configure`)

## 0.4.6 — 2026-07-23

### Added

- `role_model_preferences` em `models.json`: papel **planner** prefere **fable** → **opus** (Claude) quando declarados no cliente
- `RulesRouter.resolve_model(..., role=)` aplica preferências por papel antes do `task_map`
- Migration `0.4.5-to-0.4.6`

### Fixed

- Planner recebia Sonnet em tarefas `implementation`/`docs` porque o modelo seguia só o `task_type`

## 0.4.5 — 2026-07-23

### Added

- Orçamento de timeout por papel (`agent_timeout_default_s` / `agent_timeout_by_role` em `policies.json`); executor/corrector padrão **2400s**
- Fallback `git status --porcelain` para popular `changed_files` quando o CLI não reporta
- Issue `AGENT-TIMEOUT` + exclusão de VAL workspace/evidence vazios do `same_issue_repeat_limit` após timeout
- Regra Cursor `version-bump.mdc`: bump semver obrigatório ao entregar mudanças no pacote
- Migration `0.4.4-to-0.4.5`

### Fixed

- Hardcap `min(600, …)` por invocação de agente (tarefas longas morriam em ~10 min mesmo com `maximum_duration_seconds=3600`)
- `ProfileCliAdapter`: `request.timeout_s` passa a prevalecer sobre `profile.timeout_default_s`
- `maximum_duration_seconds` agora encerra o loop quando o tempo restante é insuficiente

### Changed

- Profiles template: `timeout_default_s` 600 → **2400** (CLIs de escrita); gemini **1200**

## 0.4.4 — 2026-07-23

### Added

- MCP chat visibility: `orchestrator_run`/`orchestrator_status` expõem `selected_agents`, `selected_models`, `active_provider`, `active_model`; `message` inclui `provider=`/`model=`; regra Cursor obriga anúncio no chat a cada poll
- Migration `0.4.3-to-0.4.4`

### Fixed

- Codex `models.json`: IDs alinhados a conta ChatGPT (`gpt-5.6-sol`); resolução de tier→modelo concreto; `sandbox_flags` do profile aplicados (`--sandbox workspace-write`, `--skip-git-repo-check`)
- `CliExecutor` usa `stdin=DEVNULL` (evita `codex exec` ficar lendo stdin vazio)
- Repair loop: falha de spawn/CLI do executor não aborta mais em `FAILED` na 1ª iteração — entra em `CORRECTING` (com fallback de executor) até `maximum_iterations`
- Repair loop: testes determinísticos falhos forçam `correct` mesmo se o validator LLM aprovar; issues `TEST-FAIL` vão no prompt do corrector
- Concorrência: `TimeoutError` do WriteLock e double-start MCP **não** marcam a tarefa em andamento como `FAILED`
- CLI adapters usam path absoluto do `detect()` (mitiga WinError 2 / PATHEXT no processo MCP)
- `CliExecutor`: `FileNotFoundError` vira exit 127 em vez de derrubar o workflow
- Acceptance criteria: meta-instruções (`IGNORAR`/`ignore`/`evitar` … função soma) não disparam mais o demo `soma_module`
- Acceptance criteria: auditorias (`complex_analysis`/`security_review`/`architecture`) mantêm ACs de evidência mesmo quando o prompt menciona “testes”/“docs”
- Acceptance criteria: tarefas não-auditoria sempre incluem `workspace_changes` (antes, keywords test/docs omitiam esse AC)
- CLI: `orchestrator agents list` (e `ls`) aceito como alias de `orchestrator agents`
- Teste de regressão Windows: `CliExecutor` resolve `.CMD` via `shutil.which` (PATHEXT / WinError 2)
- Fingerprint MCP: `code_fingerprint` reporta o hash **carregado no processo** (não só o disco); `modules_stale` + warning em `orchestrator_health` quando o disco avançou sem reload

### Changed

- Nome do servidor MCP Cursor: `multiagent-orchestrator` → **`orchestrator-ia`** (install/configure migra `mcp.json` e remove a chave legada; arquivo de rule `multiagent-orchestrator.mdc` e path de cache inalterados)
- Instalação npm/docs passam a usar `#latest` (tag git móvel de release); `github:...@latest` não é suportado pelo npm
- Política de segurança GitHub em `.github/SECURITY.md`; `docs/security.md` atualizado (Orquestrador IA Multiagente)
- Licença do projeto alterada para **MIT** (uso comercial e não comercial por qualquer pessoa)
- GitHub Actions CI desabilitado (sem plano/limite de Actions); workflow preservado em `.github/ci.yml.disabled`
- Notas de Actions movidas de `.github/README.md` para `.github/ACTIONS.md` (GitHub priorizava esse README sobre o da raiz)
- Wrapper Windows `bootstrap-agents.bat` renomeado para `orchestrator-ia.bat`
- Nome do produto padronizado para **Orquestrador IA Multiagente**; docs e URLs apontam para `henrique-starfusion/orchestrator-ia`

## 0.4.3 — 2026-07-22

### Fixed

- MCP stdio: heartbeat/`[exec]` do `CliExecutor` e eventos verbose não escrevem mais em stdout (evita `Unexpected token '[heartbeat]'` no Cursor)
- Logs INFO do SDK MCP silenciados no transporte stdio (menos ruído falso no Output do Cursor)

### Added

- Migration `0.4.2-to-0.4.3`

## 0.4.2 — 2026-07-21

### Added

- CLI `orchestrator agents` (registry JSON/text)
- `orchestrator version` / `-V` / `--version` (com `--json` → fingerprint)
- `orchestrator_health.runtime.code_fingerprint` + `features` (detecta MCP stale)
- Regra Cursor anti-MCP-stale (comparar fingerprint CLI vs MCP após update)
- Migration `0.4.1-to-0.4.2`

### Fixed

- Entry MCP Python alinhada ao PS1 (`cmd /c` + `--project ${workspaceFolder}`)
- Echo live de subprocess aplica `redact()`
- `require_independent_validation` falha se não houver validator ≠ executor
- `fake_agents` rejeitado na superfície MCP
- `.orchestrator/data` com `chmod 0o700` (best-effort)
- Parse de requirements não parte semver (`0.4.1`); auditorias → ACs `evidence`
- `orchestrator analyze` emite `warnings` (`independent_validation_ok`, `validator_equals_planner`)

## 0.4.1 — 2026-07-21

### Added

- Schema tipado de acceptance criteria (`CriterionKind` + `CriterionCheck`) com dispatch no validator
- CI GitHub Actions (pytest + suite PowerShell)
- Migration `0.4.0-to-0.4.1`

### Fixed

- Critérios de aceitação “soma” não disparam mais por substring em `resume`/`summary` (`CriteriaBuilder`)
- Menções negadas (“não criar módulo soma”) não geram AC de soma
- `WriteLock` com reclaim de PID morto e reentrancy (evita deadlock em resume/MCP)
- `orchestrator_delegate` / `orchestrator_analyze` usam `_run_coro` (não quebram no event loop MCP)
- Allowlist MCP estrita (bloqueia workspace externo mesmo com `.orchestrator/`)
- `read_only` enforced em delegate; `allow_network` rejeitado de verdade
- Overrides de agentes respeitados com `routing=automatic`
- Erros em threads background MCP deixam de ser engolidos (log + mark FAILED)

### Changed

- `orchestrator_status` expõe `error`, mensagem legível, agente ativo e ACs
- Regra Cursor `multiagent-orchestrator.mdc` documenta contrato de poll chat↔runtime
- Default `CursorMcpScope=project` (global só com `--cursor-mcp-scope user|both`)
- `DeterministicValidator`: critérios sem verificador exigem evidência (changed_files/tests)
- Critérios legados sem `kind` são migrados por inferência na carga

## 0.4.0 — 2026-07-21

### Added

- Limpeza automática de configurações legadas no `install` / `update` (modo `safe` por padrão)
- Scripts: `Detect|Backup|Migrate|Remove|Validate-LegacyConfigurations`, `Invoke-LegacyCleanupPipeline`, `Restore-LegacyBackup`
- Flags: `--skip-legacy-cleanup`, `--legacy-cleanup-mode safe|aggressive|report-only`, `--keep-legacy-backup`
- Comandos: `orchestrator legacy scan|cleanup|status|restore`
- Relatórios: `legacy-cleanup-report.md`, inventário, state em `runtime/legacy-cleanup-state.json`
- Migration `0.3.1-to-0.4.0`
- Testes de detecção, backup, safe/aggressive/report-only, restore, idempotência e preservação

### Changed

- `Migrate-LegacyClaude.ps1` virou wrapper do pipeline genérico
- CLI Node prefere `python` a `py` no Windows (evita builds free-threaded quebrados)

## 0.3.1 — 2026-07-21

### Removed / archived

- Prompt bootstrap legado movido para `docs/archive/prompts/`
- Specs/planos Superpowers movidos para `docs/archive/superpowers/`
- Stub morto `runtime/.../routing/registry.py` (não referenciado)

### Changed

- Caveman/documentação: opcional (não obrigatório); Cursor preferindo MCP a `Task`
- Skill `economize-tokens` e rule `token-economy.mdc` alinhadas ao runtime
- `.gitignore` ampliado (runtime DB, `.wolf/`, `.ai/`, caches, secrets)
- Teste anti-legado `Test-NoLegacyArtifacts.ps1`

### Preserved

- `dispatch`, migrations, adapters, `Backup-Orchestrator.ps1` (utilitário manual)
- OpenWolf/Graphify como opt-in

## 0.3.0 — 2026-07-21

### Added

- Servidor MCP **`multiagent-orchestrator`** (`orchestrator mcp serve`)
- Tools: health, analyze, delegate, run, status, events, result, cancel, resume, message, agents, memory_search
- Resources `orchestrator://…` e prompts MCP reutilizáveis
- Comandos `orchestrator cursor configure|verify|print-config`
- Rule Cursor `multiagent-orchestrator.mdc` (front controller)
- Merge seguro de `.cursor/mcp.json` (stdio/http)
- Flags instalador: `--configure-cursor-mcp`, `--cursor-transport`, `--skip-cursor`
- Docs: `mcp-integration.md`, `cursor-front-controller.md`, `human-approval-flow.md`, `mcp-tool-reference.md`, `api.md`, `security.md`

### Changed

- Cursor permanece cliente IDE; chat (qualquer modelo) é front controller via MCP
- Manager/Rules continua escolhendo CLIs no workflow (`routing=automatic`)

## 0.2.0 — 2026-07-21

### Added

- **Runtime persistente** Python (`runtime/`) com SQLite em `.orchestrator/data/orchestrator.db`
- Comandos: `orchestrator run`, `orchestrator task create|run|status|list|cancel|resume|logs|artifacts`
- Máquina de estados completa (RECEIVED → … → COMPLETED/INCOMPLETE/FAILED)
- Adapters Claude/Codex (MVP) + Gemini/Kimi/OpenCode (experimental) + Cursor como `ide-client`
- Manager model: `RulesManager` (default) + hook `openai-compatible` opcional
- Discovery/execução de testes determinísticos
- Validação independente + completion gate + documentation gate
- Memória operacional (episódios, performance de agente/estratégia)
- Docs: `runtime-architecture.md`, `task-lifecycle.md`, `agent-adapters.md`, `manager-model.md`, `memory-and-learning.md`, `cursor-integration.md`, `documentation-policy.md`

### Changed

- Instalação **núcleo primeiro**: OpenWolf/Graphify/MCPs/plugins/skills globais são **opt-in** (`--init-tools`, `--global-tools` / `orchestrator global-tools`)
- Caveman desabilitado por padrão no runtime e policies
- `dispatch --client cursor` deprecado (orientação para `orchestrator run`)
- Skills/adapters atualizados para runtime + gate documental

### Compatibility

- Comandos de instalador (`install`, `update`, `verify`, `repair`, …) preservados
- `route` / `dispatch` preservados; despacho de processo alinhado ao `CliExecutor` do runtime

## 0.1.0

- Instalador versionado, template `.orchestrator/`, global-tools, route/dispatch, profiles
