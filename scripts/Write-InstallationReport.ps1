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

$agentsSummary = 'n/a'
if ($data.agents) {
    $agentsSummary = ($data.agents | ConvertTo-Json -Compress)
}

$adaptersSummary = 'n/a'
if ($data.adapters) {
    $adaptersSummary = ($data.adapters | ConvertTo-Json -Compress)
}

$toolsSummary = 'n/a'
if ($data.tools) {
    $toolsSummary = ($data.tools | ConvertTo-Json -Compress)
}

$limitations = @()
if ($data.limitations) {
    $limitations = @($data.limitations)
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
