#Requires -Version 5.1
# Migration 0.4.18 -> 0.4.19
# Workspace task queue (QUEUED + auto-dequeue). Sem alteração de schema SQLite.
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [string]$PackageRoot,
    [string]$FromVersion,
    [string]$ToVersion,
    [switch]$DryRun
)

Write-Host '[OK] Migration 0.4.18-to-0.4.19 (workspace task queue).'
exit 0
