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
Write-Host ("[OK] migration 0.4.5-to-0.4.6 (from={0} to={1}): planner prefers fable then opus via role_model_preferences" -f $FromVersion, $ToVersion)
exit 0
