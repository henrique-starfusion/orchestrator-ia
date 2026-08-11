# Limitações, pendências e hipóteses

Tudo o que não coube nos outros nove documentos por não ser fato simples sobre
o código. Cada item traz o motivo e onde conferir.

Classificação:

- **LIM** — limite real do produto, verificado no código.
- **DIV** — divergência entre documentação existente e código.
- **PEND** — pendência: algo declarado, começado ou prometido que não está
  fechado.
- **HIP** — hipótese: leitura plausível que não pôde ser confirmada só com o
  repositório.

## Divergências entre documentação e código

Itens marcados como **resolvidos** permanecem aqui para preservar o histórico da
rodada; não descrevem uma limitação atual.

### DIV-001 — Resolvida: README alinhado à versão 0.4.82

`README.md:11` e o cabeçalho de `docs/README.md` agora declaram `0.4.82`, o mesmo
valor de `VERSION:1` e `package.json:3`. A causa da divergência era a repetição
manual do número sem checagem de sincronismo; `VERSION` fica explícito como
fonte canônica no README.

### DIV-002 — `docs/task-lifecycle.md` lista `WAITING_FOR_USER` como terminal

O documento antigo escreve: "Terminais: COMPLETED, INCOMPLETE, FAILED,
CANCELLED, WAITING_FOR_USER". No código, `TERMINAL_STATES` tem exatamente
quatro estados e **não** inclui `WAITING_FOR_USER`
(`runtime/src/orchestrator_runtime/tasks/state_machine.py:30-35`); `can_resume`
devolve `True` para ele (linha 146). A diferença é operacional: task em
`WAITING_FOR_USER` **ocupa o workspace** e bloqueia a fila
(`tasks/repository.py:173`), e pode ser retomada.

### DIV-003 — o fluxo publicado no README omite a fila

`README.md:34-36` descreve `receber → analisar → memória → planejar →
selecionar → executar → testar → validar → corrigir → documentação →
consolidar`. Falta o estado `QUEUED`, que existe desde a 0.4.19
(`tasks/state_machine.py:49-54`) e é o que qualquer operador encontra primeiro
quando duas tasks disputam o mesmo workspace.

### DIV-004 — política viva diverge do template quanto a escrita paralela

`.orchestrator/config/policies.json` deste repositório traz
`allow_parallel_workspace_writes: true`, enquanto
`package/template/.orchestrator/config/policies.json` traz `false` (diferença
única entre os dois arquivos). O default do código também é `false`
(`config.py:40` e `259`). Consequência: **este** repositório roda com fan-out
ligado; um projeto recém-instalado, não. Quem comparar comportamento entre
projetos precisa saber disso.

## Limites do produto

### LIM-001 — chaves de configuração declaradas e nunca lidas

Quatro chaves de `policies.json` são carregadas em `RuntimeLimits` e nunca
consultadas: `minimum_score_improvement`, `require_deterministic_validation`,
`require_documentation_review` e `allow_parallel_read_only_analysis`
(evidência: só aparecem em `config.py:239`, `250`, `253` e `256`). Mudar
qualquer uma não altera comportamento. Detalhe por chave em `configuracao.md`.

### LIM-002 — quatro arquivos de configuração inteiros sem leitor

`routing.json`, `validation.json`, `tools.json` e `orchestrator.json` existem em
`.orchestrator/config/` e nenhum código do runtime, do wrapper Node ou dos
scripts de instalação os lê (varredura por nome de arquivo em `runtime/src`,
`bin`, `scripts`, `package`, `tests`; a única ocorrência de `validation.json`
está em `scripts/Validate-LegacyCleanup.ps1`, em outro contexto). O roteamento
real está hardcoded em `agents/__init__.py:130-135` e em `models.json`; o limiar
de validação vem de `policies.json`. Editar esses arquivos é inócuo.

### LIM-003 — `models.json` tem mais conteúdo declarativo do que leitores

O runtime lê apenas `clients.*` (`model_flag`, `aliases`, `models`,
`prefer_aliases`, `task_map`), `task_classes.*.tier` e
`role_model_preferences` (`routing/manager.py:157-254`). `principles`, `tiers`,
`escalation`, `resolution_algorithm`, `token_economy`, `required_agent_tooling`
e `always_on_skills` não são lidos por ninguém. Em especial, o bloco
`escalation` (subir um tier após falha de validação) **não está implementado**:
o único fallback de modelo é o de cota, em `tasks/service.py:2935-2959`.

### LIM-004 — sem migração de schema do SQLite

`create_session_factory` chama `Base.metadata.create_all`
(`memory/database.py:216-219`). Isso cria tabelas ausentes, mas não altera
tabela existente. Coluna nova em base antiga exige intervenção manual. Não há
Alembic nem script de migração de dados no repositório (as migrações em
`package/migrations/` são PowerShell e tratam de **arquivos de configuração**,
não do banco).

### LIM-005 — tabelas escritas e nunca lidas

`agent_performance`, `strategy_performance` e `documentation_updates` recebem
escrita a cada task e nenhum código as consulta (ver a tabela-resumo em
`dados.md`). São material de auditoria manual. Em particular, o roteador **não**
usa desempenho histórico para escolher agente — a quarentena olha `agent_runs`,
não `agent_performance` (`tasks/service.py:2343-2362`).

### LIM-006 — `validation_issues.resolved` nunca é atualizado

A coluna existe com default 0 (`memory/database.py:156`) e nenhum código a
escreve. Não há como distinguir issue resolvida de issue aberta consultando a
tabela; a informação real está na sequência de `validation_rounds`.

### LIM-007 — nem todo evento emitido é persistido

`EventBus.emit` só ecoa em stderr e chama handlers (`events.py:60-74`). A
gravação em `task_events` é uma chamada separada a `repo.add_event`. Vários
pontos do serviço emitem sem persistir (por exemplo os eventos de fan-out em
`tasks/service.py:2612-2625` e `2701-2717`). Quem audita pelo banco vê menos do
que quem estava olhando o console.

### LIM-008 — redação de segredo continua dependente do formato da atribuição

`redact` preserva a linha e substitui somente o valor de uma atribuição cuja
chave contenha `API_KEY`, `TOKEN`, `SECRET`, `PASSWORD`, `PASSWD` ou
`AUTHORIZATION` (`agents/process.py:89-134`). Isso corrigiu o comportamento que
apagava prosa inteira, mas um segredo solto, sob chave fora desse vocabulário ou
em formato não reconhecido ainda pode chegar a `agent_runs.stdout` e aos `.txt`
de `runtime/results/`. É mitigação textual, não garantia de detecção de segredo.

### LIM-009 — busca de memória é ranqueamento por contagem de termos

`search_memories` carrega as 100 memórias mais recentes e pontua por quantos
tokens da consulta aparecem no conteúdo (`tasks/repository.py:489-511`). Sem
índice, sem stemming, sem embedding. Memória relevante mais antiga que as 100
últimas nunca é encontrada.

### LIM-010 — uma estratégia só

`RulesRouter.select_plan` devolve sempre `strategy="execute_review_repair"`
(`routing/manager.py:87`). `strategy_performance` e o campo `strategy` de
`routing_decisions` existem para comparar estratégias que ainda não existem.

### LIM-011 — manager LLM é um hook, não uma implementação

Com `provider: openai-compatible` e `enabled: true`, `build_manager` devolve
`LocalLlmManager` (`manager_model/base.py:148-155`), mas os três métodos dessa
classe delegam ao `RulesManager` (linhas 122-145). O comentário no código diz
`MVP: usa rules; LLM hook preparado`. Ligar o provider não muda decisão nenhuma
hoje.

### LIM-012 — dependência forte de Windows no instalador

O instalador é PowerShell e várias proteções são específicas de Windows:
override de sandbox do Codex (`agents/base_adapters.py:108-111`), teto de
8000 chars para `.CMD`/`.BAT` (`agents/base_adapters.py:33`), `taskkill /T /F`
(`agents/process.py:407-412`), fallback de bin global do npm
(`agents/process.py:436-473`) e o registro da frota em `%LOCALAPPDATA%`
(`Orchestrator.Common.ps1:1092`). Há caminhos POSIX no runtime, mas o
instalador não foi lido nesta rodada com foco em portabilidade.

### LIM-013 — quinze módulos são stubs de uma linha

`validation/completion_gate.py`, `validation/issues.py`,
`validation/llm_review.py`, `planning/planner.py`, `planning/criteria.py`,
`planning/strategies.py`, `memory/episodes.py`, `memory/performance.py`,
`memory/strategies.py`, `manager_model/rules.py`, `manager_model/local_llm.py`,
`manager_model/schemas.py`, `documentation/updater.py`,
`documentation/validator.py` e `testing/runner.py` têm uma linha cada e só
reexportam. A estrutura de diretórios promete uma modularização que a
implementação não tem: `tasks/service.py` sozinho concentra 3118 das ~11.8 mil
linhas do pacote.

### LIM-014 — critérios do tipo EVIDENCE são indecidíveis pelo determinístico

Critério `EVIDENCE` ou `CUSTOM` sem parâmetro devolve `None` em vez de `False`
(`validation/deterministic.py:134-139`), justamente para não reprovar entrega
válida. O efeito colateral é que **todo o mérito** desses critérios depende do
validador LLM. Numa auditoria ou pesquisa, onde quase todos os ACs são
`EVIDENCE` (`planning/analyzer.py:265-276`), o portão determinístico
praticamente não opina.

### LIM-015 — heurística de classificação é por expressão regular

`TaskAnalyzer.analyze` decide `task_type` por regex sobre o prompt
(`planning/analyzer.py:82-119`). Há proteções cuidadosas — intenção de
implementação vence palavra-chave, cláusula negada é removida, `design` só conta
com fronteira de palavra — mas continua sendo casamento de texto. Prompt
ambíguo pode nascer com o conjunto errado de critérios de aceitação, e o
critério é o que decide aprovação.

### LIM-016 — parser de seção `Critérios:` tem teto conhecido

`parse_criteria_section` documenta o próprio limite: item com `. ` no meio é
truncado ali (`planning/analyzer.py:291-297`). Critério escrito em prosa longa
pode chegar cortado ao validador.

## Pendências

### PEND-001 — a documentação antiga desta pasta não foi reconferida

Só os documentos-base listados em `docs/README.md` foram escritos ou atualizados
a partir do código.
`docs/orquestrador.md` (26 KB), `docs/cli-reference.md` (14 KB),
`docs/troubleshooting.md` (25 KB), `docs/installer-architecture.md` (10 KB),
`docs/model-routing.md`, `docs/legacy-migration.md` e os subdiretórios
`archive/`, `audits/`, `cleanup/`, `legacy/`, `maintenance/` continuam como
estavam. Podem conter mais divergências do tipo DIV-001 a DIV-004. Conferir:
comparar cada afirmação com o símbolo correspondente em
`runtime/src/orchestrator_runtime/`.

### PEND-002 — `subtasks` recém-saiu do papel

A tabela existiu desde o primeiro schema sem receber uma linha e só passou a ser
escrita na 0.4.61, com o fan-out (`tasks/repository.py:356-359`). Como o
fan-out está desligado por padrão no template (DIV-004), a maioria dos projetos
instalados continua sem nenhuma linha ali. Não há, no repositório, evidência de
execução em produção do caminho paralelo — só os testes
`test_0461_fanout_service.py`, `test_0461_fanout_split.py` e
`test_0461_worktrees.py`.

### PEND-003 — `list_subtasks` não tem chamador

O método existe em `tasks/repository.py:381` e nenhum código do serviço, do CLI
ou do MCP o chama. O resultado do fan-out chega ao operador pelos eventos e
pelos arquivos de patch, não por essa consulta.

### PEND-004 — cobertura da suíte não é medida

Não há configuração de `coverage`, `pytest-cov` nem gate de cobertura em
`runtime/pyproject.toml` ou em `package.json`. Sabemos quantos arquivos de teste
existem (68 unitários e 1 de integração), não quanto do código eles exercitam.

### PEND-005 — não há verificação automática dos exemplos desta documentação

Os comandos citados em `operacao.md` foram extraídos de `bin/orchestrator.js` e
de `cli.py`, mas **nenhum foi executado** nesta rodada — a tarefa era de análise
e escrita, e executar `install`/`update` alteraria arquivos fora de `/docs`.
Conferir: rodar cada comando com `--dry-run` num workspace descartável.

## Hipóteses

Leituras plausíveis que **não** puderam ser confirmadas só com o repositório.
Nenhuma delas foi usada como fato nos outros documentos.

### HIP-001 — o gate documental foi escrito para um caso de fixture

`DocumentationUpdater.ensure_usage_docs` tem lógica específica para a palavra
`soma`: se o prompt menciona `soma` e o README não contém `soma(`, o próprio
runtime **escreve** um bloco de uso em Python no README
(`documentation/detector.py:60-69`). O mesmo módulo `soma` é o que o
`FakeAgentAdapter` cria nos testes (`agents/base_adapters.py:296-336`) e existe
um `CriterionKind.SOMA_MODULE` dedicado (`tasks/models.py:32`).

Hipótese: esse caminho nasceu para a fixture de ponta a ponta e permaneceu no
código de produção. Efeito prático a confirmar: num projeto real cujo prompt
contenha a palavra "soma" em outro sentido, o runtime pode alterar o `README.md`
por conta própria. Conferir: executar uma task com a palavra em contexto
diferente e observar `documentation/detector.py:61`.

### HIP-002 — `raise` após `FAILED` pode deixar a task inconsistente para o chamador

Em `run_task`, o ramo de exceção não tratada marca `FAILED`, emite evento,
persiste episódio e **relança** a exceção (`tasks/service.py:713-733`). O
`finally` seguinte ainda chama `_maybe_start_next`. Para quem chamou por CLI o
processo termina com stack trace; por MCP, a tool captura. Hipótese: o
comportamento é intencional (falha visível), mas não há teste que fixe o
contrato do relance. Conferir: `runtime/tests/unit/` não tem arquivo dedicado a
esse caminho.

### HIP-003 — a fila é por processo tanto quanto por workspace

`_busy_task_id` combina duas fontes: o banco (`find_active_execution`) e o
conjunto em memória `_running_tasks` do processo atual
(`tasks/service.py:488-506`). Dois processos diferentes atendendo o mesmo
workspace enxergam apenas o banco em comum, e a exclusão de escrita real vem do
`WriteLock` em arquivo. Hipótese: a combinação é suficiente porque o lock é
autoritativo, mas o cenário de dois runtimes concorrentes no mesmo projeto não
tem teste de integração próprio. Conferir: `runtime/tests/unit/test_locks.py`
cobre o lock isolado, não a corrida entre dois `TaskService`.

### HIP-004 — quarentena pode ser tarde demais em CLI que falha devagar

A quarentena exige três runs consecutivos, cada um com menos de 30 s de duração
(`_QUARANTINE_MAX_DURATION_S`, `tasks/service.py:2325`). Hipótese: um CLI que
falha de forma consistente mas leva 40 s por tentativa nunca entra em
quarentena, e cada rotação de fallback volta a ele. Conferir: o teste
`test_0447_agent_quarantine.py` fixa o caso rápido; não há caso lento.

### HIP-005 — o número de linha das evidências envelhece rápido

O `CHANGELOG.md` mostra 61 releases na série 0.4, várias com mudanças em
`tasks/service.py`. Hipótese: boa parte das referências `arquivo:linha` desta
documentação vai deslocar em poucas releases. Mitigação já aplicada: sempre que
possível a evidência cita **também** o símbolo (`_execute_loop`,
`CompletionGate.can_complete`), que sobrevive melhor. Conferir: comparar
`git log --oneline -- runtime/src/orchestrator_runtime/tasks/service.py`.

## Não verificado nesta rodada

Registrado para quem continuar:

- Comportamento em POSIX (Linux/macOS): o código tem ramos não-Windows, mas o
  instalador e as proteções principais foram escritos para Windows (LIM-012).
- Conteúdo de `scripts/` além dos cinco scripts citados em `arquitetura.md` e
  `integracao-agentes.md`: são 36 arquivos, 7396 linhas somando o `bin`.
- `mcp/tools.py` foi lido em pontos-chave (`health`, `run`, `status`,
  `result`), não integralmente: são 941 linhas.
- `planning/loops.py`: os oito loops foram identificados por id, título e
  `task_type`; o conteúdo de cada roteiro (`stages`, `done_when`) não foi
  transcrito.
- `memory/learnings.py` (328 linhas): confirmou-se a ordem
  learning-antes-de-compactar e os caminhos de saída, não o formato interno do
  digest.
