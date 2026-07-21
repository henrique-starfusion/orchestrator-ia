#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [string]$Mode = 'install',
    $ReportData
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Orchestrator.Common.ps1')

$projectRoot = Get-ProjectRoot -ProjectPath $ProjectPath
$reportsDir = Join-Path (Get-OrchestratorRoot -ProjectPath $projectRoot) 'runtime\reports'
Ensure-Directory -Path $reportsDir | Out-Null
$reportPath = Join-Path $reportsDir 'installation-report.md'

$data = @{}
if ($ReportData -is [hashtable]) {
    $data = $ReportData
}
elseif ($ReportData -is [string] -and (Test-Path -LiteralPath $ReportData)) {
    $data = Get-Content -LiteralPath $ReportData -Raw -Encoding UTF8 | ConvertFrom-Json | ConvertTo-Json -Depth 8 | ConvertFrom-Json
}

$workspaceVersion = Read-WorkspaceVersion -ProjectPath $projectRoot
$packageVersion = Read-PackageVersion -PackageRoot (Get-PackageRoot)

function Get-ReportValue {
    param($Source, [string]$Name)
    if ($null -eq $Source) { return $null }
    if ($Source -is [hashtable]) {
        if ($Source.ContainsKey($Name)) { return $Source[$Name] }
        return $null
    }
    if ($Source.PSObject -and $Source.PSObject.Properties[$Name]) {
        return $Source.$Name
    }
    return $null
}

$agentsSummary = 'n/a'
$agents = Get-ReportValue -Source $data -Name 'agents'
if ($agents) {
    $agentsSummary = ($agents | ConvertTo-Json -Compress)
}

$adaptersSummary = 'n/a'
$adapters = Get-ReportValue -Source $data -Name 'adapters'
if ($adapters) {
    $adaptersSummary = ($adapters | ConvertTo-Json -Compress)
}

$toolsSummary = 'n/a'
$tools = Get-ReportValue -Source $data -Name 'tools'
if ($tools) {
    $toolsSummary = ($tools | ConvertTo-Json -Compress)
}

$limitations = @()
$lim = Get-ReportValue -Source $data -Name 'limitations'
if ($lim) {
    $limitations = @($lim)
}

$legacySummary = 'n/a'
$legacy = Get-ReportValue -Source $data -Name 'legacy'
if ($legacy) {
    $legacySummary = ($legacy | ConvertTo-Json -Depth 6 -Compress)
}

$lines = @(
    '# Installation Report',
    '',
    "**Generated:** $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')",
    "**Mode:** $Mode",
    "**Package version:** $packageVersion",
    "**Workspace version:** $workspaceVersion",
    '',
    '## Agents',
    '',
    "```json",
    $agentsSummary,
    '```',
    '',
    '## Adapters',
    '',
    "```json",
    $adaptersSummary,
    '```',
    '',
    '## Tools',
    '',
    "```json",
    $toolsSummary,
    '```',
    '',
    '## Legacy cleanup',
    '',
    '```json',
    $legacySummary,
    '```',
    '',
    '## Limitations',
    ''
)

if ($limitations.Count -eq 0) {
    $lines += '- none'
}
else {
    foreach ($item in $limitations) {
        $lines += "- $item"
    }
}

Set-Content -LiteralPath $reportPath -Value ($lines -join [Environment]::NewLine) -Encoding UTF8
Write-Host "[OK] Relatorio gravado: $reportPath"
exit 0
