#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Test-Helpers.ps1')

$TestName = 'Test-Repair'
$tempDir = $null
$exitCode = 1

try {
    $repoRoot = Get-TestRepoRoot
    $tempDir = New-TestProjectDirectory

    Invoke-TestInstall -ProjectPath $tempDir -PackageRoot $repoRoot

    $policiesPath = Get-OrchestratorPath -ProjectPath $tempDir -RelativePath 'config/policies.json'
    Remove-Item -LiteralPath $policiesPath -Force
    Assert-Test -Condition (-not (Test-Path -LiteralPath $policiesPath)) -Message 'policies.json was not deleted for repair test'

    $repairCode = Invoke-TestOrchestratorCommand -Command 'repair' -ProjectPath $tempDir -PackageRoot $repoRoot
    Assert-Test -Condition ($repairCode -eq 0) -Message ('repair exited with code {0}' -f $repairCode)

    Assert-Test -Condition (Test-Path -LiteralPath $policiesPath) -Message 'policies.json was not restored by repair'

    try {
        $null = Get-Content -LiteralPath $policiesPath -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        throw ('Restored policies.json is not valid JSON: {0}' -f $_.Exception.Message)
    }

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
