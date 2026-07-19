#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Test-Helpers.ps1')

$TestName = 'Test-Adapters'
$tempDir = $null
$exitCode = 1

try {
    $repoRoot = Get-TestRepoRoot
    $tempDir = New-TestProjectDirectory

    Invoke-TestInstall -ProjectPath $tempDir -PackageRoot $repoRoot

    $adapterCode = Invoke-TestScript -ScriptName 'Generate-Adapters.ps1' -Arguments @{
        ProjectPath  = $tempDir
        PackageRoot  = $repoRoot
        AllAdapters  = [switch]::Present
        Force        = [switch]::Present
    }
    Assert-Test -Condition ($adapterCode -eq 0) -Message ('Generate-Adapters exited with code {0}' -f $adapterCode)

    $claudePath = Join-Path $tempDir 'CLAUDE.md'
    $agentsPath = Join-Path $tempDir 'AGENTS.md'

    Assert-Test -Condition (Test-Path -LiteralPath $claudePath) -Message 'CLAUDE.md was not created by Generate-Adapters -AllAdapters -Force'
    Assert-Test -Condition (Test-Path -LiteralPath $agentsPath) -Message 'AGENTS.md was not created by Generate-Adapters -AllAdapters -Force'

    $claudeContent = Get-Content -LiteralPath $claudePath -Raw -Encoding UTF8
    Assert-Test -Condition ($claudeContent -match '\.orchestrator') -Message 'CLAUDE.md does not reference .orchestrator'

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
