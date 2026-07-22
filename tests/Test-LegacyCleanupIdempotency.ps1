#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Test-Helpers.ps1')

$TestName = 'Test-LegacyCleanupIdempotency'
$tempDir = $null
$exitCode = 1

try {
    $repoRoot = Get-TestRepoRoot
    $tempDir = New-TestProjectDirectory
    New-Item -ItemType Directory -Path (Join-Path $tempDir '.ai') -Force | Out-Null

    Invoke-TestInstall -ProjectPath $tempDir -PackageRoot $repoRoot
    Assert-Test -Condition (-not (Test-Path -LiteralPath (Join-Path $tempDir '.ai'))) -Message 'primeira passagem nao removeu .ai'

    Invoke-TestInstall -ProjectPath $tempDir -PackageRoot $repoRoot
    $removed = Join-Path $tempDir '.orchestrator\runtime\reports\legacy-removed.json'
    if (Test-Path -LiteralPath $removed) {
        $doc = Get-Content -LiteralPath $removed -Raw | ConvertFrom-Json
        $count = @($doc.removed).Count
        Assert-Test -Condition ($count -eq 0) -Message ('segunda passagem removeu itens inesperados: {0}' -f $count)
    }

    Write-Host ('PASS: {0}' -f $TestName) -ForegroundColor Green
    $exitCode = 0
}
catch {
    Write-Host ('FAIL: {0} - {1}' -f $TestName, $_.Exception.Message) -ForegroundColor Red
}
finally {
    if ($tempDir) { Remove-TestProjectDirectory -Path $tempDir }
}
exit $exitCode
