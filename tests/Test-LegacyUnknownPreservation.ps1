#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Test-Helpers.ps1')

$TestName = 'Test-LegacyUnknownPreservation'
$tempDir = $null
$exitCode = 1

try {
    $repoRoot = Get-TestRepoRoot
    $tempDir = New-TestProjectDirectory
    New-Item -ItemType Directory -Path (Join-Path $tempDir '.mcp') -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $tempDir '.mcp\config.json') -Value '{}' -Encoding UTF8
    Set-Content -LiteralPath (Join-Path $tempDir 'mcp.json') -Value '{}' -Encoding UTF8
    Invoke-TestInstall -ProjectPath $tempDir -PackageRoot $repoRoot
    Assert-Test -Condition (Test-Path -LiteralPath (Join-Path $tempDir '.mcp\config.json')) -Message '.mcp unknown removido'
    Assert-Test -Condition (Test-Path -LiteralPath (Join-Path $tempDir 'mcp.json')) -Message 'mcp.json unknown removido'
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
