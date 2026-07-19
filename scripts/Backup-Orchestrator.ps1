#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$ProjectPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Orchestrator.Common.ps1')

$projectRoot = Get-ProjectRoot -ProjectPath $ProjectPath
$orchestratorRoot = Get-OrchestratorRoot -ProjectPath $projectRoot

if (-not (Test-Path -LiteralPath $orchestratorRoot)) {
    Write-Host '[ERRO] .orchestrator ausente; nada para backup.'
    exit 1
}

$backupRoot = New-BackupBundle -ProjectPath $projectRoot -Paths @('.orchestrator') -Label 'orchestrator'
Write-Host "[OK] Backup criado em: $backupRoot"
exit 0
