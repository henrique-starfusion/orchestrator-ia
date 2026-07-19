#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Test-Helpers.ps1')

$TestName = 'Test-AgentDetection'
$tempDir = $null
$exitCode = 1

try {
    $repoRoot = Get-TestRepoRoot
    $tempDir = New-TestProjectDirectory

    Invoke-TestInstall -ProjectPath $tempDir -PackageRoot $repoRoot

    $detectCode = Invoke-TestScript -ScriptName 'Detect-Agents.ps1' -Arguments @{
        ProjectPath = $tempDir
    }
    Assert-Test -Condition ($detectCode -eq 0) -Message ('Detect-Agents exited with code {0}' -f $detectCode)

    $detectedPath = Get-OrchestratorPath -ProjectPath $tempDir -RelativePath 'agents/detected.json'
    Assert-Test -Condition (Test-Path -LiteralPath $detectedPath) -Message 'agents/detected.json missing'

    $detected = Get-Content -LiteralPath $detectedPath -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-Test -Condition ($null -ne $detected.agents) -Message 'detected.json has no agents array'
    Assert-Test -Condition (@($detected.agents).Count -gt 0) -Message 'detected.json agents array is empty'

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
