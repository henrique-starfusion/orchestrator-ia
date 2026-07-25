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

    # Dry-run: atualiza (ou tenta) agentes available — exit 0
    $dryRunCode = Invoke-TestScript -ScriptName 'Update-Agents.ps1' -Arguments @{
        ProjectPath  = $tempDir
        UpdateAgents = [switch]::Present
        DryRun       = [switch]::Present
    }
    Assert-Test -Condition ($dryRunCode -eq 0) -Message ('Update-Agents -DryRun exited with code {0}' -f $dryRunCode)

    # Sem UpdateAgents ainda atualiza (0.4.17+ default no script quando invocado)
    $defaultCode = Invoke-TestScript -ScriptName 'Update-Agents.ps1' -Arguments @{
        ProjectPath = $tempDir
        DryRun      = [switch]::Present
    }
    Assert-Test -Condition ($defaultCode -eq 0) -Message (
        'Update-Agents default dry-run exited with code {0}' -f $defaultCode
    )

    # Pipeline install com -SkipAgentUpdates nao deve falhar
    $skipCode = Invoke-TestScript -ScriptName 'Install-Orchestrator.ps1' -Arguments @{
        Command          = 'verify'
        ProjectPath      = $tempDir
        PackageRoot      = $repoRoot
        SkipAgentUpdates = [switch]::Present
    }
    Assert-Test -Condition ($skipCode -eq 0) -Message (
        'verify -SkipAgentUpdates exited with code {0}' -f $skipCode
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
