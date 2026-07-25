#Requires -Version 5.1
# Migration 0.4.22 -> 0.4.23
# Reexecuta detect+migrate para importar .cursor/rules, .claude/skills, etc. (aditivo).
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [string]$PackageRoot,
    [string]$FromVersion,
    [string]$ToVersion,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($ProjectPath)) {
    Write-Host '[SKIP] Migration 0.4.22-to-0.4.23: ProjectPath vazio.'
    exit 0
}

if ($DryRun) {
    Write-Host "[DRY-RUN] Detect+Migrate legacy em $ProjectPath"
    exit 0
}

$scriptsRoot = $null
if (-not [string]::IsNullOrWhiteSpace($PackageRoot)) {
    $candidate = Join-Path $PackageRoot 'scripts'
    if (Test-Path -LiteralPath $candidate) { $scriptsRoot = $candidate }
}
if (-not $scriptsRoot) {
    $scriptsRoot = Join-Path $PSScriptRoot '..\..\scripts'
    $scriptsRoot = [System.IO.Path]::GetFullPath($scriptsRoot)
}

$detect = Join-Path $scriptsRoot 'Detect-LegacyConfigurations.ps1'
$migrate = Join-Path $scriptsRoot 'Migrate-LegacyConfigurations.ps1'
if (-not (Test-Path -LiteralPath $detect) -or -not (Test-Path -LiteralPath $migrate)) {
    Write-Host "[ERRO] Scripts de legacy ausentes em $scriptsRoot"
    exit 1
}

$orch = Join-Path $ProjectPath '.orchestrator'
$inventory = Join-Path $orch 'runtime\reports\legacy-inventory.json'
New-Item -ItemType Directory -Path (Split-Path -Parent $inventory) -Force | Out-Null

& $detect -ProjectPath $ProjectPath -OutputPath $inventory
if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) { exit $LASTEXITCODE }

& $migrate -ProjectPath $ProjectPath -InventoryPath $inventory
if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) { exit $LASTEXITCODE }

Write-Host '[OK] Migration 0.4.22-to-0.4.23 (preinstall import existing config).'
exit 0
