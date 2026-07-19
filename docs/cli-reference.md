# Referência da CLI

Três formas de entrada (mesma lógica):

1. **One-liner npm:** `npx @starfusion/orchestrator init` / `orchestrator init`
2. **One-liner PowerShell:** `get.ps1` (via `gh api ... | iex` ou local)
3. **Wrapper local:** `bootstrap-agents.bat` → `scripts/Install-Orchestrator.ps1`

**Sintaxe PowerShell:** 5.1+. O BAT e o bin Node encaminham argumentos ao instalador.

---

## One-liner (projeto atual)

```bash
npx --yes github:henrique-starfusion/bootstrap-agents#develop init
```

```powershell
gh api -H "Accept: application/vnd.github.raw" "repos/henrique-starfusion/bootstrap-agents/contents/get.ps1?ref=develop" | iex
```

```bash
orchestrator init
mao init
```

---

## Invocação local

```bat
bootstrap-agents.bat <comando> [opções]
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
bootstrap-agents.bat install -ProjectPath C:\dev\meu-app
bootstrap-agents.bat verify -Project C:\dev\meu-app
```

```powershell
.\get.ps1 init -ProjectPath C:\dev\meu-app
```

---

## Comandos

### `update`

Atualiza a estrutura `.orchestrator/` do projeto atual (comando principal de manutenção).

```bash
orchestrator update
orchestrator update --force
```

```bat
bootstrap-agents.bat update -ProjectPath C:\dev\meu-app
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
bootstrap-agents.bat install -ProjectPath C:\dev\meu-app
```

**Etapas:** preflight → lock → migração legada (se aplicável) → template → manifest → detect agents → adaptadores → tools → MCPs (opt-in) → validação → updates (opt-in) → probes → relatório.

**Padrão:** probes de agentes **desabilitados** (registro skip). Use `-RunSmokeTest` para ativar.

---

### `verify`

Validação somente leitura — não altera arquivos gerenciados.

```bat
bootstrap-agents.bat verify -ProjectPath C:\dev\meu-app
```

Executa: preflight → Validate-Orchestrator → Validate-Hooks.

Útil em CI ou após clone do repositório.

---

### `upgrade`

Atualiza workspace quando a versão do pacote é **maior** que `.orchestrator/VERSION`.

```bat
bootstrap-agents.bat upgrade -ProjectPath C:\dev\meu-app
bootstrap-agents.bat upgrade -ProjectPath C:\dev\meu-app -Force
bootstrap-agents.bat upgrade -DryRun
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
bootstrap-agents.bat repair -ProjectPath C:\dev\meu-app
bootstrap-agents.bat repair -DryRun
```

Força re-aplicação do manifest com `-Force` interno.

---

### `uninstall`

Remove arquivos listados no manifest (exceto `user-owned`). Sempre cria backup em `.orchestrator/backups/` antes de remover.

```bat
bootstrap-agents.bat uninstall -ProjectPath C:\dev\meu-app
bootstrap-agents.bat uninstall -Force
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
bootstrap-agents.bat status -ProjectPath C:\dev\meu-app
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
bootstrap-agents.bat analyze -ProjectPath C:\dev\meu-app
```

Executa Detect-Environment, Detect-Agents e Validate-Orchestrator.

---

### `skills`

Lista IDs registrados em `.orchestrator/skills/registry.json`:

```bat
bootstrap-agents.bat skills -ProjectPath C:\dev\meu-app
```

Exit 1 se o registro estiver ausente.

---

## Opções globais (install)

| Parâmetro | Tipo | Descrição |
|---|---|---|
| `-DryRun` | switch | Simula; não grava lock nem copia arquivos |
| `-Force` | switch | Sobrescreve managed/generated; força migração legada |
| `-NonInteractive` | switch | Reservado para automação |
| `-PackageRoot` | string | Raiz do pacote bootstrap (padrão: pai de `scripts/`) |

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
| `-LegacyCleanup` | **Não implementado** — limitação registrada no relatório |
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
bootstrap-agents.bat install -ProjectPath C:\dev\novo-projeto
```

### Instalação completa com opt-ins

```bat
bootstrap-agents.bat install ^
  -ProjectPath C:\dev\novo-projeto ^
  -ConfigureMcps ^
  -UpdateAgents ^
  -RunSmokeTest
```

### Simular upgrade

```bat
bootstrap-agents.bat upgrade -ProjectPath C:\dev\projeto -DryRun
```

### Validar ambiente existente

```bat
bootstrap-agents.bat verify -ProjectPath C:\dev\projeto
```

### Reparar após remoção acidental

```bat
bootstrap-agents.bat repair -ProjectPath C:\dev\projeto
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
