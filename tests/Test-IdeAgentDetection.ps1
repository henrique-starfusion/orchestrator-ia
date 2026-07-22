#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Test-Helpers.ps1')

$TestName = 'Test-IdeAgentDetection'
$tempDir = $null
$fakeBin = $null
$oldPath = $env:PATH
$exitCode = 1

try {
    $repoRoot = Get-TestRepoRoot
    $tempDir = New-TestProjectDirectory

    # projeto minimo: so a arvore .orchestrator/agents
    New-Item -ItemType Directory -Path (Join-Path $tempDir '.orchestrator\agents') -Force | Out-Null

    # cursor falso: se a deteccao executar o binario, grava um marcador
    $fakeBin = Join-Path $tempDir 'fakebin'
    New-Item -ItemType Directory -Path $fakeBin -Force | Out-Null
    $fakeCursor = Join-Path $fakeBin 'cursor.cmd'
    @(
        '@echo off',
        ('echo executado > "{0}\executed.flag"' -f $fakeBin),
        'echo fake-cursor 1.0.0'
    ) | Set-Content -LiteralPath $fakeCursor -Encoding ASCII

    # fake na frente do PATH: Get-Command cursor resolve pro fake
    $env:PATH = $fakeBin + ';' + $oldPath

    $detectCode = Invoke-TestScript -ScriptName 'Detect-Agents.ps1' -Arguments @{
        ProjectPath = $tempDir
    }
    Assert-Test -Condition ($detectCode -eq 0) -Message ('Detect-Agents saiu com codigo {0}' -f $detectCode)

    # 1) agente IDE NUNCA e executado
    $flagPath = Join-Path $fakeBin 'executed.flag'
    Assert-Test -Condition (-not (Test-Path -LiteralPath $flagPath)) -Message 'deteccao EXECUTOU o binario do cursor (IDE nao pode receber exec probe)'

    # 2) cursor registrado como available com sonda pulada
    $detectedPath = Join-Path $tempDir '.orchestrator\agents\detected.json'
    Assert-Test -Condition (Test-Path -LiteralPath $detectedPath) -Message 'detected.json nao gerado'
    $det = Get-Content -LiteralPath $detectedPath -Raw | ConvertFrom-Json
    $cursor = @($det.agents) | Where-Object { $_.name -eq 'cursor' } | Select-Object -First 1
    Assert-Test -Condition ($null -ne $cursor) -Message 'entrada cursor ausente em detected.json'
    Assert-Test -Condition ($cursor.status -eq 'available') -Message ('cursor.status = {0} (esperado available)' -f $cursor.status)
    Assert-Test -Condition ($cursor.version_error -eq 'skipped_ide') -Message ('cursor.version_error = {0} (esperado skipped_ide)' -f $cursor.version_error)

    Write-Host ('PASS: {0}' -f $TestName) -ForegroundColor Green
    $exitCode = 0
}
catch {
    Write-Host ('FAIL: {0} - {1}' -f $TestName, $_.Exception.Message) -ForegroundColor Red
}
finally {
    $env:PATH = $oldPath
    if ($tempDir) {
        Remove-TestProjectDirectory -Path $tempDir
    }
}

exit $exitCode
