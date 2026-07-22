#Requires -Version 5.1
<#
.SYNOPSIS
  Pipeline completo de limpeza de legado (detect → backup → migrate → remove → validate).
#>
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [string]$PackageRoot,
    [ValidateSet('safe', 'aggressive', 'report-only')]
    [string]$Mode = 'safe',
    [switch]$SkipLegacyCleanup,
    [switch]$KeepLegacyBackup,
    [switch]$Force,
    [switch]$DryRun,
    [switch]$SkipRemove,
    [switch]$InstallValidated,
    [switch]$AdaptersValidated
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Orchestrator.Common.ps1')
. (Join-Path $PSScriptRoot 'LegacyCleanup.Lib.ps1')

$projectRoot = Get-ProjectRoot -ProjectPath $ProjectPath
$packageRootResolved = Get-PackageRoot -PackageRoot $PackageRoot
$packageVersion = Read-PackageVersion -PackageRoot $packageRootResolved
$orchestratorRoot = Get-OrchestratorRoot -ProjectPath $projectRoot
Ensure-Directory -Path (Join-Path $orchestratorRoot 'runtime\reports') | Out-Null

$inventoryPath = Join-Path $orchestratorRoot 'runtime\reports\legacy-inventory.json'
$summary = [ordered]@{
    mode              = $Mode
    skipped           = $false
    detected          = 0
    migrated          = @()
    removed           = @()
    preserved         = @()
    unknown           = @()
    backup            = $null
    validation_ok     = $false
    manual_actions    = @()
}

if ($SkipLegacyCleanup) {
    Write-Host '[AVISO] Legacy cleanup pulado (-SkipLegacyCleanup).'
    $summary.skipped = $true
    $summary.manual_actions += 'Execute: orchestrator legacy cleanup'
    Write-LegacyCleanupState -ProjectPath $projectRoot -State @{
        last_run         = (Get-Date).ToString('o')
        package_version  = $packageVersion
        mode             = $Mode
        skipped          = $true
        removed          = @()
        preserved        = @()
        imported         = @()
    } | Out-Null
    Set-Content -LiteralPath (Join-Path $orchestratorRoot 'runtime\reports\legacy-cleanup-report.json') -Value ($summary | ConvertTo-Json -Depth 6) -Encoding UTF8
    exit 0
}

Write-Host '[ETAPA] Detectar configuracoes legadas'
& (Join-Path $PSScriptRoot 'Detect-LegacyConfigurations.ps1') -ProjectPath $projectRoot -OutputPath $inventoryPath | Out-Null
$inventoryDoc = Get-JsonFileContent -Path $inventoryPath
$items = @($inventoryDoc.items)
$summary.detected = $items.Count
$summary.preserved = @($items | Where-Object { $_.classification -in @('user-owned', 'adapter-current', 'keep', 'runtime') } | ForEach-Object { $_.path })
$summary.unknown = @($items | Where-Object { $_.classification -eq 'unknown' } | ForEach-Object { $_.path })

if ($Mode -eq 'report-only') {
    Write-Host '[INFO] Mode report-only: inventario gerado, sem backup/migracao/remocao.'
    $summary.manual_actions += 'Revise legacy-inventory.json e execute legacy cleanup'
    $summary.validation_ok = $true
    Set-Content -LiteralPath (Join-Path $orchestratorRoot 'runtime\reports\legacy-cleanup-report.json') -Value ($summary | ConvertTo-Json -Depth 6) -Encoding UTF8
    $md = @(
        '# Legacy cleanup report',
        '',
        "**Mode:** report-only",
        ("**Detected:** {0}" -f $summary.detected),
        '',
        'Nenhuma remocao realizada.'
    )
    Set-Content -LiteralPath (Join-Path $orchestratorRoot 'runtime\reports\legacy-cleanup-report.md') -Value ($md -join [Environment]::NewLine) -Encoding UTF8
    exit 0
}

Write-Host '[ETAPA] Backup de legado'
& (Join-Path $PSScriptRoot 'Backup-LegacyConfigurations.ps1') -ProjectPath $projectRoot -InventoryPath $inventoryPath -Mode $Mode
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$backupMarker = Join-Path $orchestratorRoot 'runtime\reports\legacy-backup-path.txt'
$backupRoot = $null
if (Test-Path -LiteralPath $backupMarker) {
    $backupRoot = (Get-Content -LiteralPath $backupMarker -Raw -Encoding UTF8).Trim()
}
$summary.backup = $backupRoot

Write-Host '[ETAPA] Migrar conhecimento util'
& (Join-Path $PSScriptRoot 'Migrate-LegacyConfigurations.ps1') -ProjectPath $projectRoot -InventoryPath $inventoryPath -Force:$Force -DryRun:$DryRun
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$importedPath = Join-Path $orchestratorRoot 'runtime\reports\legacy-imported.json'
if (Test-Path -LiteralPath $importedPath) {
    $imp = Get-JsonFileContent -Path $importedPath
    if ($imp.PSObject.Properties['imported']) { $summary.migrated = @($imp.imported) }
}

$doRemove = -not $SkipRemove
if (-not $InstallValidated -or -not $AdaptersValidated) {
    Write-Host '[INFO] Remocao adiada: install/adapters ainda nao validados (chame novamente com -InstallValidated -AdaptersValidated).'
    $doRemove = $false
}

if ($doRemove) {
    Write-Host '[ETAPA] Remover legado seguro'
    & (Join-Path $PSScriptRoot 'Remove-LegacyConfigurations.ps1') `
        -ProjectPath $projectRoot `
        -InventoryPath $inventoryPath `
        -BackupRoot $backupRoot `
        -Mode $Mode `
        -Force:$Force `
        -DryRun:$DryRun `
        -BackupValidated `
        -MigrationCompleted `
        -InstallValidated `
        -AdaptersValidated
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    $removedPath = Join-Path $orchestratorRoot 'runtime\reports\legacy-removed.json'
    if (Test-Path -LiteralPath $removedPath) {
        $rem = Get-JsonFileContent -Path $removedPath
        if ($rem.PSObject.Properties['removed']) { $summary.removed = @($rem.removed) }
    }

    Write-Host '[ETAPA] Validar limpeza'
    & (Join-Path $PSScriptRoot 'Validate-LegacyCleanup.ps1') -ProjectPath $projectRoot -InventoryPath $inventoryPath -Mode $Mode
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $summary.validation_ok = $true
}
else {
    $summary.manual_actions += 'Remocao pendente apos validacao de install/adapters'
}

Write-LegacyCleanupState -ProjectPath $projectRoot -State @{
    last_run        = (Get-Date).ToString('o')
    package_version = $packageVersion
    mode            = $Mode
    removed         = @($summary.removed)
    preserved       = @($summary.preserved)
    imported        = @($summary.migrated)
    backup          = $backupRoot
} | Out-Null

Set-Content -LiteralPath (Join-Path $orchestratorRoot 'runtime\reports\legacy-cleanup-report.json') -Value ($summary | ConvertTo-Json -Depth 6) -Encoding UTF8

$mdLines = @(
    '# Legacy cleanup report',
    '',
    ("**Generated:** {0}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')),
    ("**Mode:** {0}" -f $Mode),
    ("**Detected:** {0}" -f $summary.detected),
    ("**Migrated:** {0}" -f ($summary.migrated -join ', ')),
    ("**Removed:** {0}" -f ($summary.removed -join ', ')),
    ("**Preserved:** {0}" -f ($summary.preserved -join ', ')),
    ("**Unknown:** {0}" -f ($summary.unknown -join ', ')),
    ("**Backup:** {0}" -f $backupRoot),
    ("**Validation:** {0}" -f $summary.validation_ok),
    '',
    '## Manual actions',
    ''
)
if (@($summary.manual_actions).Count -eq 0) { $mdLines += '- none' }
else { foreach ($a in $summary.manual_actions) { $mdLines += ("- {0}" -f $a) } }

Set-Content -LiteralPath (Join-Path $orchestratorRoot 'runtime\reports\legacy-cleanup-report.md') -Value ($mdLines -join [Environment]::NewLine) -Encoding UTF8

if (-not $KeepLegacyBackup -and $false) {
    # KeepLegacyBackup default: sempre manter backup (seguro). Flag reservada para limpeza futura de backups antigos.
}

Write-Host '[OK] Invoke-LegacyCleanupPipeline concluido.'
exit 0
