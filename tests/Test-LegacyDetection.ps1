#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Test-Helpers.ps1')

$TestName = 'Test-LegacyDetection'
$tempDir = $null
$exitCode = 1

try {
    $repoRoot = Get-TestRepoRoot
    $tempDir = New-TestProjectDirectory

    New-Item -ItemType Directory -Path (Join-Path $tempDir '.ai') -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $tempDir 'graphify-out') -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $tempDir '.claude\memory') -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $tempDir '.claude\VERSION') -Value '0.0.1' -Encoding UTF8
    Set-Content -LiteralPath (Join-Path $tempDir '.claude\memory\index.json') -Value '{}' -Encoding UTF8
    New-Item -ItemType Directory -Path (Join-Path $tempDir '.orchestrator\runtime\reports') -Force | Out-Null

    $out = Join-Path $tempDir '.orchestrator\runtime\reports\legacy-inventory.json'
    & (Join-Path $repoRoot 'scripts\Detect-LegacyConfigurations.ps1') -ProjectPath $tempDir -OutputPath $out
    Assert-Test -Condition ($LASTEXITCODE -eq 0) -Message 'Detect exit != 0'
    Assert-Test -Condition (Test-Path -LiteralPath $out) -Message 'inventory ausente'

    $doc = Get-Content -LiteralPath $out -Raw | ConvertFrom-Json
    Assert-Test -Condition ($doc.item_count -ge 3) -Message 'esperava ao menos .ai, graphify-out, .claude/*'
    $paths = @($doc.items | ForEach-Object { $_.path })
    Assert-Test -Condition ($paths -contains '.ai') -Message '.ai nao detectado'
    Assert-Test -Condition ($paths -contains 'graphify-out') -Message 'graphify-out nao detectado'

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
