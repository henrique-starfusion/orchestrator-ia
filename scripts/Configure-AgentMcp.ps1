#Requires -Version 5.1
<#
.SYNOPSIS
    Registra o MCP orchestrator-ia no .mcp.json do projeto (Claude Code / Kimi Code).

.DESCRIPTION
    bug-072 — o MCP do orquestrador so era registrado no Cursor
    (.cursor/mcp.json). Claude Code e Kimi Code leem `.mcp.json` na raiz do
    projeto (chave mcpServers — mesma convencao; verificado no dist do
    @moonshot-ai/kimi-code 0.31), entao os dois agentes nunca tinham as
    tools orchestrator_* disponiveis e trabalhavam direto nos arquivos.

    Mescla com mcpServers existentes (context7, playwright etc. sao
    preservados), atualiza a entry do orquestrador a cada run e remove a
    chave legada `multiagent-orchestrator`. Sem --project na entry: claude
    e kimi spawnam o servidor com cwd = workspace e o runtime resolve o
    projeto pelo cwd (cli.py: default_workspace=project or Path.cwd()).
    Idempotente.
#>
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [string]$PackageRoot,
    [switch]$DryRun,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Orchestrator.Common.ps1')

$projectRoot = Get-ProjectRoot -ProjectPath $ProjectPath
$mcpPath = Join-Path $projectRoot '.mcp.json'

# node absoluto quando possivel (o MCP spawna via cmd /c sem PATH garantido)
$nodeCmd = 'node'
$nodeFound = Get-Command node -ErrorAction SilentlyContinue
if ($null -ne $nodeFound -and $nodeFound.Source) {
    $nodeCmd = [string]$nodeFound.Source
}

$cliArgs = @('mcp', 'serve', '--transport', 'stdio')
$orch = Get-Command orchestrator -ErrorAction SilentlyContinue
if ($null -ne $orch) {
    $entry = [pscustomobject]@{
        type    = 'stdio'
        command = 'cmd'
        args    = @('/c', 'orchestrator') + $cliArgs
        enabled = $true
    }
}
else {
    $cliJs = $null
    if (-not [string]::IsNullOrWhiteSpace($PackageRoot)) {
        $candidate = Join-Path $PackageRoot 'bin\orchestrator.js'
        if (Test-Path -LiteralPath $candidate) {
            $cliJs = (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    if ($null -eq $cliJs) {
        Write-Host '[AVISO] bin\orchestrator.js nao encontrado; .mcp.json nao atualizado.'
        exit 0
    }
    $entry = [pscustomobject]@{
        type    = 'stdio'
        command = 'cmd'
        args    = @('/c', $nodeCmd, $cliJs) + $cliArgs
        enabled = $true
    }
}

$servers = [ordered]@{}
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
        Write-Host ('[AVISO] .mcp.json invalido em {0}; merge parcial' -f $mcpPath)
    }
}

$mcpServerKey = 'orchestrator-ia'
$legacyMcpServerKey = 'multiagent-orchestrator'

$servers[$mcpServerKey] = $entry
if ($servers.Contains($legacyMcpServerKey)) {
    $servers.Remove($legacyMcpServerKey)
}

if ($DryRun) {
    Write-Host ("[DRY-RUN] .mcp.json: registraria {0} em {1}" -f $mcpServerKey, $mcpPath)
    exit 0
}

# bug-074 — Set-Content -Encoding UTF8 do PS 5.1 grava BOM; o parser do
# kimi rejeita ("Unexpected token" no PRIMEIRO byte) e o CLI morria no boot
# em qualquer projeto com .mcp.json. Cursor tolera BOM, kimi nao. .NET
# WriteAllText com UTF8Encoding($false) = sem BOM.
$outObj = [ordered]@{ mcpServers = $servers }
$json = $outObj | ConvertTo-Json -Depth 10
[System.IO.File]::WriteAllText($mcpPath, $json, [System.Text.UTF8Encoding]::new($false))
Write-Host ("[OK] Agent MCP (claude/kimi): {0}" -f $mcpPath)

# ---------------------------------------------------------------------------
# 0.4.53 — subagente "orquestrador" do Claude Code (.claude/agents/).
# O claude auto-seleciona subagentes pela description: uma persona "operador
# do runtime" com tools restritas guia QUALQUER tarefa não-trivial para o
# runtime em vez de edição direta — camada que faltava entre o guard
# (intercepta) e o .mcp.json (tools disponíveis). Arquivo managed: regravado
# a cada install/update a partir do template do pacote.
# ---------------------------------------------------------------------------
$subagentSrc = $null
if (-not [string]::IsNullOrWhiteSpace($PackageRoot)) {
    $candidate = Join-Path $PackageRoot 'package\template\.orchestrator\agents\claude-subagents\orquestrador.md'
    if (Test-Path -LiteralPath $candidate) {
        $subagentSrc = (Resolve-Path -LiteralPath $candidate).Path
    }
}
if ($null -ne $subagentSrc) {
    $agentsDir = Join-Path $projectRoot '.claude\agents'
    $subagentDst = Join-Path $agentsDir 'orquestrador.md'
    if ($DryRun) {
        Write-Host ("[DRY-RUN] subagente claude: {0}" -f $subagentDst)
    }
    else {
        Ensure-Directory -Path $agentsDir | Out-Null
        Copy-Item -LiteralPath $subagentSrc -Destination $subagentDst -Force
        Write-Host ("[OK] Subagente claude instalado: {0}" -f $subagentDst)
    }
}
exit 0
