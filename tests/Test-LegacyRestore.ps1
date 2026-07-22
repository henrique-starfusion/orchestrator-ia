#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Test-Helpers.ps1')

$TestName = 'Test-LegacyRestore'
$tempDir = $null
$exitCode = 1

try {
    $repoRoot = Get-TestRepoRoot
    $tempDir = New-TestProjectDirectory
    New-Item -ItemType Directory -Path (Join-Path $tempDir '.ai') -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $tempDir '.ai\keep.txt') -Value 'restore-me' -Encoding UTF8

    Invoke-TestInstall -ProjectPath $tempDir -PackageRoot $repoRoot
    Assert-Test -Condition (-not (Test-Path -LiteralPath (Join-Path $tempDir '.ai'))) -Message '.ai deveria ter sido removido'

    $backups = Join-Path $tempDir '.orchestrator\backups'
    $legacyBackup = @(Get-ChildItem -LiteralPath $backups -Directory | Where-Object { $_.Name -like '*legacy-cleanup*' } | Select-Object -First 1)
    Assert-Test -Condition ($legacyBackup.Count -eq 1) -Message 'backup legacy-cleanup ausente'

    & (Join-Path $repoRoot 'scripts\Restore-LegacyBackup.ps1') -ProjectPath $tempDir -BackupId $legacyBackup[0].Name -Force
    Assert-Test -Condition ($LASTEXITCODE -eq 0) -Message 'restore falhou'
    Assert-Test -Condition (Test-Path -LiteralPath (Join-Path $tempDir '.ai\keep.txt')) -Message 'arquivo nao restaurado'
    $content = Get-Content -LiteralPath (Join-Path $tempDir '.ai\keep.txt') -Raw
    Assert-Test -Condition ($content -match 'restore-me') -Message 'conteudo restaurado incorreto'

    Write-Host ('PASS: {0}' -f $TestName) -ForegroundColor Green
    $exitCode = 0
}
catch {
    Write-Host ('FAIL: {0} - {1}' -f $TestName, $_.Exception.Message) -ForegroundColor Red
}
finally {
    if ($tempDir) { Remove-TestProjectDirectory -Path $tempDir }
}
exit $exitCode
