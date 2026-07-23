# Referência da CLI — Orquestrador IA Multiagente

Três formas de entrada:

1. **npm:** `npx @starfusion/orchestrator` / `orchestrator` / `mao`
2. **PowerShell:** `get.ps1`
3. **Wrapper local:** `orchestrator-ia.bat`

A partir de **0.2.0**, a CLI tem duas camadas:

| Camada | Comandos | Backend |
|---|---|---|
| Installer | `install`, `update`, `verify`, `repair`, `uninstall`, `status`, `route`, `dispatch`, `global-tools` | PowerShell |
| Runtime | `run`, `task *` | Python (`orchestrator_runtime`) |
| MCP / Cursor | `mcp serve\|status\|doctor`, `cursor configure\|verify\|print-config` | Python |

---

## MCP / Cursor

```bash
orchestrator mcp serve --transport stdio
orchestrator mcp serve --transport http --host 127.0.0.1 --port 8765
orchestrator mcp doctor
orchestrator cursor configure
orchestrator cursor verify
orchestrator cursor print-config
```

Installer: Cursor MCP do **projeto** roda por padrão em `init`/`install`/`update` (`--cursor-mcp-scope project`). Use `--cursor-mcp-scope user|both` para também gravar `~/.cursor/mcp.json`.

```bash
orchestrator init
orchestrator update --skip-cursor              # nao tocar no MCP do Cursor
orchestrator update --cursor-mcp-scope user    # so global
```

---

## Runtime

```bash
orchestrator run --prompt "Crie modulo soma com testes e docs"
orchestrator task create --prompt "..."
orchestrator task run <id>
orchestrator task status <id>
orchestrator task list
orchestrator task cancel <id>
orchestrator task resume <id>
orchestrator task logs <id>
orchestrator task artifacts <id>
```

Opções comuns: `--project`, `--profile`, `--max-iterations`, `--timeout`, `--planner`, `--executor`, `--validator`, `--manager-provider`, `--fake-agents` (CI), `--json`, `--dry-run`.

Requer Python 3.11+.

---

## One-liner (projeto atual)

```bash
npx --yes github:henrique-starfusion/orchestrator-ia#latest init
```

```powershell
gh api -H "Accept: application/vnd.github.raw" "repos/henrique-starfusion/orchestrator-ia/contents/get.ps1?ref=latest" | iex
```

```bash
orchestrator init
mao init
```

---

## Invocação local

```bat
orchestrator-ia.bat <comando> [opções]
```

```powershell
.\get.ps1 <comando> [opções]
.\scripts\Install-Orchestrator.ps1 <comando> [opções]
```

### Projeto-alvo

| Parâmetro | Alias | Descrição |
|---|---|---|
| `-ProjectPath <caminho>` | `-Project` | Raiz do repositório alvo. Padrão: diretório atual |

Exemplos:

```bash
orchestrator init
orchestrator verify --project C:\dev\meu-app
```

```bat
orchestrator-ia.bat install -ProjectPath C:\dev\meu-app
orchestrator-ia.bat verify -Project C:\dev\meu-app
```

```powershell
.\get.ps1 init -ProjectPath C:\dev\meu-app
```

---

## Comandos

### `global-tools`

Instala/configura no **perfil do usuário** (Claude, Cursor, `~/.agents`, npm global): Context7, Playwright, Superpowers, etc. Veja [`global-tools.md`](global-tools.md).

```bash
orchestrator global-tools
orchestrator init --skip-global-tools
```

### `update`

Atualiza a estrutura `.orchestrator/` do projeto atual (comando principal de manutenção).

Antes, atualize o CLI se estiver instalado via npm global:

```bash
npm install -g github:henrique-starfusion/orchestrator-ia#latest
```

Ou rode o update direto com npx (baixa a tip de `develop`):

```bash
npx --yes github:henrique-starfusion/orchestrator-ia#latest update
```

Com o CLI no PATH:

```bash
orchestrator update
orchestrator update --force
```

```bat
orchestrator-ia.bat update -ProjectPath C:\dev\meu-app
```

```powershell
.\get.ps1 update
```

Fluxo:

1. Preflight
2. Sync do pacote via git (quando `PackageRoot` for clone)
3. `Update-Orchestrator.ps1` — migrations (se houver) + template + manifest
4. Detect-Agents + Generate-Adapters
5. Install-Tools (salvo `-SkipTools`)
6. Install-GlobalTools (salvo `-SkipGlobalTools`) — MCPs/plugins/skills no perfil do usuário
6. Validate + relatório (`Mode=update`)

Versões iguais: sincroniza **somente o que falta** (aditivo).  
Pacote mais novo: backup + upgrade de VERSION.  
`-Force`: reaplica arquivos managed.

`upgrade` é alias de `update`.

---

### `init` / `install`

`init` é alias de `install` (padrão OpenWolf/Graphify).

Instala ou completa o ambiente `.orchestrator/` no projeto-alvo.

```bat
orchestrator-ia.bat install -ProjectPath C:\dev\meu-app
```

**Etapas:** preflight → lock → migração legada (se aplicável) → template → manifest → detect agents → adaptadores → tools → MCPs (opt-in) → validação → updates (opt-in) → probes → relatório.

**Padrão:** probes de agentes **desabilitados** (registro skip). Use `-RunSmokeTest` para ativar.

---

### `verify`

Validação somente leitura — não altera arquivos gerenciados.

```bat
orchestrator-ia.bat verify -ProjectPath C:\dev\meu-app
```

Executa: preflight → Validate-Orchestrator → Validate-Hooks.

Útil em CI ou após clone do repositório.

---

### `upgrade`

Atualiza workspace quando a versão do pacote é **maior** que `.orchestrator/VERSION`.

```bat
orchestrator-ia.bat upgrade -ProjectPath C:\dev\meu-app
orchestrator-ia.bat upgrade -ProjectPath C:\dev\meu-app -Force
orchestrator-ia.bat upgrade -DryRun
```

| Situação | Resultado |
|---|---|
| Versões iguais | Informa e sai 0 (salvo `-Force`) |
| Pacote > workspace | Backup + Copy-TemplateTree + Apply-Manifest + sync VERSION |
| Workspace > pacote | Exit 6 |
| Comparação inválida | Exit 1 (use `-Force` para continuar) |

---

### `repair`

Restaura arquivos gerenciados ausentes ou inconsistentes.

```bat
orchestrator-ia.bat repair -ProjectPath C:\dev\meu-app
orchestrator-ia.bat repair -DryRun
```

Força re-aplicação do manifest com `-Force` interno.

---

### `uninstall`

Remove arquivos listados no manifest (exceto `user-owned`). Sempre cria backup em `.orchestrator/backups/` antes de remover.

```bat
orchestrator-ia.bat uninstall -ProjectPath C:\dev\meu-app
orchestrator-ia.bat uninstall -Force
```

| Flag | Efeito |
|---|---|
| `-Force` | Remove diretório `.orchestrator/` inteiro após processar manifest |
| `-DryRun` | Lista o que seria removido |

Adaptadores na raiz do projeto (`.claude/`, `CLAUDE.md`, etc.) **não** são removidos automaticamente.

---

### `status`

Resumo do workspace:

```bat
orchestrator-ia.bat status -ProjectPath C:\dev\meu-app
```

Exibe:

- Caminho do projeto
- Versão do pacote e do workspace
- Agentes `available` (de `detected.json`)
- Contagem de tools (de `tools/registry.json`)

---

### `analyze`

Diagnóstico combinado:

```bat
orchestrator-ia.bat analyze -ProjectPath C:\dev\meu-app
```

Executa Detect-Environment, Detect-Agents e Validate-Orchestrator.

---

### `skills`

Lista IDs registrados em `.orchestrator/skills/registry.json`:

```bat
orchestrator-ia.bat skills -ProjectPath C:\dev\meu-app
```

Exit 1 se o registro estiver ausente.

### `route` / `dispatch`

Resolvem `task_class` → modelo e despacham prompt ao CLI do agente:

```bash
orchestrator route --task-class docs --client claude --json
orchestrator dispatch --task-class docs --client claude --prompt "Atualize o README"
```

O despacho monta a linha de comando a partir do perfil declarativo `.orchestrator/agents/profiles/<client>.json` (subcomando não-interativo, flag de prompt, timeout); sem o perfil, o comando falha instruindo `orchestrator update`. `--dry-run` imprime a linha planejada sem executar — funciona mesmo com o CLI ausente do PATH. Perfis `verified: false` geram `[AVISO]`. Cliente `cursor` é `ide-client`: não executa CLI; orienta uso de `orchestrator run` / MCP (`dispatch --client cursor` está deprecado).

A execução é sempre acompanhada: a saída do agente filho é transmitida ao vivo no console (`  > ` stdout, `  ! ` stderr), com heartbeat `[INFO]` a cada 30s. Ao atingir o timeout o processo é finalizado e a saída parcial é preservada. No `orchestrator dispatch`, o timeout vem de `timeout_default_s` do profile (template: 2400s para CLIs de escrita). No `orchestrator run` / MCP, o runtime aplica `policies.agent_timeout_by_role` capped pelo tempo restante de `maximum_duration_seconds` — **não** use só `maximum_duration_seconds` esperando alongar cada agente. Além de `result.txt` e `model-choice.json`, todo despacho grava `runtime/results/<stamp>-<task_class>-status.json` com `status` (`completed|failed|timeout`), `exit_code` e `duration_s` — registro durável para outras sessões verificarem falha. Falha imprime `[ERRO]` e retorna exit code ≠ 0; nunca rode dispatch em segundo plano sem acompanhar até o fim.

---

## Opções globais (install)

| Parâmetro | Tipo | Descrição |
|---|---|---|
| `-DryRun` | switch | Simula; não grava lock nem copia arquivos |
| `-Force` | switch | Sobrescreve managed/generated; força migração legada |
| `-NonInteractive` | switch | Reservado para automação |
| `-PackageRoot` | string | Raiz do pacote orchestrator-ia (padrão: pai de `scripts/`) |

### Agentes

| Parâmetro | Descrição |
|---|---|
| `-UpdateAgents` | Executa `Update-Agents.ps1` após validação |
| `-InstallMissingAgents` | **Não implementado** — aparece como limitação no relatório |
| `-SkipAgentProbes` | Força skip de probes (padrão implícito sem smoke test) |
| `-RunSmokeTest` | Ativa probes somente leitura (`--help`) |

### Ferramentas

| Parâmetro | Descrição |
|---|---|
| `-SkipTools` | Pula `Install-Tools.ps1` |
| `-RefreshTools` | Tenta consultar/atualizar OpenWolf (npm) e Graphify (uv) |
| `-InitTools` | Força `openwolf init` + `graphify install --project` |
| `-SkipToolInit` | Detecta tools sem inicializar no projeto |

### MCP

| Parâmetro | Descrição |
|---|---|
| `-ConfigureMcps` | Registra Context7 desabilitado em `mcp/registry.json` |

### Legado / testes

| Parâmetro | Descrição |
|---|---|
| `-SkipLegacyCleanup` | Pula limpeza de legado (padrão: limpeza `safe` ativa) |
| `-LegacyCleanupMode` | `safe` \| `aggressive` \| `report-only` |
| `-KeepLegacyBackup` | Mantém backup de legado (sempre criado sob `.orchestrator/backups/`) |
| `legacy scan\|cleanup\|status\|restore` | Comandos dedicados de legado |
| `-RunProjectTests` | **Não implementado** — limitação registrada no relatório |

---

## Comportamento de `-UpdateAgents`

Quando `-UpdateAgents` está presente:

1. Para agentes `available`:
   - `codex` → tenta `codex update`
   - `claude` → tenta `claude update`
2. Com **`-Force`** adicional e instalação via npm:
   - `npm install -g <pacote>` conforme `Get-AgentNpmPackageMap`

Falhas são **avisos** — não abortam o install.

Pacotes npm mapeados: `@anthropic-ai/claude-code`, `@openai/codex`, `@google/gemini-cli`, `opencode-ai`, `@qwen-code/qwen-code`, `@github/copilot`, `aider`, `@continuedev/cli`.

---

## Comportamento de `-ConfigureMcps`

Adiciona ou atualiza entrada **Context7** em `.orchestrator/mcp/registry.json`:

- `enabled: false` por padrão
- `command: npx`, `args: ["-y", "@upstash/context7-mcp"]`
- `recommended: true`

Use `-Force` para sobrescrever entrada existente.

---

## Comportamento de probes

| Cenário | Probes |
|---|---|
| `install` (padrão) | Skip (`SkipAgentProbes`) |
| `install -RunSmokeTest` | Executa `--help` por agente available (timeout 30s) |
| `install -SkipAgentProbes` | Skip explícito |

Resultado em `.orchestrator/agents/probe-results.json`.

---

## Exit codes

| Código | Quando |
|---|---|
| 0 | Sucesso |
| 1 | Erro de execução, preflight, validação ou comparação inválida (upgrade) |
| 2 | Comando inválido |
| 6 | `.orchestrator/VERSION` > `VERSION` do pacote |

---

## Exemplos práticos

### Primeira instalação mínima

```bat
orchestrator-ia.bat install -ProjectPath C:\dev\novo-projeto
```

### Instalação completa com opt-ins

```bat
orchestrator-ia.bat install ^
  -ProjectPath C:\dev\novo-projeto ^
  -ConfigureMcps ^
  -UpdateAgents ^
  -RunSmokeTest
```

### Simular upgrade

```bat
orchestrator-ia.bat upgrade -ProjectPath C:\dev\projeto -DryRun
```

### Validar ambiente existente

```bat
orchestrator-ia.bat verify -ProjectPath C:\dev\projeto
```

### Reparar após remoção acidental

```bat
orchestrator-ia.bat repair -ProjectPath C:\dev\projeto
```

---

## Relatório de instalação

Gerado em:

```text
.orchestrator/runtime/reports/installation-report.md
```

Inclui agentes detectados, adaptadores, tools e **limitações** (flags reservadas não implementadas).

---

## Ver também

- [`installer-architecture.md`](installer-architecture.md)
- [`legacy-migration.md`](legacy-migration.md)
- [`troubleshooting.md`](troubleshooting.md)
