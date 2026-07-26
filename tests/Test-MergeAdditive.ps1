#Requires -Version 5.1
<#
.SYNOPSIS
    bug-003 — update aditivo em arquivos mode=merge: chave nova do template
    entra; valor customizado pelo usuario NUNCA e sobrescrito.
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Test-Helpers.ps1')
. (Join-Path (Get-TestScriptsRoot) 'Orchestrator.Common.ps1')

$TestName = 'Test-MergeAdditive'
$tempDir = $null
$exitCode = 1

try {
    $tempDir = New-TestProjectDirectory
    $templatePath = Join-Path $tempDir 'template.json'
    $destPath = Join-Path $tempDir 'dest.json'

    # Template tem chave nova de topo (model_flag), chave nova aninhada
    # (limits.stale_received_ttl_hours) e valor default divergente do usuario.
    @'
{
  "version": "0.4.26",
  "clients": {
    "opencode": { "model": "default", "model_flag": "--model" },
    "claude":   { "model": "claude-sonnet-5", "model_flag": "--model" }
  },
  "limits": { "maximum_iterations": 3, "stale_received_ttl_hours": 6 }
}
'@ | Set-Content -LiteralPath $templatePath -Encoding UTF8

    # Destino do usuario: sem model_flag, sem stale_received_ttl_hours,
    # com maximum_iterations customizado (9) e um bloco proprio.
    @'
{
  "version": "0.4.19",
  "clients": {
    "opencode": { "model": "default" },
    "claude":   { "model": "claude-opus-5" }
  },
  "limits": { "maximum_iterations": 9 },
  "meu_bloco": { "preservar": true }
}
'@ | Set-Content -LiteralPath $destPath -Encoding UTF8

    $changed = Merge-JsonFileAdditive -TemplatePath $templatePath -DestinationPath $destPath
    Assert-Test -Condition ($changed -eq $true) -Message 'merge aditivo deveria reportar mudanca'

    $result = Get-Content -LiteralPath $destPath -Raw -Encoding UTF8 | ConvertFrom-Json

    # Chaves NOVAS entraram (o caso do GuardLine que ficou sem model_flag)
    Assert-Test -Condition ($result.clients.opencode.model_flag -eq '--model') -Message 'model_flag novo deve ser injetado'
    Assert-Test -Condition ($null -ne $result.limits.PSObject.Properties['stale_received_ttl_hours']) -Message 'chave aninhada nova deve entrar'
    Assert-Test -Condition ($result.limits.stale_received_ttl_hours -eq 6) -Message 'valor da chave nova vem do template'

    # Valores do usuario PRESERVADOS
    Assert-Test -Condition ($result.limits.maximum_iterations -eq 9) -Message 'valor customizado do usuario nao pode ser sobrescrito'
    Assert-Test -Condition ($result.clients.claude.model -eq 'claude-opus-5') -Message 'modelo escolhido pelo usuario preservado'
    Assert-Test -Condition ($result.version -eq '0.4.19') -Message 'version do destino nao e sobrescrita pelo template'
    Assert-Test -Condition ($result.meu_bloco.preservar -eq $true) -Message 'bloco proprio do usuario preservado'

    # Idempotencia: segunda passada nao muda nada
    $again = Merge-JsonFileAdditive -TemplatePath $templatePath -DestinationPath $destPath
    Assert-Test -Condition ($again -eq $false) -Message 'segunda passada deve ser no-op (idempotente)'

    # Nao-JSON e ignorado com seguranca
    $txtDest = Join-Path $tempDir 'nota.md'
    Set-Content -LiteralPath $txtDest -Value 'conteudo do usuario' -Encoding UTF8
    $skipped = Merge-JsonFileAdditive -TemplatePath $templatePath -DestinationPath $txtDest
    Assert-Test -Condition ($skipped -eq $false) -Message 'arquivo nao-JSON deve ser ignorado'
    Assert-Test -Condition ((Get-Content -LiteralPath $txtDest -Raw) -match 'conteudo do usuario') -Message 'arquivo nao-JSON intacto'

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
