# Arquitetura do instalador

Documentação técnica do pacote **bootstrap-agents** / **@starfusion/orchestrator** (v0.1.0). Descreve como o instalador materializa `.orchestrator/` no projeto-alvo de forma determinística e incremental.

Quickstart one-liner: [`quickstart-oneliner.md`](quickstart-oneliner.md)

---

## Visão geral

```text
  npx / orchestrator          get.ps1 (gh api|iex)       bootstrap-agents.bat
  (@starfusion/orchestrator)  cache LOCALAPPDATA         wrapper fino local
             \                        |                        /
              \                       |                       /
               \                      |                      /
                +---------------------+---------------------+
                                      |
                                      v
                        Install-Orchestrator.ps1
                        (init | install | verify | ...)
                                      |
              +-----------+-----------+-----------+
              |           |           |           |
          Detect-*   Copy/Apply  Generate-*  Validate-*
```

**Fonte da verdade do pacote:** `package/template/.orchestrator/`  
**Fonte da verdade do workspace:** `<projeto>/.orchestrator/`  
**Contrato de arquivos:** `package/manifest.json`  
**CLI npm:** `package.json` → bin `orchestrator` / `mao` → `bin/orchestrator.js`

---

## Entradas (três frentes, uma lógica)

### 1. npm / npx (estilo OpenWolf)

```bash
npx --yes github:henrique-starfusion/bootstrap-agents#develop init
orchestrator init
mao init
```

`bin/orchestrator.js`:

1. Resolve a raiz do pacote npm (`dirname/..`)
2. Usa o diretório atual como `-ProjectPath` (ou `--project`)
3. Localiza `powershell.exe` / `pwsh`
4. Invoca `scripts/Install-Orchestrator.ps1` com `-NonInteractive`

### 2. get.ps1 (one-liner PowerShell)

```powershell
gh api -H "Accept: application/vnd.github.raw" `
  "repos/henrique-starfusion/bootstrap-agents/contents/get.ps1?ref=develop" | iex
```

`get.ps1`:

1. Se já estiver dentro de um pacote completo, usa `$PSScriptRoot`
2. Senão, sincroniza cache em `%LOCALAPPDATA%\StarFusion\multiagent-orchestrator` via `gh` ou `git`
3. Executa `Install-Orchestrator.ps1` no projeto atual

### 3. BAT fino (clone local)

`bootstrap-agents.bat` apenas:

1. Fixa o diretório para a raiz do pacote (`%~dp0`)
2. Invoca PowerShell com `-ExecutionPolicy Bypass`
3. Executa `scripts/Install-Orchestrator.ps1` repassando `%*`
4. Propaga `%ERRORLEVEL%`

Não há parsing de flags no BAT — use sintaxe PowerShell (`-ProjectPath`, `-DryRun`, etc.) ou as flags `--*` do CLI Node.

---

## Roteador: Install-Orchestrator.ps1

### Comandos

| Comando | Scripts invocados | Altera disco? |
|---|---|---|
| `init` | Alias de `install` | Sim (salvo `-DryRun`) |
| `install` | Pipeline completo abaixo | Sim (salvo `-DryRun`) |
| `verify` | Detect-Environment → Validate-Orchestrator → Validate-Hooks | Não |
| `upgrade` | Update-Orchestrator.ps1 | Sim |
| `repair` | Repair-Orchestrator.ps1 | Sim |
| `uninstall` | Uninstall-Orchestrator.ps1 | Sim (remove gerenciados) |
| `status` | Leitura local | Não |
| `analyze` | Detect-Environment, Detect-Agents, Validate-Orchestrator | Parcial |
| `skills` | Lê skills/registry.json | Não |

### Pipeline do `install`

```text
1. Compare-SemVer (workspace vs pacote) → recusa se workspace > pacote
2. Detect-Environment.ps1          (preflight)
3. New-InstallationLock            (runtime/install.lock)
4. Migrate-LegacyClaude.ps1        (se .claude/VERSION e sem .orchestrator/VERSION)
5. Copy-TemplateTree               (package/template/.orchestrator → projeto)
6. Apply-Manifest                  (modos managed/merge/generated)
7. Sync-WorkspaceVersion           (se VERSION ausente)
8. Detect-Agents.ps1
9. Generate-Adapters.ps1
10. Install-Tools.ps1               (salvo -SkipTools)
11. Configure-Mcps.ps1              (se -ConfigureMcps)
12. Validate-Orchestrator.ps1
13. Validate-Hooks.ps1
14. Update-Agents.ps1               (se -UpdateAgents)
15. Probe-Agents.ps1                (skip por padrão; -RunSmokeTest ativa)
16. Write-InstallationReport.ps1
17. Remove-InstallationLock         (finally)
```

---

## Orchestrator.Common.ps1

Biblioteca compartilhada. Funções principais:

| Função | Papel |
|---|---|
| `Get-PackageRoot` / `Get-ProjectRoot` | Resolve caminhos |
| `Get-OrchestratorRoot` | `<projeto>/.orchestrator` |
| `Read-PackageVersion` / `Read-WorkspaceVersion` | Lê arquivos VERSION |
| `Compare-SemVer` | Compara semver (System.Version) |
| `Import-Manifest` / `Apply-Manifest` | Aplica entradas do manifest |
| `Copy-TemplateTree` | Copia árvore template (skip se existe, salvo `-Force`) |
| `Copy-ManagedFile` | Copia unitária respeitando modo |
| `Test-PackageIntegrity` | Valida manifest + sources |
| `New-BackupBundle` / backups | Snapshots em `.orchestrator/backups/` |
| `New-InstallationLock` | Evita installs concorrentes |
| `Get-AdapterVendorMap` | Mapeia agente → vendor de adaptador |
| `Sync-WorkspaceVersion` | Grava `.orchestrator/VERSION` |

---

## Modos do manifest

Cada entrada em `package/manifest.json` tem um `mode`:

| Modo | Comportamento no install |
|---|---|
| `managed` | Copia se ausente; skip se existe (use `-Force` para sobrescrever) |
| `merge` | Copia só se destino ausente (preserva customizações) |
| `generated` | Copia se ausente; skip se existe (ex.: `detected.json`, `tools/registry.json`) |
| `user-owned` | Nunca sobrescreve destino existente |
| `runtime` | Reservado para artefatos de execução |

O `repair` força re-aplicação com `-Force` nos modos gerenciados.

---

## Template vs adaptadores

### `.orchestrator/` (canônico)

Copiado integralmente de `package/template/.orchestrator/`. Contém config, skills, memória, MCP, hooks, runtime, etc.

### Adaptadores (por vendor)

Copiados de `package/template/adapters/<vendor>/` para a raiz do projeto **somente** quando o agente correspondente está `available` em `detected.json`.

Mapeamento (`Get-AdapterVendorMap`):

```text
claude → claude    codex → codex      gemini → gemini
kimi, kimi-code → kimi    cursor → cursor    opencode → opencode
```

Adaptadores **não duplicam** configuração — redirecionam leitura para `.orchestrator/`.

---

## Versionamento

| Arquivo | Significado |
|---|---|
| `VERSION` (raiz do pacote) | Versão publicada do bootstrap |
| `.orchestrator/VERSION` (workspace) | Versão instalada no projeto |

Regras:

- **install:** recusa se workspace > pacote (exit 6)
- **upgrade:** backup prévio em `.orchestrator/backups/<timestamp>-pre-upgrade/`; aplica tree + manifest; sincroniza VERSION
- **migrations:** scripts `package/migrations/<from>-to-<to>.ps1` (estrutura preparada; aplicação automática evoluirá)

---

## Artefatos gerados em runtime

| Caminho | Produtor |
|---|---|
| `agents/detected.json` | Detect-Agents |
| `agents/probe-results.json` | Probe-Agents |
| `agents/registry.json` | Detect-Agents (merge) |
| `tools/registry.json` | Install-Tools |
| `mcp/registry.json` | Configure-Mcps (opt-in) |
| `runtime/validations/*.log` | Detect-Environment, validações |
| `runtime/reports/installation-report.md` | Write-InstallationReport |
| `runtime/install.lock` | Install (durante execução) |
| `backups/*` | upgrade, uninstall, migração legada |

---

## Integridade e validação

**Preflight (`Detect-Environment`):**

- PowerShell ≥ 5.1
- git no PATH
- Integridade do pacote (manifest + sources)
- Permissão de escrita
- Espaço livre ≥ 50 MB
- Lock disponível

**Validate-Orchestrator:**

- `.orchestrator/` e subpastas obrigatórias (`config`, `agents`, `skills`, `runtime`, `memory`)
- JSON válido em `config/*.json` e `agents/registry.json`
- Arquivos `managed` do manifest presentes

**Validate-Hooks:**

- Verifica estrutura de hooks sem ativá-los durante install

---

## Exit codes

| Código | Significado |
|---|---|
| 0 | Sucesso |
| 1 | Erro geral / validação / preflight |
| 2 | Comando inválido |
| 6 | Workspace mais novo que o pacote |

---

## Extensibilidade

Para evoluir o pacote sem quebrar workspaces:

1. Adicionar arquivos ao template e ao `manifest.json`
2. Criar migração `package/migrations/X-to-Y.ps1` quando transformação for necessária
3. Preferir modo `merge` para JSON que o usuário pode customizar
4. Nunca apagar `.orchestrator/` inteiro em upgrade

---

## Referências

- [`quickstart-oneliner.md`](quickstart-oneliner.md) — instalação em uma linha
- [`cli-reference.md`](cli-reference.md) — parâmetros e exemplos
- [`legacy-migration.md`](legacy-migration.md) — `.claude/` → `.orchestrator/`
- [`repo-layout.md`](repo-layout.md) — organização deste repositório
- [`legacy/README.md`](legacy/README.md) — material deprecado
- [`troubleshooting.md`](troubleshooting.md) — diagnóstico operacional
- `package/template/docs/agent-environment.md` — layout canônico no workspace
