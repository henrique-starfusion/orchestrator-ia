#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Test-Helpers.ps1')

$TestName = 'Test-AgentUpdates'
$tempDir = $null
$exitCode = 1

try {
    $repoRoot = Get-TestRepoRoot
    $tempDir = New-TestProjectDirectory

    Invoke-TestInstall -ProjectPath $tempDir -PackageRoot $repoRoot

    $dryRunCode = Invoke-TestScript -ScriptName 'Update-Agents.ps1' -Arguments @{
        ProjectPath = $tempDir
        DryRun      = [switch]::Present
    }
    Assert-Test -Condition ($dryRunCode -eq 0) -Message ('Update-Agents -DryRun exited with code {0}' -f $dryRunCode)

    $noOpCode = Invoke-TestScript -ScriptName 'Update-Agents.ps1' -Arguments @{
        ProjectPath = $tempDir
    }
    Assert-Test -Condition ($noOpCode -eq 0) -Message (
        'Update-Agents without -UpdateAgents exited with code {0}' -f $noOpCode
    )

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
