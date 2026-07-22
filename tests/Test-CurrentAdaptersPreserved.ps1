#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Test-Helpers.ps1')

$TestName = 'Test-CurrentAdaptersPreserved'
$tempDir = $null
$exitCode = 1

try {
    $repoRoot = Get-TestRepoRoot
    $tempDir = New-TestProjectDirectory
    New-Item -ItemType Directory -Path (Join-Path $tempDir '.ai') -Force | Out-Null
    Invoke-TestInstall -ProjectPath $tempDir -PackageRoot $repoRoot

    # Adaptadores atuais gerados ou stubs
    $hasClaude = (Test-Path -LiteralPath (Join-Path $tempDir 'CLAUDE.md')) -or (Test-Path -LiteralPath (Join-Path $tempDir '.claude'))
    Assert-Test -Condition $hasClaude -Message 'adaptador Claude ausente apos install'
    Assert-Test -Condition (Test-Path -LiteralPath (Join-Path $tempDir '.orchestrator\VERSION')) -Message '.orchestrator ausente'
    Assert-Test -Condition (-not (Test-Path -LiteralPath (Join-Path $tempDir '.ai'))) -Message '.ai legado ainda presente'

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
