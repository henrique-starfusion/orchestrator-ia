#Requires -Version 5.1
# Migration 0.4.19 -> 0.4.20
# Registry de projetos + propagacao automatica no update do pacote.
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [string]$PackageRoot,
    [string]$FromVersion,
    [string]$ToVersion,
    [switch]$DryRun
)

Write-Host '[OK] Migration 0.4.19-to-0.4.20 (project registry + propagate).'
exit 0
