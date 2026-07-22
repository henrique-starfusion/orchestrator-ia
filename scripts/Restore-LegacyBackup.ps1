#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [Parameter(Mandatory = $true)]
    [string]$BackupId,
    [switch]$DryRun,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Orchestrator.Common.ps1')
. (Join-Path $PSScriptRoot 'LegacyCleanup.Lib.ps1')

$projectRoot = Get-ProjectRoot -ProjectPath $ProjectPath
$backupsRoot = Join-Path (Get-OrchestratorRoot -ProjectPath $projectRoot) 'backups'

$backupRoot = $null
if (Test-Path -LiteralPath $BackupId) {
    $backupRoot = (Resolve-Path -LiteralPath $BackupId).Path
}
else {
    $candidate = Join-Path $backupsRoot $BackupId
    if (Test-Path -LiteralPath $candidate) {
        $backupRoot = (Resolve-Path -LiteralPath $candidate).Path
    }
    else {
        $matches = @(Get-ChildItem -LiteralPath $backupsRoot -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -eq $BackupId -or $_.Name -like ("*{0}*" -f $BackupId) })
        if ($matches.Count -eq 1) {
            $backupRoot = $matches[0].FullName
        }
    }
}

if ([string]::IsNullOrWhiteSpace($backupRoot) -or -not (Test-Path -LiteralPath $backupRoot)) {
    Write-Host ("[ERRO] Backup nao encontrado: {0}" -f $BackupId)
    exit 1
}

if (-not (Test-LegacyPathInsideProject -ProjectRoot $projectRoot -CandidatePath $backupRoot)) {
    # Backup deve estar dentro de .orchestrator/backups do projeto
    $orch = Get-OrchestratorRoot -ProjectPath $projectRoot
    if (-not $backupRoot.StartsWith($orch, [System.StringComparison]::OrdinalIgnoreCase)) {
        Write-Host '[ERRO] Backup fora do projeto.'
        exit 1
    }
}

$manifestPath = Join-Path $backupRoot 'manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath)) {
    Write-Host '[ERRO] manifest.json ausente no backup.'
    exit 1
}

$manifest = Get-JsonFileContent -Path $manifestPath
$entries = @()
if ($manifest.PSObject.Properties['items']) { $entries = @($manifest.items) }
elseif ($manifest.PSObject.Properties['entries']) { $entries = @($manifest.entries) }

$restored = 0
foreach ($entry in $entries) {
    $origRel = $null
    if ($entry.PSObject.Properties['original_path']) { $origRel = $entry.original_path }
    elseif ($entry.PSObject.Properties['path']) { $origRel = $entry.path }
    if ([string]::IsNullOrWhiteSpace($origRel)) { continue }

    $relFs = ($origRel -replace '/', '\')
    $source = Join-Path $backupRoot $relFs
    $dest = Join-Path $projectRoot $relFs

    if (-not (Test-Path -LiteralPath $source)) { continue }
    if (-not (Test-LegacyPathInsideProject -ProjectRoot $projectRoot -CandidatePath $dest)) { continue }

    if ($DryRun) {
        Write-Host ("[DRY-RUN] Restaurar {0}" -f $origRel)
        continue
    }

    $parent = Split-Path -Parent $dest
    if (-not [string]::IsNullOrWhiteSpace($parent)) {
        Ensure-Directory -Path $parent | Out-Null
    }

    if ((Test-Path -LiteralPath $dest) -and -not $Force) {
        Write-Host ("[INFO] Destino existe, use -Force: {0}" -f $origRel)
        continue
    }

    if (Test-Path -LiteralPath $source -PathType Container) {
        if (Test-Path -LiteralPath $dest) {
            Remove-Item -LiteralPath $dest -Recurse -Force
        }
        Copy-Item -LiteralPath $source -Destination $dest -Recurse -Force
    }
    else {
        Copy-Item -LiteralPath $source -Destination $dest -Force
    }
    $restored++
    Write-Host ("[OK] Restaurado: {0}" -f $origRel)
}

Write-Host ("[OK] Restore-LegacyBackup: {0} itens" -f $restored)
exit 0
