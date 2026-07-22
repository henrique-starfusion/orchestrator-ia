#Requires -Version 5.1
<#
.SYNOPSIS
    One-liner bootstrap do Orquestrador IA Multiagente (estilo OpenWolf/Graphify).

.DESCRIPTION
    Sincroniza o pacote para um cache local e executa a instalacao no diretorio atual
    (ou em -ProjectPath).

.EXAMPLES
    # Na pasta do projeto (com gh autenticado):
    gh api -H "Accept: application/vnd.github.raw" "repos/henrique-starfusion/orchestrator-ia/contents/get.ps1?ref=latest" | iex

    # Se o repositorio estiver clonado/publicado:
    irm https://raw.githubusercontent.com/henrique-starfusion/orchestrator-ia/latest/get.ps1 | iex

    # Local:
    .\get.ps1
    .\get.ps1 verify
    .\get.ps1 update
    .\get.ps1 upgrade -Force
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('init', 'install', 'verify', 'update', 'upgrade', 'repair', 'uninstall', 'status', 'analyze', 'skills')]
    [string]$Command = 'init',

    [Alias('Project')]
    [string]$ProjectPath = (Get-Location).Path,

    [string]$Repo = 'henrique-starfusion/orchestrator-ia',
    [string]$Branch = 'latest',
    [string]$CacheRoot,
    [switch]$ForceRefresh,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemainingArgs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($Command -eq 'init') { $Command = 'install' }
if ($Command -eq 'upgrade') { $Command = 'update' }

function Get-DefaultCacheRoot {
    if ($env:LOCALAPPDATA) {
        return (Join-Path $env:LOCALAPPDATA 'StarFusion\multiagent-orchestrator')
    }
    if ($env:HOME) {
        return (Join-Path $env:HOME '.local\share\starfusion\multiagent-orchestrator')
    }
    return (Join-Path $env:TEMP 'starfusion-multiagent-orchestrator')
}

function Test-IsPackageRoot {
    param([string]$Path)
    return (Test-Path -LiteralPath (Join-Path $Path 'scripts\Install-Orchestrator.ps1')) -and
        (Test-Path -LiteralPath (Join-Path $Path 'package\template\.orchestrator\VERSION'))
}

function Sync-PackageCache {
    param(
        [string]$CachePath,
        [string]$RepoName,
        [string]$BranchName,
        [switch]$Force
    )

    $gitDir = Join-Path $CachePath '.git'
    $gh = Get-Command gh -ErrorAction SilentlyContinue
    $git = Get-Command git -ErrorAction SilentlyContinue

    if ((Test-IsPackageRoot -Path $CachePath) -and -not $Force) {
        if ($git -and (Test-Path -LiteralPath $gitDir)) {
            Write-Host "[get] Atualizando cache: $CachePath"
            & $git.Source -C $CachePath fetch --depth 1 origin $BranchName 2>$null | Out-Null
            & $git.Source -C $CachePath checkout -q FETCH_HEAD 2>$null | Out-Null
            if ($LASTEXITCODE -ne 0) {
                & $git.Source -C $CachePath pull --ff-only origin $BranchName 2>$null | Out-Null
            }
        }
        else {
            Write-Host "[get] Usando cache existente: $CachePath"
        }
        return
    }

    if (Test-Path -LiteralPath $CachePath) {
        Write-Host "[get] Recriando cache: $CachePath"
        Remove-Item -LiteralPath $CachePath -Recurse -Force
    }

    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $CachePath) | Out-Null

    if ($gh) {
        Write-Host "[get] Clonando $RepoName ($BranchName) via gh..."
        & $gh.Source repo clone $RepoName $CachePath -- --depth 1 -b $BranchName
        if ($LASTEXITCODE -ne 0) { throw "gh repo clone falhou com codigo $LASTEXITCODE" }
        return
    }

    if ($git) {
        $url = "https://github.com/$RepoName.git"
        Write-Host "[get] Clonando $url ($BranchName) via git..."
        & $git.Source clone --depth 1 -b $BranchName $url $CachePath
        if ($LASTEXITCODE -ne 0) { throw "git clone falhou com codigo $LASTEXITCODE" }
        return
    }

    throw 'Nem gh nem git encontrados. Instale GitHub CLI (gh) ou Git para baixar o pacote.'
}

# Se este script ja esta dentro de um pacote completo, use-o; senao sincronize cache.
$invokedRoot = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($invokedRoot) -and $MyInvocation.MyCommand.Path) {
    $invokedRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
}

$packageRoot = $null
if ($invokedRoot -and (Test-IsPackageRoot -Path $invokedRoot)) {
    $packageRoot = (Resolve-Path -LiteralPath $invokedRoot).Path
    Write-Host "[get] Pacote local: $packageRoot"
}
else {
    if ([string]::IsNullOrWhiteSpace($CacheRoot)) {
        $CacheRoot = Get-DefaultCacheRoot
    }
    Sync-PackageCache -CachePath $CacheRoot -RepoName $Repo -BranchName $Branch -Force:$ForceRefresh
    if (-not (Test-IsPackageRoot -Path $CacheRoot)) {
        throw "Cache invalido apos sync: $CacheRoot"
    }
    $packageRoot = (Resolve-Path -LiteralPath $CacheRoot).Path
}

$projectResolved = (Resolve-Path -LiteralPath $ProjectPath).Path
$installer = Join-Path $packageRoot 'scripts\Install-Orchestrator.ps1'

Write-Host "[get] Projeto:  $projectResolved"
Write-Host "[get] Comando:  $Command"

$argList = @(
    '-NoProfile',
    '-NonInteractive',
    '-ExecutionPolicy', 'Bypass',
    '-File', $installer,
    $Command,
    '-ProjectPath', $projectResolved,
    '-PackageRoot', $packageRoot,
    '-NonInteractive'
)

if ($RemainingArgs -and $RemainingArgs.Count -gt 0) {
    $argList += $RemainingArgs
}

$ps = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
if (-not (Test-Path -LiteralPath $ps)) {
    $psCmd = Get-Command powershell.exe -ErrorAction SilentlyContinue
    if (-not $psCmd) { throw 'powershell.exe nao encontrado.' }
    $ps = $psCmd.Source
}

$proc = Start-Process -FilePath $ps -ArgumentList $argList -Wait -PassThru -NoNewWindow
exit $proc.ExitCode
