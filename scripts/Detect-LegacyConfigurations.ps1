#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [string]$OutputPath,
    [switch]$Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Orchestrator.Common.ps1')
. (Join-Path $PSScriptRoot 'LegacyCleanup.Lib.ps1')

$projectRoot = Get-ProjectRoot -ProjectPath $ProjectPath
$inventory = @(Get-LegacyInventory -ProjectPath $projectRoot)

$payload = [pscustomobject]@{
    scanned_at     = (Get-Date).ToString('o')
    project_root   = $projectRoot
    item_count     = $inventory.Count
    items          = $inventory
    removable_safe = @(Get-LegacyRemovableItems -Inventory $inventory -Mode 'safe').Count
    migratable     = @(Get-LegacyMigratableItems -Inventory $inventory).Count
}

$orchestratorRoot = Get-OrchestratorRoot -ProjectPath $projectRoot
$defaultOut = Join-Path $orchestratorRoot 'runtime\reports\legacy-inventory.json'
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    if (Test-Path -LiteralPath $orchestratorRoot) {
        Ensure-Directory -Path (Split-Path -Parent $defaultOut) | Out-Null
        $OutputPath = $defaultOut
    }
}

if (-not [string]::IsNullOrWhiteSpace($OutputPath)) {
    $parent = Split-Path -Parent $OutputPath
    if (-not [string]::IsNullOrWhiteSpace($parent)) {
        Ensure-Directory -Path $parent | Out-Null
    }
    Set-Content -LiteralPath $OutputPath -Value ($payload | ConvertTo-Json -Depth 8) -Encoding UTF8
}

if ($Json) {
    $payload | ConvertTo-Json -Depth 8 | Write-Output
}
else {
    Write-Host ("[OK] Detect-LegacyConfigurations: {0} itens" -f $inventory.Count)
    foreach ($item in $inventory) {
        Write-Host ("  - [{0}] {1} ({2})" -f $item.classification, $item.path, $item.reason)
    }
}

# Retorna via exit; callers leem o JSON
exit 0
