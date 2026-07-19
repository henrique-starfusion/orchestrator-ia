#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [string]$PackageRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Orchestrator.Common.ps1')

$projectRoot = Get-ProjectRoot -ProjectPath $ProjectPath
$packageRootResolved = Get-PackageRoot -PackageRoot $PackageRoot
$orchestratorRoot = Get-OrchestratorRoot -ProjectPath $projectRoot
$errors = New-Object System.Collections.Generic.List[string]

Write-Host '[INFO] Validando orchestrator...'

if (-not (Test-Path -LiteralPath $orchestratorRoot)) {
    Write-Host '[ERRO] .orchestrator ausente.'
    exit 1
}

$versionPath = Join-Path $orchestratorRoot 'VERSION'
if (-not (Test-Path -LiteralPath $versionPath)) {
    $errors.Add('.orchestrator/VERSION ausente') | Out-Null
}

$requiredDirs = @(
    'config',
    'agents',
    'skills',
    'runtime',
    'memory'
)

foreach ($dir in $requiredDirs) {
    $path = Join-Path $orchestratorRoot $dir
    if (-not (Test-Path -LiteralPath $path)) {
        $errors.Add(".orchestrator/$dir ausente") | Out-Null
    }
}

$configDir = Join-Path $orchestratorRoot 'config'
if (Test-Path -LiteralPath $configDir) {
    Get-ChildItem -LiteralPath $configDir -Filter '*.json' -File | ForEach-Object {
        try {
            $null = Get-Content -LiteralPath $_.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
        }
        catch {
            $errors.Add(("JSON invalido: config/{0} - {1}" -f $_.Name, $_.Exception.Message)) | Out-Null
        }
    }
}

$agentsRegistry = Join-Path $orchestratorRoot 'agents\registry.json'
if (Test-Path -LiteralPath $agentsRegistry) {
    try {
        $null = Get-Content -LiteralPath $agentsRegistry -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        $errors.Add('agents/registry.json invalido') | Out-Null
    }
}
else {
    $errors.Add('agents/registry.json ausente') | Out-Null
}

try {
    $manifest = Import-Manifest -PackageRoot $packageRootResolved
    foreach ($entry in $manifest.files) {
        if ($entry.mode -ne 'managed') { continue }
        $destPath = Join-Path $projectRoot ($entry.destination -replace '/', '\')
        if (-not (Test-Path -LiteralPath $destPath)) {
            $errors.Add(("Arquivo gerenciado ausente: {0}" -f $entry.destination)) | Out-Null
        }
    }
}
catch {
    $errors.Add(('Manifesto: {0}' -f $_.Exception.Message)) | Out-Null
}

if ($errors.Count -gt 0) {
    foreach ($err in $errors) {
        Write-Host "[ERRO] $err"
    }
    exit 1
}

Write-Host '[OK] Validate-Orchestrator concluido.'
exit 0
