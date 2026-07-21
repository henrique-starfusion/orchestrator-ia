#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Test-Helpers.ps1')

$TestName = 'Test-LegacyCleanupAggressive'
$tempDir = $null
$tempDir2 = $null
$exitCode = 1

try {
    $repoRoot = Get-TestRepoRoot
    $tempDir = New-TestProjectDirectory
    New-Item -ItemType Directory -Path (Join-Path $tempDir '.ai') -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $tempDir 'orchestrator') -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $tempDir 'orchestrator\old.txt') -Value 'x' -Encoding UTF8

    # Sem -Force deve falhar na remocao aggressive
    $installer = Join-Path $repoRoot 'scripts\Install-Orchestrator.ps1'
    & $installer install -ProjectPath $tempDir -PackageRoot $repoRoot -NonInteractive -SkipGlobalTools -LegacyCleanupMode aggressive
    Assert-Test -Condition ($LASTEXITCODE -ne 0) -Message 'aggressive sem -Force deveria falhar'

    $tempDir2 = New-TestProjectDirectory
    New-Item -ItemType Directory -Path (Join-Path $tempDir2 '.ai') -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $tempDir2 'orchestrator') -Force | Out-Null
    Invoke-TestInstall -ProjectPath $tempDir2 -PackageRoot $repoRoot -ExtraArgs @('-LegacyCleanupMode', 'aggressive', '-Force')
    Assert-Test -Condition (-not (Test-Path -LiteralPath (Join-Path $tempDir2 '.ai'))) -Message '.ai nao removido em aggressive+Force'
    Assert-Test -Condition (-not (Test-Path -LiteralPath (Join-Path $tempDir2 'orchestrator'))) -Message 'orchestrator/ nao removido'

    Write-Host ('PASS: {0}' -f $TestName) -ForegroundColor Green
    $exitCode = 0
}
catch {
    Write-Host ('FAIL: {0} - {1}' -f $TestName, $_.Exception.Message) -ForegroundColor Red
}
finally {
    if ($tempDir) { Remove-TestProjectDirectory -Path $tempDir }
    if ($tempDir2) { Remove-TestProjectDirectory -Path $tempDir2 }
}
exit $exitCode
