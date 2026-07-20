#Requires -Version 5.1
<#
.SYNOPSIS
    Resolve task_class + client -> model usando .orchestrator/config/models.json
#>
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [Parameter(Mandatory = $true)]
    [string]$TaskClass,
    [ValidateSet('claude', 'codex', 'cursor', 'gemini', 'opencode', 'kimi', 'auto')]
    [string]$Client = 'auto',
    [switch]$Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Orchestrator.Common.ps1')

$projectRoot = Get-ProjectRoot -ProjectPath $ProjectPath
$modelsPath = Join-Path (Get-OrchestratorRoot -ProjectPath $projectRoot) 'config\models.json'
if (-not (Test-Path -LiteralPath $modelsPath)) {
    throw "models.json ausente: $modelsPath (rode orchestrator update)"
}

$models = Get-JsonFileContent -Path $modelsPath
$taskClass = $TaskClass.Trim().ToLowerInvariant()

if (-not $models.task_classes.PSObject.Properties[$taskClass]) {
    throw ("task_class desconhecida: {0}. Veja config/models.json" -f $taskClass)
}

$tier = [string]$models.task_classes.$taskClass.tier

function Resolve-ClientName {
    param([string]$Requested)
    if ($Requested -ne 'auto') { return $Requested }

    $detectedPath = Join-Path (Get-OrchestratorRoot -ProjectPath $projectRoot) 'agents\detected.json'
    $order = @('claude', 'cursor', 'codex', 'gemini', 'opencode', 'kimi')
    if (Test-Path -LiteralPath $detectedPath) {
        $det = Get-JsonFileContent -Path $detectedPath
        $available = @()
        if ($det.agents) {
            foreach ($a in @($det.agents)) {
                if ($a.available -eq $true -or $a.status -eq 'available') {
                    $available += [string]$a.id
                    if ($a.name) { $available += [string]$a.name }
                }
            }
        }
        foreach ($c in $order) {
            if ($available -contains $c) { return $c }
            if (Resolve-CommandExecutable -Name $c) { return $c }
        }
    }

    foreach ($c in $order) {
        if (Resolve-CommandExecutable -Name $c) { return $c }
    }
    return 'cursor'
}

$clientName = Resolve-ClientName -Requested $Client
$clientCfg = $models.clients.$clientName
if ($null -eq $clientCfg) {
    throw ("cliente ausente em models.json: {0}" -f $clientName)
}

$modelKey = $null
$hasTaskMap = $null -ne $clientCfg.PSObject.Properties['task_map']
$hasAliases = $null -ne $clientCfg.PSObject.Properties['aliases']
$hasModels = $null -ne $clientCfg.PSObject.Properties['models']

if ($hasTaskMap -and $clientCfg.task_map.PSObject.Properties[$taskClass]) {
    $modelKey = [string]$clientCfg.task_map.$taskClass
}
elseif ($hasAliases -and $clientCfg.aliases.PSObject.Properties[$tier]) {
    $modelKey = [string]$clientCfg.aliases.$tier
}
else {
    $modelKey = $tier
}

$modelId = $modelKey
if ($hasModels -and $clientCfg.models.PSObject.Properties[$modelKey]) {
    $modelId = [string]$clientCfg.models.$modelKey
}

$alias = $null
if ($hasAliases -and $clientCfg.aliases.PSObject.Properties[$tier]) {
    $alias = [string]$clientCfg.aliases.$tier
}
# Para Claude, task_map pode apontar direto para alias (haiku/sonnet/opus/fable)
if ($hasAliases -and $clientCfg.aliases.PSObject.Properties.Name -contains $modelKey) {
    $alias = $modelKey
}
elseif ($modelKey -in @('haiku', 'sonnet', 'opus', 'fable')) {
    $alias = $modelKey
}

$flag = $null
if ($clientCfg.PSObject.Properties['model_flag']) {
    $flag = [string]$clientCfg.model_flag
}

$result = [ordered]@{
    task_class   = $taskClass
    tier         = $tier
    client       = $clientName
    model_key    = $modelKey
    model        = $modelId
    alias        = $alias
    model_flag   = $flag
    cursor_slug  = $null
    invoke_hint  = $null
}

if ($clientName -eq 'cursor') {
    $result.cursor_slug = $modelId
    $result.invoke_hint = ('Task model="{0}" (obrigatorio; sem model herda o pai)' -f $modelId)
}
elseif ($flag -and $alias) {
    $result.invoke_hint = ('{0} {1} {2}' -f $clientCfg.cli, $flag, $alias)
}
elseif ($flag) {
    $result.invoke_hint = ('{0} {1} {2}' -f $clientCfg.cli, $flag, $modelId)
}

if ($Json) {
    # Success stream: CLI route chama sem atribuir; Invoke-RoutedAgent captura com Out-String
    Write-Output ([pscustomobject]$result | ConvertTo-Json -Depth 6)
}
else {
    Write-Host ('task_class={0}' -f $result.task_class)
    Write-Host ('tier={0}' -f $result.tier)
    Write-Host ('client={0}' -f $result.client)
    Write-Host ('model={0}' -f $result.model)
    if ($result.alias) { Write-Host ('alias={0}' -f $result.alias) }
    if ($result.invoke_hint) { Write-Host ('invoke={0}' -f $result.invoke_hint) }
}

exit 0
