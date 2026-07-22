#Requires -Version 5.1
<#
.SYNOPSIS
  Checks anti-legado: falha se artefatos obsoletos reaparecerem no pacote.
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Test-Helpers.ps1')

$TestName = 'Test-NoLegacyArtifacts'
$exitCode = 1
$repoRoot = Get-TestRepoRoot

try {
    # Fonte canônica não pode ser .claude ou .ai no template
    Assert-Test -Condition (-not (Test-Path -LiteralPath (Join-Path $repoRoot 'package\template\.claude'))) -Message 'template .claude/ nao deve existir como fonte canonica'
    Assert-Test -Condition (-not (Test-Path -LiteralPath (Join-Path $repoRoot 'package\template\.ai'))) -Message 'template .ai/ nao deve existir'
    Assert-Test -Condition (Test-Path -LiteralPath (Join-Path $repoRoot 'package\template\.orchestrator')) -Message '.orchestrator template ausente'

    # Prompt legado nao pode voltar a docs/ operacional (apenas archive)
    Assert-Test -Condition (-not (Test-Path -LiteralPath (Join-Path $repoRoot 'docs\legacy\prompt_ambiente_multiagente.md'))) -Message 'prompt legado deve estar em docs/archive/prompts/'
    Assert-Test -Condition (Test-Path -LiteralPath (Join-Path $repoRoot 'docs\archive\prompts\prompt_ambiente_multiagente.md')) -Message 'arquivo arquivado do prompt ausente'

    # Cursor profile nao e worker
    $cursorProfile = Join-Path $repoRoot 'package\template\.orchestrator\agents\profiles\cursor.json'
    Assert-Test -Condition (Test-Path -LiteralPath $cursorProfile) -Message 'cursor profile ausente'
    $cursor = Get-Content -LiteralPath $cursorProfile -Raw | ConvertFrom-Json
    Assert-Test -Condition ($cursor.kind -eq 'ide-client') -Message 'cursor.kind deve ser ide-client'
    Assert-Test -Condition ($cursor.executable -eq $false) -Message 'cursor.executable deve ser false'

    # OpenWolf/Graphify nao sao obrigatorios no install padrao (flags existem, default opt-in)
    $installScript = Get-Content -LiteralPath (Join-Path $repoRoot 'scripts\Install-Orchestrator.ps1') -Raw
    Assert-Test -Condition ($installScript -match '\$doInitTools = \$false') -Message 'InitTools deve ser opt-in (doInitTools=false por padrao)'
    Assert-Test -Condition ($installScript -match '\$doGlobalTools = \$false') -Message 'GlobalTools deve ser opt-in'

    # Manifest nao referencia sources inexistentes
    $manifest = Get-Content -LiteralPath (Join-Path $repoRoot 'package\manifest.json') -Raw | ConvertFrom-Json
    foreach ($f in @($manifest.files)) {
        $src = Join-Path $repoRoot ('package\' + ($f.source -replace '/', '\'))
        Assert-Test -Condition (Test-Path -LiteralPath $src) -Message ("manifest source ausente: {0}" -f $f.source)
    }

    # Sem docs/superpowers ativo (foi arquivado)
    Assert-Test -Condition (-not (Test-Path -LiteralPath (Join-Path $repoRoot 'docs\superpowers'))) -Message 'docs/superpowers deve ter sido arquivado'

    Write-Host ('PASS: {0}' -f $TestName) -ForegroundColor Green
    $exitCode = 0
}
catch {
    Write-Host ('FAIL: {0} - {1}' -f $TestName, $_.Exception.Message) -ForegroundColor Red
}

exit $exitCode
