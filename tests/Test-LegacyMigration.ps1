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

    New-Item -ItemType Directory -Path $legacyMemory -Force | Out-Null
    New-Item -ItemType Directory -Path $legacyRules -Force | Out-Null

    Set-Content -LiteralPath (Join-Path $legacyRoot 'VERSION') -Value '0.0.9' -Encoding UTF8
    Set-Content -LiteralPath (Join-Path $legacyMemory 'index.json') -Value '{"entries":[]}' -Encoding UTF8
    Set-Content -LiteralPath (Join-Path $legacyRules 'project.md') -Value '# Legacy project rules' -Encoding UTF8

    Invoke-TestInstall -ProjectPath $tempDir -PackageRoot $repoRoot

    $versionPath = Get-OrchestratorPath -ProjectPath $tempDir -RelativePath 'VERSION'
    Assert-Test -Condition (Test-Path -LiteralPath $versionPath) -Message '.orchestrator/VERSION missing after legacy migration install'

    $migrationReport = Get-OrchestratorPath -ProjectPath $tempDir -RelativePath 'runtime/reports/migration-legacy-claude.md'
    $backupsRoot = Get-OrchestratorPath -ProjectPath $tempDir -RelativePath 'backups'
    $hasMigrationReport = Test-Path -LiteralPath $migrationReport
    $hasBackup = $false
    if (Test-Path -LiteralPath $backupsRoot) {
        $backupDirs = @(Get-ChildItem -LiteralPath $backupsRoot -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -like '*legacy-migration*' -or $_.Name -like '*pre-*' })
        $hasBackup = ($backupDirs.Count -gt 0)
    }

    Assert-Test -Condition ($hasMigrationReport -or $hasBackup) -Message 'No migration report or backup evidence found after legacy install'

    $importPath = Get-OrchestratorPath -ProjectPath $tempDir -RelativePath 'memory/legacy-import/claude'
    Assert-Test -Condition (Test-Path -LiteralPath $importPath) -Message 'memory/legacy-import/claude ausente apos migracao'

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
