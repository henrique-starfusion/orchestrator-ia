#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Test-Helpers.ps1')

$TestName = 'Test-Install'
$tempDir = $null
$exitCode = 1

try {
    $repoRoot = Get-TestRepoRoot
    $packageVersion = Get-PackageVersion -PackageRoot $repoRoot
    $tempDir = New-TestProjectDirectory

    Invoke-TestInstall -ProjectPath $tempDir -PackageRoot $repoRoot

    $versionPath = Get-OrchestratorPath -ProjectPath $tempDir -RelativePath 'VERSION'
    Assert-Test -Condition (Test-Path -LiteralPath $versionPath) -Message '.orchestrator/VERSION missing after install'

    $workspaceVersion = (Get-Content -LiteralPath $versionPath -Raw -Encoding UTF8).Trim()
    Assert-Test -Condition ($workspaceVersion -eq $packageVersion) -Message (
        'VERSION mismatch: expected {0}, got {1}' -f $packageVersion, $workspaceVersion
    )

    $policiesPath = Get-OrchestratorPath -ProjectPath $tempDir -RelativePath 'config/policies.json'
    Assert-Test -Condition (Test-Path -LiteralPath $policiesPath) -Message 'config/policies.json missing'

    try {
        $null = Get-Content -LiteralPath $policiesPath -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        throw ('config/policies.json is not valid JSON: {0}' -f $_.Exception.Message)
    }

    $skillPath = Get-OrchestratorPath -ProjectPath $tempDir -RelativePath 'skills/orchestrate/SKILL.md'
    Assert-Test -Condition (Test-Path -LiteralPath $skillPath) -Message 'skills/orchestrate/SKILL.md missing'

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
