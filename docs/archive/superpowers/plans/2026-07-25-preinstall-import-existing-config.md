# Plano 0.4.23 — Importar rules/skills/config existentes ANTES do install

Data: 2026-07-25. Task: preinstall_import_existing_config. Estratégia: execute_review_repair.

## Fatos verificados no código (base do plano)

1. Ordem já correta: `scripts/Install-Orchestrator.ps1:588` chama `Invoke-LegacyCleanupPipeline.ps1` (detect → backup → migrate) ANTES de `Copy-TemplateTree` (`:602`). Não é preciso reordenar nada — o gap é só cobertura de fontes.
2. Catálogo de hotspots: `scripts/LegacyCleanup.Lib.ps1:68-79` (`Get-LegacyChildHotspots`). Hoje `.claude/skills` está como `adapter-legacy` sem `MigrationTarget`; `.cursor/rules` não existe como hotspot (só `.cursor/rules/openwolf.mdc` = delete); `.codex/skills`, `.gemini/skills`, `.opencode/skills` ausentes.
3. Adapters raiz (`CLAUDE.md`, `AGENTS.md`, `CURSOR.md`, `GEMINI.md`, `KIMI.md`, `CODEX.md`) estão em `Get-LegacyKnownCatalog` (`LegacyCleanup.Lib.ps1:57-62`) como `adapter-current`. `Get-LegacyInventory` (`:115`) itera catálogo ANTES dos hotspots e deduplica por path — logo a mudança tem que ser NO catálogo, não em hotspot duplicado.
4. Cópia: `scripts/Migrate-LegacyConfigurations.ps1` — para diretório copia filhos de primeiro nível (`:58-63`, merge aditivo, skip se destino existe sem `-Force`); para arquivo, `Ensure-Directory $dest` + `Copy-Item source → dest` copia o arquivo PARA DENTRO do diretório destino mantendo o nome (`:55,67`). Marker `LEGACY-IMPORT.md` já é criado (`:71-84`).
5. Remoção: `Get-LegacyRemovableItems` (`LegacyCleanup.Lib.ps1:141`) só remove `delete`/`replace` (safe) e `adapter-legacy` (aggressive). Classificação `migrate` NUNCA é removida — reclassificar para `migrate` já protege as origens.
6. Skill discovery: `runtime/src/orchestrator_runtime/skills/discovery.py:117-120` faz `rglob("SKILL.md")` sob `.orchestrator/skills` — skills em `.orchestrator/skills/legacy-import/**` JÁ são descobertas. Nenhuma mudança de código; só teste provando.
7. Rules geradas do Cursor a excluir da cópia (fonte: `package/template/adapters/cursor/.cursor/rules/`): `call-agent.mdc`, `git-workflow.mdc`, `multiagent-orchestrator.mdc`, `orchestrator.mdc`, `runtime.mdc`, `token-economy.mdc`, `version-bump.mdc`, mais `openwolf.mdc` (gerada pelo OpenWolf, já classificada delete).
8. Migrations vivem em `package/migrations/` (última: `0.4.21-to-0.4.22.ps1`). Template VERSION: `package/template/.orchestrator/VERSION`. Features: `runtime/src/orchestrator_runtime/diagnostics.py:26` (`FEATURES`).

## Passos de implementação (executor)

### Passo 1 — `scripts/LegacyCleanup.Lib.ps1`

Em `Get-LegacyChildHotspots`:
- Alterar `.claude/skills`: `Classification='migrate'`, `SafeToRemove=$false`, `MigrationTarget='.orchestrator/skills/legacy-import/claude'` (era `adapter-legacy`).
- Adicionar `.cursor/rules` (directory): `Classification='migrate'`, `SafeToRemove=$false`, `MigrationTarget='.orchestrator/rules/legacy-import/cursor'`. Manter a entrada existente `.cursor/rules/openwolf.mdc` = delete.
- Adicionar `.codex/skills` → `.orchestrator/skills/legacy-import/codex` (migrate).
- Adicionar `.gemini/skills` → `.orchestrator/skills/legacy-import/gemini` (migrate).
- Adicionar `.opencode/skills` → `.orchestrator/skills/legacy-import/opencode` (migrate).
- Manter `.agents/skills` → `.orchestrator/skills/legacy-import` como está (mudar o destino quebraria idempotência de installs existentes; documentar).

Em `Get-LegacyKnownCatalog`:
- Alterar `CLAUDE.md`, `AGENTS.md`, `CODEX.md`, `GEMINI.md`, `KIMI.md`, `CURSOR.md` de `adapter-current` para `Classification='migrate'`, `SafeToRemove=$false`, `MigrationTarget='.orchestrator/memory/legacy-import/adapters'`. A cópia de arquivo→dir preserva o nome (fato 4); os 6 podem compartilhar o mesmo destino. Snapshot incondicional (aditivo, requires-review) — não tentar detectar "conteúdo user" heuristicamente.
- ATENÇÃO efeito colateral: `New-LegacyInventoryItem:98` computa `contains_user_content` da classificação, e `Invoke-LegacyCleanupPipeline.ps1:69` monta `preserved` de `adapter-current|user-owned|keep|runtime` — os adapters saem da lista `preserved` e entram em `migrated`. Verificar se algum teste (`tests/Test-LegacyUserOwnedPreservation.ps1`, `Test-LegacyDetection.ps1`, `Test-LegacyCleanupSafe.ps1`) asserta classificação/preservação desses paths e ajustar as expectativas.

Nova função no Lib (para o Passo 2 e para testes referenciarem a mesma lista):

```powershell
function Get-LegacyMigrationExcludedNames {
    param([Parameter(Mandatory = $true)][string]$SourcePath)
    switch (($SourcePath -replace '\\', '/')) {
        '.cursor/rules' {
            return @('openwolf.mdc', 'call-agent.mdc', 'git-workflow.mdc',
                     'multiagent-orchestrator.mdc', 'orchestrator.mdc',
                     'runtime.mdc', 'token-economy.mdc', 'version-bump.mdc')
        }
        default { return @() }
    }
}
```

### Passo 2 — `scripts/Migrate-LegacyConfigurations.ps1`

No loop de cópia de diretório (`:58-63`), somar excludes por fonte ao `$skipNames` existente:

```powershell
$excluded = @(Get-LegacyMigrationExcludedNames -SourcePath $item.path)
...
if ($skipNames -contains $_.Name -or $excluded -contains $_.Name) { return }
```

Sem mudança no schema do inventário JSON (exclusão fica no script+Lib, não no item).

### Passo 3 — diagnostics

`runtime/src/orchestrator_runtime/diagnostics.py`: append em `FEATURES`:

```python
# 0.4.23 — import de config existente (rules/skills/adapters) antes do install
"preinstall_import_existing_config",
```

### Passo 4 — versão + migration

- `VERSION`, `package.json` (version), `runtime/pyproject.toml`, `runtime/src/orchestrator_runtime/__init__.py`, `package/template/.orchestrator/VERSION`: 0.4.22 → 0.4.23.
- Criar `package/migrations/0.4.22-to-0.4.23.ps1` seguindo o padrão de `0.4.21-to-0.4.22.ps1`; corpo: reexecutar `Detect-LegacyConfigurations.ps1` + `Migrate-LegacyConfigurations.ps1` no projeto (sem `-Force`) para que installs existentes importem as fontes recém-cobertas; idempotente (merge aditivo já garante skip de destinos existentes).

### Passo 5 — docs

- `docs/legacy-cleanup.md`: tabela com as novas fontes → destinos (as 5 novas entradas de hotspot + snapshot de adapters), nota sobre exclusão das rules geradas do Cursor e sobre `.agents/skills` manter destino legado.
- `README.md`: seção curta "Importação de configuração existente" com exemplo executável (`orchestrator install` em repo com `.cursor/rules`/`.claude/skills` → resultado em `.orchestrator/**/legacy-import/`). Necessário para AC-003 (docs_example aponta README.md).
- `CHANGELOG.md`: seção 0.4.23.

### Passo 6 — testes

- `tests/Test-LegacyMigration.ps1` (estender fixture existente, mesmo padrão `Invoke-TestInstall`):
  - Criar `.cursor/rules/foo.mdc` (user), `.cursor/rules/orchestrator.mdc` (nome gerado), `.claude/skills/bar/SKILL.md`, `.codex/skills/baz/SKILL.md`, `CLAUDE.md` com conteúdo user, antes do install.
  - Asserts pós-install: `foo.mdc` existe em `.orchestrator/rules/legacy-import/cursor/`; `orchestrator.mdc` NÃO existe lá; `bar/SKILL.md` em `.orchestrator/skills/legacy-import/claude/`; `baz/SKILL.md` em `.../codex/`; snapshot `CLAUDE.md` em `.orchestrator/memory/legacy-import/adapters/`; origens (`.cursor/rules/foo.mdc`, `.claude/skills/bar/SKILL.md`, `CLAUDE.md` raiz) intactas.
- `tests/Test-LegacyCleanupSafe.ps1`: assert que `.cursor/rules` e `.claude/skills` sobrevivem ao modo safe.
- Runtime: `runtime/tests/unit/test_skill_discovery_legacy_import.py` — fixture tmp com `.orchestrator/skills/legacy-import/claude/bar/SKILL.md` (frontmatter `name: bar`), `discover_skills(include_user_global=False)` encontra `bar` (satisfaz AC de discovery sem mudar `discovery.py`).

### Passo 7 — verificação e entrega

- `npm test` (suite PowerShell) e `npm run test:runtime`. Sessão autônoma pode bloquear exec (aprendizado durável deste host): nesse caso, verificação estática linha a linha + deixar execução para o papel tester (runtime) do plano da task.
- Após verde: commit + push develop; `orchestrator update -Force` no pacote com propagate (etapa interativa/pipeline).

## Restrições reafirmadas

- Import 100% aditivo; nunca apagar `.cursor/rules`, `.claude/skills`, `CLAUDE.md` e demais origens em modo safe (classificação `migrate` garante — fato 5).
- Pipeline detect → backup → migrate → template → validate → remove intacto (só catálogo + exclusões mudam).
- Defaults de routing 0.4.21+ (executor opus / validator sonnet) não são tocados.
- MCP possivelmente stale — editar disco diretamente.

## Critérios de aceitação → onde são provados

| AC | Prova |
|---|---|
| AC-001 workspace_changes | Passos 1–5 (diffs em scripts/, runtime/, docs/, VERSION, migration) |
| AC-002 tests_pass | Passo 6 + 7 (suites PowerShell + pytest) |
| AC-003 docs_example README.md | Passo 5 (seção com exemplo executável no README) |
| Install importa sem apagar origem | Test-LegacyMigration asserts origem intacta |
| Hotspots catalogados / migratable | Passo 1 (`Get-LegacyChildHotspots` + catálogo) |
| Discovery acha skills legacy-import | Já funciona (`discovery.py:120` rglob); teste novo prova |
| VERSION/CHANGELOG/migration 0.4.23 | Passo 4–5 |
