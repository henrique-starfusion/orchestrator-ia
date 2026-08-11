# Catálogo de funcionalidades implementadas

Visão única do que o produto faz no estado correspondente a `VERSION:1`. O
catálogo separa superfície pública de mecanismo interno e não inclui roadmap.

Exposição usada nas tabelas:

- **Pública** — há comando, tool MCP ou arquivo de configuração destinado ao
  operador.
- **Configuração** — existe e é acionável, mas somente por chave de
  `.orchestrator/config/`, sem comando dedicado.
- **Interna** — existe no código e participa do produto, mas não tem entrada
  direta para o usuário; estas linhas cumprem a marcação obrigatória de
  funcionalidade não exposta.

## Instalador e pacote

| Funcionalidade | O que resolve | Comando ou ponto de entrada | Exposição | Evidência no código |
|---|---|---|---|---|
| Wrapper único Node | Separa comandos de pacote dos comandos do runtime e inicia PowerShell ou Python com o ambiente correto | `orchestrator <comando>` | Pública | `mapCommand`, `runRuntime`, `runInstaller` e `main` em `bin/orchestrator.js:94-175,331-451` |
| Bootstrap por one-liner com cache | Obtém o pacote por `gh` ou `git`, reutiliza cache local e executa o instalador no projeto-alvo | `get.ps1 [install\|verify\|update\|...]` | Pública | `Sync-PackageCache` em `get.ps1:62-140` |
| Instalação idempotente de `.orchestrator/` | Aplica o template sem tratar todos os arquivos como sobrescrita cega; modos `managed`, `merge`, `user-owned`, `generated` e `runtime` preservam a responsabilidade de cada artefato | `orchestrator install` / `orchestrator init` | Pública | `Apply-Manifest`, `Copy-ManagedFile` e `Copy-TemplateTree` em `scripts/Orchestrator.Common.ps1`; branch `install` em `scripts/Install-Orchestrator.ps1` |
| Update com comparação de versão e backup | Recusa downgrade acidental, sincroniza estrutura ausente em versão igual e cria backup antes de bump ou `-Force` | `orchestrator update [-Force]` | Pública | `scripts/Update-Orchestrator.ps1:25-63` e branch `update` em `scripts/Install-Orchestrator.ps1:257-359` |
| Sync do pacote sem truncar clone completo | Atualiza o repositório do pacote, mantendo `--depth 1` apenas quando ele já é shallow e usando fast-forward no clone completo | acionado por `orchestrator update` | Pública | `Sync-PackageSource` em `scripts/Orchestrator.Common.ps1:1016-1105`; cache em `get.ps1:74-93` |
| Verificação da instalação e hooks | Confere ambiente, estrutura instalada e hooks sem executar uma task | `orchestrator verify` | Pública | branch `verify` em `scripts/Install-Orchestrator.ps1:236-254`; `Detect-Environment.ps1`, `Validate-Orchestrator.ps1`, `Validate-Hooks.ps1` |
| Detecção, probe e geração de adapters | Descobre CLIs instalados, testa compatibilidade do profile e materializa adapters no projeto | acionado por `install` e `update` | Pública | `Detect-Agents.ps1`; `Probe-Agents.ps1`; `Generate-Adapters.ps1`; chamadas em `scripts/Install-Orchestrator.ps1:305-345,716,838-844` |
| Atualização e instalação de CLIs de agentes | Atualiza agentes existentes e, quando solicitado, tenta instalar os ausentes por métodos curados | opções `-UpdateAgents`, `-SkipAgentUpdates`, `-InstallMissingAgents`; `Update-Agents.ps1 -Only` | Pública | `scripts/Update-Agents.ps1`; mapas `Get-AgentNpmPackageMap`, `Get-AgentNativeInstallerMap`, `Get-AgentChocolateyPackageMap` e `Get-AgentScoopPackageMap` em `scripts/Orchestrator.Common.ps1` |
| Ferramentas globais e pacotes de skills | Instala ferramentas opt-in, configura MCPs/plugins globais e lista/instala pacotes de skills curados | `orchestrator global-tools`; `orchestrator skills list\|install` | Pública | branches `global-tools` e `skills` em `scripts/Install-Orchestrator.ps1:123-135,572`; `Install-GlobalTools.ps1`; `Install-SkillPack.ps1` |
| Migração e limpeza de legado com restauração | Inventaria, faz backup, migra, remove ou restaura configurações antigas conforme o modo escolhido | `orchestrator legacy scan\|cleanup\|status\|restore` | Pública | branch `legacy` em `scripts/Install-Orchestrator.ps1:178-231`; `Invoke-LegacyCleanupPipeline.ps1`; `Restore-LegacyBackup.ps1` |
| Registro e propagação para a frota | Mantém registry de projetos instalados, remove entradas inválidas, descobre workspaces e aplica update nos destinos | `orchestrator update` com `-NoPropagate`/`-Discover` | Pública | `Get-ProjectRegistryPath`, `Register-OrchestratorProject`, `Find-OrchestratorProjects` em `scripts/Orchestrator.Common.ps1:1111-1315`; `Propagate-OrchestratorUpdate.ps1` |
| Relatório de instalação | Materializa inventário legível do que foi instalado, detectado e validado | gerado no fim de `install`/`update` | Interna | `Write-InstallationReport.ps1`; chamadas em `scripts/Install-Orchestrator.ps1:478,923` |
| Reparo e desinstalação | Reaplica a instalação para reparar artefatos ou remove o ambiente instalado | `orchestrator repair`; `orchestrator uninstall` | Pública | branches correspondentes em `scripts/Install-Orchestrator.ps1`; `Repair-Orchestrator.ps1`; `Uninstall-Orchestrator.ps1` |

## Runtime

| Funcionalidade | O que resolve | Comando ou ponto de entrada | Exposição | Evidência no código |
|---|---|---|---|---|
| Execução persistente multiestágio | Conduz a task por análise, memória, plano, seleção, execução, testes, validação, correção, documentação e consolidação | `orchestrator run --prompt "..."` | Pública | `TaskService._execute_loop` em `runtime/src/orchestrator_runtime/tasks/service.py:1860-2896`; `TaskState` em `tasks/state_machine.py:10-27` |
| Gestão separada da task | Permite criar agora, executar depois, consultar, listar, cancelar, retomar, ver logs, acompanhar e listar artefatos | `orchestrator task create\|run\|status\|list\|cancel\|resume\|logs\|watch\|artifacts` | Pública | comandos em `runtime/src/orchestrator_runtime/cli.py:210-447` |
| Análise e plano sem executar | Classifica, cria critérios e plano sem chamar executor nem alterar a entrega | `orchestrator run --dry-run` | Pública | opção em `runtime/src/orchestrator_runtime/cli.py:130-180`; `TaskService._dry_run` |
| Fila e paralelismo por escopo | Serializa colisões e admite tasks concorrentes somente abaixo do teto e com escopos disjuntos | `--scope`; `max_parallel_tasks` | Pública | `TaskService._blocking_task_id` e `_maybe_start_next` em `runtime/src/orchestrator_runtime/tasks/service.py:1420-1547`; `execution/scopes.py` |
| Adoção e limpeza de órfãs | Retira `RECEIVED` e a cabeça `QUEUED` do limbo quando o processo dono morreu, respeitando leases e guardas de admissão | acionada por create/status/list/watch | Interna | `TaskService._adopt_orphan_received`, `_queued_orphan_head` e `_adopt_orphan_queued`; `runtime/src/orchestrator_runtime/tasks/service.py:1584-1659` |
| Cancelamento hard-stop e retomada segura | Mata CLIs filhos no cancel e reinicia task retomada pelo começo lógico do pipeline | `orchestrator task cancel`; `orchestrator task resume` | Pública | `TaskService.cancel`, `_ensure_runnable`, `_execute_loop`; `runtime/src/orchestrator_runtime/tasks/state_machine.py:137-182` |
| Pausa estruturada para decisão humana | Interpreta `REQUIRES_INPUT`, guarda pergunta/opções e permite devolver uma mensagem antes de retomar | `orchestrator_message` no MCP; `task resume` no CLI | Pública | ramo `REQUIRES_INPUT` de `TaskService._execute_loop`; transições de `WAITING_FOR_USER` em `tasks/state_machine.py:114-121` |
| Classificação, loops e critérios tipados | Escolhe tipo/risco/complexidade, detecta roteiro e transforma critérios declarados ou inferidos em checks persistidos | prefixo `/loop-<id>`, alias `/<id>` ou `--loop`; critérios `AC-001:`/seção `Critérios:` | Pública | `TaskAnalyzer`, `CriteriaBuilder`, `Planner` em `runtime/src/orchestrator_runtime/planning/analyzer.py`; `LOOPS` e `detect_loop` em `planning/loops.py` |
| Descoberta de regras e skills | Seleciona regras de projeto e skills instaladas relevantes; skill selector usa modelo rápido e fallback heurístico | configuração `skill_selection`; rules em `.cursor/rules/` e `.orchestrator/rules/` | Configuração | `rules/discovery.py`; `skills/discovery.py`; `skills/selector.py`; `TaskService._select_skills` em `tasks/service.py:2923-2970` |
| Baseline Git robusta | Completa `changed_files` quando o CLI não informa, cobrindo árvore já suja e repositórios Git filhos imediatos | automática em cada execução | Interna | `GitBaseline`, `capture_baseline`, `changed_files_since` em `runtime/src/orchestrator_runtime/execution/git_workspace.py:18-260`; `TaskService._enrich_changed_files` |
| Descoberta e execução de testes por stack | Encontra comandos reais para npm, Python, Rust, Go, .NET, Maven, Gradle e Make, inclusive em subdiretórios/repositórios tocados | automática na fase `TESTING` | Interna | `TestDiscovery` e `TestRunner.run_all` em `runtime/src/orchestrator_runtime/testing/discovery.py`; `stack_test_commands:162-165` |
| Baseline de testes e classificação de ambiente | Distingue regressão introduzida de falha pré-existente, ferramenta/dependência ausente e suíte sem testes | automática antes do primeiro executor e na fase `TESTING` | Interna | `TaskService._execute_loop:2100-2135`; `TestRunner.run_all:168-367`; `DeterministicValidator` |
| Validação determinística + revisão LLM + correção | Avalia critérios tipados, exige validator independente e volta a `CORRECTING` quando o veredito pede reparo | `minimum_validation_score`, `require_independent_validation` | Configuração | `DeterministicValidator`, `LlmReviewValidator`, `CompletionGate` em `runtime/src/orchestrator_runtime/validation/deterministic.py`; fase `VALIDATING` em `TaskService._execute_loop` |
| Integridade dos testes alterados | Detecta enfraquecimento suspeito de assertions, remoção/skip de testes e expõe o achado ao validator | automática sobre o diff | Interna | `analyze_diff` e `summarize` em `runtime/src/orchestrator_runtime/validation/test_integrity.py:81-163`; uso em `TaskService` |
| Gate documental | Revisa README/CHANGELOG/docs e links locais antes de autorizar `COMPLETED` | automático em `UPDATING_DOCUMENTATION` | Interna | `DocumentationDetector`, `DocumentationUpdater`, `DocumentationValidator` em `runtime/src/orchestrator_runtime/documentation/detector.py`; `TaskService._execute_loop:2851-2895` |
| Timeout em dois eixos | Separa teto duro (`run_timeout`) de silêncio sem progresso (`idle_timeout`) e reserva orçamento do veredito | `agent_timeout_by_role`, `agent_no_output_timeout_s` | Configuração | `AgentTimeoutPolicy`, `minimum_task_budget_s`, `resolve_agent_timeout_policy` em `runtime/src/orchestrator_runtime/execution/timeouts.py` |
| Retry de lançamento com jitter | Reexecuta processo que não nasceu sem sincronizar todos os agentes na mesma espera e sem ultrapassar o orçamento | automático após falha `launch` | Interna | `TaskService._launch_backoff_s` e `_retry_launch_failure` em `runtime/src/orchestrator_runtime/tasks/service.py:3751-3875` |
| Fan-out em worktrees e merge por patch | Decompõe uma entrega em subtarefas isoladas, coleta patches e os aplica de forma controlada | `allow_parallel_workspace_writes` + `max_parallel_subtasks >= 2` | Configuração | `TaskService._fanout_enabled`, `_decompose` e fluxo de fan-out; `runtime/src/orchestrator_runtime/execution/worktrees.py` |
| Redação de valores de segredo | Evita persistir valores de atribuições reconhecidas sem apagar a linha inteira que o runtime ainda precisa interpretar | automática na saída de agente | Interna | `redact` em `runtime/src/orchestrator_runtime/agents/process.py:89-134` |

## Integração com agentes

| Funcionalidade | O que resolve | Comando ou ponto de entrada | Exposição | Evidência no código |
|---|---|---|---|---|
| Profiles declarativos de CLI | Define invocação, flags, transporte do prompt, modelo, timeout e códigos de saída por agente sem criar um executor Python por fornecedor | JSON em `.orchestrator/agents/profiles/`; `orchestrator agents` | Pública | `DeclarativeCliAdapter.build_command`, `continue_session` e `load_profile` em `runtime/src/orchestrator_runtime/agents/base_adapters.py:96-185,339-340`; `AgentRegistry` |
| Suporte instalado a seis clientes | Fornece profiles para Claude, Codex, Cursor, Gemini, Kimi e OpenCode; Cursor é cliente IDE e não worker selecionável | `orchestrator agents` | Pública | `package/template/.orchestrator/agents/profiles/*.json`; bloqueio de Cursor em `RulesRouter._pick`, `routing/manager.py:109-134` |
| Roteamento por papel, capacidade e modelo | Escolhe planner/executor/validator, evita o agente que já atende o chat quando possível, resolve modelo por papel/task e mantém fallbacks | overrides `--planner`, `--executor`, `--validator`; `models.json` | Pública | `RulesRouter.select_plan`, `_pick`, `resolve_model_candidates` em `runtime/src/orchestrator_runtime/routing/manager.py:47-185` |
| Fallback por cota | Tenta o próximo modelo confirmado do mesmo cliente quando o atual esgota cota | automático na chamada do agente | Interna | `routing/quota.py`; `RulesRouter.resolve_model_candidates`; ramo `should_retry_next_model` em `TaskService._run_agent` |
| Anti-recursão de agente filho | Marca cada CLI spawnado com `ORCHESTRATOR_CHILD_AGENT=1` e impede esse processo de delegar outra vez | automático; variável `ORCHESTRATOR_CHILD_AGENT` | Interna | `is_child_agent` e `CliExecutor.run` em `runtime/src/orchestrator_runtime/agents/process.py:58-66,194-215`; `TaskService._child_agent_restriction_block:3082-3098` |
| Prompt por stdin quando argv não cabe | Evita o limite de linha de comando no Windows e devolve diagnóstico próprio para profile que não aceita stdin | automático pelo profile `prompt_via`/`prompt_stdin` | Configuração | `DeclarativeCliAdapter.continue_session` em `runtime/src/orchestrator_runtime/agents/base_adapters.py:141-185` |
| Diagnóstico de falha do agente | Separa autenticação, instalação, serviço do provedor, falha de lançamento e erro normal antes de decidir ação | automático | Interna | `classify_agent_failure` em `runtime/src/orchestrator_runtime/agents/health.py:166-220` |
| Auto-reparo controlado | Reinstala uma vez o CLI classificado como quebrado reutilizando os instaladores curados; auth/serviço/launch não entram nesse reparo | `agent_auto_repair`; `Update-Agents.ps1 -Only` | Configuração | `repair_agent` em `runtime/src/orchestrator_runtime/agents/repair.py:61-97`; `TaskService._maybe_repair_and_retry` |
| Fake adapters para CI | Executa o pipeline sem provedores externos e produz fixture determinística | `--fake-agents` | Pública para testes | `FakeAgentAdapter` em `runtime/src/orchestrator_runtime/agents/base_adapters.py:260-336` |

## MCP

| Funcionalidade | O que resolve | Comando ou ponto de entrada | Exposição | Evidência no código |
|---|---|---|---|---|
| Servidor FastMCP por stdio ou HTTP | Expõe o mesmo `TaskService` para chats/IDEs sem duplicar a lógica de execução | `orchestrator mcp serve --transport stdio\|http` | Pública | `create_fastmcp_server` e `serve` em `runtime/src/orchestrator_runtime/mcp/server.py:39-56,259` |
| Tools de execução e acompanhamento | Cria task, retorna status/eventos/resultado, cancela, retoma e entrega mensagem humana | `orchestrator_run`, `status`, `events`, `result`, `cancel`, `resume`, `message` | Pública | tools registradas em `runtime/src/orchestrator_runtime/mcp/server.py:120-195` |
| Tools de análise, delegação e inventário | Classifica sem executar, delega um papel pontual, lista agentes e busca memória | `orchestrator_analyze`, `delegate`, `agents`, `memory_search` | Pública | `runtime/src/orchestrator_runtime/mcp/server.py:69-118,197-215` |
| Resources somente leitura | Permite ler health, agentes, status, eventos, plano, resultado e validação por URI | `orchestrator://...` | Pública | registros em `runtime/src/orchestrator_runtime/mcp/server.py:217-243`; `OrchestratorMcpResources` em `mcp/resources.py:15-62` |
| Prompts MCP reutilizáveis | Orienta front controllers nos fluxos de orquestrar, delegar, validar e investigar sem substituir tools | prompts MCP do servidor | Pública | `PROMPTS` em `runtime/src/orchestrator_runtime/mcp/prompts.py:3-41`; registro em `mcp/server.py:245-254` |
| Configuração do Cursor | Mescla o servidor MCP em `.cursor/mcp.json` e instala/verifica a regra do front controller | `orchestrator cursor configure\|verify\|print-config` | Pública | comandos em `runtime/src/orchestrator_runtime/cli.py:493-593`; `mcp/cursor_config.py` |
| Proteção contra processo MCP stale | Compara fingerprint carregado com o disco e recusa/avisa quando o processo longo não executa o código atual | `orchestrator_health`; `orchestrator version --json`; `mcp doctor` | Pública | `code_fingerprint` em `runtime/src/orchestrator_runtime/diagnostics.py:149-190`; `orchestrator_health` em `mcp/server.py:56-67` |

## Memória e aprendizado

| Funcionalidade | O que resolve | Comando ou ponto de entrada | Exposição | Evidência no código |
|---|---|---|---|---|
| Persistência SQLite da execução | Conserva tasks, eventos, runs de agente/teste, roteamento, validação, documentação, memória e métricas entre processos | `.orchestrator/data/orchestrator.db` | Interna | modelos em `runtime/src/orchestrator_runtime/memory/database.py`; `TaskRepository` em `tasks/repository.py` |
| Recuperação lexical de memória | Busca episódios/learnings anteriores por termos do novo prompt antes do planejamento | `orchestrator_memory_search`; fase `RETRIEVING_MEMORY` | Pública | `TaskRepository.search_memories`; chamadas em `TaskService._execute_loop:1930-1939`; tool MCP em `mcp/server.py:201-215` |
| Episódio terminal | Grava resumo, estado, score e revisão documental ao terminar uma task | automático em `_persist_episode` | Interna | `TaskService._persist_episode` em `runtime/src/orchestrator_runtime/tasks/service.py:4618-4644` |
| Learn-then-compact | Extrai digest e aprendizado durável, atualiza Markdown/índice/OpenWolf e só depois trunca outputs grandes | `context_compaction` em `policies.json` | Configuração | `TaskService._learn_then_compact` em `tasks/service.py:4646-4714`; `memory/learnings.py` |
| Export legível de episódio e learning | Mantém arquivos Markdown consultáveis sem abrir o banco | `.orchestrator/memory/episodes/` e `memory/learnings/` | Pública como artefato | `TaskService._export_memory_markdown:4716-4725`; `write_markdown` e `update_index` em `memory/learnings.py` |
| Métricas de agente e estratégia | Acumula desempenho observado para auditoria e estatística | tabelas `agent_performance` e `strategy_performance` | Interna, sem consulta operacional direta | `TaskRepository.update_agent_performance` e `update_strategy_performance`; escrita em `TaskService._persist_episode:4635-4638` |

## Observabilidade

| Funcionalidade | O que resolve | Comando ou ponto de entrada | Exposição | Evidência no código |
|---|---|---|---|---|
| Eventos estruturados | Nomeia mudanças de estado, agentes, testes, validação, documentação, memória, fila e término sem poluir stdout do MCP stdio | stderr e tabela `task_events` | Interna, consumida pelas superfícies públicas | `EventType`, `RuntimeEvent`, `EventBus.emit` em `runtime/src/orchestrator_runtime/events.py:13-82`; `TaskRepository.add_event` |
| Acompanhamento incremental padrão | Transmite eventos novos com cursor, termina no estado terminal e evita loops de shell inventados | `orchestrator task watch <id>` | Pública | `task_watch` em `runtime/src/orchestrator_runtime/cli.py:349-438`; `TaskService.follow_events:996-1023` |
| Heartbeat de agente e de loop | Mostra vida durante CLI ativo e também entre agentes, com fase, idade do sinal e PID | `task status --text`; `orchestrator_status` | Pública | `EventType.AGENT_PROGRESS`/`LOOP_PROGRESS` em `events.py:21-27`; `TaskService.status:957-994`; `_loop_heartbeat`/`_register_heartbeat` |
| Ledger de degradações | Consolida perda de independência, auth, serviço, launch, premissa, plano cru e desvio de escopo num formato único | campo `degradations` em status/result | Pública | `TaskService.degradations` em `runtime/src/orchestrator_runtime/tasks/service.py:1077-1202` |
| Logs e artefatos da task | Permite auditar eventos e arquivos produzidos por uma execução específica | `orchestrator task logs`; `task artifacts` | Pública | comandos em `runtime/src/orchestrator_runtime/cli.py:340-447`; `TaskService.logs` e `TaskService.artifacts` |
| Fingerprint e lista de capacidades | Expõe hash do código carregado, diferença para o disco e flags estáveis de comportamento | `orchestrator version --json`; `orchestrator_health` | Pública | `_FINGERPRINT_FILES`, `FEATURES`, `code_fingerprint` em `runtime/src/orchestrator_runtime/diagnostics.py:9-190` |

## Limites de leitura do catálogo

“Implementada” não significa “habilitada por padrão”. Fan-out, compactação,
auto-reparo e paralelismo dependem das chaves citadas; defaults e divergências
entre configuração viva e template ficam em `configuracao.md` e
`limitacoes.md`. Arquivos declarativos sem leitor e estruturas ainda sem
superfície operacional também permanecem registrados em `limitacoes.md`, com a
evidência correspondente.
