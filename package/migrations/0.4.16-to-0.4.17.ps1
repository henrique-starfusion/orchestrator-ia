#Requires -Version 5.1
# Migration 0.4.16 -> 0.4.17
# Update-Agents passa a rodar por padrao em install/update; opt-out -SkipAgentUpdates.
# Sem mudanca estrutural obrigatoria no template alem de VERSION (Apply-Manifest).
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [string]$PackageRoot,
    [switch]$DryRun
)

Write-Host '[OK] Migration 0.4.16-to-0.4.17 (Update-Agents default ON).'
exit 0
