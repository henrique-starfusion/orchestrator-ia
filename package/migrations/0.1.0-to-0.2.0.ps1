#Requires -Version 5.1
<#
.SYNOPSIS
  Migration 0.1.0 -> 0.2.0: runtime config + documentation policy defaults.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectPath,
    [string]$PackageRoot,
    [string]$FromVersion,
    [string]$ToVersion
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$orch = Join-Path $ProjectPath '.orchestrator'
$data = Join-Path $orch 'data'
New-Item -ItemType Directory -Force -Path $data | Out-Null

if ($PackageRoot) {
    $managerSrc = Join-Path $PackageRoot 'package\template\.orchestrator\config\manager_model.json'
    $managerDst = Join-Path $orch 'config\manager_model.json'
    if ((Test-Path -LiteralPath $managerSrc) -and -not (Test-Path -LiteralPath $managerDst)) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $managerDst) | Out-Null
        Copy-Item -LiteralPath $managerSrc -Destination $managerDst -Force
    }
}

Write-Host ("[OK] migration 0.1.0-to-0.2.0 (from={0} to={1}): data/ + manager_model.json" -f $FromVersion, $ToVersion)
exit 0
