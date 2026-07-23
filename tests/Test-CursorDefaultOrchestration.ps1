#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Test-Helpers.ps1')

$TestName = 'Test-CursorDefaultOrchestration'
$exitCode = 1
$repoRoot = Get-TestRepoRoot

try {
    $liveRules = Join-Path $repoRoot '.cursor\rules'
    $templateRules = Join-Path $repoRoot 'package\template\adapters\cursor\.cursor\rules'
    $ruleName = 'multiagent-orchestrator.mdc'
    $tokenRuleName = 'token-economy.mdc'

    $liveRulePath = Join-Path $liveRules $ruleName
    $templateRulePath = Join-Path $templateRules $ruleName
    $liveRule = Get-Content -LiteralPath $liveRulePath -Raw -Encoding UTF8
    $templateRule = Get-Content -LiteralPath $templateRulePath -Raw -Encoding UTF8

    # Literals with accents must not live in this .ps1: Windows PowerShell 5.1
    # reads scripts as system ANSI (cp1252) unless UTF-8 BOM is present.
    $modeHeading = '## Modo padr{0}o: orquestrador' -f [char]0x00E3
    $withoutAsking = 'sem o usu{0}rio pedir' -f [char]0x00E1
    $exceptionsHeading = '## Exce{0}{1}es' -f [char]0x00E7, [char]0x00F5
    $antiHeading = '## Anti-padr{0}es' -f [char]0x00F5
    $orderHeading = '## Ordem obrigat{0}ria' -f [char]0x00F3
    $prefHeading = '## Prefer{0}ncia' -f [char]0x00EA
    $chooseMenu = 'Analise cada solicita{0}{1}o e escolha entre:' -f [char]0x00E7, [char]0x00E3
    $trivialDoc = 'Pergunta / edi{0}{1}o trivial' -f [char]0x00E7, [char]0x00E3
    $bugFixDoc = 'Bug fix / mudan{0}a de l{1}gica (qualquer tamanho)' -f [char]0x00E7, [char]0x00F3

    Assert-Test -Condition ($liveRule -match 'alwaysApply:\s*true') -Message 'rule Cursor deve usar alwaysApply=true'
    Assert-Test -Condition ($liveRule.Contains($modeHeading)) -Message 'modo padrao obrigatorio ausente na rule Cursor'
    Assert-Test -Condition ($liveRule.Contains($withoutAsking)) -Message 'rule nao declara chamada automatica sem pedido do usuario'
    Assert-Test -Condition ($liveRule.Contains('## Gatilhos')) -Message 'secao Gatilhos ausente'
    Assert-Test -Condition ($liveRule.Contains($exceptionsHeading)) -Message 'secao Excecoes ausente'
    Assert-Test -Condition ($liveRule.Contains($antiHeading)) -Message 'secao Anti-padroes ausente'
    Assert-Test -Condition ($liveRule.Contains('bug fix NUNCA')) -Message 'bug fix ainda pode ser classificado como trivial'
    Assert-Test -Condition ($liveRule.Contains('arquivo:linha')) -Message 'rule nao exige evidencia para preferencias de projeto'
    Assert-Test -Condition ($liveRule -eq $templateRule) -Message 'rule Cursor live diverge do template do pacote'

    $liveTokenRulePath = Join-Path $liveRules $tokenRuleName
    $templateTokenRulePath = Join-Path $templateRules $tokenRuleName
    $liveTokenRule = Get-Content -LiteralPath $liveTokenRulePath -Raw -Encoding UTF8
    $templateTokenRule = Get-Content -LiteralPath $templateTokenRulePath -Raw -Encoding UTF8

    Assert-Test -Condition ($liveTokenRule.Contains($orderHeading)) -Message 'token-economy ainda nao define ordem obrigatoria'
    Assert-Test -Condition (-not $liveTokenRule.Contains($prefHeading)) -Message 'token-economy ainda usa preferencia opcional'
    Assert-Test -Condition ($liveTokenRule.Contains($withoutAsking)) -Message 'token-economy nao exige chamada automatica'
    Assert-Test -Condition ($liveTokenRule -eq $templateTokenRule) -Message 'token-economy live diverge do template do pacote'

    $runtimeCli = Get-Content -LiteralPath (Join-Path $repoRoot 'runtime\src\orchestrator_runtime\cli.py') -Raw -Encoding UTF8
    Assert-Test -Condition ($runtimeCli.Contains($modeHeading)) -Message 'cursor configure ainda gera rule sem modo padrao'
    Assert-Test -Condition (-not $runtimeCli.Contains($chooseMenu)) -Message 'cursor configure ainda gera menu permissivo'

    $docs = Get-Content -LiteralPath (Join-Path $repoRoot 'docs\cursor-front-controller.md') -Raw -Encoding UTF8
    Assert-Test -Condition (-not $docs.Contains($trivialDoc)) -Message 'docs ainda autorizam edicao trivial inline'
    Assert-Test -Condition ($docs.Contains($bugFixDoc)) -Message 'docs nao registram default para bug fix'

    $liveCursorDoc = Get-Content -LiteralPath (Join-Path $repoRoot 'CURSOR.md') -Raw -Encoding UTF8
    $templateCursorDoc = Get-Content -LiteralPath (Join-Path $repoRoot 'package\template\adapters\cursor\CURSOR.md') -Raw -Encoding UTF8
    Assert-Test -Condition ($liveCursorDoc.Contains('DEFAULT to `orchestrator_run`')) -Message 'CURSOR.md nao declara orchestrator_run como default'
    Assert-Test -Condition ($liveCursorDoc -eq $templateCursorDoc) -Message 'CURSOR.md live diverge do template do pacote'

    Write-Host ('PASS: {0}' -f $TestName) -ForegroundColor Green
    $exitCode = 0
}
catch {
    Write-Host ('FAIL: {0} - {1}' -f $TestName, $_.Exception.Message) -ForegroundColor Red
}

exit $exitCode
