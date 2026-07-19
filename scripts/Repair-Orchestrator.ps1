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

Write-Host '[INFO] Reparando arquivos gerenciados ausentes...'

if (-not $DryRun) {
    Copy-TemplateTree -ProjectPath $projectRoot -PackageRoot $packageRootResolved -Force | Out-Null
}

$applyParams = @{
    ProjectPath = $projectRoot
    PackageRoot = $packageRootResolved
    Force       = $true
}
if ($DryRun) { $applyParams.DryRun = $true }
$results = Apply-Manifest @applyParams
$restored = @($results | Where-Object { $_.action -ne 'skipped' }).Count

Write-Host "[OK] Repair-Orchestrator: $restored itens processados."
exit 0
