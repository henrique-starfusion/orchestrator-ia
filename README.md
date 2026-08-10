# Orquestrador IA Multiagente

Projeto desenvolvido e mantido pela **StarFusion**.

- **Desenvolvedor:** Henrique Rodrigues
- **Licença:** [MIT](LICENSE) — uso comercial e não comercial permitido
- **Copyright © 2026** StarFusion Consultoria, Tecnologia e Soluções em Informática LTDA.

Pacote portátil para instalar, validar e manter um **ambiente multiagente genérico** e um **runtime persistente** em qualquer repositório. O orquestrador não pertence a uma aplicação específica: projetos-alvo são workspaces de execução.

**Versão atual:** 0.4.7 — ver [`CHANGELOG.md`](CHANGELOG.md).

---

## O que é o Orquestrador IA Multiagente

Duas camadas:

| Camada | Papel | Status |
|---|---|---|
| **Installer** | Instala/atualiza `.orchestrator/`, detecta agentes, adaptadores | implementado |
| **Runtime** | Executa o ciclo multiagente com SQLite, gates e evidências | implementado (MVP) |

```bash
orchestrator install                 # nucleo do workspace
orchestrator cursor configure        # MCP + rule no Cursor
orchestrator mcp serve               # tools MCP para o chat
orchestrator run --prompt "..."      # tarefa real (CLI)
```

Fluxo do runtime:

```text
receber → analisar → memória → planejar → selecionar → executar
→ testar → validar → corrigir → documentação → consolidar
```

Cursor é **cliente IDE** (front controller via MCP; não worker). MVP: Claude planeja/valida, Codex executa, runtime testa.

Documentação: [`docs/mcp-integration.md`](docs/mcp-integration.md) · [`docs/orquestrador.md`](docs/orquestrador.md) · [`docs/security.md`](docs/security.md) · [Security policy](.github/SECURITY.md)

---

## Por que `.orchestrator/` é a fonte canônica

Toda configuração compartilhada vive em **`.orchestrator/`** — políticas, skills, memória, registro de agentes, MCPs, ferramentas, hooks e artefatos de runtime.

Pastas e arquivos específicos de cada CLI ou IDE são **adaptadores finos** que apenas redirecionam para `.orchestrator/`:

| Adaptador | Exemplos |
|---|---|
| Claude Code | `.claude/`, `CLAUDE.md` |
| Codex / OpenCode | `.codex/`, `AGENTS.md` |
| Cursor | `.cursor/rules/`, `CURSOR.md` |
| Gemini CLI | `.gemini/`, `GEMINI.md` |
| Kimi CLI | `.kimi/`, `KIMI.md` |

**Não crie árvores paralelas de configuração.** Estenda `.orchestrator/` e deixe os adaptadores apontarem para ela.

Documentação detalhada do layout: `package/template/docs/agent-environment.md` (copiada para o projeto durante instalação, quando aplicável).

---

## Orquestrador, agentes e modelos

| Conceito | O que é | Exemplo |
|---|---|---|
| **Orquestrador** | Camada de coordenação, políticas e memória do workspace | Config em `.orchestrator/config/` |
| **Agente** | CLI ou IDE que executa tarefas delegadas | Claude Code, Codex, Cursor, Gemini |
| **Modelo** | LLM usado por um agente em uma sessão | Definido pelo próprio agente/fornecedor |

O bootstrap **detecta agentes** (binários no PATH), **gera adaptadores** e **registra capacidades** — não substitui a escolha de modelo feita dentro de cada CLI.

---

## CLIs suportados (detecção)

O instalador verifica presença no PATH e registra em `.orchestrator/agents/detected.json`:

`claude`, `codex`, `gemini`, `kimi`, `kimi-code`, `opencode`, `qwen`, `qwen-code`, `copilot`, `github-copilot`, `aider`, `goose`, `amp`, `kiro`, `cursor`, `continue`, `openhands`, `openclaw`, `droid`, `factory`

Nenhum é obrigatório além do que você usar na prática. Adaptadores de template existem para: **Claude, Codex, Cursor, Gemini, Kimi e OpenCode**.

---

## Instalação

Na pasta do seu projeto:

### Node.js / npm (recomendado)

```bash
npx --yes github:henrique-starfusion/orchestrator-ia#latest init
```

Ou instalar o CLI global e reutilizar em vários projetos:

```bash
npm install -g github:henrique-starfusion/orchestrator-ia#latest
cd C:\caminho\do\seu\projeto
orchestrator init
```

Equivalente curto: `mao init` (alias do mesmo binário).

> **Nota:** com origem `github:`, o npm usa fragmento git (`#latest`), **não** `...@latest` (sintaxe de registry).  
> `github:henrique-starfusion/orchestrator-ia@latest` **não funciona**. Alternativas: `#latest`, `#v0.4.4`, `#semver:*` ou tip de `#main`.

### PowerShell (Windows, com `gh` autenticado)

```powershell
gh api -H "Accept: application/vnd.github.raw" "repos/henrique-starfusion/orchestrator-ia/contents/get.ps1?ref=latest" | iex
```

Isso baixa o pacote para `%LOCALAPPDATA%\StarFusion\multiagent-orchestrator` (cache) e instala `.orchestrator/` no diretório atual.

### Atualização

Há **dois níveis**: atualizar o CLI (pacote npm) e atualizar a estrutura `.orchestrator/` do projeto.

#### 1) Atualizar o CLI via npm (global)

```bash
npm install -g github:henrique-starfusion/orchestrator-ia#latest
```

Sem instalar global — sempre a tag `latest` (release estável):

```bash
npx --yes github:henrique-starfusion/orchestrator-ia#latest update
```

#### 2) Atualizar a estrutura do projeto

Com o CLI já no PATH, na pasta do projeto:

```bash
orchestrator update
```

Equivalente: `mao update`. Alias legado: `orchestrator upgrade`.

Via clone local:

```bat
orchestrator-ia.bat update -ProjectPath C:\caminho\do\projeto
```

Fluxo típico (CLI global + projeto):

```bash
npm install -g github:henrique-starfusion/orchestrator-ia#latest
cd C:\caminho\do\seu\projeto
orchestrator update
```

O `update` sincroniza o pacote, aplica template/manifest de forma aditiva, redetecta agentes e valida. Use `-Force` / `--force` para sobrescrever arquivos gerenciados.

### Ferramentas globais (vários projetos)

No `init`/`update`, o pacote também configura no **perfil do usuário** (não só no projeto):

- MCPs: Context7, Playwright, Sequential Thinking (Claude + Cursor)
- Plugins Claude: context7, playwright, superpowers, skill-creator, atlassian, frontend-design, **caveman**
- Skills globais (`~/.agents`): Superpowers, find-skills, Firecrawl, **caveman** (economia de tokens)
- CLIs: `openwolf` (npm `-g`), `firecrawl-cli` (npm `-g`), **graphify** (`uv tool install graphifyy`)
- Roteamento de modelos por tarefa: `.orchestrator/config/models.json` (docs→Sonnet 5, análise complexa→Fable 5, trivial→Haiku). Ver [`docs/model-routing.md`](docs/model-routing.md).

```bash
orchestrator global-tools
```

Pular: `--skip-global-tools`. Detalhes: [`docs/global-tools.md`](docs/global-tools.md).

### O que acontece no `init`

1. Obtém o pacote versionado (npm/npx ou cache git/`gh`)
2. Copia o template para `.orchestrator/` (idempotente)
3. Detecta agentes CLI no PATH
4. Gera adaptadores mínimos (`CLAUDE.md`, `AGENTS.md`, etc.)
5. Instala/configura ferramentas globais (MCPs, plugins, skills)
6. Valida a instalação e grava relatório em `.orchestrator/runtime/reports/`

Não usa agentes de IA para montar a estrutura. OpenWolf/Graphify no projeto e tools globais não bloqueiam o bootstrap se falharem.

### Pré-requisitos

- **PowerShell 5.1+** (Windows) ou PowerShell 7+
- **git** no PATH (e/ou **gh** para one-liner PowerShell / repositório privado)
- **Node.js 18+** apenas se usar `npx` / `npm`
- Permissão de escrita no projeto-alvo
- Pelo menos **50 MB** livres no volume do projeto

### Instalação a partir do clone local

```bat
orchestrator-ia.bat init
orchestrator-ia.bat install -ProjectPath C:\caminho\do\projeto
```

```powershell
.\get.ps1
.\scripts\Install-Orchestrator.ps1 init -ProjectPath C:\caminho\do\projeto
```

Após sucesso, o workspace terá `.orchestrator/VERSION` alinhado à `VERSION` do pacote (atualmente **0.1.0**).

---

## Comandos

| Comando | Descrição |
|---|---|
| `init` | Alias de `install` (compatível com OpenWolf/Graphify) |
| `install` | Instala ou completa a estrutura `.orchestrator/` (padrão) |
| `update` | Atualiza a estrutura `.orchestrator/` do projeto atual (recomendado) |
| `global-tools` | Instala MCPs/plugins/skills/CLIs no perfil do usuário |
| `route` | Resolve `task_class` → modelo (JSON/texto) sem herdar o chat atual |
| `dispatch` | Despacha prompt ao CLI (claude/codex) com o modelo roteado |
| `verify` | Preflight + validação; não altera arquivos gerenciados |
| `upgrade` | Alias de `update` (compatibilidade) |
| `repair` | Restaura arquivos gerenciados ausentes ou corrompidos |
| `uninstall` | Remove arquivos gerenciados; faz backup prévio |
| `status` | Exibe versões, agentes detectados e ferramentas |
| `analyze` | Detect + validate (diagnóstico) |
| `skills` | Lista skills registradas do workspace |

Exemplos:

```bash
# Na pasta do projeto — atualiza estrutura canônica
orchestrator update
```

```bat
orchestrator-ia.bat update -ProjectPath C:\meu-projeto
orchestrator-ia.bat verify -ProjectPath C:\meu-projeto
orchestrator-ia.bat status
```

O `update`:

1. sincroniza o pacote (git pull, quando aplicável);
2. aplica template/manifest (aditivo; `-Force` sobrescreve managed);
3. redetecta agentes e regenera adaptadores ausentes;
4. valida e grava relatório.

### Comparação de versões

| Situação | Comportamento |
|---|---|
| Sem `.orchestrator/VERSION` | `install` cria estrutura |
| Workspace == pacote | `upgrade` informa que não há atualização |
| Workspace < pacote | `upgrade` aplica template + manifest |
| Workspace > pacote | **Recusado** (exit code 6) |

---

## Opções principais

Parâmetros PowerShell aceitos via BAT (encaminhamento direto):

| Opção | Efeito |
|---|---|
| `-ProjectPath` / `-Project` | Caminho do projeto-alvo |
| `-DryRun` | Simula etapas sem alterar disco |
| `-UpdateAgents` | (compat) Força etapa de update de CLIs — **já é o padrão em 0.4.17+** |
| `-SkipAgentUpdates` / `--skip-agent-updates` | Pula atualização dos CLIs de agentes existentes |
| `-SkipTools` | Pula detecção/registro de OpenWolf e Graphify |
| `-RefreshTools` | Consulta/atualiza versões publicadas (avisos se falhar) |
| `-ConfigureMcps` | Atualiza `.orchestrator/mcp/registry.json` (Context7 desabilitado) |
| `-RunSmokeTest` | Executa probes de agentes (`--help`, somente leitura) |
| `-SkipAgentProbes` | Pula probes (padrão no install sem smoke test) |
| Limpeza de legado | **Padrão `safe`** em install/update — ver [`docs/legacy-cleanup.md`](docs/legacy-cleanup.md) |
| `-Force` | Sobrescreve arquivos gerenciados / força migração e reparo |
| `-InstallMissingAgents` | **Reservado** — não implementado |
| `-RunProjectTests` | **Reservado** — runner genérico não incluído |
| `-NonInteractive` | Reservado para fluxos automatizados |
| `-PackageRoot` | Raiz do pacote orchestrator-ia (padrão: pai de `scripts/`) |

Exemplo completo:

```bat
orchestrator-ia.bat install -ProjectPath C:\meu-projeto -ConfigureMcps -UpdateAgents -RunSmokeTest
```

Simulação:

```bat
orchestrator-ia.bat install -ProjectPath C:\meu-projeto -DryRun
```

---

## Detecção de agentes e atualização de CLIs

1. **Detect-Agents** — varre PATH, grava `detected.json` e atualiza `registry.json`.
2. **Update-Agents** (padrão em install/update desde 0.4.17) — atualiza CLIs já instalados (`claude`/`codex`/`kimi`/npm/choco/scoop); falhas viram avisos. Opt-out: `-SkipAgentUpdates`.
3. **Detect-Agents** de novo — refresca versões após o update.
4. **Generate-Adapters** — copia adaptadores finos só para agentes `available` (já com as versões atualizadas).
5. **Probe-Agents** — por padrão **ignorado** no install; use `-RunSmokeTest` para probes somente leitura.

Relatório final: `.orchestrator/runtime/reports/installation-report.md`

---

## Adaptadores

Gerados a partir de `package/template/adapters/` para vendors detectados:

| Vendor | Conteúdo típico |
|---|---|
| `claude` | `.claude/README.md`, `CLAUDE.md` |
| `codex` | `.codex/README.md`, `AGENTS.md` |
| `cursor` | `.cursor/rules/orchestrator.mdc`, `CURSOR.md` |
| `gemini` | `.gemini/README.md`, `GEMINI.md` |
| `kimi` | `.kimi/README.md`, `KIMI.md` |
| `opencode` | `.opencode/README.md`, `AGENTS.md` |

Adaptadores existentes **não são sobrescritos** sem `-Force`.

---

## Memória (`.orchestrator/memory/`)

Conhecimento durável do projeto — **nunca** a memória global do fornecedor como fonte da verdade.

```text
.orchestrator/memory/
├── index.json
├── architecture/
├── decisions/
├── episodes/
├── failures/
├── lessons/
├── project/
├── strategies/
├── tasks/
└── archive/
```

Use a skill `save-knowledge` e scripts sob `.orchestrator/scripts/memory/` para persistir aprendizado entre tarefas.

---

## Skills

Skills de orquestração registradas em `.orchestrator/skills/registry.json`:

- `orchestrate`, `analyze-project`, `analyze-task`, `plan-task`
- `select-agents`, `call-agent`, `run-tests`, `validate-result`
- `correction-loop`, `save-knowledge`

Listar no workspace:

```bat
orchestrator-ia.bat skills -ProjectPath C:\meu-projeto
```

Skills externas: `.orchestrator/skills/external/` · Quarentena: `quarantined/`

### Pacotes de skills (0.4.68+)

Coleções externas entram por um instalador com **mapa curado** — nunca por URL
livre, mesma regra do mapa de agentes:

```bash
orchestrator skills list
orchestrator skills install marketing --project D:\StarFusion\vavi
```

Instala em `.orchestrator/skills/<pacote>/` com um `SKILLPACK.json` de
procedência (origem, licença, data, contagem). O `skill_selector` passa a
considerá-las na task seguinte, sem código novo.

| Pacote | Conteúdo | Licença |
|---|---|---|
| `marketing` | 49 skills: CRO, copy, SEO, ads, pricing, lançamento, RevOps | MIT (Corey Haines) |

**Instale por projeto, não na frota.** O seletor recebe a lista inteira de
skills a cada task; 49 descrições extras encarecem também as tasks de código.
Um pacote de marketing num backend é só custo.

### Perfis de invocação por CLI

Cada agente tem um perfil declarativo em `.orchestrator/agents/profiles/<cli>.json` (mecânica de invocação: subcomando não-interativo, flag de prompt, saída, timeout). **CLI novo = JSON novo, zero código** — o dispatch e a skill `call-agent` leem o perfil. Schema: `package/schemas/agent-profile.schema.json`. Agentes classe IDE (cursor, kiro) são detectados por presença no PATH, sem sonda de execução.

---

## MCPs

Registro em `.orchestrator/mcp/registry.json`. Com `-ConfigureMcps`, o instalador adiciona **Context7** como recomendado e **desabilitado por padrão** (transporte stdio via `npx`).

Configs, auditorias e servidores desabilitados ficam em subpastas de `mcp/`. Ative MCPs explicitamente no registro — nunca durante install sem opt-in.

---

## Plugins opcionais (OpenWolf, Graphify)

No `init` / `install` / `update`, o instalador **detecta e inicializa** as tools se estiverem no PATH:

| Tool | Detecção | Inicialização no projeto |
|---|---|---|
| OpenWolf | `openwolf` | `openwolf init` → cria `.wolf/` |
| Graphify | `graphify` | `graphify install --project` |

Status gravado em:

```text
.orchestrator/tools/registry.json
.orchestrator/tools/openwolf/status.json
.orchestrator/tools/graphify/status.json
```

Flags:

| Flag | Efeito |
|---|---|
| `-InitTools` | Força inicialização |
| `-SkipToolInit` | Só detecta (não roda init) |
| `-SkipTools` | Ignora tools por completo |
| `-RefreshTools` | Consulta/atualiza pacotes (npm/uv) |

Ausência ou falha de init **nunca bloqueia** o bootstrap. Instale globalmente antes, se precisar:

```bash
npm install -g openwolf
uv tool install graphifyy
# ou: npm i -g @sentropic/graphify
```

---

## Princípios de segurança

- Sem escrita paralela no mesmo workspace (`allow_parallel_workspace_writes: false`)
- Paralelismo permitido só em análise somente leitura
- Timeout em comandos externos; logs em `.orchestrator/runtime/validations/`
- **Sem tokens ou segredos** no repositório
- Hooks opcionais; falha de hook não deve bloquear agentes
- Lock de instalação: `.orchestrator/runtime/install.lock`
- Integridade do pacote verificada via `package/manifest.json` e `checksums.json`
- Anti-recursão via variáveis de ambiente (`ORCHESTRATOR_CHILD_AGENT`, etc.)

Políticas padrão em `.orchestrator/config/policies.json` (score mínimo 0.9, máximo 3 iterações, validação independente obrigatória).

---

## Solução de problemas (básico)

| Sintoma | Ação |
|---|---|
| `npx` / clone falha (repo privado) | `gh auth login` e credential helper do Git |
| `gh api ... \| iex` 404 / credenciais | `gh auth status` e escopo `repo` |
| `orchestrator` não encontrado | Confirme `npm bin -g` no PATH |
| Cache PowerShell corrompido | Apague `%LOCALAPPDATA%\StarFusion\multiagent-orchestrator` |
| `git nao encontrado` | Instale Git e adicione ao PATH |
| `Lock de instalacao ja existe` | Remova `.orchestrator/runtime/install.lock` se nenhum install estiver ativo |
| `Workspace mais novo que o pacote` | Atualize o pacote orchestrator-ia ou use versão compatível |
| Arquivos gerenciados ausentes | `orchestrator repair` ou `orchestrator-ia.bat repair` |
| Validação falhou | `orchestrator verify` e leia logs em `runtime/validations/` |
| Agentes não detectados | Confirme CLI no PATH; rode `orchestrator status` |

Guia completo: [`docs/troubleshooting.md`](docs/troubleshooting.md)

---

## Arquitetura resumida

```text
npx / orchestrator / mao      → CLI Node (bin/orchestrator.js)
get.ps1                       → one-liner PowerShell + cache local
orchestrator-ia.bat          → wrapper fino (%* → PowerShell)
        └─► scripts/Install-Orchestrator.ps1   → roteador (init|install|…)
            scripts/Orchestrator.Common.ps1    → helpers
package/
├── manifest.json             → arquivos gerenciados (managed/merge/generated)
├── checksums.json            → integridade
├── template/.orchestrator/   → árvore canônica
├── template/adapters/        → adaptadores por vendor
└── migrations/               → scripts <from>-to-<to>.ps1
```

- Funcionamento completo: [`docs/orquestrador.md`](docs/orquestrador.md)
- Arquitetura: [`docs/installer-architecture.md`](docs/installer-architecture.md)
- CLI: [`docs/cli-reference.md`](docs/cli-reference.md)
- One-liner: [`docs/quickstart-oneliner.md`](docs/quickstart-oneliner.md)

---

## Honestidade do resultado

O modo de falha mais documentado de agente de código é **declarar sucesso
independente do que aconteceu**. Esta frota já viveu isso: uma task fechou
`COMPLETED score=1.0` com os **dois** validators mortos. O runtime aceita
degradar — e é certo que aceite —, mas o resultado tem que dizer.

Toda degradação aceita aparece em `orchestrator task status` e no
`orchestrator_result`, num registro único:

```json
"degradations": [
  {"kind": "validation_not_independent", "impact": "o score não reflete revisão de mérito", "action": "reexecute com um validator vivo"},
  {"kind": "agent_auth_required",        "impact": "codex não pôde trabalhar",              "action": "codex login"},
  {"kind": "plan_not_refined",           "impact": "rodou com o plano determinístico",      "action": "reexecute se o plano importava"}
]
```

Os campos antigos (`independent_validation`, `agent_auth_required`,
`plan_refined`) continuam saindo — cliente que já os consome não quebra.

Cada degradação carrega o **remédio certo para a causa**, não um genérico: a
mesma `validation_not_independent` pede "reexecute com um validator vivo" quando
um agente falhou, e "aumente `maximum_duration_seconds`" quando faltou relógio.
Mandar caçar um defeito que não existe custa a mesma hora que não mandar nada.

Pela mesma razão, falha de agente tem **quatro** categorias e não uma — os
remédios são opostos:

| Categoria | O que quebrou | Remédio |
|---|---|---|
| `install` | CLI ausente ou corrompido | reinstala sozinho, uma vez por processo |
| `auth` | CLI vivo, sem credencial | só o dono resolve — reinstalar apagaria a sessão |
| `service` | servidor do provedor | nada a digitar: esperar ou trocar de agente |
| `launch` | o processo não nasceu | liberar recurso da máquina; não é o CLI |

As duas últimas existem porque `install` era o destino de tudo que o
classificador não reconhecia — e era a categoria com o remédio mais caro. Erro de
servidor reinstalava um CLI intacto (300 s por ocorrência, para falhar igual em
seguida); e falta de recurso da máquina disparava uma reinstalação que **também
não conseguia nascer**. Quando o remédio custa cinco minutos, "não foi o CLI"
precisa ser uma resposta possível.

### Dá para acompanhar o que está rodando (0.4.73+)

Task longa parada no mesmo estado é indistinguível de task morta — e essa dúvida
já custou trabalho cancelado por impaciência nesta frota. Duas coisas causavam
isso: `updated_at` só muda em **transição de estado** (um executor legítimo passa
25 min em `EXECUTING` sem tocá-lo), e o sinal de vida só existia **enquanto um
CLI estava no ar**. Nos vãos — escolha de agentes, consolidação, gravação de
memória, gate de documentação, troca de etapa — o runtime ficava mudo.

Agora o **loop** bate a cada 20–30 s durante toda a execução, e o `status`
responde "travou?" sem exigir leitura de log:

```json
"live": {"signal": "loop_progress", "signal_age_s": 8, "phase": "EXECUTING",
         "phase_elapsed_s": 412, "agent_active": true, "agent": "codex",
         "pid": 50764, "pid_alive": true}
```

`agent_active` distingue "esperando o codex" de "entre etapas"; `phase_elapsed_s`
é a idade **da fase**, não da task; `pid_alive` é a resposta direta. No console,
cada batida sai como `[loop_progress] <fase> há Ns — <quem está no ar>`.

O reaper **ignora** essa batida de propósito: ela nasce de uma thread do processo
dono e continuaria batendo com o loop travado num lock. Ela prova que o processo
vive, não que o trabalho anda — a decisão de cancelar segue apoiada em progresso
de verdade.

### Nenhum score é inventado (0.4.71+)

O executor pode encerrar uma tarefa declarando que a **premissa está incorreta**
— o arquivo não existe, o bug já foi corrigido, o campo já está lá. É um
resultado legítimo: não há o que entregar. Mas é o executor julgando o próprio
trabalho, então três regras valem:

- o score fica **nulo**, nunca `1.0`. Ninguém validou nada, e um número
  inventado contamina relatório, learnings e métricas de estratégia;
- a alegação **não apaga** uma rejeição já gravada. Depois de um veredito
  negativo em disco, a task encerra `INCOMPLETE` com os dois fatos;
- o resultado sempre traz `premise_declared_unverified`, dizendo que nada foi
  entregue e que ninguém julgou a alegação.

### O teto da task cabe o trabalho (0.4.70+)

`maximum_duration_seconds` tem **piso derivado** dos tetos por papel: ele nunca
fica abaixo do percurso `planejar → executar → testar → julgar → corrigir →
julgar` (8700 s nos padrões). Antes os dois números se contradiziam — teto 3600
contra papéis que somam 8700 — e toda task que realmente usava o orçamento
morria antes do validator, que é o último a ser chamado. Só as tarefas grandes
falhavam, e a mensagem parecia mérito.

Teto é limite de **paciência**, não de qualidade: subi-lo não faz task nenhuma
demorar mais, só para de matar as que ainda estavam trabalhando. `executor` e
`corrector` também devolvem 600 s do restante para que o veredito sempre caiba.

### Integridade de teste (0.4.68+)

O executor escreve o código **e** os testes, e o gate só verifica se a suíte
fica verde — nada impedia baixar uma asserção para passar. O runtime lê o
**diff de verdade** dos arquivos de teste e sinaliza três padrões mecânicos:
asserções removidas, testes desligados por `skip`/`Ignore`, casos apagados.

O achado é **não-bloqueante** de propósito: refator legítimo também remove
asserção. Ele obriga o validador a justificar — *um teste alterado é culpado
até a justificativa remontar à spec* — e vira `blocking` só se o juiz
confirmar. O validador também é instruído a tratar o relato do executor como
hipótese falsificável, reexecutar o que puder e marcar `UNVERIFIABLE` em vez de
aceitar por omissão.

> Heurística reimplementada a partir do
> [fable-method](https://github.com/Sahir619/fable-method) (MIT). Nenhum texto
> ou prompt foi copiado.

---

## Migração legada `.claude/`

Se existir `.claude/VERSION` sem `.orchestrator/VERSION`, o `install` executa `Migrate-LegacyClaude.ps1` (importa memória/regras para `legacy-import/`). Veja [`docs/legacy-migration.md`](docs/legacy-migration.md).

### Importação de configuração existente (0.4.23+)

Antes de instalar o template, o orquestrador **copia** rules/skills/adapters já presentes no repo para `.orchestrator/**/legacy-import/` (aditivo; não apaga a origem):

```bash
# Repo com .cursor/rules/meu-projeto.mdc e .claude/skills/foo/SKILL.md
cd /caminho/do/projeto
orchestrator install

# Resultado (origens intactas):
# .orchestrator/rules/legacy-import/cursor/meu-projeto.mdc
# .orchestrator/skills/legacy-import/claude/foo/SKILL.md
# .orchestrator/memory/legacy-import/adapters/CLAUDE.md   # se CLAUDE.md existir na raiz
```

Detalhes e exclusões de rules geradas: [`docs/legacy-cleanup.md`](docs/legacy-cleanup.md).

O prompt antigo está arquivado em [`docs/archive/prompts/`](docs/archive/prompts/) — **não use** para instalação.

---

## Roadmap

Fora do escopo da v0.1, evolução planejada:

1. **Docker** — workers isolados por agente
2. **API** — REST / SSE / WebSocket para orquestração remota
3. **ACP** — integração com IDEs e protocolos de agente

Prioridade atual (v0.1): detecção de CLIs, bootstrap incremental versionado, skills, memória local, validação e relatórios.

---

## Conteúdo deste repositório

| Artefato | Função |
|---|---|
| `VERSION` | Versão do Orquestrador IA Multiagente |
| `package.json` | Pacote npm `@starfusion/orchestrator` (bins `orchestrator`, `mao`) |
| `bin/orchestrator.js` | CLI Node — one-liner / global |
| `get.ps1` | One-liner PowerShell (cache + install no cwd) |
| `orchestrator-ia.bat` | Wrapper fino Windows → PowerShell (**em uso**) |
| `install.ps1` | Atalho PowerShell local (**em uso**) |
| `scripts/` | Implementação PowerShell do instalador |
| `package/` | Template, manifest, checksums, migrações |
| `tests/` | Suíte de testes em fixtures temporárias |
| `docs/` | Documentação do produto |
| `docs/orquestrador.md` | Guia completo de funcionamento |
| `docs/legacy/` | Prompt e material deprecados |
| `docs/repo-layout.md` | Organização deste repositório |
| `LICENSE` | MIT (uso comercial e não comercial) |

**Repositório:** https://github.com/henrique-starfusion/orchestrator-ia (release: tag `latest` / `main`)

Layout detalhado: [`docs/repo-layout.md`](docs/repo-layout.md)

---

## Atribuição

**Orquestrador IA Multiagente** — desenvolvido e mantido pela **StarFusion**  
Desenvolvedor: **Henrique Rodrigues**  

**Copyright © 2026 StarFusion Consultoria, Tecnologia e Soluções em Informática LTDA.**  
Licença [MIT](LICENSE) — livre para uso, modificação e distribuição (comercial e não comercial).
