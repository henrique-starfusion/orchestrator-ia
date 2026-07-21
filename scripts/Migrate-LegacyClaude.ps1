#Requires -Version 5.1
<#
.SYNOPSIS
  Wrapper compativel: delega para Migrate-LegacyConfigurations.
#>
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [switch]$Force,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Orchestrator.Common.ps1')

$projectRoot = Get-ProjectRoot -ProjectPath $ProjectPath
$legacyVersionPath = Join-Path $projectRoot '.claude\VERSION'
$orchestratorRoot = Get-OrchestratorRoot -ProjectPath $projectRoot

if (-not (Test-Path -LiteralPath $legacyVersionPath)) {
    Write-Host '[INFO] .claude/VERSION ausente; migracao legada nao necessaria.'
    exit 0
}

if ((Test-Path -LiteralPath (Join-Path $orchestratorRoot 'VERSION')) -and -not $Force) {
    Write-Host '[INFO] .orchestrator/VERSION ja existe; migracao Claude wrapper ignorada (use legacy cleanup).'
    exit 0
}

Write-Host '[INFO] Migrate-LegacyClaude -> Migrate-LegacyConfigurations'

# Garante inventario
$inventoryPath = Join-Path $orchestratorRoot 'runtime\reports\legacy-inventory.json'
Ensure-Directory -Path (Split-Path -Parent $inventoryPath) | Out-Null
& (Join-Path $PSScriptRoot 'Detect-LegacyConfigurations.ps1') -ProjectPath $projectRoot -OutputPath $inventoryPath | Out-Null

if (-not $DryRun) {
    $null = New-BackupBundle -ProjectPath $projectRoot -Paths @('.claude', '.orchestrator') -Label 'legacy-migration'
}

& (Join-Path $PSScriptRoot 'Migrate-LegacyConfigurations.ps1') -ProjectPath $projectRoot -InventoryPath $inventoryPath -Force:$Force -DryRun:$DryRun
exit $LASTEXITCODE
