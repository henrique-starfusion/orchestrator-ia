#Requires -Version 5.1
<#
.SYNOPSIS
    Despacha um prompt para o CLI do agente com o modelo resolvido por task_class.
#>
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [Parameter(Mandatory = $true)]
    [string]$TaskClass,
    [Parameter(Mandatory = $true)]
    [string]$Prompt,
    [ValidateSet('claude', 'codex', 'cursor', 'gemini', 'opencode', 'kimi', 'auto')]
    [string]$Client = 'auto',
    [switch]$DryRun,
    [switch]$PrintOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Orchestrator.Common.ps1')

$projectRoot = Get-ProjectRoot -ProjectPath $ProjectPath
$resolveScript = Join-Path $PSScriptRoot 'Resolve-ModelRoute.ps1'

$jsonText = & $resolveScript -ProjectPath $projectRoot -TaskClass $TaskClass -Client $Client -Json | Out-String
$route = $jsonText | ConvertFrom-Json
if ($null -eq $route -or -not $route.model) {
    throw 'Falha ao resolver rota de modelo'
}

$runtimeDir = Join-Path (Get-OrchestratorRoot -ProjectPath $projectRoot) 'runtime\results'
Ensure-Directory -Path $runtimeDir | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$choicePath = Join-Path $runtimeDir ("{0}-{1}-model-choice.json" -f $stamp, $TaskClass)
Write-JsonFile -Path $choicePath -Object $route

Write-Host ("[route] {0} / {1} -> {2} ({3})" -f $route.task_class, $route.client, $route.model, $route.tier)

if ($route.client -eq 'cursor') {
    Write-Host '[INFO] Cliente cursor: nao ha CLI de despacho. Use Task com model= obrigatorio:'
    Write-Host ("       model=`"{0}`"" -f $route.model)
    Write-Host ("[OK] model-choice gravado: {0}" -f $choicePath)
    if ($PrintOnly -or $DryRun) { exit 0 }
    exit 0
}

if ($PrintOnly) {
    Write-Host ("invoke_hint={0}" -f $route.invoke_hint)
    exit 0
}

$cliName = [string]$route.client
$cmd = Resolve-CommandExecutable -Name $cliName
if (-not $cmd) {
    throw ("CLI nao encontrado no PATH: {0}" -f $cliName)
}

$args = @()
if ($route.model_flag) {
    $modelArg = if ($route.alias) { [string]$route.alias } else { [string]$route.model }
    $args += @([string]$route.model_flag, $modelArg)
}

if ($cliName -eq 'claude') {
    $args += @('-p', $Prompt)
}
elseif ($cliName -eq 'codex') {
    $args += @($Prompt)
}
else {
    $args += @($Prompt)
}

Write-Host ("[ETAPA] {0} {1}" -f $cmd.Source, ($args -join ' '))
if ($DryRun) {
    Write-Host '[DRY-RUN] despacho nao executado'
    exit 0
}

$result = Invoke-ExternalCommand -FilePath $cmd.Source -ArgumentList $args -TimeoutSeconds 600 -WorkingDirectory $projectRoot
$outPath = Join-Path $runtimeDir ("{0}-{1}-result.txt" -f $stamp, $TaskClass)
@($result.stdout, $result.stderr) | Set-Content -LiteralPath $outPath -Encoding UTF8
Write-Host ("[OK] exit={0} result={1}" -f $result.exit_code, $outPath)
exit $result.exit_code
