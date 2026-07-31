#Requires -Version 5.1
<#
.SYNOPSIS
    Migra aliases obsoletos de modelo em .orchestrator/config/models.json.

.DESCRIPTION
    bug-074 (continuacao) — o manifest aplica models.json com mode=merge, e
    o merge PRESERVA os valores do projeto: o alias ficticio `kimi-latest`
    (nunca existiu no CLI) ficou congelado nos 12 projetos mesmo apos o
    template ser corrigido para os aliases reais do ~/.kimi-code/config.toml
    (kimi-code/k3 etc.). Toda run com `-m kimi-latest` falharia.

    Patch cirurgico e idempotente: se clients.kimi.models tiver
    `kimi-latest` em qualquer tier, regrava os 4 tiers com os aliases
    reais. Nao toca em nenhum outro client nem em task_map. Backup unico.
#>
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Orchestrator.Common.ps1')

$projectRoot = Get-ProjectRoot -ProjectPath $ProjectPath
$modelsPath = Join-Path $projectRoot '.orchestrator\config\models.json'
if (-not (Test-Path -LiteralPath $modelsPath)) { exit 0 }

try {
    $models = Get-Content -LiteralPath $modelsPath -Raw -Encoding UTF8 | ConvertFrom-Json
}
catch {
    Write-Host '[AVISO] models.json invalido; migracao de aliases ignorada.'
    exit 0
}
if ($null -eq $models -or -not $models.PSObject.Properties['clients']) { exit 0 }
$clients = $models.clients
if (-not $clients.PSObject.Properties['kimi']) { exit 0 }
$kimi = $clients.kimi
if (-not $kimi.PSObject.Properties['models']) { exit 0 }

$stale = $false
foreach ($tier in @('fast', 'balanced', 'deep', 'max')) {
    if ($kimi.models.PSObject.Properties[$tier] -and [string]$kimi.models.$tier -eq 'kimi-latest') {
        $stale = $true
    }
}
if (-not $stale) { exit 0 }

$realAliases = [ordered]@{
    fast     = 'kimi-code/kimi-for-coding-highspeed'
    balanced = 'kimi-code/k3'
    deep     = 'kimi-code/k3'
    max      = 'kimi-code/k3'
}

if ($DryRun) {
    Write-Host ("[DRY-RUN] {0}: kimi-latest -> aliases reais (k3)" -f $modelsPath)
    exit 0
}

$backupPath = "$modelsPath.bak-bug074"
if (-not (Test-Path -LiteralPath $backupPath)) {
    Copy-Item -LiteralPath $modelsPath -Destination $backupPath -Force
}
$kimi.models = [pscustomobject]$realAliases
$json = $models | ConvertTo-Json -Depth 20
[System.IO.File]::WriteAllText($modelsPath, $json, [System.Text.UTF8Encoding]::new($false))
Write-Host ("[OK] {0}: aliases kimi migrados para k3" -f $modelsPath)
exit 0
