#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [string]$InventoryPath,
    [ValidateSet('safe', 'aggressive', 'report-only')]
    [string]$Mode = 'safe',
    [switch]$Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Orchestrator.Common.ps1')
. (Join-Path $PSScriptRoot 'LegacyCleanup.Lib.ps1')

$projectRoot = Get-ProjectRoot -ProjectPath $ProjectPath
$errors = New-Object System.Collections.Generic.List[string]

# Re-scan
$current = @(Get-LegacyInventory -ProjectPath $projectRoot)
$stillRemovable = @(Get-LegacyRemovableItems -Inventory $current -Mode $Mode)

# Adaptadores atuais devem existir apos install com agentes (soft check)
$adapterHints = @('CLAUDE.md', 'AGENTS.md', '.cursor\rules')
$adaptersOk = $true
# Soft: so falha se .orchestrator ausente
if (-not (Test-Path -LiteralPath (Join-Path (Get-OrchestratorRoot -ProjectPath $projectRoot) 'VERSION'))) {
    $errors.Add('.orchestrator/VERSION ausente apos cleanup')
    $adaptersOk = $false
}

# Itens delete safe nao devem permanecer
foreach ($item in $stillRemovable) {
    if ($item.classification -in @('delete', 'replace') -and $item.safe_to_remove) {
        $errors.Add(("Item legado removivel ainda presente: {0}" -f $item.path))
    }
}

# Unknown/user-owned nao devem ter sido tocados — apenas informar
$preserved = @($current | Where-Object { $_.classification -in @('unknown', 'user-owned', 'runtime', 'adapter-current', 'keep') })

$result = [pscustomobject]@{
    ok                 = ($errors.Count -eq 0)
    mode               = $Mode
    remaining_removable = $stillRemovable.Count
    preserved_count    = $preserved.Count
    adapters_ok        = $adaptersOk
    errors             = @($errors.ToArray())
    validated_at       = (Get-Date).ToString('o')
}

$reportPath = Join-Path (Get-OrchestratorRoot -ProjectPath $projectRoot) 'runtime\reports\legacy-cleanup-validation.json'
Ensure-Directory -Path (Split-Path -Parent $reportPath) | Out-Null
Set-Content -LiteralPath $reportPath -Value ($result | ConvertTo-Json -Depth 6) -Encoding UTF8

if ($Json) {
    $result | ConvertTo-Json -Depth 6 | Write-Output
}

if ($result.ok) {
    Write-Host '[OK] Validate-LegacyCleanup passou.'
    exit 0
}

Write-Host '[ERRO] Validate-LegacyCleanup falhou:'
foreach ($e in $errors) { Write-Host ("  - {0}" -f $e) }
exit 1
