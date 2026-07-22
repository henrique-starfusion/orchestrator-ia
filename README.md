# Bootstrap Agents — Orquestrador Multiagente

Projeto desenvolvido e mantido pela **StarFusion**.

- **Desenvolvedor:** Henrique Rodrigues
- **Copyright © 2026 StarFusion Consultoria, Tecnologia e Soluções em Informática LTDA.** Todos os direitos reservados.

Pacote portátil para instalar, validar e manter um **ambiente multiagente genérico** e um **runtime persistente** em qualquer repositório. O orquestrador não pertence a uma aplicação específica: projetos-alvo são workspaces de execução.

**Versão atual:** 0.4.3 — ver [`CHANGELOG.md`](CHANGELOG.md).

---

## O que é o orquestrador multiagente

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

Documentação: [`docs/mcp-integration.md`](docs/mcp-integration.md) · [`docs/orquestrador.md`](docs/orquestrador.md)

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
npx --yes github:henrique-starfusion/bootstrap-agents#develop init
```

Ou instalar o CLI global e reutilizar em vários projetos:

```bash
npm install -g github:henrique-starfusion/bootstrap-agents#develop
cd C:\caminho\do\seu\projeto
orchestrator init
```

Equivalente curto: `mao init` (alias do mesmo binário).

### PowerShell (Windows, com `gh` autenticado)

```powershell
gh api -H "Accept: application/vnd.github.raw" "repos/henrique-starfusion/bootstrap-agents/contents/get.ps1?ref=develop" | iex
```

Isso baixa o pacote para `%LOCALAPPDATA%\StarFusion\multiagent-orchestrator` (cache) e instala `.orchestrator/` no diretório atual.

### Atualização

Há **dois níveis**: atualizar o CLI (pacote npm) e atualizar a estrutura `.orchestrator/` do projeto.

#### 1) Atualizar o CLI via npm (global)

```bash
npm install -g github:henrique-starfusion/bootstrap-agents#develop
```

Sem instalar global — sempre a tip da branch `develop`:

```bash
npx --yes github:henrique-starfusion/bootstrap-agents#develop update
```

#### 2) Atualizar a estrutura do projeto

Com o CLI já no PATH, na pasta do projeto:

```bash
orchestrator update
```

Equivalente: `mao update`. Alias legado: `orchestrator upgrade`.

Via clone local:

```bat
bootstrap-agents.bat update -ProjectPath C:\caminho\do\projeto
```

Fluxo típico (CLI global + projeto):

```bash
npm install -g github:henrique-starfusion/bootstrap-agents#develop
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
bootstrap-agents.bat init
bootstrap-agents.bat install -ProjectPath C:\caminho\do\projeto
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
bootstrap-agents.bat update -ProjectPath C:\meu-projeto
bootstrap-agents.bat verify -ProjectPath C:\meu-projeto
bootstrap-agents.bat status
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
| `-UpdateAgents` | Tenta `claude update`, `codex update`; com `-Force`, npm global |
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
| `-PackageRoot` | Raiz do pacote bootstrap (padrão: pai de `scripts/`) |

Exemplo completo:

```bat
bootstrap-agents.bat install -ProjectPath C:\meu-projeto -ConfigureMcps -UpdateAgents -RunSmokeTest
```

Simulação:

```bat
bootstrap-agents.bat install -ProjectPath C:\meu-projeto -DryRun
```

---

## Detecção de agentes e atualizações opcionais

1. **Detect-Agents** — varre PATH, grava `detected.json` e atualiza `registry.json`.
2. **Generate-Adapters** — copia adaptadores finos só para agentes `available`.
3. **Update-Agents** (opcional, `-UpdateAgents`) — atualiza CLIs conhecidos; falhas viram avisos.
4. **Probe-Agents** — por padrão **ignorado** no install; use `-RunSmokeTest` para probes somente leitura.

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
bootstrap-agents.bat skills -ProjectPath C:\meu-projeto
```

Skills externas: `.orchestrator/skills/external/` · Quarentena: `quarantined/`

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
| `Workspace mais novo que o pacote` | Atualize o pacote bootstrap ou use versão compatível |
| Arquivos gerenciados ausentes | `orchestrator repair` ou `bootstrap-agents.bat repair` |
| Validação falhou | `orchestrator verify` e leia logs em `runtime/validations/` |
| Agentes não detectados | Confirme CLI no PATH; rode `orchestrator status` |

Guia completo: [`docs/troubleshooting.md`](docs/troubleshooting.md)

---

## Arquitetura resumida

```text
npx / orchestrator / mao      → CLI Node (bin/orchestrator.js)
get.ps1                       → one-liner PowerShell + cache local
bootstrap-agents.bat          → wrapper fino (%* → PowerShell)
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

## Migração legada `.claude/`

Se existir `.claude/VERSION` sem `.orchestrator/VERSION`, o `install` executa `Migrate-LegacyClaude.ps1` (importa memória/regras para `legacy-import/`). Veja [`docs/legacy-migration.md`](docs/legacy-migration.md).

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
| `VERSION` | Versão do pacote bootstrap |
| `package.json` | Pacote npm `@starfusion/orchestrator` (bins `orchestrator`, `mao`) |
| `bin/orchestrator.js` | CLI Node — one-liner / global |
| `get.ps1` | One-liner PowerShell (cache + install no cwd) |
| `bootstrap-agents.bat` | Wrapper fino Windows → PowerShell (**em uso**) |
| `install.ps1` | Atalho PowerShell local (**em uso**) |
| `scripts/` | Implementação PowerShell do instalador |
| `package/` | Template, manifest, checksums, migrações |
| `tests/` | Suíte de testes em fixtures temporárias |
| `docs/` | Documentação do produto |
| `docs/orquestrador.md` | Guia completo de funcionamento |
| `docs/legacy/` | Prompt e material deprecados |
| `docs/repo-layout.md` | Organização deste repositório |
| `LICENSE` | Todos os direitos reservados (StarFusion) |

**Repositório:** https://github.com/henrique-starfusion/bootstrap-agents (branch `develop`)

Layout detalhado: [`docs/repo-layout.md`](docs/repo-layout.md)

---

## Atribuição

Projeto desenvolvido e mantido pela **StarFusion**  
Desenvolvedor: **Henrique Rodrigues**  

**Copyright © 2026 StarFusion Consultoria, Tecnologia e Soluções em Informática LTDA.** Todos os direitos reservados.
