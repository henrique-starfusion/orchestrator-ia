#Requires -Version 5.1
param(
    [string]$ProjectPath,
    [string]$PackageRoot,
    [string]$FromVersion,
    [string]$ToVersion
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\..\scripts\Orchestrator.Common.ps1')
$projectRoot = Get-ProjectRoot -ProjectPath $ProjectPath
$orch = Get-OrchestratorRoot -ProjectPath $projectRoot
Ensure-Directory -Path (Join-Path $orch 'runtime\reports') | Out-Null
Write-Host ("[OK] migration 0.4.1-to-0.4.2 (from={0} to={1}): code fingerprint, version CLI, analyze semver/audit ACs" -f $FromVersion, $ToVersion)
exit 0
