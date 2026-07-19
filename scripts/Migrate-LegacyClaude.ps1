#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [switch]$Force,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Orchestrator.Common.ps1')

$projectRoot = Get-ProjectRoot -ProjectPath $ProjectPath
$legacyVersionPath = Join-Path $projectRoot '.claude\VERSION'
$orchestratorRoot = Get-OrchestratorRoot -ProjectPath $projectRoot

if (-not (Test-Path -LiteralPath $legacyVersionPath)) {
    Write-Host '[INFO] .claude/VERSION ausente; migracao legada nao necessaria.'
    exit 0
}

if ((Test-Path -LiteralPath (Join-Path $orchestratorRoot 'VERSION')) -and -not $Force) {
    Write-Host '[INFO] .orchestrator/VERSION ja existe; migracao ignorada.'
    exit 0
}

Write-Host '[INFO] Migrando estrutura legada .claude -> .orchestrator...'

if (-not $DryRun) {
    $backupRoot = New-BackupBundle -ProjectPath $projectRoot -Paths @('.claude', '.orchestrator') -Label 'legacy-migration'
    Write-Host "[INFO] Backup de migracao: $backupRoot"
}

Ensure-Directory -Path $orchestratorRoot | Out-Null
Ensure-Directory -Path (Join-Path $orchestratorRoot 'memory') | Out-Null
Ensure-Directory -Path (Join-Path $orchestratorRoot 'rules') | Out-Null
Ensure-Directory -Path (Join-Path $orchestratorRoot 'runtime\reports') | Out-Null

$legacyVersion = (Get-Content -LiteralPath $legacyVersionPath -Raw -Encoding UTF8).Trim()
$packageVersion = Read-PackageVersion -PackageRoot (Get-PackageRoot)
$targetVersion = if ($packageVersion) { $packageVersion } else { $legacyVersion }

$mappings = @(
    @{ Source = '.claude\memory'; Dest = '.orchestrator\memory\legacy-import' },
    @{ Source = '.claude\rules'; Dest = '.orchestrator\rules\legacy-import' }
)

foreach ($map in $mappings) {
    $source = Join-Path $projectRoot $map.Source
    $dest = Join-Path $projectRoot $map.Dest

    if (-not (Test-Path -LiteralPath $source)) {
        continue
    }

    if ($DryRun) {
        Write-Host "[DRY-RUN] Copiar $($map.Source) -> $($map.Dest)"
        continue
    }

    if (Test-Path -LiteralPath $dest) {
        if (-not $Force) {
            Write-Host "[INFO] Destino ja existe, ignorado: $($map.Dest)"
            continue
        }
    }

    Copy-Item -LiteralPath $source -Destination $dest -Recurse -Force
}

if (-not $DryRun) {
    Sync-WorkspaceVersion -ProjectPath $projectRoot -Version $targetVersion | Out-Null

    $reportPath = Join-Path $orchestratorRoot 'runtime\reports\migration-legacy-claude.md'
    $reportLines = @(
        '# Legacy Migration Report',
        '',
        "**Date:** $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')",
        "**Legacy version:** $legacyVersion",
        "**Orchestrator version:** $targetVersion",
        '',
        '## Actions',
        '',
        '- Imported `.claude/memory` into `.orchestrator/memory/legacy-import` when present',
        '- Imported `.claude/rules` into `.orchestrator/rules/legacy-import` when present',
        '- Kept `.claude/` as adapter layer (not removed)',
        '',
        '## Notes',
        '',
        '- Review imported content and consolidate into canonical `.orchestrator/` paths.'
    )
    Set-Content -LiteralPath $reportPath -Value ($reportLines -join [Environment]::NewLine) -Encoding UTF8
}

Write-Host '[OK] Migrate-LegacyClaude concluido.'
exit 0
