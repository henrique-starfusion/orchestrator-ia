#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [switch]$RefreshTools,
    [switch]$SkipTools,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'

. (Join-Path $PSScriptRoot 'Orchestrator.Common.ps1')

if ($SkipTools) {
    Write-Host '[INFO] Install-Tools ignorado (-SkipTools).'
    exit 0
}

$projectRoot = Get-ProjectRoot -ProjectPath $ProjectPath
$orchestratorRoot = Get-OrchestratorRoot -ProjectPath $projectRoot
$toolsRegistryPath = Join-Path $orchestratorRoot 'tools\registry.json'
Ensure-Directory -Path (Join-Path $orchestratorRoot 'tools') | Out-Null

$tools = @()

$openwolfCmd = Get-Command openwolf -ErrorAction SilentlyContinue
if ($openwolfCmd) {
    $tools += [pscustomobject]@{
        name    = 'openwolf'
        status  = 'available'
        path    = $openwolfCmd.Source
        version = $null
    }
    Write-Host '[INFO] OpenWolf detectado.'
}
else {
    Write-Host '[AVISO] OpenWolf nao encontrado.'
}

$graphifyCmd = Get-Command graphify -ErrorAction SilentlyContinue
if ($graphifyCmd) {
    $version = $null
    $verResult = Invoke-ExternalCommand -FilePath $graphifyCmd.Source -ArgumentList '--version' -TimeoutSeconds 10 -WorkingDirectory $projectRoot
    if (-not $verResult.timed_out -and $verResult.exit_code -eq 0) {
        $version = ($verResult.stdout + $verResult.stderr).Trim()
    }

    $tools += [pscustomobject]@{
        name    = 'graphify'
        status  = 'available'
        path    = $graphifyCmd.Source
        version = $version
    }
    Write-Host '[INFO] Graphify detectado.'
}
else {
    Write-Host '[AVISO] Graphify nao encontrado.'
}

if ($RefreshTools) {
    $npmCmd = Get-Command npm -ErrorAction SilentlyContinue
    if ($npmCmd) {
        Write-Host '[INFO] Consultando versao publicada do OpenWolf...'
        if ($DryRun) {
            Write-Host '[DRY-RUN] npm view openwolf version'
        }
        else {
            $result = Invoke-ExternalCommand -FilePath $npmCmd.Source -ArgumentList 'view openwolf version' -TimeoutSeconds 60
            if ($result.exit_code -ne 0) {
                Write-Host "[AVISO] npm view openwolf falhou: $($result.stderr)"
            }
        }
    }

    $uvCmd = Get-Command uv -ErrorAction SilentlyContinue
    if ($uvCmd) {
        Write-Host '[INFO] Tentando atualizar Graphify via uv...'
        if ($DryRun) {
            Write-Host '[DRY-RUN] uv tool upgrade graphifyy'
        }
        else {
            $result = Invoke-ExternalCommand -FilePath $uvCmd.Source -ArgumentList 'tool upgrade graphifyy' -TimeoutSeconds 180
            if ($result.exit_code -ne 0) {
                Write-Host "[AVISO] uv tool upgrade graphifyy falhou: $($result.stderr)"
            }
        }
    }
}

if (-not $DryRun) {
    Write-JsonFile -Path $toolsRegistryPath -Object @{
        version    = '0.1.0'
        updated_at = (Get-Date).ToString('o')
        tools      = @($tools)
    }
}

Write-Host '[OK] Install-Tools concluido (somente deteccao; falhas de refresh sao avisos).'
exit 0
