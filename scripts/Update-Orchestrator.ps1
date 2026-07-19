#Requires -Version 5.1
<#
.SYNOPSIS
    Atualiza a estrutura .orchestrator/ do workspace a partir do pacote.

.DESCRIPTION
    - Se o pacote for mais novo: backup + sync + VERSION
    - Se as versoes forem iguais: sincroniza arquivos ausentes (aditivo)
    - Com -Force: sobrescreve arquivos managed
#>
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [string]$PackageRoot,
    [switch]$Force,
    [switch]$DryRun,
    [switch]$SkipBackup
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Orchestrator.Common.ps1')

$projectRoot = Get-ProjectRoot -ProjectPath $ProjectPath
$packageRootResolved = Get-PackageRoot -PackageRoot $PackageRoot
$packageVersion = Read-PackageVersion -PackageRoot $packageRootResolved
$workspaceVersion = Read-WorkspaceVersion -ProjectPath $projectRoot

if (-not (Test-Path -LiteralPath (Get-OrchestratorRoot -ProjectPath $projectRoot))) {
    Write-Host '[ERRO] .orchestrator ausente. Execute "orchestrator init" antes de update.'
    exit 1
}

Write-Host "[INFO] Pacote: $packageVersion | Workspace: $workspaceVersion"

$comparison = Compare-SemVer -Left $workspaceVersion -Right $packageVersion
if ($comparison -eq 'newer') {
    Write-Host '[ERRO] Workspace mais novo que o pacote; update recusado.'
    exit 6
}

$isVersionBump = ($comparison -eq 'older')
$isEqual = ($comparison -eq 'equal')

if ($comparison -eq 'invalid' -and -not $Force) {
    Write-Host '[AVISO] Comparacao de versao invalida; use -Force para continuar.'
    exit 1
}

if ($isEqual -and -not $Force) {
    Write-Host '[INFO] Versoes iguais; sincronizando estrutura ausente (aditivo)...'
}
elseif ($isVersionBump) {
    Write-Host ("[INFO] Atualizando estrutura {0} -> {1}..." -f $workspaceVersion, $packageVersion)
}
elseif ($Force) {
    Write-Host '[INFO] Update forcado (-Force): reaplicando arquivos managed...'
}

if (-not $DryRun -and -not $SkipBackup -and ($isVersionBump -or $Force)) {
    $backupRoot = New-BackupBundle -ProjectPath $projectRoot -Paths @('.orchestrator') -Label 'pre-update'
    Write-Host "[INFO] Backup pre-update: $backupRoot"
}

# Aplicar migrations versionadas quando o pacote for mais novo
$migrationsDir = Join-Path $packageRootResolved 'package\migrations'
if ($isVersionBump -and (Test-Path -LiteralPath $migrationsDir)) {
    $migrationScripts = @(Get-ChildItem -LiteralPath $migrationsDir -Filter '*.ps1' -File -ErrorAction SilentlyContinue |
        Sort-Object Name)
    foreach ($script in $migrationScripts) {
        Write-Host ("[ETAPA] Migration: {0}" -f $script.Name)
        if ($DryRun) {
            Write-Host ("[DRY-RUN] {0}" -f $script.FullName)
            continue
        }
        & $script.FullName -ProjectPath $projectRoot -PackageRoot $packageRootResolved -FromVersion $workspaceVersion -ToVersion $packageVersion
        if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) {
            Write-Host ("[ERRO] Migration falhou: {0} (exit {1})" -f $script.Name, $LASTEXITCODE)
            exit 1
        }
    }
    if ($migrationScripts.Count -eq 0) {
        Write-Host '[INFO] Nenhuma migration .ps1 em package/migrations.'
    }
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
    if ($isVersionBump -or $Force -or [string]::IsNullOrWhiteSpace($workspaceVersion)) {
        Sync-WorkspaceVersion -ProjectPath $projectRoot -Version $packageVersion | Out-Null
        Write-Host ("[OK] .orchestrator/VERSION = {0}" -f $packageVersion)
    }
}

Write-Host '[OK] Update-Orchestrator concluido.'
exit 0
