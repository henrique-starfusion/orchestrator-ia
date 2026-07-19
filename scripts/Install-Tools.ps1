#Requires -Version 5.1
<#
.SYNOPSIS
    Detecta, opcionalmente atualiza e inicializa OpenWolf / Graphify no projeto.

.DESCRIPTION
    Por padrao apenas detecta. Com -InitTools:
      - openwolf init  (cria .wolf/ no projeto)
      - graphify install --project  (instala skill no projeto)
    Falhas nunca abortam o bootstrap principal.
#>
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [switch]$RefreshTools,
    [switch]$InitTools,
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
$toolsRoot = Join-Path $orchestratorRoot 'tools'
$toolsRegistryPath = Join-Path $toolsRoot 'registry.json'
$openwolfDir = Join-Path $toolsRoot 'openwolf'
$graphifyDir = Join-Path $toolsRoot 'graphify'
Ensure-Directory -Path $toolsRoot | Out-Null
Ensure-Directory -Path $openwolfDir | Out-Null
Ensure-Directory -Path $graphifyDir | Out-Null

function Write-ToolStatus {
    param(
        [string]$Path,
        [hashtable]$Object
    )
    if ($DryRun) { return }
    Write-JsonFile -Path $Path -Object $Object
}

$tools = @()

# --- OpenWolf ---
$openwolfCmd = Resolve-CommandExecutable -Name 'openwolf'
$openwolfEntry = [ordered]@{
    name           = 'openwolf'
    status         = 'not_installed'
    path           = $null
    version        = $null
    initialized    = $false
    init_exit_code = $null
    notes          = @()
}

if ($openwolfCmd) {
    $openwolfEntry.status = 'available'
    $openwolfEntry.path = $openwolfCmd.Source
    Write-Host "[INFO] OpenWolf detectado: $($openwolfCmd.Source)"

    $ver = Invoke-ExternalCommand -FilePath $openwolfCmd.Source -ArgumentList @('--version') -TimeoutSeconds 30 -WorkingDirectory $projectRoot
    if ($ver.exit_code -eq 0 -and -not $ver.timed_out) {
        $openwolfEntry.version = (($ver.stdout + $ver.stderr) -split "`r?`n" | Select-Object -First 1).Trim()
    }

    if ($RefreshTools) {
        $npmCmd = Get-Command npm -ErrorAction SilentlyContinue
        if ($npmCmd) {
            Write-Host '[INFO] Consultando versao publicada do OpenWolf...'
            if ($DryRun) {
                Write-Host '[DRY-RUN] npm view openwolf version'
            }
            else {
                $npmView = Invoke-ExternalCommand -FilePath $npmCmd.Source -ArgumentList @('view', 'openwolf', 'version') -TimeoutSeconds 60
                if ($npmView.exit_code -eq 0) {
                    $openwolfEntry.notes += ("npm latest: {0}" -f $npmView.stdout.Trim())
                }
                else {
                    Write-Host "[AVISO] npm view openwolf falhou: $($npmView.stderr)"
                    $openwolfEntry.notes += 'npm view falhou'
                }
            }
        }
    }

    if ($InitTools) {
        $wolfMarker = Join-Path $projectRoot '.wolf'
        Write-Host '[ETAPA] Inicializando OpenWolf no projeto (openwolf init)...'
        if ($DryRun) {
            Write-Host '[DRY-RUN] openwolf init'
            $openwolfEntry.notes += 'dry-run init'
        }
        else {
            $init = Invoke-ExternalCommand -FilePath $openwolfCmd.Source -ArgumentList @('init') -TimeoutSeconds 300 -WorkingDirectory $projectRoot
            $openwolfEntry.init_exit_code = $init.exit_code
            if ($init.timed_out) {
                Write-Host '[AVISO] openwolf init excedeu timeout; bootstrap continua.'
                $openwolfEntry.notes += 'init timed out'
                $openwolfEntry.status = 'init_timeout'
            }
            elseif ($init.exit_code -eq 0) {
                $openwolfEntry.initialized = $true
                Write-Host '[OK] OpenWolf init concluido.'
            }
            else {
                Write-Host "[AVISO] openwolf init falhou (exit $($init.exit_code)); bootstrap continua."
                if ($init.stderr) { Write-Host $init.stderr }
                if ($init.stdout) { Write-Host $init.stdout }
                $openwolfEntry.notes += ("init failed: {0}" -f $init.exit_code)
                $openwolfEntry.status = 'init_failed'
            }
        }
        if (Test-Path -LiteralPath $wolfMarker) {
            $openwolfEntry.initialized = $true
            $openwolfEntry.notes += '.wolf/ presente'
        }
    }
    elseif (Test-Path -LiteralPath (Join-Path $projectRoot '.wolf')) {
        $openwolfEntry.initialized = $true
        $openwolfEntry.notes += '.wolf/ ja existia'
    }
}
else {
    Write-Host '[AVISO] OpenWolf nao encontrado no PATH. Instale com: npm install -g openwolf'
    $openwolfEntry.notes += 'not in PATH'
}

$tools += [pscustomobject]$openwolfEntry
Write-ToolStatus -Path (Join-Path $openwolfDir 'status.json') -Object ([hashtable]$openwolfEntry)

# --- Graphify ---
$graphifyCmd = Resolve-CommandExecutable -Name 'graphify'
$graphifyEntry = [ordered]@{
    name           = 'graphify'
    status         = 'not_installed'
    path           = $null
    version        = $null
    initialized    = $false
    init_exit_code = $null
    notes          = @()
}

if ($graphifyCmd) {
    $graphifyEntry.status = 'available'
    $graphifyEntry.path = $graphifyCmd.Source
    Write-Host "[INFO] Graphify detectado: $($graphifyCmd.Source)"

    $verResult = Invoke-ExternalCommand -FilePath $graphifyCmd.Source -ArgumentList @('--version') -TimeoutSeconds 30 -WorkingDirectory $projectRoot
    if (-not $verResult.timed_out -and $verResult.exit_code -eq 0) {
        $graphifyEntry.version = (($verResult.stdout + $verResult.stderr) -split "`r?`n" | Select-Object -First 1).Trim()
    }

    if ($RefreshTools) {
        $uvCmd = Get-Command uv -ErrorAction SilentlyContinue
        if ($uvCmd) {
            Write-Host '[INFO] Tentando atualizar Graphify via uv...'
            if ($DryRun) {
                Write-Host '[DRY-RUN] uv tool upgrade graphifyy'
            }
            else {
                $up = Invoke-ExternalCommand -FilePath $uvCmd.Source -ArgumentList @('tool', 'upgrade', 'graphifyy') -TimeoutSeconds 180
                if ($up.exit_code -ne 0) {
                    Write-Host "[AVISO] uv tool upgrade graphifyy falhou: $($up.stderr)"
                    $graphifyEntry.notes += 'uv upgrade falhou'
                }
                else {
                    $graphifyEntry.notes += 'uv upgrade ok'
                }
            }
        }
        else {
            Write-Host '[AVISO] uv nao encontrado; refresh do Graphify ignorado.'
        }
    }

    if ($InitTools) {
        Write-Host '[ETAPA] Inicializando Graphify no projeto (graphify install --project)...'
        if ($DryRun) {
            Write-Host '[DRY-RUN] graphify install --project'
            $graphifyEntry.notes += 'dry-run install --project'
        }
        else {
            $init = Invoke-ExternalCommand -FilePath $graphifyCmd.Source -ArgumentList @('install', '--project') -TimeoutSeconds 180 -WorkingDirectory $projectRoot
            $graphifyEntry.init_exit_code = $init.exit_code
            if ($init.exit_code -eq 0) {
                $graphifyEntry.initialized = $true
                Write-Host '[OK] Graphify install --project concluido.'
            }
            else {
                Write-Host "[AVISO] graphify install --project falhou (exit $($init.exit_code)); bootstrap continua."
                if ($init.stderr) { Write-Host $init.stderr }
                if ($init.stdout) { Write-Host $init.stdout }
                $graphifyEntry.notes += ("install --project failed: {0}" -f $init.exit_code)
                $graphifyEntry.status = 'init_failed'
            }
        }
    }
}
else {
    Write-Host '[AVISO] Graphify nao encontrado no PATH. Instale com: uv tool install graphifyy  OU  npm i -g @sentropic/graphify'
    $graphifyEntry.notes += 'not in PATH'
}

$tools += [pscustomobject]$graphifyEntry
Write-ToolStatus -Path (Join-Path $graphifyDir 'status.json') -Object ([hashtable]$graphifyEntry)

if (-not $DryRun) {
    Write-JsonFile -Path $toolsRegistryPath -Object @{
        version    = '0.1.0'
        updated_at = (Get-Date).ToString('o')
        init_tools = [bool]$InitTools
        tools      = @($tools)
    }
}

if ($InitTools) {
    Write-Host '[OK] Install-Tools concluido (deteccao + inicializacao opcional).'
}
else {
    Write-Host '[OK] Install-Tools concluido (somente deteccao). Use -InitTools para openwolf init / graphify install --project.'
}
exit 0
