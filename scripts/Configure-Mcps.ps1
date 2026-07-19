#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [switch]$ConfigureMcps,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Orchestrator.Common.ps1')

if (-not $ConfigureMcps) {
    Write-Host '[INFO] Configure-Mcps ignorado (use -ConfigureMcps).'
    exit 0
}

$projectRoot = Get-ProjectRoot -ProjectPath $ProjectPath
$mcpDir = Join-Path (Get-OrchestratorRoot -ProjectPath $projectRoot) 'mcp'
Ensure-Directory -Path $mcpDir | Out-Null
$registryPath = Join-Path $mcpDir 'registry.json'

$registry = Get-JsonFileContent -Path $registryPath
if ($null -eq $registry) {
    $registry = [pscustomobject]@{
        version = '0.1.0'
        servers = @()
    }
}

$servers = @()
if ($registry.servers) {
    $servers = @($registry.servers)
}

$context7 = $servers | Where-Object { $_.id -eq 'context7' } | Select-Object -First 1
if ($null -eq $context7 -or $Force) {
    $context7Entry = [pscustomobject]@{
        id          = 'context7'
        name        = 'Context7'
        description = 'Documentation lookup MCP (recommended, disabled by default)'
        enabled     = $false
        transport   = 'stdio'
        command     = 'npx'
        args        = @('-y', '@upstash/context7-mcp')
        recommended = $true
    }

    $filtered = @($servers | Where-Object { $_.id -ne 'context7' })
    $filtered += $context7Entry
    $servers = $filtered
}

Write-JsonFile -Path $registryPath -Object @{
    version    = '0.1.0'
    updated_at = (Get-Date).ToString('o')
    servers    = @($servers)
}

Write-Host '[OK] MCP registry atualizado (Context7 desabilitado por padrao).'
exit 0
