#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [string]$InventoryPath,
    [switch]$Force,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Orchestrator.Common.ps1')
. (Join-Path $PSScriptRoot 'LegacyCleanup.Lib.ps1')

$projectRoot = Get-ProjectRoot -ProjectPath $ProjectPath
$orchestratorRoot = Get-OrchestratorRoot -ProjectPath $projectRoot
Ensure-Directory -Path $orchestratorRoot | Out-Null

if ([string]::IsNullOrWhiteSpace($InventoryPath)) {
    $InventoryPath = Join-Path $orchestratorRoot 'runtime\reports\legacy-inventory.json'
}
if (-not (Test-Path -LiteralPath $InventoryPath)) {
    & (Join-Path $PSScriptRoot 'Detect-LegacyConfigurations.ps1') -ProjectPath $projectRoot -OutputPath $InventoryPath | Out-Null
}

$inventoryDoc = Get-JsonFileContent -Path $InventoryPath
$migratable = @(Get-LegacyMigratableItems -Inventory @($inventoryDoc.items))
$imported = New-Object System.Collections.Generic.List[string]

foreach ($item in $migratable) {
    $source = Join-Path $projectRoot ($item.path -replace '/', '\')
    $destRel = ($item.migration_target -replace '/', '\')
    $dest = Join-Path $projectRoot $destRel

    if (-not (Test-Path -LiteralPath $source)) { continue }
    if (-not (Test-LegacyPathInsideProject -ProjectRoot $projectRoot -CandidatePath $source)) { continue }
    if (-not (Test-LegacyPathInsideProject -ProjectRoot $projectRoot -CandidatePath $dest)) {
        Write-Host ("[AVISO] Destino fora do projeto ignorado: {0}" -f $item.migration_target)
        continue
    }

    # Nao copiar secrets obvios
    $skipNames = @('.env', '.env.local', 'credentials.json', 'secrets.json')

    if ($DryRun) {
        Write-Host ("[DRY-RUN] Migrar {0} -> {1}" -f $item.path, $item.migration_target)
        continue
    }

    if ((Test-Path -LiteralPath $dest) -and -not $Force) {
        Write-Host ("[INFO] Destino ja existe (legacy-import), merge aditivo: {0}" -f $item.migration_target)
    }

    Ensure-Directory -Path $dest | Out-Null

    if (Test-Path -LiteralPath $source -PathType Container) {
        Get-ChildItem -LiteralPath $source -Force | ForEach-Object {
            if ($skipNames -contains $_.Name) { return }
            $target = Join-Path $dest $_.Name
            if ((Test-Path -LiteralPath $target) -and -not $Force) { return }
            Copy-Item -LiteralPath $_.FullName -Destination $target -Recurse -Force
        }
    }
    else {
        if ($skipNames -contains [System.IO.Path]::GetFileName($source)) { continue }
        Copy-Item -LiteralPath $source -Destination $dest -Force
    }

    # Marker de revisao
    $marker = Join-Path $dest 'LEGACY-IMPORT.md'
    if (-not (Test-Path -LiteralPath $marker)) {
        $markerLines = @(
            '# Legacy import',
            '',
            'Status: candidate / requires-review',
            '',
            ('Source: {0}' -f $item.path),
            ('Imported: {0}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')),
            '',
            'Nao promover automaticamente para paths ativos do orquestrador.'
        )
        Set-Content -LiteralPath $marker -Value ($markerLines -join [Environment]::NewLine) -Encoding UTF8
    }

    $imported.Add($item.path) | Out-Null
    Write-Host ("[OK] Migrado {0} -> {1}" -f $item.path, $item.migration_target)
}

# Compat: tambem gera relatorio no formato antigo se .claude/VERSION existia
$legacyClaudeVersion = Join-Path $projectRoot '.claude\VERSION'
if ((Test-Path -LiteralPath $legacyClaudeVersion) -and -not $DryRun) {
    $reportPath = Join-Path $orchestratorRoot 'runtime\reports\migration-legacy-claude.md'
    Ensure-Directory -Path (Split-Path -Parent $reportPath) | Out-Null
    $lines = @(
        '# Legacy Migration Report',
        '',
        "**Date:** $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')",
        '',
        '## Actions',
        '',
        '- Imported via Migrate-LegacyConfigurations (generic pipeline)',
        '- Content marked legacy-import / requires-review',
        '',
        '## Imported',
        ''
    )
    foreach ($p in $imported) { $lines += ('- {0}' -f $p) }
    Set-Content -LiteralPath $reportPath -Value ($lines -join [Environment]::NewLine) -Encoding UTF8
}

Write-Host ("[OK] Migrate-LegacyConfigurations: {0} itens" -f $imported.Count)
# Export lista para o pipeline via arquivo
$importListPath = Join-Path $orchestratorRoot 'runtime\reports\legacy-imported.json'
Ensure-Directory -Path (Split-Path -Parent $importListPath) | Out-Null
Set-Content -LiteralPath $importListPath -Value (@{ imported = @($imported.ToArray()) } | ConvertTo-Json -Depth 4) -Encoding UTF8
exit 0
