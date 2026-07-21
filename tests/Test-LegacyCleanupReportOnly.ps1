#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Test-Helpers.ps1')

$TestName = 'Test-LegacyCleanupReportOnly'
$tempDir = $null
$exitCode = 1

try {
    $repoRoot = Get-TestRepoRoot
    $tempDir = New-TestProjectDirectory
    New-Item -ItemType Directory -Path (Join-Path $tempDir '.ai') -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $tempDir '.ai\x.txt') -Value 'keep-until-cleanup' -Encoding UTF8

    Invoke-TestInstall -ProjectPath $tempDir -PackageRoot $repoRoot -ExtraArgs @('-LegacyCleanupMode', 'report-only')

    Assert-Test -Condition (Test-Path -LiteralPath (Join-Path $tempDir '.ai\x.txt')) -Message 'report-only nao deveria remover .ai'
    $inv = Join-Path $tempDir '.orchestrator\runtime\reports\legacy-inventory.json'
    Assert-Test -Condition (Test-Path -LiteralPath $inv) -Message 'inventory deveria existir em report-only'

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
