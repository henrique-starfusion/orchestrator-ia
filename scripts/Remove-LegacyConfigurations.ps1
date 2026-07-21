#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [string]$InventoryPath,
    [string]$BackupRoot,
    [ValidateSet('safe', 'aggressive', 'report-only')]
    [string]$Mode = 'safe',
    [switch]$Force,
    [switch]$DryRun,
    [switch]$InstallValidated,
    [switch]$AdaptersValidated,
    [switch]$BackupValidated,
    [switch]$MigrationCompleted
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Orchestrator.Common.ps1')
. (Join-Path $PSScriptRoot 'LegacyCleanup.Lib.ps1')

$projectRoot = Get-ProjectRoot -ProjectPath $ProjectPath

if ($Mode -eq 'report-only') {
    Write-Host '[INFO] Mode report-only: nenhuma remocao.'
    exit 0
}

if ($Mode -eq 'aggressive' -and -not $Force) {
    Write-Host '[ERRO] Modo aggressive exige -Force.'
    exit 1
}

if (-not $BackupValidated -or -not $MigrationCompleted -or -not $InstallValidated -or -not $AdaptersValidated) {
    Write-Host '[ERRO] Remocao bloqueada: backup/migracao/install/adapters nao validados.'
    exit 1
}

if ([string]::IsNullOrWhiteSpace($InventoryPath)) {
    $InventoryPath = Join-Path (Get-OrchestratorRoot -ProjectPath $projectRoot) 'runtime\reports\legacy-inventory.json'
}
$inventoryDoc = Get-JsonFileContent -Path $InventoryPath
$removable = @(Get-LegacyRemovableItems -Inventory @($inventoryDoc.items) -Mode $Mode)
$removed = New-Object System.Collections.Generic.List[string]

foreach ($item in $removable) {
    $rel = ($item.path -replace '/', '\')
    $full = Join-Path $projectRoot $rel

    if (-not (Test-Path -LiteralPath $full)) { continue }
    if (-not (Test-LegacyPathInsideProject -ProjectRoot $projectRoot -CandidatePath $full)) {
        Write-Host ("[AVISO] Path fora do projeto ignorado: {0}" -f $item.path)
        continue
    }

    # Nunca remover .git ou .orchestrator raiz
    $norm = ($item.path -replace '\\', '/').Trim('/').ToLowerInvariant()
    if ($norm -eq '.git' -or $norm -eq '.orchestrator' -or $norm.StartsWith('.git/')) {
        Write-Host ("[AVISO] Protegido, nao removido: {0}" -f $item.path)
        continue
    }

    if ($DryRun) {
        Write-Host ("[DRY-RUN] Remover {0}" -f $item.path)
        continue
    }

    try {
        Remove-Item -LiteralPath $full -Recurse -Force -ErrorAction Stop
        $removed.Add($item.path) | Out-Null
        Write-Host ("[OK] Removido legado: {0}" -f $item.path)
    }
    catch {
        Write-Host ("[ERRO] Falha ao remover {0}: {1}" -f $item.path, $_.Exception.Message)
        exit 1
    }
}

$outPath = Join-Path (Get-OrchestratorRoot -ProjectPath $projectRoot) 'runtime\reports\legacy-removed.json'
Ensure-Directory -Path (Split-Path -Parent $outPath) | Out-Null
Set-Content -LiteralPath $outPath -Value (@{ removed = @($removed.ToArray()); mode = $Mode } | ConvertTo-Json -Depth 4) -Encoding UTF8
Write-Host ("[OK] Remove-LegacyConfigurations: {0} removidos" -f $removed.Count)
exit 0
