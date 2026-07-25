#Requires -Version 5.1
# Migration 0.4.23 -> 0.4.24
# - Reaplica patch models.json (inclui planner)
# - Prune registry de fixtures Temp
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [string]$PackageRoot,
    [string]$FromVersion,
    [string]$ToVersion,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

$modelsMig = Join-Path $PSScriptRoot '0.4.20-to-0.4.21.ps1'
if (Test-Path -LiteralPath $modelsMig) {
    & $modelsMig -ProjectPath $ProjectPath -PackageRoot $PackageRoot -FromVersion $FromVersion -ToVersion $ToVersion -DryRun:$DryRun
}

$scriptsRoot = $null
if (-not [string]::IsNullOrWhiteSpace($PackageRoot)) {
    $candidate = Join-Path $PackageRoot 'scripts'
    if (Test-Path -LiteralPath $candidate) { $scriptsRoot = $candidate }
}
if (-not $scriptsRoot) {
    $scriptsRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\scripts'))
}
$common = Join-Path $scriptsRoot 'Orchestrator.Common.ps1'
if (Test-Path -LiteralPath $common) {
    . $common
    Prune-OrchestratorProjectRegistry -DryRun:$DryRun | Out-Null
}

Write-Host '[OK] Migration 0.4.23-to-0.4.24 (cancel hard-stop / registry prune / planner prefs).'
exit 0
