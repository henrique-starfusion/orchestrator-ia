#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [string]$PackageRoot,
    [switch]$Force,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Orchestrator.Common.ps1')

$projectRoot = Get-ProjectRoot -ProjectPath $ProjectPath
$packageRootResolved = Get-PackageRoot -PackageRoot $PackageRoot
$orchestratorRoot = Get-OrchestratorRoot -ProjectPath $projectRoot

Write-Host '[INFO] Desinstalando orchestrator...'

if (-not (Test-Path -LiteralPath $orchestratorRoot)) {
    Write-Host '[INFO] .orchestrator ausente; nada a remover.'
    exit 0
}

if (-not $DryRun) {
    $backupRoot = New-BackupBundle -ProjectPath $projectRoot -Paths @('.orchestrator') -Label 'pre-uninstall'
    Write-Host "[INFO] Backup pre-uninstall: $backupRoot"
}

$manifest = Import-Manifest -PackageRoot $packageRootResolved
$removed = 0

foreach ($entry in $manifest.files) {
    if ($entry.mode -eq 'user-owned') {
        continue
    }

    $destPath = Join-Path $projectRoot ($entry.destination -replace '/', '\')
    if (-not (Test-Path -LiteralPath $destPath)) {
        continue
    }

    if ($DryRun) {
        Write-Host "[DRY-RUN] Remover: $($entry.destination)"
        $removed++
        continue
    }

    Remove-Item -LiteralPath $destPath -Force -Recurse -ErrorAction SilentlyContinue
    $removed++
}

if ($Force) {
    if ($DryRun) {
        Write-Host '[DRY-RUN] Remover .orchestrator completo'
    }
    elseif (Test-Path -LiteralPath $orchestratorRoot) {
        Remove-Item -LiteralPath $orchestratorRoot -Recurse -Force
    }
}

Write-Host "[OK] Uninstall-Orchestrator: $removed arquivos gerenciados processados."
exit 0
