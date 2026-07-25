#Requires -Version 5.1
# Migration 0.4.17 -> 0.4.18
# Codex anti-hang: restrição child-agent always-on + fail-fast collab Wait.
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [string]$PackageRoot,
    [string]$FromVersion,
    [string]$ToVersion,
    [switch]$DryRun
)

Write-Host '[OK] Migration 0.4.17-to-0.4.18 (Codex child-agent hang fix).'
exit 0
