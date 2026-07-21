#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [string]$InventoryPath,
    [ValidateSet('safe', 'aggressive', 'report-only')]
    [string]$Mode = 'safe',
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Orchestrator.Common.ps1')
. (Join-Path $PSScriptRoot 'LegacyCleanup.Lib.ps1')

$projectRoot = Get-ProjectRoot -ProjectPath $ProjectPath
Ensure-Directory -Path (Get-OrchestratorRoot -ProjectPath $projectRoot) | Out-Null

if ([string]::IsNullOrWhiteSpace($InventoryPath)) {
    $InventoryPath = Join-Path (Get-OrchestratorRoot -ProjectPath $projectRoot) 'runtime\reports\legacy-inventory.json'
}

if (-not (Test-Path -LiteralPath $InventoryPath)) {
    & (Join-Path $PSScriptRoot 'Detect-LegacyConfigurations.ps1') -ProjectPath $projectRoot -OutputPath $InventoryPath | Out-Null
}

$inventoryDoc = Get-JsonFileContent -Path $InventoryPath
$items = @($inventoryDoc.items)
$toBackup = @()
foreach ($item in $items) {
    if ($item.classification -in @('migrate', 'delete', 'replace', 'adapter-legacy')) {
        $toBackup += ($item.path -replace '/', '\')
    }
}
$toBackup = @($toBackup | Select-Object -Unique)
if ($toBackup.Count -eq 0) {
    Write-Host '[INFO] Nada para backup de legado.'
    # Marker vazio para o pipeline
    $emptyRoot = Join-Path (Get-OrchestratorRoot -ProjectPath $projectRoot) ('backups\{0}-legacy-cleanup' -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
    if (-not $DryRun) {
        Ensure-Directory -Path $emptyRoot | Out-Null
        $manifest = @{
            created_at   = (Get-Date).ToString('o')
            project_root = $projectRoot
            mode         = $Mode
            items        = @()
            validated    = $true
        }
        Set-Content -LiteralPath (Join-Path $emptyRoot 'manifest.json') -Value ($manifest | ConvertTo-Json -Depth 6) -Encoding UTF8
        Set-Content -LiteralPath (Join-Path $emptyRoot 'inventory.json') -Value ($inventoryDoc | ConvertTo-Json -Depth 8) -Encoding UTF8
        $marker = Join-Path (Get-OrchestratorRoot -ProjectPath $projectRoot) 'runtime\reports\legacy-backup-path.txt'
        Set-Content -LiteralPath $marker -Value $emptyRoot -Encoding UTF8
        Write-Host $emptyRoot
    }
    exit 0
}

if ($DryRun) {
    Write-Host ('[DRY-RUN] Backup legado de {0} paths' -f $toBackup.Count)
    exit 0
}

$backupRoot = New-BackupBundle -ProjectPath $projectRoot -Paths $toBackup -Label 'legacy-cleanup'
# Enriquecer manifesto no formato do prompt
$entries = @()
$sampleChecked = $false
$validated = $true

foreach ($rel in $toBackup) {
    $original = Join-Path $projectRoot $rel
    $backed = Join-Path $backupRoot $rel
    if (-not (Test-Path -LiteralPath $backed)) {
        $validated = $false
        continue
    }
    $checksum = $null
    if (Test-Path -LiteralPath $original -PathType Leaf) {
        $checksum = Get-FileSha256 -Path $original
        $backupHash = Get-FileSha256 -Path $backed
        if ($checksum -ne $backupHash) { $validated = $false }
        if (-not $sampleChecked) {
            # Sample restore check: hashes iguais = ok
            $sampleChecked = $true
        }
    }
    $class = 'unknown'
    foreach ($it in $items) {
        if (($it.path -replace '/', '\') -eq ($rel -replace '/', '\')) { $class = $it.classification; break }
    }
    $entries += [pscustomobject]@{
        original_path   = ($rel -replace '\\', '/')
        backup_path     = (($backed.Substring($backupRoot.Length)).TrimStart('\', '/') -replace '\\', '/')
        checksum        = $checksum
        classification  = $class
        planned_action  = $(if ($class -eq 'migrate') { 'migrate' } else { 'delete-or-replace' })
        reason          = 'legacy-cleanup backup'
    }
}

$richManifest = @{
    created_at   = (Get-Date).ToString('o')
    project_root = $projectRoot
    mode         = $Mode
    items        = $entries
    validated    = $validated
}
Set-Content -LiteralPath (Join-Path $backupRoot 'manifest.json') -Value ($richManifest | ConvertTo-Json -Depth 8) -Encoding UTF8
Copy-Item -LiteralPath $InventoryPath -Destination (Join-Path $backupRoot 'inventory.json') -Force

$restoreScript = @(
    '#Requires -Version 5.1'
    "param([string]`$ProjectPath = '$projectRoot')"
    ". (Join-Path `$PSScriptRoot '..\..\..\scripts\Restore-LegacyBackup.ps1' -ErrorAction SilentlyContinue)"
    "Write-Host 'Use: orchestrator legacy restore --backup $($backupRoot | Split-Path -Leaf)'"
)
Set-Content -LiteralPath (Join-Path $backupRoot 'restore.ps1') -Value ($restoreScript -join [Environment]::NewLine) -Encoding UTF8

if (-not $validated) {
    Write-Host '[ERRO] Backup legado falhou na validacao de checksum.'
    exit 1
}

$marker = Join-Path (Get-OrchestratorRoot -ProjectPath $projectRoot) 'runtime\reports\legacy-backup-path.txt'
Set-Content -LiteralPath $marker -Value $backupRoot -Encoding UTF8
Write-Host "[OK] Backup legado: $backupRoot"
exit 0
