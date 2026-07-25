#Requires -Version 5.1
# Migration 0.4.21 -> 0.4.22
# Reaplica o patch de models.json (0.4.21 no-op não atualizou mode=merge).
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [string]$PackageRoot,
    [string]$FromVersion,
    [string]$ToVersion,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

$sibling = Join-Path $PSScriptRoot '0.4.20-to-0.4.21.ps1'
if (-not (Test-Path -LiteralPath $sibling)) {
    Write-Host '[ERRO] Migration irmã 0.4.20-to-0.4.21.ps1 ausente.'
    exit 1
}

& $sibling -ProjectPath $ProjectPath -PackageRoot $PackageRoot -FromVersion $FromVersion -ToVersion $ToVersion -DryRun:$DryRun
exit $LASTEXITCODE
