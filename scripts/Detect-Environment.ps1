#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [string]$PackageRoot,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Orchestrator.Common.ps1')

$projectRoot = Get-ProjectRoot -ProjectPath $ProjectPath
$packageRootResolved = Get-PackageRoot -PackageRoot $PackageRoot
$logFile = $null

try {
    $orchestratorRoot = Get-OrchestratorRoot -ProjectPath $projectRoot
    if (Test-Path -LiteralPath $orchestratorRoot) {
        $logFile = Write-OrchestratorLog -ProjectPath $projectRoot -Message 'Detect-Environment started'
    }
    else {
        $validationsDir = Join-Path $projectRoot '.orchestrator\runtime\validations'
        Ensure-Directory -Path $validationsDir | Out-Null
        $logFile = Join-Path $validationsDir ("preflight-{0}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
        Add-Content -LiteralPath $logFile -Value '[INFO] Detect-Environment started (pre-orchestrator)' -Encoding UTF8
    }

    Write-Host '[INFO] Preflight: verificando ambiente...'

    if ($PSVersionTable.PSVersion.Major -lt 5) {
        Write-Host '[ERRO] PowerShell 5.1 ou superior e obrigatorio.'
        exit 1
    }

    $gitCmd = Get-Command git -ErrorAction SilentlyContinue
    if (-not $gitCmd) {
        Write-Host '[ERRO] git nao encontrado no PATH.'
        exit 1
    }

    $integrity = Test-PackageIntegrity -PackageRoot $packageRootResolved
    if (-not $integrity.ok) {
        foreach ($err in $integrity.errors) {
            Write-Host "[ERRO] Integridade do pacote: $err"
        }
        exit 1
    }

    $testDir = Join-Path $projectRoot '.orchestrator\runtime\validations'
    try {
        Ensure-Directory -Path $testDir | Out-Null
        $probeFile = Join-Path $testDir ('write-test-{0}.tmp' -f (Get-Random))
        if (-not $DryRun) {
            Set-Content -LiteralPath $probeFile -Value 'ok' -Encoding UTF8
            Remove-Item -LiteralPath $probeFile -Force
        }
    }
    catch {
        Write-Host '[ERRO] Sem permissao de escrita no projeto.'
        exit 1
    }

    $drive = (Split-Path -Qualifier $projectRoot)
    if ($drive) {
        $driveInfo = New-Object System.IO.DriveInfo($drive)
        $freeMb = [math]::Round($driveInfo.AvailableFreeSpace / 1MB, 2)
        if ($freeMb -lt 50) {
            Write-Host "[ERRO] Espaco livre insuficiente: ${freeMb}MB (minimo 50MB)."
            exit 1
        }
        Write-Host "[INFO] Espaco livre: ${freeMb}MB"
    }

    if (-not (Test-InstallationLockAvailable -ProjectPath $projectRoot)) {
        Write-Host '[ERRO] Lock de instalacao ja existe (.orchestrator/runtime/install.lock).'
        exit 1
    }

    Write-Host '[OK] Preflight concluido.'
    if ($logFile) {
        Add-Content -LiteralPath $logFile -Value '[OK] Preflight concluido.' -Encoding UTF8
    }
    exit 0
}
catch {
    Write-Host "[ERRO] $($_.Exception.Message)"
    if ($logFile) {
        Add-Content -LiteralPath $logFile -Value ("[ERRO] {0}" -f $_.Exception.Message) -Encoding UTF8
    }
    exit 1
}
