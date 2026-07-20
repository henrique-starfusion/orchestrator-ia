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

$profilePath = Join-Path (Get-OrchestratorRoot -ProjectPath $projectRoot) ("agents\profiles\{0}.json" -f [string]$route.client)
if (-not (Test-Path -LiteralPath $profilePath)) {
    throw ("Profile de agente ausente: {0}. Rode 'orchestrator update' para regenerar." -f $profilePath)
}
$profile = Get-JsonFileContent -Path $profilePath

if ($profile.kind -eq 'ide-hint') {
    Write-Host ("[INFO] Cliente {0}: sem CLI de despacho." -f $profile.id)
    Write-Host ("       {0}" -f [string]$profile.hint)
    Write-Host ("[OK] model-choice gravado: {0}" -f $choicePath)
    exit 0
}

if ($profile.PSObject.Properties['verified'] -and $profile.verified -ne $true) {
    Write-Host ("[AVISO] profile '{0}' verified=false (extraido de docs, nao testado neste host)" -f $profile.id)
}

$args = @()
if ($profile.invoke.subcommand) { $args += @($profile.invoke.subcommand | ForEach-Object { [string]$_ }) }
if ($route.model_flag) {
    $modelArg = if ($route.alias) { [string]$route.alias } else { [string]$route.model }
    $args += @([string]$route.model_flag, $modelArg)
}
$promptFlag = $null
if ($profile.invoke.PSObject.Properties['prompt_flag'] -and $null -ne $profile.invoke.prompt_flag) {
    $promptFlag = [string]$profile.invoke.prompt_flag
}
if ($promptFlag) { $args += @($promptFlag, $Prompt) } else { $args += @($Prompt) }

$cliName = [string]$profile.id
Write-Host ("[ETAPA] {0} {1}" -f $cliName, ($args -join ' '))

if ($PrintOnly) {
    Write-Host ("invoke_hint={0}" -f $route.invoke_hint)
    exit 0
}
if ($DryRun) {
    Write-Host '[DRY-RUN] despacho nao executado'
    exit 0
}

$cmd = Resolve-CommandExecutable -Name $cliName
if (-not $cmd) {
    throw ("CLI nao encontrado no PATH: {0}. Instale-o ou use outro --client." -f $cliName)
}

$timeoutS = 600
if ($profile.PSObject.Properties['timeout_default_s'] -and [int]$profile.timeout_default_s -gt 0) {
    $timeoutS = [int]$profile.timeout_default_s
}

$result = Invoke-ExternalCommand -FilePath $cmd.Source -ArgumentList $args -TimeoutSeconds $timeoutS -WorkingDirectory $projectRoot
$outPath = Join-Path $runtimeDir ("{0}-{1}-result.txt" -f $stamp, $TaskClass)
@($result.stdout, $result.stderr) | Set-Content -LiteralPath $outPath -Encoding UTF8
Write-Host ("[OK] exit={0} result={1}" -f $result.exit_code, $outPath)
exit $result.exit_code
