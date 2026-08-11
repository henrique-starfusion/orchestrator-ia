# Regras de negócio da execução

Invariantes que o runtime impõe ao receber, executar, validar e concluir uma
task. Este documento descreve comportamento implementado, não intenção futura.
Cada regra traz a razão operacional para impedir que uma refatoração remova uma
proteção paga por incidente.

## Ciclo de vida e autoridade do estado

### RN-001 — Estado terminal não tem transição de saída

**Regra.** `COMPLETED`, `INCOMPLETE`, `FAILED` e `CANCELLED` são os únicos
estados terminais. Seus conjuntos em `ALLOWED_TRANSITIONS` são vazios, e uma
gravação posterior com objeto stale não pode ressuscitar a task.

**Razão.** Cancelamento ou conclusão pode vencer uma corrida enquanto outro
objeto ainda está em memória. Aceitar a gravação atrasada faria trabalho já
encerrado voltar a `VALIDATING` ou outro estado intermediário.

**Evidência.** `TERMINAL_STATES` e `ALLOWED_TRANSITIONS` em
`runtime/src/orchestrator_runtime/tasks/state_machine.py:30-35,123-126`;
`TaskRepository.save` e `TaskRepository.transition` em
`runtime/src/orchestrator_runtime/tasks/repository.py:198-285`.

### RN-002 — Retomada do meio reinicia em `ANALYZING`

**Regra.** Task retomável parada em qualquer estado de meio de pipeline reentra
por `ANALYZING`; não continua da fase em que o processo anterior morreu.

**Razão.** O processo novo não possui sessão de agente nem contexto vivo da
fase interrompida. Continuar de `VALIDATING`, por exemplo, tentaria transições
incompatíveis e julgaria uma execução incompleta.

**Evidência.** `MID_PIPELINE_STATES` e as arestas de reentrada em
`runtime/src/orchestrator_runtime/tasks/state_machine.py:137-167`;
`TaskService._execute_loop` em
`runtime/src/orchestrator_runtime/tasks/service.py:1872-1891`.

### RN-003 — Transição para o mesmo estado é idempotente

**Regra.** Pedir a transição `X → X` não grava estado nem emite evento.

**Razão.** Retry de MCP e duplo resume podem repetir a mesma operação. Tratar a
repetição como erro transformaria idempotência do cliente em `FAILED`.

**Evidência.** `assert_transition` em
`runtime/src/orchestrator_runtime/tasks/state_machine.py:171-179` e
`TaskRepository.transition` em
`runtime/src/orchestrator_runtime/tasks/repository.py:248-276`.

### RN-004 — Cancelamento é hard stop e vence a corrida

**Regra.** `cancel_requested` é relido do banco entre as fases, os processos de
agente ativos são encerrados e qualquer tentativa posterior de avançar uma task
terminal é abortada.

**Razão.** Marcar apenas a linha do banco deixaria o loop e os CLIs filhos
trabalhando como zumbis, capazes de gravar eventos e estados depois do cancel.

**Evidência.** `TaskService.cancel` e `TaskService._ensure_runnable` em
`runtime/src/orchestrator_runtime/tasks/service.py:885-953`;
`CliExecutor.kill_active` em
`runtime/src/orchestrator_runtime/agents/process.py:462`;
`TaskRepository.transition` em
`runtime/src/orchestrator_runtime/tasks/repository.py:258-285`.

## Admissão, fila e escopo

### RN-005 — Paralelismo exige vaga e escopos disjuntos

**Regra.** Uma task só entra junto de outras quando o número de ativas está
abaixo de `max_parallel_tasks` **e** seu escopo não sobrepõe o de nenhuma ativa.

**Razão.** O teto protege a máquina contra excesso de processos; o teste de
escopo protege a árvore compartilhada contra dois agentes no mesmo código. Uma
das duas condições isolada não cobre o outro risco.

**Evidência.** `TaskService._blocking_task_id` em
`runtime/src/orchestrator_runtime/tasks/service.py:1420-1453` e
`TaskService._maybe_start_next` em
`runtime/src/orchestrator_runtime/tasks/service.py:1510-1547`.

### RN-006 — Escopo vazio significa desconhecido e sobrepõe tudo

**Regra.** A ausência de escopo não significa “nenhum arquivo”; significa
“desconhecido”. Por isso `scopes_overlap` devolve verdadeiro se qualquer lado
for vazio e a execução serializa.

**Razão.** Considerar vazio como disjunto autorizaria uma task sem prova de
escopo a rodar sobre qualquer outra. Serializar custa tempo; concorrer errado
pode misturar entregas.

**Evidência.** contrato do módulo e `scopes_overlap` em
`runtime/src/orchestrator_runtime/execution/scopes.py:1-18,78-90`;
`TaskService.task_scope` em
`runtime/src/orchestrator_runtime/tasks/service.py:1386-1397`.

### RN-007 — Escopo do dono vence; desvio é detectado, não bloqueado

**Regra.** `--scope` informado pelo dono tem precedência sobre a inferência do
analisador. Depois da execução, arquivo fora desse escopo vira degradação
`scope_violation`; o runtime não impede a escrita no momento em que acontece.

**Razão.** O escopo autoriza concorrência e não pode ser ampliado por palpite do
planner. Como todos trabalham na mesma árvore, a segunda defesa possível é
tornar o desvio visível ao validador e ao operador.

**Evidência.** `TaskService.task_scope` em
`runtime/src/orchestrator_runtime/tasks/service.py:1386-1397`;
`TaskService.scope_violations` e `TaskService.degradations` em
`runtime/src/orchestrator_runtime/tasks/service.py:1182-1224`;
`outside_scope` em `runtime/src/orchestrator_runtime/execution/scopes.py:141-166`.

### RN-008 — Adoção de órfã `QUEUED` exige todas as guardas

**Regra.** Só a cabeça FIFO pode ser adotada. Ela precisa ter vencido a lease,
não estar cancelada, rodando ou já adotada; o bloqueador deve ter terminado ou
não pode haver execução ativa; teto e escopo ainda precisam liberar a entrada.
O claim é refeito sob lock e renova `updated_at` como lease persistida.

**Razão.** Relaxar qualquer guarda permite pular FIFO, roubar task viva, furar o
teto, colidir escopos ou iniciar a mesma task por dois pollers.

**Evidência.** `TaskService._queued_orphan_head` e
`TaskService._adopt_orphan_queued` em
`runtime/src/orchestrator_runtime/tasks/service.py:1584-1659`.

## Limites, orçamento e repetição

### RN-009 — Iterações e duração têm teto

**Regra.** O loop encerra `INCOMPLETE` quando `maximum_iterations` é atingido ou
quando restam menos de `MIN_AGENT_TIMEOUT_S` no orçamento total.

**Razão.** Sem ambos os limites, rejeições sucessivas ou um agente lento podem
consumir recursos indefinidamente; apenas um dos tetos não limita a outra
dimensão.

**Evidência.** `TaskService._execute_loop` em
`runtime/src/orchestrator_runtime/tasks/service.py:2047-2077`;
defaults em `runtime/src/orchestrator_runtime/config.py:20-21`.

### RN-010 — A mesma issue não pode repetir indefinidamente

**Regra.** Ao alcançar `same_issue_repeat_limit`, a decisão vira
`stop_incomplete`. Para issues do validador, a identidade combina id e descrição
normalizada; o id posicional sozinho não basta.

**Razão.** O teto interrompe correções circulares. Combinar a descrição evita
encerrar por coincidência quando `VAL-001` representa problemas diferentes em
rodadas diferentes.

**Evidência.** contagem e decisão em
`runtime/src/orchestrator_runtime/tasks/service.py:2768-2804`; caminho de infra
em `TaskService._reject_iteration_infra`, linhas 3685-3709 do mesmo arquivo.

### RN-011 — O veredito conserva orçamento próprio

**Regra.** `executor` e `corrector` não recebem todo o tempo restante:
`VERDICT_RESERVE_S` reserva 600 segundos para o validator. Além disso, o
`maximum_duration_seconds` efetivo não pode ficar abaixo do percurso mínimo
planner → executor → tester → validator → corrector → validator.

**Razão.** Sem reserva e piso, uma volta longa consome o orçamento antes do
último papel; trabalho possivelmente pronto termina sem veredito.

**Evidência.** `_SPENDER_ROLES`, `VERDICT_RESERVE_S`,
`minimum_task_budget_s` e `resolve_agent_timeout_policy` em
`runtime/src/orchestrator_runtime/execution/timeouts.py:49-70,147-226`;
`RuntimeLimits.fit_task_budget` em `runtime/src/orchestrator_runtime/config.py`.

## Mérito, testes e validação

### RN-012 — Falha de infraestrutura não vira julgamento de mérito

**Regra.** Spawn ausente, saída vazia, timeout sem entrega, serviço indisponível
e falha de lançamento seguem issues de infraestrutura, rotação/fallback e
degradações próprias. O resultado não pode fingir que um agente avaliou o
trabalho.

**Razão.** Agente que não iniciou ou não produziu não observou a entrega. Cobrar
`workspace_changes`, fabricar score ou reinstalar por erro do provedor produz
diagnóstico falso e queima iterações sem correção possível no código.

**Evidência.** `TaskService._reject_iteration_infra` em
`runtime/src/orchestrator_runtime/tasks/service.py:3657-3720`;
`classify_agent_failure` em
`runtime/src/orchestrator_runtime/agents/health.py:166-220`;
`TaskService.degradations` em
`runtime/src/orchestrator_runtime/tasks/service.py:1077-1202`.

### RN-013 — Falha pré-existente e ambiente ausente não são regressão da task

**Regra.** O runtime captura uma baseline de testes antes do primeiro executor.
Mesma assinatura de falha depois vira `preexisting`; ferramenta, dependência ou
coleção de testes ausente vira `skipped`, não `introduced`.

**Razão.** Uma task não deve ser reprovada por quebra que já encontrou na árvore
nem por ferramenta indisponível na máquina. Falha realmente introduzida continua
bloqueante.

**Evidência.** baseline em
`runtime/src/orchestrator_runtime/tasks/service.py:2100-2135`;
`TestRunner.run_all` em
`runtime/src/orchestrator_runtime/testing/discovery.py:168-190,244-367`;
`DeterministicValidator` em
`runtime/src/orchestrator_runtime/validation/deterministic.py:74`.

### RN-014 — Validator independente não pode ser o executor

**Regra.** Com `require_independent_validation`, o roteador seleciona outro
agente; se uma rotação posterior igualar validator e executor, o serviço tenta
novo fallback e registra a perda de independência quando não houver alternativa.

**Razão.** Autor da mudança não fornece revisão independente da própria entrega.
Marcar o caso degradado impede que o score seja apresentado como parecer que
nunca existiu.

**Evidência.** `RulesRouter.select_plan` em
`runtime/src/orchestrator_runtime/routing/manager.py:53-99`;
guarda antes da validação em
`runtime/src/orchestrator_runtime/tasks/service.py:2585-2629`;
`TaskService._independence_note` e `TaskService.degradations`.

### RN-015 — Gate documental antecede `COMPLETED`

**Regra.** Aprovação e testes não concluem sozinhos. O runtime passa por
`UPDATING_DOCUMENTATION`, grava a revisão e só chega a `COMPLETED` se
`CompletionGate` aceitar testes, validação, score, ausência de blockers e
validação documental.

**Razão.** Sem o gate, mudança de comportamento pode sair sem revisão da
documentação e entrega com links locais quebrados pode ser declarada completa.

**Evidência.** gate no final de `TaskService._execute_loop` em
`runtime/src/orchestrator_runtime/tasks/service.py:2851-2895`;
`CompletionGate.can_complete` em
`runtime/src/orchestrator_runtime/validation/deterministic.py:266-289`;
`DocumentationUpdater.ensure_usage_docs` em
`runtime/src/orchestrator_runtime/documentation/detector.py:34-81`.

### RN-016 — Alegação de premissa incorreta não apaga rejeição anterior

**Regra.** `PREMISE_MISMATCH` declarado pelo executor não fabrica score 1.0. Se
já existe rejeição persistida, a task encerra `INCOMPLETE`; sem rejeição, a
alegação fica explícita como não verificada e o score permanece nulo.

**Razão.** O executor não pode substituir o validator nem lavar um parecer
contrário já gravado. Score perfeito sem julgamento contamina métricas e oculta
que nada foi entregue.

**Evidência.** ramo `premise_mismatch` em
`runtime/src/orchestrator_runtime/tasks/service.py:2217-2260` e
`TaskService._premise_note`/`TaskService.degradations` no mesmo módulo.

## Classificação, loops e critérios

### RN-017 — Negação e hipótese não contam como intenção de loop

**Regra.** `detect_loop` remove cláusulas condicionais e negadas antes de pontuar
keywords. Prefixo explícito (`/loop-bug`, `/bug`) continua vencendo a heurística.

**Razão.** Texto como “não é correção de bug” ou “se for bug, corrija” descreve
negação ou ramo hipotético, não o roteiro principal. Pontuá-lo impõe fases e ACs
incompatíveis com a tarefa real.

**Evidência.** `_CONDITIONAL_CLAUSE_RE`, `_NEGATED_CLAUSE_RE` e `detect_loop` em
`runtime/src/orchestrator_runtime/planning/loops.py:405-469`.

### RN-018 — Loop de código não impõe gates de código a task não-código

**Regra.** Se o `task_type` final é `docs`, `review`, `complex_analysis`,
`security_review` ou `architecture`, critérios herdados de loop de implementação
passam por `_safe_loop_criteria`: `tests_pass` é removido e
`workspace_changes` vira evidência quando aplicável. Critérios escritos pelo
usuário continuam soberanos.

**Razão.** Uma menção incidental a defeito não pode obrigar uma análise ou
documentação a produzir código. A defesa duplicada cobre tanto construção nova
quanto plano persistido com critérios antigos.

**Evidência.** `_NON_CODE_TASK_TYPES`, `_loop_is_compatible` e
`_safe_loop_criteria` em
`runtime/src/orchestrator_runtime/planning/analyzer.py:186-238`;
`CriteriaBuilder.build` e `Planner.plan` no mesmo arquivo, linhas 406-417 e
509-527.

## Evidência de entrega e memória

### RN-019 — `changed_files` deve enxergar nova edição em árvore já suja

**Regra.** O baseline Git guarda `content_hashes` e
`nested_content_hashes` somente para paths já sujos. `changed_files_since`
combina mudança do porcelain com mudança de SHA-256 na raiz e nos repositórios
filhos imediatos.

**Razão.** Código XY do porcelain não muda quando um arquivo já `M` é editado de
novo, e uma restauração pode fazê-lo desaparecer do status. Sem hash, trabalho
real fica invisível; hashear toda a árvore, por outro lado, cobra custo alto em
toda task.

**Evidência.** `GitBaseline`, `_dirty_content_hashes`,
`_changed_paths_in_repo` e `changed_files_since` em
`runtime/src/orchestrator_runtime/execution/git_workspace.py:18-37,153-190,235-260`;
`TaskService._enrich_changed_files` em
`runtime/src/orchestrator_runtime/tasks/service.py:3995-4016`.

### RN-020 — Aprendizado é salvo antes da compactação

**Regra.** Ao persistir o episódio, o runtime grava learning em SQLite,
Markdown, índice e OpenWolf antes de truncar artefatos grandes de resultado.
Falha desse caminho não muda o estado final da task.

**Razão.** Compactar primeiro destruiria a fonte usada para extrair o
aprendizado durável. A memória é otimização posterior ao resultado e não pode
derrubar trabalho já julgado.

**Evidência.** `TaskService._persist_episode` e
`TaskService._learn_then_compact` em
`runtime/src/orchestrator_runtime/tasks/service.py:4618-4714`;
`compact_result_artifacts` em
`runtime/src/orchestrator_runtime/memory/learnings.py:308-328`.

## Processos de agente

### RN-021 — Processo lançado é registrado de forma recuperável

**Regra.** Todo CLI de agente lançado pelo runtime tem sua identidade
persistida no instante do spawn, na tabela `agent_processes`: `pid`, `image` e
`create_time` lidos do sistema operacional, mais `owner_pid` (o processo do
runtime que lançou), `task_id` e `started_at`. A saída do processo fecha o
registro com `finished_at`.

**Razão.** O único rastreador anterior era um set em memória
(`CliExecutor._active_pids`), consumido só por `kill_active()` no cancelamento
ordenado. Ele desaparece junto com o processo que o criou — ou seja, cobre
exatamente o caso em que o runtime está vivo, e órfão é por definição o caso em
que ele já não está. `agent_runs` não serve para isso: a linha só nasce quando o
processo termina e a tabela não tem coluna de PID. Sem registro durável, nenhum
outro processo consegue nem saber que aquele CLI existe.

O registro vale para **todo** ponto que fabrica executor de CLI, não só o do
despacho comum: o fan-out cria um `CliExecutor` NOVO por subtarefa (executor
compartilhado quebraria o heartbeat e a sonda de silêncio, que olham a árvore
principal enquanto a subtarefa escreve no worktree), e executor novo nasce sem
`on_launch`. Sem ligar o rastreamento também lá, justamente os CLIs mais
numerosos — N subtarefas em paralelo — ficariam invisíveis para a ceifa.

**Evidência.** `AgentProcessRow` em
`runtime/src/orchestrator_runtime/memory/database.py:113-140`;
`CliExecutor.on_launch`/`_notify_launch`/`_notify_exit` em
`runtime/src/orchestrator_runtime/agents/process.py:189-197,329,474-499`;
`TaskService._register_process_tracking` em
`runtime/src/orchestrator_runtime/tasks/service.py:1675-1723`, ligado no despacho
comum em `runtime/src/orchestrator_runtime/tasks/service.py:4569` e no fan-out em
`runtime/src/orchestrator_runtime/tasks/service.py:4242-4270`;
`TaskRepository.add_agent_process` e `finish_agent_process` em
`runtime/src/orchestrator_runtime/tasks/repository.py:427-441`.

### RN-022 — Nenhum processo é morto sem identidade conferida

**Regra.** Antes de qualquer kill, a identidade ATUAL do PID é lida do próprio
sistema operacional (Windows: `GetProcessTimes` + `QueryFullProcessImageNameW`;
Linux: `/proc/<pid>/stat`) e precisa conferir com a registrada nos **dois**
campos: nome da imagem e instante de criação. Identidade divergente — ou
ilegível — encerra o assunto sem kill.

**Razão.** O Windows recicla número de processo. Matar por número mataria o
programa alheio que herdou o número, e o custo do erro é assimétrico: deixar um
órfão vivo custa recurso de máquina, matar o processo errado custa o trabalho de
outra pessoa. Por isso a falha é sempre para o lado de não matar.

**Evidência.** `ProcessIdentity`, `process_identity` e `identity_matches` em
`runtime/src/orchestrator_runtime/agents/reaper.py:43-81`; leitores do S.O. em
`runtime/src/orchestrator_runtime/agents/reaper.py:84-159`.

### RN-023 — Ceifa de órfão exige as quatro condições juntas

**Regra.** Um CLI só é ceifado quando satisfaz tudo ao mesmo tempo: (1) o PID
foi registrado pelo próprio orquestrador ao lançar o agente; (2) a identidade
atual confere (RN-022); (3) a task dona está em estado terminal **ou** o
processo do runtime que o lançou está morto; (4) passou
`orphan_agent_reap_after_s` desde o lançamento. A ceifa roda nos pontos de poll
que já existem (`status`, `list_tasks`, `follow_events`, `create_task`) — sem
daemon, processo novo ou thread de poll periódico — e a reivindicação de cada
linha (`reaped_at`, sob gate de thread e lock de arquivo) a torna idempotente
entre pollers concorrentes. `kill_active()` no cancelamento permanece intacto.

**Razão.** Cada condição barra um estrago distinto: sem (1) o runtime mataria
processo que não lançou; sem (2) mataria o herdeiro do número; sem (3) mataria
agente que está trabalhando agora; sem (4) mataria no vão entre o spawn e o
primeiro sinal de vida. O acionamento por poll é o mesmo padrão da adoção de
task órfã (RN-008): a frota já faz poll com frequência, e um vigia próprio seria
mais um processo para ficar órfão.

**Evidência.** `TaskService._reap_orphan_agents`, `_agent_process_orphan` e
`_reap_orphan_agents_safe` em
`runtime/src/orchestrator_runtime/tasks/service.py:1725-1820`; gancho nos polls
em `runtime/src/orchestrator_runtime/tasks/service.py:882-891`;
`TaskRepository.claim_agent_process` em
`runtime/src/orchestrator_runtime/tasks/repository.py:474-488`;
`RuntimeLimits.orphan_agent_reap_after_s` em
`runtime/src/orchestrator_runtime/config.py:103,359-361`.

## Como alterar uma regra

Mudança numa RN exige reconferir o símbolo citado, o motivo registrado nos
comentários do código e os testes que fixam o comportamento. Se código e regra
divergirem, o código atual é a fonte de verdade e a divergência deve ser
registrada em `limitacoes.md` antes de promover a nova afirmação — convenção de
evidência definida em `docs/README.md`.
