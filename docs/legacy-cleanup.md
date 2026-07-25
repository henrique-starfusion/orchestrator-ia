# Limpeza de configurações legadas

A partir da **0.4.0**, `orchestrator install` / `init` / `update` / `upgrade` executam limpeza de legado por padrão no modo **safe**.

## Pipeline

```text
detect → backup → migrate → install/update .orchestrator → adapters → validate
→ remove (safe) → validate cleanup → relatório
```

## Modos

| Modo | Comportamento |
|---|---|
| `safe` (padrão) | Remove só itens comprovadamente substituídos (`.ai/`, `graphify-out/`, `orchestrator/`, `.claude/VERSION`, …) |
| `aggressive` | Amplia remoções marcadas `safe_to_remove`; **exige** `--force` |
| `report-only` | Só inventário/plano; não remove |

## Flags

```bash
orchestrator init
orchestrator init --skip-legacy-cleanup
orchestrator init --legacy-cleanup-mode report-only
orchestrator init --legacy-cleanup-mode aggressive --force
orchestrator init --keep-legacy-backup
```

PowerShell: `-SkipLegacyCleanup`, `-LegacyCleanupMode`, `-KeepLegacyBackup`, `-Force`.

## Comandos dedicados

```bash
orchestrator legacy scan
orchestrator legacy cleanup --legacy-cleanup-mode safe
orchestrator legacy status
orchestrator legacy restore --backup <id> --force
```

## Backup e restore

Backup em:

```text
.orchestrator/backups/<timestamp>-legacy-cleanup/
```

Contém `manifest.json` (SHA-256), `inventory.json`, `restore.ps1`.

Restore **não** roda no uninstall — só via `legacy restore`.

## Migração de conhecimento

No `install` / `init` / `update`, **antes** de copiar o template, o pipeline detecta e importa configuração existente para paths `legacy-import` (requires-review). A origem **não** é apagada no modo safe.

| Fonte | Destino |
|---|---|
| `.claude/memory` | `.orchestrator/memory/legacy-import/claude/` |
| `.claude/rules` | `.orchestrator/rules/legacy-import/claude/` |
| `.claude/skills` | `.orchestrator/skills/legacy-import/claude/` |
| `.cursor/rules` (user) | `.orchestrator/rules/legacy-import/cursor/` |
| `.codex/skills` | `.orchestrator/skills/legacy-import/codex/` |
| `.gemini/skills` | `.orchestrator/skills/legacy-import/gemini/` |
| `.opencode/skills` | `.orchestrator/skills/legacy-import/opencode/` |
| `.agents/skills` | `.orchestrator/skills/legacy-import/` (path histórico) |
| `CLAUDE.md`, `AGENTS.md`, `CURSOR.md`, `CODEX.md`, `GEMINI.md`, `KIMI.md` | `.orchestrator/memory/legacy-import/adapters/` |

Skills sob `.orchestrator/skills/legacy-import/**` entram no catálogo do runtime (`discover_skills` faz `rglob`).

### Exclusões na cópia de `.cursor/rules`

Não são importadas (geradas pelo template/OpenWolf): `openwolf.mdc`, `call-agent.mdc`, `git-workflow.mdc`, `multiagent-orchestrator.mdc`, `orchestrator.mdc`, `runtime.mdc`, `token-economy.mdc`, `version-bump.mdc`.

## Preservado automaticamente

- `user-owned` (`.aider`, `.continue`, …)
- `unknown` (`.mcp`, `mcp.json`, …)
- `runtime` (`.wolf`, `.graphify`)
- pastas de adaptador (`.claude/`, `.cursor/`, …) — remove apenas filhos legado conhecidos (`delete`/`replace`)
- arquivos de adaptador na raiz — **snapshot** em `legacy-import/adapters/`; o arquivo original permanece
- `.git/`, código-fonte, secrets, `.env`

## Relatórios

- `.orchestrator/runtime/reports/legacy-inventory.json`
- `.orchestrator/runtime/reports/legacy-cleanup-report.md`
- `.orchestrator/runtime/legacy-cleanup-state.json`
- seção **Legacy cleanup** em `installation-report.md`

## Troubleshooting

| Sintoma | Ação |
|---|---|
| Quero só ver o plano | `--legacy-cleanup-mode report-only` |
| Remoção agressiva falhou | adicione `--force` |
| Precisei do arquivo antigo | `orchestrator legacy restore --backup <pasta> --force` |
| Pular limpeza | `--skip-legacy-cleanup` |
