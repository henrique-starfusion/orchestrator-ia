#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Test-Helpers.ps1')

$TestName = 'Test-LegacyMigration'
$tempDir = $null
$exitCode = 1

try {
    $repoRoot = Get-TestRepoRoot
    $tempDir = New-TestProjectDirectory

    $legacyRoot = Join-Path $tempDir '.claude'
    $legacyMemory = Join-Path $legacyRoot 'memory'
    $legacyRules = Join-Path $legacyRoot 'rules'
    $claudeSkills = Join-Path $legacyRoot 'skills\bar'
    $cursorRules = Join-Path $tempDir '.cursor\rules'
    $codexSkills = Join-Path $tempDir '.codex\skills\baz'

    New-Item -ItemType Directory -Path $legacyMemory -Force | Out-Null
    New-Item -ItemType Directory -Path $legacyRules -Force | Out-Null
    New-Item -ItemType Directory -Path $claudeSkills -Force | Out-Null
    New-Item -ItemType Directory -Path $cursorRules -Force | Out-Null
    New-Item -ItemType Directory -Path $codexSkills -Force | Out-Null

    Set-Content -LiteralPath (Join-Path $legacyRoot 'VERSION') -Value '0.0.9' -Encoding UTF8
    Set-Content -LiteralPath (Join-Path $legacyMemory 'index.json') -Value '{"entries":[]}' -Encoding UTF8
    Set-Content -LiteralPath (Join-Path $legacyRules 'project.md') -Value '# Legacy project rules' -Encoding UTF8
    Set-Content -LiteralPath (Join-Path $claudeSkills 'SKILL.md') -Value "---`nname: bar`ndescription: test skill`n---`n# bar" -Encoding UTF8
    Set-Content -LiteralPath (Join-Path $cursorRules 'foo.mdc') -Value '# User cursor rule' -Encoding UTF8
    Set-Content -LiteralPath (Join-Path $cursorRules 'orchestrator.mdc') -Value '# Generated — should not import' -Encoding UTF8
    Set-Content -LiteralPath (Join-Path $codexSkills 'SKILL.md') -Value "---`nname: baz`ndescription: codex skill`n---`n# baz" -Encoding UTF8
    Set-Content -LiteralPath (Join-Path $tempDir 'CLAUDE.md') -Value '# User CLAUDE adapter content' -Encoding UTF8

    Invoke-TestInstall -ProjectPath $tempDir -PackageRoot $repoRoot

    $versionPath = Get-OrchestratorPath -ProjectPath $tempDir -RelativePath 'VERSION'
    Assert-Test -Condition (Test-Path -LiteralPath $versionPath) -Message '.orchestrator/VERSION missing after legacy migration install'

    $migrationReport = Get-OrchestratorPath -ProjectPath $tempDir -RelativePath 'runtime/reports/migration-legacy-claude.md'
    $backupsRoot = Get-OrchestratorPath -ProjectPath $tempDir -RelativePath 'backups'
    $hasMigrationReport = Test-Path -LiteralPath $migrationReport
    $hasBackup = $false
    if (Test-Path -LiteralPath $backupsRoot) {
        $backupDirs = @(Get-ChildItem -LiteralPath $backupsRoot -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -like '*legacy-migration*' -or $_.Name -like '*pre-*' -or $_.Name -like '*legacy-cleanup*' })
        $hasBackup = ($backupDirs.Count -gt 0)
    }

    Assert-Test -Condition ($hasMigrationReport -or $hasBackup) -Message 'No migration report or backup evidence found after legacy install'

    $importPath = Get-OrchestratorPath -ProjectPath $tempDir -RelativePath 'memory/legacy-import/claude'
    Assert-Test -Condition (Test-Path -LiteralPath $importPath) -Message 'memory/legacy-import/claude ausente apos migracao'

    # 0.4.23 — preinstall import
    $importedCursor = Join-Path $tempDir '.orchestrator\rules\legacy-import\cursor\foo.mdc'
    Assert-Test -Condition (Test-Path -LiteralPath $importedCursor) -Message 'foo.mdc nao importado de .cursor/rules'

    $skippedGenerated = Join-Path $tempDir '.orchestrator\rules\legacy-import\cursor\orchestrator.mdc'
    Assert-Test -Condition (-not (Test-Path -LiteralPath $skippedGenerated)) -Message 'orchestrator.mdc gerado nao deveria ser importado'

    $importedClaudeSkill = Join-Path $tempDir '.orchestrator\skills\legacy-import\claude\bar\SKILL.md'
    Assert-Test -Condition (Test-Path -LiteralPath $importedClaudeSkill) -Message 'skill bar nao importada de .claude/skills'

    $importedCodexSkill = Join-Path $tempDir '.orchestrator\skills\legacy-import\codex\baz\SKILL.md'
    Assert-Test -Condition (Test-Path -LiteralPath $importedCodexSkill) -Message 'skill baz nao importada de .codex/skills'

    $adapterSnap = Join-Path $tempDir '.orchestrator\memory\legacy-import\adapters\CLAUDE.md'
    Assert-Test -Condition (Test-Path -LiteralPath $adapterSnap) -Message 'snapshot CLAUDE.md ausente em legacy-import/adapters'

    # Origens intactas (modo safe nao apaga migrate)
    Assert-Test -Condition (Test-Path -LiteralPath (Join-Path $cursorRules 'foo.mdc')) -Message '.cursor/rules/foo.mdc origem removida'
    Assert-Test -Condition (Test-Path -LiteralPath (Join-Path $claudeSkills 'SKILL.md')) -Message '.claude/skills/bar origem removida'
    Assert-Test -Condition (Test-Path -LiteralPath (Join-Path $tempDir 'CLAUDE.md')) -Message 'CLAUDE.md raiz removido'

    Write-Host ('PASS: {0}' -f $TestName) -ForegroundColor Green
    $exitCode = 0
}
catch {
    Write-Host ('FAIL: {0} - {1}' -f $TestName, $_.Exception.Message) -ForegroundColor Red
}
finally {
    if ($tempDir) {
        Remove-TestProjectDirectory -Path $tempDir
    }
}

exit $exitCode
