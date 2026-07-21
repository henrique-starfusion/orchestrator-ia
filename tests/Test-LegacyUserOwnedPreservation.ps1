#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Test-Helpers.ps1')

$TestName = 'Test-LegacyUserOwnedPreservation'
$tempDir = $null
$exitCode = 1

try {
    $repoRoot = Get-TestRepoRoot
    $tempDir = New-TestProjectDirectory
    foreach ($d in @('.aider', '.continue', '.cline')) {
        $dir = Join-Path $tempDir $d
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $dir 'user.json') -Value '{}' -Encoding UTF8
    }
    Invoke-TestInstall -ProjectPath $tempDir -PackageRoot $repoRoot
    foreach ($d in @('.aider', '.continue', '.cline')) {
        $file = Join-Path (Join-Path $tempDir $d) 'user.json'
        Assert-Test -Condition (Test-Path -LiteralPath $file) -Message ("user-owned removido: {0}" -f $d)
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
