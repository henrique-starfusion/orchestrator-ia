#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Test-Helpers.ps1')

$TestName = 'Test-Uninstall'
$tempDir = $null
$exitCode = 1

try {
    $repoRoot = Get-TestRepoRoot
    $tempDir = New-TestProjectDirectory

    Invoke-TestInstall -ProjectPath $tempDir -PackageRoot $repoRoot

    $orchestratorRoot = Join-Path $tempDir '.orchestrator'
    Assert-Test -Condition (Test-Path -LiteralPath $orchestratorRoot) -Message '.orchestrator missing before uninstall'

    $uninstallCode = Invoke-TestOrchestratorCommand -Command 'uninstall' -ProjectPath $tempDir -PackageRoot $repoRoot -Force
    Assert-Test -Condition ($uninstallCode -eq 0) -Message ('uninstall exited with code {0}' -f $uninstallCode)

    $orchestratorRemoved = -not (Test-Path -LiteralPath $orchestratorRoot)
    Assert-Test -Condition $orchestratorRemoved -Message '.orchestrator still present after uninstall -Force'

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
