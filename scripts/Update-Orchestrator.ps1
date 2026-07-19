#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [string]$PackageRoot,
    [switch]$Force,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Orchestrator.Common.ps1')

$projectRoot = Get-ProjectRoot -ProjectPath $ProjectPath
$packageRootResolved = Get-PackageRoot -PackageRoot $PackageRoot
$packageVersion = Read-PackageVersion -PackageRoot $packageRootResolved
$workspaceVersion = Read-WorkspaceVersion -ProjectPath $projectRoot

Write-Host "[INFO] Pacote: $packageVersion | Workspace: $workspaceVersion"

$comparison = Compare-SemVer -Left $workspaceVersion -Right $packageVersion
if ($comparison -eq 'newer') {
    Write-Host '[ERRO] Workspace mais novo que o pacote; upgrade recusado.'
    exit 6
}

if ($comparison -eq 'equal' -and -not $Force) {
    Write-Host '[INFO] Versoes iguais; nenhuma atualizacao necessaria.'
    exit 0
}

if ($comparison -eq 'invalid' -and -not $Force) {
    Write-Host '[AVISO] Comparacao de versao invalida; use -Force para continuar.'
    exit 1
}

if (-not $DryRun) {
    $backupRoot = New-BackupBundle -ProjectPath $projectRoot -Paths @('.orchestrator') -Label 'pre-upgrade'
    Write-Host "[INFO] Backup pre-upgrade: $backupRoot"
}

$migrationsDir = Join-Path $packageRootResolved 'package\migrations'
if (Test-Path -LiteralPath $migrationsDir) {
    Write-Host '[INFO] Migracoes encontradas em package/migrations (aplicacao manual se necessario).'
}

$treeParams = @{
    ProjectPath = $projectRoot
    PackageRoot = $packageRootResolved
}
if ($Force) { $treeParams.Force = $true }
if ($DryRun) { $treeParams.DryRun = $true }
Copy-TemplateTree @treeParams | Out-Null

$applyParams = @{
    ProjectPath = $projectRoot
    PackageRoot = $packageRootResolved
}
if ($Force) { $applyParams.Force = $true }
if ($DryRun) { $applyParams.DryRun = $true }
Apply-Manifest @applyParams | Out-Null

if (-not $DryRun) {
    Sync-WorkspaceVersion -ProjectPath $projectRoot -Version $packageVersion | Out-Null
}

Write-Host '[OK] Update-Orchestrator concluido.'
exit 0
