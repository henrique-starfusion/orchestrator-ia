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
Write-Host ("[OK] migration 0.4.6-to-0.4.7 (from={0} to={1}): runtime stdio UTF-8; Cursor rules default=orchestrator; SQLite data unchanged" -f $FromVersion, $ToVersion)
exit 0
