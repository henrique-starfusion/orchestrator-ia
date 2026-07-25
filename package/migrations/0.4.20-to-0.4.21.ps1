#Requires -Version 5.1
# Migration 0.4.20 -> 0.4.21
# role_model_preferences: executor/corrector = opus|gpt-5.6-sol; validator = sonnet/balanced.
# Apply-Manifest recopia models.json do template.
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [string]$PackageRoot,
    [string]$FromVersion,
    [string]$ToVersion,
    [switch]$DryRun
)

Write-Host '[OK] Migration 0.4.20-to-0.4.21 (executor strong / validator mid-tier).'
exit 0
