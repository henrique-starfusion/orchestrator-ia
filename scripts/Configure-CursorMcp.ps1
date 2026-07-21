#Requires -Version 5.1
<#
.SYNOPSIS
  Configura MCP do Orquestrador no Cursor do projeto (merge seguro).
#>
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [ValidateSet('stdio', 'http')]
    [string]$CursorTransport = 'stdio',
    [string]$CursorMcpUrl = 'http://127.0.0.1:8765/mcp',
    [string]$PackageRoot,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Orchestrator.Common.ps1')

$projectRoot = Get-ProjectRoot -ProjectPath $ProjectPath
$cursorDir = Join-Path $projectRoot '.cursor'
$rulesDir = Join-Path $cursorDir 'rules'
Ensure-Directory -Path $rulesDir | Out-Null

$mcpPath = Join-Path $cursorDir 'mcp.json'
$servers = @{}
if (Test-Path -LiteralPath $mcpPath) {
    try {
        $raw = Get-Content -LiteralPath $mcpPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($raw.mcpServers) {
            foreach ($p in $raw.mcpServers.PSObject.Properties) {
                $servers[$p.Name] = $p.Value
            }
        }
    }
    catch {
        Write-Host '[AVISO] mcp.json existente invalido; sera recriado parcialmente'
    }
}

if ($CursorTransport -eq 'http') {
    $servers['multiagent-orchestrator'] = [pscustomobject]@{ url = $CursorMcpUrl }
}
else {
    # Preferir node + caminho absoluto do pacote: no Windows, `orchestrator.cmd`
    # global pode apontar para versao antiga sem subcomando mcp.
    $cliJs = $null
    if (-not [string]::IsNullOrWhiteSpace($PackageRoot)) {
        $candidate = Join-Path $PackageRoot 'bin\orchestrator.js'
        if (Test-Path -LiteralPath $candidate) {
            $cliJs = (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    if ([string]::IsNullOrWhiteSpace($cliJs)) {
        $servers['multiagent-orchestrator'] = [pscustomobject]@{
            command = 'orchestrator'
            args    = @('mcp', 'serve', '--transport', 'stdio')
        }
    }
    else {
        $nodeCmd = 'node'
        $nodeProbe = Get-Command node -ErrorAction SilentlyContinue
        if ($null -ne $nodeProbe -and -not [string]::IsNullOrWhiteSpace($nodeProbe.Source)) {
            $nodeCmd = $nodeProbe.Source
        }
        $servers['multiagent-orchestrator'] = [pscustomobject]@{
            command = $nodeCmd
            args    = @($cliJs, 'mcp', 'serve', '--transport', 'stdio')
        }
    }
}

$outObj = [ordered]@{ mcpServers = [ordered]@{} }
foreach ($key in $servers.Keys) {
    $outObj.mcpServers[$key] = $servers[$key]
}
($outObj | ConvertTo-Json -Depth 8) | Set-Content -LiteralPath $mcpPath -Encoding UTF8
Write-Host ("[OK] Cursor MCP: {0}" -f $mcpPath)

$ruleSrc = $null
if ($PackageRoot) {
    $ruleSrc = Join-Path $PackageRoot 'package\template\adapters\cursor\.cursor\rules\multiagent-orchestrator.mdc'
}
$ruleDst = Join-Path $rulesDir 'multiagent-orchestrator.mdc'
if ($ruleSrc -and (Test-Path -LiteralPath $ruleSrc)) {
    if ($Force -or -not (Test-Path -LiteralPath $ruleDst)) {
        Copy-Item -LiteralPath $ruleSrc -Destination $ruleDst -Force
        Write-Host ("[OK] Cursor rule: {0}" -f $ruleDst)
    }
}

Write-Host '[OK] Configure-CursorMcp concluido'
exit 0
