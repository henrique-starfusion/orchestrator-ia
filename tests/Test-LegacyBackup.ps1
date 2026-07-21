#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Test-Helpers.ps1')

$TestName = 'Test-LegacyBackup'
$tempDir = $null
$exitCode = 1

try {
    $repoRoot = Get-TestRepoRoot
    $tempDir = New-TestProjectDirectory
    New-Item -ItemType Directory -Path (Join-Path $tempDir '.ai\nested') -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $tempDir '.ai\nested\x.txt') -Value 'legacy' -Encoding UTF8
    New-Item -ItemType Directory -Path (Join-Path $tempDir '.orchestrator\runtime\reports') -Force | Out-Null

    $inv = Join-Path $tempDir '.orchestrator\runtime\reports\legacy-inventory.json'
    & (Join-Path $repoRoot 'scripts\Detect-LegacyConfigurations.ps1') -ProjectPath $tempDir -OutputPath $inv | Out-Null
    & (Join-Path $repoRoot 'scripts\Backup-LegacyConfigurations.ps1') -ProjectPath $tempDir -InventoryPath $inv -Mode safe
    Assert-Test -Condition ($LASTEXITCODE -eq 0) -Message 'Backup falhou'

    $marker = Join-Path $tempDir '.orchestrator\runtime\reports\legacy-backup-path.txt'
    Assert-Test -Condition (Test-Path -LiteralPath $marker) -Message 'marker de backup ausente'
    $backupRoot = (Get-Content -LiteralPath $marker -Raw).Trim()
    Assert-Test -Condition (Test-Path -LiteralPath (Join-Path $backupRoot 'manifest.json')) -Message 'manifest ausente'
    Assert-Test -Condition (Test-Path -LiteralPath (Join-Path $backupRoot 'inventory.json')) -Message 'inventory no backup ausente'
    Assert-Test -Condition (Test-Path -LiteralPath (Join-Path $backupRoot '.ai\nested\x.txt')) -Message 'arquivo nao copiado'
    $manifest = Get-Content -LiteralPath (Join-Path $backupRoot 'manifest.json') -Raw | ConvertFrom-Json
    Assert-Test -Condition ([bool]$manifest.validated) -Message 'backup nao validado'

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
