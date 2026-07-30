# Changelog

## Unreleased

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
