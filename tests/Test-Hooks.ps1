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

    # bug-080 (0.4.57): o guard de codigo-fonte virou CONSULTIVO — exit 0 sempre,
    # aviso entregue como systemMessage no stdout. O sinal observavel passou a
    # ser o TEXTO; assertar exit 2 aqui testava o guard antigo e dava vermelho
    # num comportamento correto (foi o que aconteceu na suite de 0.4.59).
    function Invoke-Guard {
        param([string]$File = $payloadFile)
        # 2>nul DENTRO do cmd: redirecionar stderr de nativo pelo PowerShell 5.1
        # transforma cada linha em ErrorRecord e, com ErrorActionPreference=Stop,
        # o proprio aviso do guard derruba o teste.
        $out = cmd /c "node ""$guard"" < ""$File"" 2>nul"
        return [pscustomobject]@{ Code = $LASTEXITCODE; Out = ($out -join "`n") }
    }

    $first = Invoke-Guard
    Assert-Test -Condition ($first.Code -eq 0) -Message (
        'guard bloqueou a 1a edicao (bug-080: tem que ser consultivo, exit 0), veio {0}' -f $first.Code
    )
    Assert-Test -Condition ($first.Out -match 'ORQUESTRADOR NAO ACIONADO') -Message 'guard nao avisou na 1a edicao de codigo-fonte'

    $second = Invoke-Guard
    Assert-Test -Condition ([string]::IsNullOrWhiteSpace($second.Out)) -Message 'guard repetiu o aviso dentro da janela (viraria ruido a cada edicao)'

    # Envelhece o marcador alem da janela de rearme.
    $state = Get-Content -LiteralPath $stamp -Raw -Encoding UTF8 | ConvertFrom-Json
    $state.last_at = [int64]$state.last_at - (21 * 60000)
    # WriteAllText sem BOM: Set-Content -Encoding UTF8 no PS 5.1 escreve BOM e o
    # JSON.parse do node quebra — foi assim que o contador zerou na 1a tentativa.
    [System.IO.File]::WriteAllText(
        $stamp, ($state | ConvertTo-Json -Compress), (New-Object System.Text.UTF8Encoding($false))
    )

    $rearmed = Invoke-Guard
    Assert-Test -Condition ($rearmed.Out -match 'ORQUESTRADOR NAO ACIONADO') -Message 'guard nao rearmou apos a janela: volta a ser aviso unico'

    $final = Get-Content -LiteralPath $stamp -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-Test -Condition ($final.edits -eq 3) -Message (
        'contador de edicoes diretas errado: esperado 3, veio {0}' -f $final.edits
    )

    # Arquivo que nao e codigo-fonte nunca bloqueia.
    $docFile = Join-Path $tempDir 'guard-doc.json'
    Set-Content -LiteralPath $docFile `
        -Value '{"session_id":"test-rearm2","tool_input":{"file_path":"C:/proj/README.md"}}' `
        -Encoding ASCII
    $doc = Invoke-Guard -File $docFile
    Assert-Test -Condition ($doc.Code -eq 0) -Message 'guard bloqueou edicao de documentacao'
    Assert-Test -Condition ([string]::IsNullOrWhiteSpace($doc.Out)) -Message 'guard avisou em edicao de documentacao (alvo isento)'

    # bug-057: flag de filho e VALOR, nao presenca. '0' herdado nao silencia
    # o guard; so valor real ('1') identifica o executor delegado.
    $childFile = Join-Path $tempDir 'guard-child.json'
    Set-Content -LiteralPath $childFile `
        -Value '{"session_id":"test-childflag","tool_input":{"file_path":"C:/proj/src/other.py"}}' `
        -Encoding ASCII
    $env:ORCHESTRATOR_CHILD_AGENT = '0'
    $flagZero = Invoke-Guard -File $childFile
    Assert-Test -Condition ($flagZero.Out -match 'ORQUESTRADOR NAO ACIONADO') -Message 'guard silenciou com ORCHESTRATOR_CHILD_AGENT=0 (presence-based, bug-057)'
    $env:ORCHESTRATOR_CHILD_AGENT = '1'
    $flagOne = Invoke-Guard -File $childFile
    Assert-Test -Condition ($flagOne.Code -eq 0) -Message 'guard bloqueou o proprio executor delegado (ORCHESTRATOR_CHILD_AGENT=1)'
    Assert-Test -Condition ([string]::IsNullOrWhiteSpace($flagOne.Out)) -Message 'guard avisou o executor delegado (ORCHESTRATOR_CHILD_AGENT=1)'
    Remove-Item Env:ORCHESTRATOR_CHILD_AGENT -ErrorAction SilentlyContinue

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
