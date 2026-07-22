#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Test-Helpers.ps1')

$TestName = 'Test-DispatchMonitoring'
$tempDir = $null
$originalPath = $env:Path
$originalChildFlag = $env:ORCHESTRATOR_CHILD_AGENT
$exitCode = 1

try {
    $repoRoot = Get-TestRepoRoot
    $tempDir = New-TestProjectDirectory
    . (Join-Path $repoRoot 'scripts\Orchestrator.Common.ps1')

    # --- [A] Invoke-ExternalCommand: exit code e streams preservados ---
    $binDir = Join-Path $tempDir 'bin'
    New-Item -ItemType Directory -Path $binDir -Force | Out-Null

    $fakeCmd = Join-Path $binDir 'fake.cmd'
    Set-Content -LiteralPath $fakeCmd -Encoding Ascii -Value @'
@echo off
echo hello-stdout
echo oops-stderr 1>&2
exit /b 3
'@

    $r = Invoke-ExternalCommand -FilePath $fakeCmd -TimeoutSeconds 30
    Assert-Test -Condition ($r.exit_code -eq 3) -Message ('exit_code = {0} (esperado 3)' -f $r.exit_code)
    Assert-Test -Condition (-not $r.timed_out) -Message 'timed_out inesperado no caso de exit 3'
    Assert-Test -Condition ($r.stdout -match 'hello-stdout') -Message ('stdout perdido: [{0}]' -f $r.stdout)
    Assert-Test -Condition ($r.stderr -match 'oops-stderr') -Message ('stderr perdido: [{0}]' -f $r.stderr)

    # --- [B] Timeout mata processo mas PRESERVA saida parcial ---
    $sleeperCmd = Join-Path $binDir 'sleeper.cmd'
    Set-Content -LiteralPath $sleeperCmd -Encoding Ascii -Value @'
@echo off
echo BEFORE-SLEEP
ping -n 30 127.0.0.1 > nul
'@

    $r2 = Invoke-ExternalCommand -FilePath $sleeperCmd -TimeoutSeconds 3
    Assert-Test -Condition ($r2.timed_out) -Message 'sleeper nao marcou timed_out'
    Assert-Test -Condition ($r2.stdout -match 'BEFORE-SLEEP') -Message ('saida parcial descartada no timeout: [{0}]' -f $r2.stdout)
    Assert-Test -Condition ($r2.stderr -match 'Process timed out') -Message 'stderr sem marcador de timeout'

    # --- [C] Dispatch integrado: claude falso no PATH -> status.json completed ---
    New-Item -ItemType Directory -Path (Join-Path $tempDir '.orchestrator\config') -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $tempDir '.orchestrator\agents\profiles') -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $repoRoot 'package\template\.orchestrator\config\models.json') `
        -Destination (Join-Path $tempDir '.orchestrator\config\models.json') -Force
    Copy-Item -LiteralPath (Join-Path $repoRoot 'package\template\.orchestrator\agents\profiles\claude.json') `
        -Destination (Join-Path $tempDir '.orchestrator\agents\profiles\claude.json') -Force
    @{ version = '0.1.0'; detected_at = '2026-07-21T00:00:00'; agents = @(@{ name = 'claude'; status = 'available'; command = 'claude.cmd' }) } |
        ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $tempDir '.orchestrator\agents\detected.json') -Encoding UTF8

    Set-Content -LiteralPath (Join-Path $binDir 'claude.cmd') -Encoding Ascii -Value @'
@echo off
echo FAKE-CLAUDE-OUT %*
exit /b 0
'@

    $env:Path = $binDir + ';' + $env:Path
    $env:ORCHESTRATOR_CHILD_AGENT = ''
    $dispatchScript = Join-Path $repoRoot 'scripts\Invoke-RoutedAgent.ps1'

    $out1 = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $dispatchScript `
        -ProjectPath $tempDir -TaskClass docs -Client claude -Prompt 'PING' 2>&1 | Out-String
    $code1 = $LASTEXITCODE
    Assert-Test -Condition ($code1 -eq 0) -Message ('dispatch completed saiu com {0}: {1}' -f $code1, $out1)
    Assert-Test -Condition ($out1 -match '  > FAKE-CLAUDE-OUT') -Message ('saida ao vivo ausente (prefixo "  > "): {0}' -f $out1)

    $resultsDir = Join-Path $tempDir '.orchestrator\runtime\results'
    $statusFile = Get-ChildItem -LiteralPath $resultsDir -Filter '*-docs-status.json' | Select-Object -First 1
    Assert-Test -Condition ($null -ne $statusFile) -Message 'status.json nao gravado no caso completed'
    $statusJson = Get-Content -LiteralPath $statusFile.FullName -Raw | ConvertFrom-Json
    Assert-Test -Condition ($statusJson.status -eq 'completed') -Message ('status = {0} (esperado completed)' -f $statusJson.status)
    Assert-Test -Condition ($statusJson.exit_code -eq 0) -Message ('status exit_code = {0} (esperado 0)' -f $statusJson.exit_code)
    $resultFile = Join-Path $resultsDir $statusJson.result_file
    Assert-Test -Condition ((Get-Content -LiteralPath $resultFile -Raw) -match 'FAKE-CLAUDE-OUT.*PING') -Message 'result.txt sem saida do agente'

    # --- [D] Dispatch com falha: exit 7 -> status failed + [ERRO] + exit propagado ---
    Set-Content -LiteralPath (Join-Path $binDir 'claude.cmd') -Encoding Ascii -Value @'
@echo off
echo BOOM 1>&2
exit /b 7
'@

    $out2 = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $dispatchScript `
        -ProjectPath $tempDir -TaskClass implementation -Client claude -Prompt 'PING' 2>&1 | Out-String
    $code2 = $LASTEXITCODE
    Assert-Test -Condition ($code2 -eq 7) -Message ('dispatch failed saiu com {0} (esperado 7): {1}' -f $code2, $out2)
    Assert-Test -Condition ($out2 -match '\[ERRO\] status=failed') -Message ('[ERRO] ausente na falha: {0}' -f $out2)

    $statusFile2 = Get-ChildItem -LiteralPath $resultsDir -Filter '*-implementation-status.json' | Select-Object -First 1
    Assert-Test -Condition ($null -ne $statusFile2) -Message 'status.json nao gravado no caso failed'
    $statusJson2 = Get-Content -LiteralPath $statusFile2.FullName -Raw | ConvertFrom-Json
    Assert-Test -Condition ($statusJson2.status -eq 'failed') -Message ('status = {0} (esperado failed)' -f $statusJson2.status)
    Assert-Test -Condition ($statusJson2.exit_code -eq 7) -Message ('status exit_code = {0} (esperado 7)' -f $statusJson2.exit_code)

    Write-Host ('PASS: {0}' -f $TestName) -ForegroundColor Green
    $exitCode = 0
}
catch {
    Write-Host ('FAIL: {0} - {1}' -f $TestName, $_.Exception.Message) -ForegroundColor Red
}
finally {
    $env:Path = $originalPath
    $env:ORCHESTRATOR_CHILD_AGENT = $originalChildFlag
    if ($tempDir) {
        Remove-TestProjectDirectory -Path $tempDir
    }
}

exit $exitCode
