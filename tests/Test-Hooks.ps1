#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Test-Helpers.ps1')

$TestName = 'Test-Hooks'
$tempDir = $null
$exitCode = 1

try {
    $repoRoot = Get-TestRepoRoot
    $tempDir = New-TestProjectDirectory

    Invoke-TestInstall -ProjectPath $tempDir -PackageRoot $repoRoot

    $validateCode = Invoke-TestScript -ScriptName 'Validate-Hooks.ps1' -Arguments @{
        ProjectPath = $tempDir
    }
    Assert-Test -Condition ($validateCode -eq 0) -Message ('Validate-Hooks exited with code {0}' -f $validateCode)

    # 0.4.34 — o guard tem que REARMAR. Antes avisava uma vez por sessao: numa
    # sessao de 12h no proprio repo do orquestrador ele apareceu as 01:03 e nunca
    # mais, com dezenas de arquivos de codigo editados direto depois disso.
    $guard = Join-Path $tempDir '.orchestrator\hooks\active\orchestrator-guard.js'
    Assert-Test -Condition (Test-Path -LiteralPath $guard) -Message 'orchestrator-guard.js ausente apos install'

    $env:CLAUDE_PROJECT_DIR = $tempDir
    Remove-Item Env:ORCHESTRATOR_CHILD_AGENT -ErrorAction SilentlyContinue
    Remove-Item Env:ORCHESTRATOR_GUARD -ErrorAction SilentlyContinue
    $stamp = Join-Path $tempDir '.orchestrator\runtime\guard\test-rearm.notified'
    # stdin via REDIRECT, nao via pipe: o pipe do PowerShell nao chega ao
    # fs.readFileSync(0) do node — o hook leria vazio e sairia 0, dando um teste
    # verde para um guard que nunca bloqueou. O Claude Code entrega o payload
    # corretamente; a limitacao e do harness.
    $payloadFile = Join-Path $tempDir 'guard-payload.json'
    Set-Content -LiteralPath $payloadFile `
        -Value '{"session_id":"test-rearm","tool_input":{"file_path":"C:/proj/src/app.py"}}' `
        -Encoding ASCII

    function Invoke-Guard {
        param([string]$File = $payloadFile)
        # 2>nul DENTRO do cmd: redirecionar stderr de nativo pelo PowerShell 5.1
        # transforma cada linha em ErrorRecord e, com ErrorActionPreference=Stop,
        # o proprio aviso do guard derruba o teste.
        cmd /c "node ""$guard"" < ""$File"" 2>nul" | Out-Null
        return $LASTEXITCODE
    }

    Assert-Test -Condition ((Invoke-Guard) -eq 2) -Message 'guard nao bloqueou a 1a edicao de codigo-fonte'
    Assert-Test -Condition ((Invoke-Guard) -eq 0) -Message 'guard bloqueou de novo dentro da janela (travaria a sessao)'

    # Envelhece o marcador alem da janela de rearme.
    $state = Get-Content -LiteralPath $stamp -Raw -Encoding UTF8 | ConvertFrom-Json
    $state.last_at = [int64]$state.last_at - (21 * 60000)
    # WriteAllText sem BOM: Set-Content -Encoding UTF8 no PS 5.1 escreve BOM e o
    # JSON.parse do node quebra — foi assim que o contador zerou na 1a tentativa.
    [System.IO.File]::WriteAllText(
        $stamp, ($state | ConvertTo-Json -Compress), (New-Object System.Text.UTF8Encoding($false))
    )

    Assert-Test -Condition ((Invoke-Guard) -eq 2) -Message 'guard nao rearmou apos a janela: volta a ser aviso unico'

    $final = Get-Content -LiteralPath $stamp -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-Test -Condition ($final.edits -eq 3) -Message (
        'contador de edicoes diretas errado: esperado 3, veio {0}' -f $final.edits
    )

    # Arquivo que nao e codigo-fonte nunca bloqueia.
    $docFile = Join-Path $tempDir 'guard-doc.json'
    Set-Content -LiteralPath $docFile `
        -Value '{"session_id":"test-rearm2","tool_input":{"file_path":"C:/proj/README.md"}}' `
        -Encoding ASCII
    Assert-Test -Condition ((Invoke-Guard -File $docFile) -eq 0) -Message 'guard bloqueou edicao de documentacao'

    Remove-Item Env:CLAUDE_PROJECT_DIR -ErrorAction SilentlyContinue

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
