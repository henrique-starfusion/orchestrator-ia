#Requires -Version 5.1
<#
.SYNOPSIS
  Configura MCP do Orquestrador no Cursor (projeto e/ou perfil global).
#>
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [ValidateSet('stdio', 'http')]
    [string]$CursorTransport = 'stdio',
    [string]$CursorMcpUrl = 'http://127.0.0.1:8765/mcp',
    [string]$PackageRoot,
    [ValidateSet('project', 'user', 'both')]
    [string]$CursorMcpScope = 'both',
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Orchestrator.Common.ps1')

function New-OrchestratorMcpServerEntry {
    param(
        [string]$Transport,
        [string]$HttpUrl,
        [string]$PackageRoot
    )

    if ($Transport -eq 'http') {
        return [pscustomobject]@{
            url     = $HttpUrl
            enabled = $true
        }
    }

    # Perfil global do Cursor no Windows costuma usar cmd /c (igual aos outros MCPs).
    # Preferir CLI global `orchestrator` quando existir; senao node + bin do pacote.
    # ${workspaceFolder} e interpolado pelo Cursor (mcp.json) para o root do projeto aberto.
    $projectArg = '${workspaceFolder}'
    $orch = Get-Command orchestrator -ErrorAction SilentlyContinue
    if ($null -ne $orch) {
        return [pscustomobject]@{
            command = 'cmd'
            args    = @('/c', 'orchestrator', 'mcp', 'serve', '--transport', 'stdio', '--project', $projectArg)
            enabled = $true
        }
    }

    $cliJs = $null
    if (-not [string]::IsNullOrWhiteSpace($PackageRoot)) {
        $candidate = Join-Path $PackageRoot 'bin\orchestrator.js'
        if (Test-Path -LiteralPath $candidate) {
            $cliJs = (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($cliJs)) {
        $nodeCmd = 'node'
        $nodeProbe = Get-Command node -ErrorAction SilentlyContinue
        if ($null -ne $nodeProbe -and -not [string]::IsNullOrWhiteSpace($nodeProbe.Source)) {
            $nodeCmd = $nodeProbe.Source
        }
        return [pscustomobject]@{
            command = 'cmd'
            args    = @('/c', $nodeCmd, $cliJs, 'mcp', 'serve', '--transport', 'stdio', '--project', $projectArg)
            enabled = $true
        }
    }

    return [pscustomobject]@{
        command = 'cmd'
        args    = @('/c', 'orchestrator', 'mcp', 'serve', '--transport', 'stdio', '--project', $projectArg)
        enabled = $true
    }
}

function Merge-CursorMcpFile {
    param(
        [Parameter(Mandatory = $true)][string]$McpPath,
        [Parameter(Mandatory = $true)]$ServerEntry,
        [switch]$Force
    )

    Ensure-Directory -Path (Split-Path -Parent $McpPath) | Out-Null
    $servers = [ordered]@{}
    if (Test-Path -LiteralPath $McpPath) {
        try {
            $raw = Get-Content -LiteralPath $McpPath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($raw.mcpServers) {
                foreach ($p in $raw.mcpServers.PSObject.Properties) {
                    $servers[$p.Name] = $p.Value
                }
            }
        }
        catch {
            Write-Host ('[AVISO] mcp.json invalido em {0}; merge parcial' -f $McpPath)
        }
    }

    if ($servers.Contains('multiagent-orchestrator') -and -not $Force) {
        # Atualiza entry do orquestrador mesmo sem -Force (config conhecida)
        $servers['multiagent-orchestrator'] = $ServerEntry
    }
    else {
        $servers['multiagent-orchestrator'] = $ServerEntry
    }

    $outObj = [ordered]@{ mcpServers = $servers }
    ($outObj | ConvertTo-Json -Depth 10) | Set-Content -LiteralPath $McpPath -Encoding UTF8
    Write-Host ("[OK] Cursor MCP: {0}" -f $McpPath)
}

$projectRoot = Get-ProjectRoot -ProjectPath $ProjectPath
$packageRootResolved = $null
if (-not [string]::IsNullOrWhiteSpace($PackageRoot)) {
    $packageRootResolved = (Resolve-Path -LiteralPath $PackageRoot).Path
}

$entry = New-OrchestratorMcpServerEntry -Transport $CursorTransport -HttpUrl $CursorMcpUrl -PackageRoot $packageRootResolved

if ($CursorMcpScope -in @('project', 'both')) {
    $projectMcp = Join-Path $projectRoot '.cursor\mcp.json'
    Merge-CursorMcpFile -McpPath $projectMcp -ServerEntry $entry -Force:$Force

    $rulesDir = Join-Path $projectRoot '.cursor\rules'
    Ensure-Directory -Path $rulesDir | Out-Null
    $ruleSrc = $null
    if ($packageRootResolved) {
        $ruleSrc = Join-Path $packageRootResolved 'package\template\adapters\cursor\.cursor\rules\multiagent-orchestrator.mdc'
    }
    $ruleDst = Join-Path $rulesDir 'multiagent-orchestrator.mdc'
    if ($ruleSrc -and (Test-Path -LiteralPath $ruleSrc)) {
        if ($Force -or -not (Test-Path -LiteralPath $ruleDst)) {
            Copy-Item -LiteralPath $ruleSrc -Destination $ruleDst -Force
            Write-Host ("[OK] Cursor rule: {0}" -f $ruleDst)
        }
    }
}

if ($CursorMcpScope -in @('user', 'both')) {
    $userMcp = Join-Path $env:USERPROFILE '.cursor\mcp.json'
    Merge-CursorMcpFile -McpPath $userMcp -ServerEntry $entry -Force:$Force
}

Write-Host '[OK] Configure-CursorMcp concluido'
exit 0
