#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Test-Helpers.ps1')

$TestName = 'Test-Upgrade'
$tempDir = $null
$exitCode = 1

try {
    $repoRoot = Get-TestRepoRoot
    $packageVersion = Get-PackageVersion -PackageRoot $repoRoot
    $tempDir = New-TestProjectDirectory

    Invoke-TestInstall -ProjectPath $tempDir -PackageRoot $repoRoot

    $versionPath = Get-OrchestratorPath -ProjectPath $tempDir -RelativePath 'VERSION'
    Set-Content -LiteralPath $versionPath -Value '0.0.1' -Encoding UTF8

    $upgradeCode = Invoke-TestOrchestratorCommand -Command 'upgrade' -ProjectPath $tempDir -PackageRoot $repoRoot
    Assert-Test -Condition ($upgradeCode -eq 0) -Message ('upgrade exited with code {0}' -f $upgradeCode)

    $workspaceVersion = (Get-Content -LiteralPath $versionPath -Raw -Encoding UTF8).Trim()
    Assert-Test -Condition ($workspaceVersion -eq $packageVersion) -Message (
        'VERSION not restored after upgrade: expected {0}, got {1}' -f $packageVersion, $workspaceVersion
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
