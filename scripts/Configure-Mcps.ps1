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

$recommended = @(
    [pscustomobject]@{
        id          = 'context7'
        name        = 'Context7'
        description = 'Documentacao de bibliotecas (global via npx @upstash/context7-mcp)'
        enabled     = $true
        transport   = 'stdio'
        command     = 'npx'
        args        = @('-y', '@upstash/context7-mcp')
        recommended = $true
        scope       = 'global'
    },
    [pscustomobject]@{
        id          = 'playwright'
        name        = 'Playwright'
        description = 'Browser automation MCP (global via npx @playwright/mcp)'
        enabled     = $true
        transport   = 'stdio'
        command     = 'npx'
        args        = @('-y', '@playwright/mcp@latest')
        recommended = $true
        scope       = 'global'
    },
    [pscustomobject]@{
        id          = 'sequential-thinking'
        name        = 'Sequential Thinking'
        description = 'Raciocinio estruturado MCP'
        enabled     = $true
        transport   = 'stdio'
        command     = 'npx'
        args        = @('-y', '@modelcontextprotocol/server-sequential-thinking@latest')
        recommended = $true
        scope       = 'global'
    }
)

foreach ($entry in $recommended) {
    $existing = $servers | Where-Object { $_.id -eq $entry.id } | Select-Object -First 1
    if ($null -eq $existing -or $Force) {
        $servers = @($servers | Where-Object { $_.id -ne $entry.id }) + @($entry)
    }
}

Write-JsonFile -Path $registryPath -Object @{
    version    = '0.1.0'
    updated_at = (Get-Date).ToString('o')
    servers    = @($servers)
}

Write-Host '[OK] MCP registry do workspace atualizado (context7, playwright, sequential-thinking).'
exit 0
