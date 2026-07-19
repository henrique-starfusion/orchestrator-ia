#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Test-Helpers.ps1')

$TestName = 'Test-Idempotency'
$tempDir = $null
$exitCode = 1

try {
    $repoRoot = Get-TestRepoRoot
    $tempDir = New-TestProjectDirectory

    Invoke-TestInstall -ProjectPath $tempDir -PackageRoot $repoRoot

    $policiesPath = Get-OrchestratorPath -ProjectPath $tempDir -RelativePath 'config/policies.json'
    $versionPath = Get-OrchestratorPath -ProjectPath $tempDir -RelativePath 'VERSION'

    $policiesHashBefore = Get-TestFileSha256 -Path $policiesPath
    $versionHashBefore = Get-TestFileSha256 -Path $versionPath

    Invoke-TestInstall -ProjectPath $tempDir -PackageRoot $repoRoot

    $policiesHashAfter = Get-TestFileSha256 -Path $policiesPath
    $versionHashAfter = Get-TestFileSha256 -Path $versionPath

    Assert-Test -Condition ($policiesHashBefore -eq $policiesHashAfter) -Message (
        'policies.json changed after second install (before={0}, after={1})' -f $policiesHashBefore, $policiesHashAfter
    )
    Assert-Test -Condition ($versionHashBefore -eq $versionHashAfter) -Message (
        'VERSION changed after second install (before={0}, after={1})' -f $versionHashBefore, $versionHashAfter
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
