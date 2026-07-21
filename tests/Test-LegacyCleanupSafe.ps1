#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Test-Helpers.ps1')

$TestName = 'Test-LegacyCleanupSafe'
$tempDir = $null
$exitCode = 1

try {
    $repoRoot = Get-TestRepoRoot
    $tempDir = New-TestProjectDirectory

    New-Item -ItemType Directory -Path (Join-Path $tempDir '.ai') -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $tempDir '.ai\old.txt') -Value 'x' -Encoding UTF8
    New-Item -ItemType Directory -Path (Join-Path $tempDir 'graphify-out') -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $tempDir '.claude\memory') -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $tempDir '.claude\VERSION') -Value '0.0.9' -Encoding UTF8
    Set-Content -LiteralPath (Join-Path $tempDir '.claude\memory\index.json') -Value '{"entries":[]}' -Encoding UTF8
    # user-owned deve sobreviver
    New-Item -ItemType Directory -Path (Join-Path $tempDir '.aider') -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $tempDir '.aider\cfg.yml') -Value 'keep: true' -Encoding UTF8

    Invoke-TestInstall -ProjectPath $tempDir -PackageRoot $repoRoot

    Assert-Test -Condition (-not (Test-Path -LiteralPath (Join-Path $tempDir '.ai'))) -Message '.ai deveria ter sido removido (safe)'
    Assert-Test -Condition (-not (Test-Path -LiteralPath (Join-Path $tempDir 'graphify-out'))) -Message 'graphify-out deveria ter sido removido'
    Assert-Test -Condition (Test-Path -LiteralPath (Join-Path $tempDir '.aider\cfg.yml')) -Message '.aider user-owned removido indevidamente'
    Assert-Test -Condition (Test-Path -LiteralPath (Join-Path $tempDir '.orchestrator\VERSION')) -Message 'VERSION ausente'
    $importMem = Join-Path $tempDir '.orchestrator\memory\legacy-import\claude'
    Assert-Test -Condition (Test-Path -LiteralPath $importMem) -Message 'memoria nao migrada para legacy-import/claude'
    $report = Join-Path $tempDir '.orchestrator\runtime\reports\legacy-cleanup-report.md'
    Assert-Test -Condition (Test-Path -LiteralPath $report) -Message 'relatorio legacy-cleanup ausente'

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
