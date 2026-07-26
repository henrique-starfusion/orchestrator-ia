# Auditoria — Uso da frota (0.4.25) + Onboarding de agentes

**Data:** 2026-07-26
**Escopo:** por que a frota de 10 projetos não usa o Orquestrador corretamente e o que corrigir.
**Modo:** somente leitura (sem commit, sem push, sem alteração de runtime, sem `npm test`/`pytest`).
**Sessão:** interativa, acesso pleno ao workspace `D:\StarFusion\bootstrap-agents`.

## Nota de método (limitação de acesso)

O sandbox desta sessão permite leitura apenas dentro de `D:\StarFusion\bootstrap-agents`.
Tentativas de ler `D:\StarFusion\printbee\CLAUDE.md` (Read e Grep) retornaram
`Claude requested permissions to read from ... but you haven't granted it yet`, e `cd D:/StarFusion`
foi bloqueado. Portanto:

- Números por projeto (tasks, tamanhos de arquivo, contagem de pastas de backup do printbee) vêm do
  **dataset fornecido no prompt** e são citados como tal.
- Todos os achados sobre **causa raiz** foram verificados diretamente nos arquivos-fonte do pacote
  (`package/template/adapters/**`, `scripts/**`, `runtime/src/**`) e no próprio workspace instalado
  (`.orchestrator/`, `AGENTS.md`, `CLAUDE.md`), que são **os mesmos artefatos distribuídos** para os
  10 projetos. Cada achado abaixo traz caminho + linha.

---

## 1. Sumário executivo

A frota não deixa de usar o Orquestrador por falta de runtime — deixa por **falta de onboarding
vendor-neutro**. As instruções operacionais ricas existem em **um único lugar que só o Cursor lê**
(`.cursor/rules/multiagent-orchestrator.mdc`, 94 linhas). O que chega a Claude Code, Codex CLI e
Gemini é um adapter de 998 / 431 / 391 bytes que menciona **um** comando (`orchestrator run --prompt`)
sem verificação, sem poll, sem staleness, sem anti-recursão útil e sem MCP.

Quatro fatores compostos:

| # | Fator | Efeito medido/observado |
|---|-------|--------------------------|
| A-1 | Instruções ricas exclusivas do Cursor | Agente não-Cursor gastou 1m38s + 22.100 tokens só para descobrir como invocar (incidente 2026-07-26) |
| A-2 | MCP `orchestrator-ia` registrado **só** para Cursor | Claude Code/Gemini/Codex não têm as tools `orchestrator_*`; CLI é o único caminho — e é o menos documentado |
| A-3 | Mojibake real em `AGENTS.md` distribuído | `AGENTS.md:25-27` contém `â†’` no lugar de `→`; causa raiz em `scripts/Generate-Adapters.ps1:63` |
| A-4 | `.orchestrator/backups/` sem retenção | 4.912 de 5.083 arquivos sob `.orchestrator/` são backup = **96,6% de ruído** em glob/grep |

Consequência de funil: **86 tasks na frota, 8 COMPLETED (9,3%), 59 CANCELLED (68,6%)** (dataset).
A relação causal com o desconhecimento operacional é **parcial e argumentada na seção 5** — não é a
causa única (a auditoria de 2026-07-25 já documentou bug-022 e hangs do Codex), mas é a causa que
explica por que o operador *não tem alternativa a cancelar*.

---

## 2. Achado A-1 — As instruções de operação moram num arquivo que só o Cursor lê

### Evidência

Arquivo rico, vendor-específico:

- `.cursor/rules/multiagent-orchestrator.mdc` — 5.077 bytes, 94 linhas, `alwaysApply: true` (linha 3).
  Contém: gatilhos de orquestração (linhas 16-21), anti-padrões (29-36), **contrato de poll
  obrigatório** (38-49), **protocolo anti-MCP-stale** com `code_fingerprint`/`modules_stale`/probe
  (51-67), regras duras (69-78) e formato de anúncio de provider/model (85-93).

Adapters distribuídos aos demais agentes (`package/template/adapters/`, tamanhos reais medidos):

```
998  claude/CLAUDE.md
431  codex/AGENTS.section.md
578  codex/AGENTS.codex.section.md
391  gemini/GEMINI.md
260  gemini/GEMINI.section.md
260  kimi/KIMI.section.md
400  opencode/AGENTS.section.md
268  opencode/AGENTS.opencode.section.md
```

`package/template/adapters/claude/CLAUDE.md` tem **32 linhas** e menciona exatamente um comando
(linha 13): `orchestrator run --prompt "<atividade>"`. Não menciona `task status`, `task list`,
`task logs`, `task resume`, `version`, poll, ou MCP. `gemini/GEMINI.md` (9 linhas) diz apenas
"Prefer `orchestrator run` for multi-agent tasks" (linha 6). `codex/AGENTS.section.md:4` idem.

Não existe local vendor-neutro para essas regras: `package/template/.orchestrator/` **não tem
diretório `rules/`** (listagem: `agents config hooks mcp memory orchestration runtime schemas
scripts skills tools`), e o `.orchestrator/rules/` instalado contém só `legacy-import/`
(3 arquivos, todos de migração de legado).

### Confronto com o incidente

A sequência observada em `D:\StarFusion\printbee` é explicada linha a linha:

| Passo do agente | Por que aconteceu |
|---|---|
| Leu `CLAUDE.md`, achou só `orchestrator run --prompt` | É literalmente tudo que `claude/CLAUDE.md:13` oferece |
| Tentou **localizar o CLI** no disco | Nenhum adapter diz que `orchestrator` está no PATH (bin npm: `package.json:15-18` mapeia `orchestrator`→`bin/orchestrator.js`) |
| Varreu `.orchestrator/**/*.{md,json,ps1,js,ts}` | `CLAUDE.md:6` manda "Read project rules and skills from `.orchestrator/`" sem dizer *quais* subpastas |
| "Há muito ruído vindo dos backups" | Ver A-4 |
| Concluiu que precisaria **delegar a um subagente com shell** | O adapter não diz que o CLI é chamável direto, e a regra anti-recursão distribuída é uma frase solta (ver A-5) |
| **Nunca** citou o MCP `orchestrator-ia` | Ver A-2: o MCP não está registrado para Claude Code |
| **Nunca** citou `task status/create` nem `version` | Esses comandos não aparecem em nenhum adapter não-Cursor |

O CLI de fato expõe tudo que faltava — `bin/orchestrator.js:32-33`:

```
orchestrator run --prompt "..."
orchestrator task create|run|status|list|cancel|resume|logs|artifacts
```

e `runtime/src/orchestrator_runtime/cli.py` confirma os subcomandos reais:
`version` (64), `agents` (86), `run` (114), `task create` (155), `task run` (186),
`task status` (209), `task list` (223), `task cancel` (238), `task resume` (248),
`task logs` (264), `task artifacts` (273).

**Nada disso está documentado para agentes não-Cursor.** O conhecimento existe; a distribuição não.

---

## 3. Achado A-2 — O MCP `orchestrator-ia` é registrado exclusivamente para o Cursor

### Evidência

- `package/template/adapters/cursor/.cursor/mcp.json.example` registra o server
  `orchestrator-ia` (`cmd /c orchestrator mcp serve --transport stdio --project ${workspaceFolder}`).
- `scripts/Configure-CursorMcp.ps1:123` escreve `.cursor\mcp.json` do projeto e `:142`
  `$env:USERPROFILE\.cursor\mcp.json`. **Nenhum outro destino.**
- `scripts/Install-GlobalTools.ps1:193-225` também só monta `mcpServers` para o Cursor.
- Busca por registro MCP de outros vendors: só esses dois scripts contêm `mcpServers`
  (`grep -rln "mcpServers" scripts/`).
- No workspace instalado **não existe** `.mcp.json` na raiz (listagem de `ls -a` da raiz), e
  `.claude/settings.json` não contém a substring `mcp` (Grep case-insensitive: *No matches found*).

### Efeito

O servidor MCP tem 12 tools (`runtime/src/orchestrator_runtime/mcp/server.py`):
`orchestrator_health` (51), `orchestrator_analyze` (64), `orchestrator_delegate` (86),
`orchestrator_run` (115), `orchestrator_status` (150), `orchestrator_events` (154),
`orchestrator_result` (166), `orchestrator_cancel` (178), `orchestrator_resume` (182),
`orchestrator_message` (188), `orchestrator_agents` (192), `orchestrator_memory_search` (196).

Todo o contrato de poll do `.mdc` (linhas 38-49) e o protocolo anti-stale (51-67) são escritos
**em termos dessas tools**. Para Claude Code, Codex e Gemini elas não existem — logo, mesmo que a
regra do Cursor fosse copiada literalmente, seria inexecutável. O bloco canônico da seção 7
resolve isso descrevendo **MCP e CLI lado a lado**, com o CLI como caminho garantido.

Observação: `.cursor/mcp.json` = 980 bytes nos 10 projetos (dataset) — ou seja, **o front controller
está instalado em toda a frota, mas endereçado a um único cliente**.

---

## 4. Achado A-3 — Mojibake CONFIRMADO no adapter distribuído (`AGENTS.md`), não no `CLAUDE.md`

### Evidência direta (bytes)

Template-fonte, limpo — `package/template/adapters/codex/AGENTS.codex.section.md:11`:

```
20 20 2d 20 66 61 73 74 20 e2 86 92 20 60 67 70 74 ...
                            ^^^^^^^^ = U+2192 "→" em UTF-8 correto
```

Arquivo **instalado** no projeto — `AGENTS.md:25` (raiz de `bootstrap-agents`):

```
20 20 2d 20 66 61 73 74 20 c3 a2 e2 80 a0 e2 80 99 20 60 67 70 74 ...
                            ^^^^^ ^^^^^^^^ ^^^^^^^^
                            "â"    "†"      "’"     = "â†’"
```

Renderizado, `AGENTS.md:25-27`:

```
  - fast â†’ `gpt-5.6-terra-medium`
  - balanced (docs/impl) â†’ `gpt-5.6-sol-medium`
  - deep/max â†’ `gpt-5.6-sol`
```

Isto é a assinatura exata de **UTF-8 lido como CP1252 e reescrito como UTF-8**
(`E2 86 92` → `â` `†` `’` → `C3A2 E280A0 E28099`). É o mesmo padrão do `a†'` citado no prompt.

### Causa raiz

`scripts/Generate-Adapters.ps1` tem dois caminhos de escrita:

| Linha | Caminho | Comportamento | Resultado |
|---|---|---|---|
| 93 | `Copy-Item` (arquivos inteiros) | cópia byte a byte | **`CLAUDE.md`, `GEMINI.md`, `KIMI.md` ficam íntegros** |
| 63 | `Get-Content -LiteralPath ... -Raw` (arquivos `*.section.md`) | **sem `-Encoding`** | PowerShell 5.1 assume ANSI/CP1252 quando não há BOM |
| 67 | `Get-Content -LiteralPath $destPath -Raw` | idem | idem |
| 72/75 | `Add-Content` / `Set-Content -Encoding UTF8` | reescreve os caracteres já corrompidos em UTF-8 | **grava o mojibake permanentemente** |

Os templates `*.section.md` **não têm BOM** (primeiros bytes de `codex/AGENTS.section.md` e
`gemini/GEMINI.section.md`: `3c 21 2d 2d 20 6f 72 63` = `<!-- orc`), então o autodetect do PS 5.1
cai no default ANSI. `claude/CLAUDE.md` também não tem BOM (`23 20 4f 72 63 68 65 73` = `# Orches`),
mas escapa por ir pelo `Copy-Item`.

### Correção do prompt

O prompt supunha mojibake no `CLAUDE.md`. **Verificado: falso para `CLAUDE.md`, verdadeiro para
`AGENTS.md`.** `CLAUDE.md` na raiz do workspace está em UTF-8 válido —
`od -A d -c CLAUDE.md` mostra `documenta 303 247 303 243 o` (ç, ã corretos, offset 0000496) e
`342 206 222` (`→`, offsets 0000768/0000816/0000848/0000896). O canal corrompido é o de *seções
anexadas*, que é justamente o canal do `AGENTS.md` — o arquivo lido por Codex CLI e OpenCode.

### Degradação da leitura

`â†’` no meio de uma tabela de roteamento de modelos (`fast â†’ gpt-5.6-terra-medium`) não impede a
leitura, mas: (a) consome tokens extras por caractere de substituição; (b) sinaliza ao agente que o
arquivo é lixo gerado, reduzindo a confiança nele; (c) se um dia o mojibake atingir um **comando**
(ex.: um path com acento, ou o próprio bloco canônico da seção 7, que é cheio de "ção"), o comando
copiado pelo agente falha.

### Risco imediato

Durante esta auditoria surgiram, às **2026-07-26 17:41** (mtime), cinco arquivos novos e não
rastreados por git — evidentemente de uma sessão paralela implementando esta mesma remediação:

```
2904  2026-07-26 17:41:07  package/template/adapters/claude/CLAUDE.usage.section.md
2904  2026-07-26 17:41:15  package/template/adapters/codex/AGENTS.usage.section.md
2904  2026-07-26 17:41:15  package/template/adapters/gemini/GEMINI.usage.section.md
2904  2026-07-26 17:41:15  package/template/adapters/kimi/KIMI.usage.section.md
2904  2026-07-26 17:41:15  package/template/adapters/opencode/AGENTS.usage.section.md
```

(`git status --short` os lista como `??`.) Eles casam com o regex de seção em
`Generate-Adapters.ps1:61` (`(\.[A-Za-z0-9_-]+)?\.section\.md$` → qualificador `.usage`), portanto
**vão pelo caminho `Get-Content` sem `-Encoding` da linha 63**. O conteúdo deles é português
acentuado ("é o modo **padrão**", "iteração", "não cancele por impaciência"). **Se instalados hoje,
chegam mojibakados em toda a frota.** É preciso corrigir a linha 63/67 *antes* de rodar
`orchestrator update`, ou usar um bloco sem acentos (é o que a seção 7 entrega).

---

## 5. Achado A-4 — `.orchestrator/backups/` é 96,6% do que um agente vê

### Evidência (medida neste workspace)

```
find .orchestrator -type f            → 5.083 arquivos
find .orchestrator/backups -type f    → 4.912 arquivos  (96,6%)
  ...  -name "*.md"                   →   974
  ...  -name "*.json"                 → 1.018
ls .orchestrator/backups | wc -l      →    67 pastas
```

Dataset do prompt: printbee tem 42 pastas de backup; a frota varia de 12 a 67.

Nomes: `20260719-160641-pre-update`, `20260721-194656-legacy-cleanup`, … — dois backups por
`update` (um `pre-update` + um `legacy-cleanup`), gerados por
`scripts/Orchestrator.Common.ps1:494` e `scripts/Backup-LegacyConfigurations.ps1:40`.

### Não há retenção

`Test-ShouldExcludeFromOrchestratorBackup` (`scripts/Orchestrator.Common.ps1:436-448`) só evita
backup-de-backup. Poda de backups antigos **não existe** — está declarada como pendência em
`scripts/Invoke-LegacyCleanupPipeline.ps1:178`:

> `# KeepLegacyBackup default: sempre manter backup (seguro). Flag reservada para limpeza futura de backups antigos.`

### Por que o `.gitignore` não resolve

`.gitignore:2` ignora `/.orchestrator/` — o que ajuda ferramentas que respeitam gitignore, mas:
(a) o agente do incidente **glob explícito** `.orchestrator/**/*.{md,json,ps1,js,ts}`, que ignora a
regra; (b) `.gitignore` não é lido por Codex CLI / Gemini CLI da mesma forma; (c) não existe
`.claudeignore`, `.cursorignore` nem `.geminiignore` no projeto (`ls -a | grep -i ignore` retorna só
`.gitignore`).

Uma busca por `*.md` sob `.orchestrator/` retorna **974 hits de backup** contra dezenas de arquivos
reais — sinal-ruído de ~1:20. É racional o agente reclamar e desistir.

### Mitigação concreta (3 níveis, do mais barato ao mais correto)

1. **Instrução (grátis, imediata):** o bloco canônico da seção 7 nomeia explicitamente
   `.orchestrator/backups/`, `.orchestrator/runtime/results/` e `.orchestrator/data/` como
   "não vasculhar", e nomeia onde a config real está. Custo zero, cobre todos os vendors.
2. **Retenção (uma flag):** implementar a pendência de `Invoke-LegacyCleanupPipeline.ps1:178` —
   manter os N mais recentes (sugestão N=3) e apagar o resto ao fim de `orchestrator update`.
   Reduziria 67 → 3 pastas (~4.700 arquivos a menos por projeto).
3. **Relocação (a correção estrutural):** mover a raiz de backup de
   `<projeto>/.orchestrator/backups/` para
   `%LOCALAPPDATA%\StarFusion\orchestrator\backups\<projeto>\`, alinhando com onde o registry já
   vive (`%LOCALAPPDATA%\StarFusion\orchestrator\projects.json`). Tira o ruído do workspace de vez;
   exige ajustar `Orchestrator.Common.ps1:494` e `Restore-LegacyBackup.ps1:18`/`:44` (que hoje exige
   que o backup esteja dentro do projeto).

Recomendação: **1 agora** (é doc, entra junto com o bloco canônico), **2 no próximo patch**,
**3 no próximo minor**.

---

## 6. Achado A-5 — Relação entre desconhecimento operacional e os 68,6% de cancelamento

Este é o achado com **inferência**, não medição direta. Declaro a força de cada elo.

### O que é fato (dataset)

| Projeto | Tasks | CANCELLED | COMPLETED | Última |
|---|---|---|---|---|
| printbee | 55 | 44 (80%) | 3 (5,5%) | 2026-07-25 20:24 |
| bootstrap-agents | 25 | 11 | 2 (8%) | 2026-07-25 18:30 |
| GuardLine.BR | 3 | 3 (100%) | 0 | 2026-07-23 |
| adzora | 3 | 1 | 0 | 2026-07-22 |
| **frota** | **86** | **59 (68,6%)** | **8 (9,3%)** | — |

Sem DB (runtime nunca rodou): corehub, gangsheeter, rivero, starfusion, ukomerce, vavi — **6 de 10**.

### Elo forte: os 4 projetos que usam o runtime são exatamente os que têm o adapter mínimo

O dataset mostra `CLAUDE.md == 998 bytes` (o template mínimo, byte a byte) em bootstrap-agents,
adzora, printbee e GuardLine.BR — **os mesmos 4 que têm DB**. Os 6 sem DB têm `CLAUDE.md` maior
(corehub 11.663, gangsheeter 14.868, vavi 2.320, rivero/starfusion 1.831, ukomerce 1.013), isto é,
conteúdo próprio do projeto **que sobrescreveu ou nunca recebeu o adapter** — `Generate-Adapters.ps1:83`
pula o destino quando o arquivo já existe e `-Force` não foi passado:

```powershell
if ((Test-Path -LiteralPath $destPath) -and -not $Force) { $skipped++; return }
```

**Conclusão sólida:** onde o adapter não foi instalado, o runtime nunca rodou (0 de 6). Onde foi,
rodou (4 de 4). A instrução distribuída é o gatilho de adoção — e hoje ela é de 998 bytes.

### Elo médio: só 2 dos 10 projetos têm as instruções ricas

`.cursor/rules/multiagent-orchestrator.mdc` (5.077 bytes) existe em **bootstrap-agents e printbee**
(dataset). São justamente os dois com volume real de tasks (25 e 55) — e também os dois com mais
cancelamento absoluto (11 e 44). Ou seja: ter a regra rica **aumentou o uso**, mas **não reduziu o
cancelamento** — porque a regra endereça o *quando orquestrar*, e o problema do funil é o
*acompanhar até o fim*.

Lendo o `.mdc`: 12 das 94 linhas (38-49) tratam de poll, e **zero linhas** tratam de
"quanto tempo é normal esperar" ou "não cancele". O único texto sobre duração esperada em toda a
base de regras é… inexistente.

### Elo fraco (declarado como hipótese, não como medição)

A cadeia "agente não sabe acompanhar → operador não vê progresso → cancela → refaz inline" é
**consistente** com os dados e com o padrão P0-2 já documentado em
`docs/audits/2026-07-25-multi-project-orchestrator-usage-audit.md:75`
("Padrão 'cancela e faz inline pelo chat' domina o funil"), mas **não é isolável** das causas de
infraestrutura já registradas na mesma auditoria: bug-022 (cancel não encerra o loop, linha 59) e os
hangs do Codex no Windows/erro 740 (linha 84).

**Formulação honesta:** o desconhecimento operacional não *cria* o cancelamento — as falhas de infra
criam. Ele **remove a alternativa ao cancelamento**. Um agente que soubesse rodar
`orchestrator task status <id>` e `task logs <id>` poderia distinguir "travado" de "trabalhando" e
optar por `task resume` em vez de cancelar. Hoje nenhum agente não-Cursor sabe que esses comandos
existem — e nem os do Cursor sabem quanto tempo esperar.

**Teste que confirmaria/refutaria:** após distribuir o bloco canônico, medir a razão
`task resume` / `task cancel` nos próximos 30 dias. Hoje ela é praticamente zero
(`task resume` não aparece em nenhuma instrução distribuída).

---

## 7. Bloco canônico proposto (vendor-neutro, pronto para copiar)

**Destino:** anexar em `CLAUDE.md`, `AGENTS.md` e `GEMINI.md` de **todos os 10 projetos**
(mais `KIMI.md`/`CURSOR.md` por consistência). Distribuir como `*.usage.section.md` nos adapters,
já que `Generate-Adapters.ps1:58-79` faz append idempotente por marcador (primeira linha).

**Nota deliberada sobre acentuação:** o texto abaixo é **sem acentos**. Isso não é descuido — é a
única forma de o bloco sobreviver ao bug do achado A-3 (`Generate-Adapters.ps1:63`) **hoje**, sem
depender de deploy de código. Depois de corrigir a linha 63 para
`Get-Content -LiteralPath $_.FullName -Raw -Encoding UTF8` (e a linha 67 idem), o bloco pode ser
reescrito com acentuação normal.

**Contagem:** 55 linhas (limite de 60 respeitado).

```markdown
<!-- orchestrator:how-to-use -->
## Como usar o Orquestrador (todo agente: Claude, Codex, Gemini, Kimi, OpenCode, Cursor)

Este projeto tem o Orquestrador Multiagente instalado. Ele e o modo padrao para
qualquer tarefa nao-trivial — o usuario nao precisa pedir.

### 1. Voce e filho ou principal?
Se `ORCHESTRATOR_CHILD_AGENT` estiver definida no ambiente, voce E um agente
delegado: faca o trabalho INLINE e NUNCA delegue de novo (nem orquestrador, nem
subagentes) — delegacao aninhada trava a execucao. Caso contrario, siga abaixo.

### 2. Quando orquestrar
Qualquer um destes: alterar codigo-fonte (mesmo 1 linha de logica); corrigir bug
(bug fix nunca e "trivial"); criar/alterar testes, build ou configuracao; tarefa
com criterios de aceitacao, validacao ou multiplos arquivos.
Resposta direta so para: duvida conceitual, leitura sem edicao, typo/formatacao.

### 3. Como chamar
MCP (preferido SE as tools `orchestrator_*` existirem nesta sessao):
`orchestrator_run` -> guarde `task_id` -> `orchestrator_status` a cada
`next_poll_after_seconds` -> `orchestrator_events` se parecer parado ->
`orchestrator_result` no fim. So declare sucesso/fracasso apos o `result`.

CLI (sempre funciona; unico caminho quando nao ha MCP):
```bash
orchestrator run --prompt "<atividade com criterios de aceitacao>"  # sincrono
orchestrator task create --prompt "..."    # cria sem executar; devolve task_id
orchestrator task list                     # tasks recentes + estado
orchestrator task status <task_id>         # estado, iteracao, score, blockers
orchestrator task logs <task_id>           # saida dos agentes
orchestrator task resume <task_id>         # retoma task nao-terminal
orchestrator task cancel <task_id>         # ultimo recurso (ver secao 4)
orchestrator version --json                # versao + code_fingerprint
```
Nao procure o CLI no disco: `orchestrator` ja esta no PATH (bin npm global).
Overrides: `--executor <agente> --validator <agente> --max-iterations N`.
No Windows nao use `codex` como validator (trava por sandbox; use `claude`).

### 4. Acompanhe ate o fim — nao cancele por impaciencia
Duracoes normais: SELECTING_AGENTS ~2min, EXECUTING 5-30min, VALIDATING ~7min.
Minutos parado no mesmo estado e ESPERADO, nao e travamento.
Antes de cancelar rode `task status` e `task logs`. Havendo progresso, espere.
Cancelar e refazer inline joga fora trabalho ja pago e e hoje a maior causa de
tarefa perdida nesta frota: 68,6% das tasks terminam CANCELLED.

### 5. Staleness do runtime
Apos `orchestrator update`, compare `orchestrator version --json`
(`code_fingerprint`) com `orchestrator_health` -> `runtime.code_fingerprint`.
Divergiu, ou `modules_stale=true`: peca reload do MCP e nao declare "verificado".

### 6. O que NAO vasculhar
`.orchestrator/backups/`, `.orchestrator/runtime/results/` e `.orchestrator/data/`
sao artefatos gerados (milhares de arquivos) — exclua de glob e grep.
Config real fica em `.orchestrator/config/`, `.orchestrator/agents/profiles/` e
`.orchestrator/skills/`.
```

---

## 8. Recomendações priorizadas

| ID | Ação | Onde | Prioridade |
|---|---|---|---|
| R1 | Corrigir encoding: `-Encoding UTF8` em `Get-Content` | `scripts/Generate-Adapters.ps1:63` e `:67` | **P0** — bloqueia R2 se o bloco tiver acentos |
| R2 | Distribuir o bloco da seção 7 como `*.usage.section.md` para claude/codex/gemini/kimi/opencode/cursor | `package/template/adapters/*/` | **P0** |
| R3 | Reinstalar adapters nos 6 projetos sem DB com `-Force` (hoje `Generate-Adapters.ps1:83` pula) | corehub, gangsheeter, rivero, starfusion, ukomerce, vavi | **P0** — 0 de 6 nunca rodaram o runtime |
| R4 | Registrar o MCP `orchestrator-ia` para Claude Code (`.mcp.json` na raiz) e demais vendors | `scripts/Configure-CursorMcp.ps1` (generalizar) | P1 |
| R5 | Implementar retenção de backups (manter 3) | `scripts/Invoke-LegacyCleanupPipeline.ps1:178` | P1 |
| R6 | Consolidar `AGENTS.md` corrompido: regerar com `-Force` após R1 | 10 projetos | P1 |
| R7 | Mover a raiz de backups para `%LOCALAPPDATA%` | `Orchestrator.Common.ps1:494`, `Restore-LegacyBackup.ps1:18/44` | P2 |
| R8 | Adicionar `discover_roots` = `["D:\\StarFusion", "D:\\GuardLine"]` (GuardLine.BR só sobrevive pela entrada explícita) | `%LOCALAPPDATA%\StarFusion\orchestrator\projects.json` | P2 |
| R9 | Medir razão `task resume`/`task cancel` em 30 dias para validar o elo da seção 6 | orchestrator.db | P2 |

Conflito a resolver antes de R2: os cinco `*.usage.section.md` criados às 17:41 de hoje
(seção 4, "Risco imediato") cobrem o mesmo escopo com acentuação. Escolher **uma** versão —
ou aplicar R1 primeiro e manter a acentuada, ou substituí-la pela versão sem acentos da seção 7.
Instalar a acentuada sem R1 propaga mojibake para os 10 projetos.

---

## 9. Critérios de aceitação desta auditoria

- **AC-001** — Arquivo novo `docs/audits/2026-07-26-fleet-orchestrator-usage-and-agent-onboarding.md`
  criado; auditorias anteriores (`2026-07-24-*`, `2026-07-25-*`) intocadas. ✅
- **AC-002** — Cada achado traz caminho:linha ou número do dataset:
  A-1 (`multiagent-orchestrator.mdc:3,16-21,38-49,51-67`; `claude/CLAUDE.md:6,13`; `cli.py:64-273`;
  `bin/orchestrator.js:32-33`), A-2 (`Configure-CursorMcp.ps1:123,142`;
  `Install-GlobalTools.ps1:193-225`; `mcp/server.py:51-196`), A-3 (bytes de
  `AGENTS.codex.section.md:11` vs `AGENTS.md:25`; `Generate-Adapters.ps1:61,63,67,72,75,93`),
  A-4 (5.083/4.912/67 medidos; `Orchestrator.Common.ps1:436-448,494`;
  `Invoke-LegacyCleanupPipeline.ps1:178`), A-5 (dataset de 86 tasks; `Generate-Adapters.ps1:83`;
  `2026-07-25-multi-project-orchestrator-usage-audit.md:59,75,84`). ✅
- **AC-003** — Seção 7 traz o bloco integral, vendor-neutro, em português, 55 linhas (≤ 60). ✅
- **Restrições** — Nenhum commit, push, alteração de runtime, `npm test` ou `pytest` nesta sessão.
  Único arquivo criado: este relatório. ✅

---

## 10. Nota sobre o blocker `VAL-001: npm test` (fora do escopo desta auditoria)

O validador reprovou uma iteração desta task com `VAL-001: Teste falhou: npm test` /
`TEST-FAIL: cmd=npm test status=failed exit=1`. Verificação estática (sem executar a suíte, que o
prompt proíbe):

1. **`npm test` não cobre nada que esta auditoria produziu.** `package.json:46` mapeia
   `test` → `powershell -File tests/Run-AllTests.ps1`, que roda apenas `tests/Test-*.ps1`
   (`Run-AllTests.ps1:11-13`) — testes de instalador, adapters, perfis de agente e limpeza de legado.
   O entregável desta task é um único arquivo em `docs/audits/`. Grep por `docs/audits` em `tests/`
   retorna **zero** referências (únicos hits de `docs` são a *task class* `docs` em
   `Test-AgentProfiles.ps1:70-73`).
2. **Os `*.usage.section.md` também não são cobertos.** Grep por `section.md` em
   `Test-Adapters.ps1`, `Test-CurrentAdaptersPreserved.ps1`, `Test-Idempotency.ps1` e
   `Test-ProjectPropagate.ps1` retorna zero hits — nenhuma asserção sobre a lista de arquivos de
   adapter que a sessão paralela criou às 17:41.
3. **A única alteração de código na working tree é de outra task.**
   `git diff --stat` = `runtime/src/orchestrator_runtime/tasks/repository.py | 12 ++++++++++++`
   (guard de `CancelledError` em `transition()`, correção do bug-022). É código Python; `npm test`
   não executa pytest (`package.json:47` separa `test:runtime`). Mesmo assim, é uma mudança de
   runtime **anterior a esta sessão** e explicitamente fora das restrições
   ("sem alterar código de runtime").

**Conclusão:** `VAL-001` é um falso-positivo em relação ao escopo desta task — a suíte que falhou
não observa nenhum artefato produzido aqui. Corrigi-la exigiria executar `npm test` e alterar
`scripts/`/`runtime/`, ambos vetados pelo prompt. Fica registrado como pendência interativa:
rodar `npm test` isoladamente na working tree limpa para separar falha pré-existente
(provavelmente `Test-AgentProfiles.ps1`, que invoca CLIs reais) do guard novo em `repository.py`.
