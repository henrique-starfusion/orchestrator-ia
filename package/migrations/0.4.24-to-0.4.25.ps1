#Requires -Version 5.1
# Migration 0.4.24 -> 0.4.25
# planner Claude: fable → opus → sonnet (fallback de cota no runtime).
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

Write-Host '[OK] Migration 0.4.24-to-0.4.25 (planner model quota fallback).'
exit 0
