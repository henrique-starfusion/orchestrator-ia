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

    # 0.4.54 — espelho para kimi code: o discovery de agents do kimi le
    # `.kimi-code/agents/` no projeto (docs customization/agents.html). O
    # MESMO arquivo serve os dois runtimes: kimi carrega frontmatter
    # claude-style (tools comma-separated OK; campos desconhecidos ignorados)
    # e o campo whenToUse guia a delegacao no kimi.
    $kimiAgentsDir = Join-Path $projectRoot '.kimi-code\agents'
    $kimiSubagentDst = Join-Path $kimiAgentsDir 'orquestrador.md'
    if ($DryRun) {
        Write-Host ("[DRY-RUN] subagente kimi: {0}" -f $kimiSubagentDst)
    }
    else {
        Ensure-Directory -Path $kimiAgentsDir | Out-Null
        Copy-Item -LiteralPath $subagentSrc -Destination $kimiSubagentDst -Force
        Write-Host ("[OK] Subagente kimi instalado: {0}" -f $kimiSubagentDst)
    }
}

# ---------------------------------------------------------------------------
# 0.4.56 — espelhos codex (TOML) e opencode (Markdown) do subagente.
# Codex descobre agents em `.codex/agents/*.toml` (formato name+description+
# developer_instructions, confirmado nos projetos); opencode le
# `.opencode/agent/*.md` com frontmatter mode: subagent. Gemini fica de fora:
# CLI nao instalado neste host.
# ---------------------------------------------------------------------------
$mirrors = @(
    @{
        Src    = 'package\template\.orchestrator\agents\codex-subagents\orquestrador.toml'
        DstDir = '.codex\agents'
        Dst    = 'orquestrador.toml'
        Label  = 'codex'
    },
    @{
        Src    = 'package\template\.orchestrator\agents\opencode-subagents\orquestrador.md'
        DstDir = '.opencode\agent'
        Dst    = 'orquestrador.md'
        Label  = 'opencode'
    }
)
foreach ($m in $mirrors) {
    if ([string]::IsNullOrWhiteSpace($PackageRoot)) { continue }
    $src = Join-Path $PackageRoot $m.Src
    if (-not (Test-Path -LiteralPath $src)) { continue }
    $dir = Join-Path $projectRoot $m.DstDir
    $dst = Join-Path $dir $m.Dst
    if ($DryRun) {
        Write-Host ("[DRY-RUN] subagente {0}: {1}" -f $m.Label, $dst)
        continue
    }
    Ensure-Directory -Path $dir | Out-Null
    Copy-Item -LiteralPath $src -Destination $dst -Force
    Write-Host ("[OK] Subagente {0} instalado: {1}" -f $m.Label, $dst)
}

# ---------------------------------------------------------------------------
# 0.4.59 — AGENTE PADRAO DA SESSAO (bug-083).
#
# Instalar o subagente so o torna DISPONIVEL: a thread principal continua
# sendo o agente generico, que decide sozinho se delega. Os dois CLIs que
# expoem "rodar a sessao COMO um agente nomeado" passam a apontar para o
# orquestrador — o desvio deixa de depender da boa vontade do modelo:
#
#   claude code : .claude/settings.json -> "agent": "orquestrador"
#                 (docs: "Run the main thread as a named subagent... Applies
#                 that subagent's system prompt, tool restrictions, and model")
#   opencode    : opencode.json -> "default_agent": "orquestrador"
#                 (docs: precisa ser agente PRIMARY; subagent puro cai no
#                 fallback "build" com warning — por isso o template usa
#                 `mode: all`, que serve como primary E subagent)
#
# Sem equivalente (verificado na doc oficial, 08/2026): gemini CLI (so
# experimental.enableAgents / agents.overrides), codex ([agents] tem apenas
# max_threads/max_depth) e kimi code (config.toml e de provider/modelo).
# Nesses tres o desvio segue via subagente + AGENTS.md, ja instalados acima.
#
# Chave gerenciada com respeito ao usuario: grava quando ausente ou ja nossa;
# valor DIFERENTE definido pelo usuario e preservado com aviso.
# ---------------------------------------------------------------------------
$agentName = 'orquestrador'

function Set-DefaultAgentKey {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Key,
        [Parameter(Mandatory = $true)][string]$Value,
        [Parameter(Mandatory = $true)][string]$Label,
        [switch]$WhatIfDryRun
    )

    $data = $null
    if (Test-Path -LiteralPath $Path) {
        try {
            $raw = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
            if (-not [string]::IsNullOrWhiteSpace($raw)) {
                $data = $raw | ConvertFrom-Json
            }
        }
        catch {
            Write-Host ("[AVISO] {0} invalido; agente padrao {1} nao definido." -f $Label, $Value)
            return
        }
    }
    if ($null -eq $data) { $data = [pscustomobject]@{} }

    $current = $null
    if ($data.PSObject.Properties[$Key]) { $current = [string]$data.$Key }

    if ($current -eq $Value) {
        Write-Host ("[OK] {0}: agente padrao ja e '{1}'." -f $Label, $Value)
        return
    }
    if (-not [string]::IsNullOrWhiteSpace($current)) {
        Write-Host ("[AVISO] {0}: '{1}' = '{2}' definido pelo usuario; preservado. Para orquestrar por padrao, use '{3}'." -f `
                $Label, $Key, $current, $Value)
        return
    }
    if ($WhatIfDryRun) {
        Write-Host ("[DRY-RUN] {0}: definiria {1} = '{2}'" -f $Label, $Key, $Value)
        return
    }

    $data | Add-Member -NotePropertyName $Key -NotePropertyValue $Value -Force
    Ensure-Directory -Path (Split-Path -Parent $Path) | Out-Null
    # UTF8 sem BOM: mesmo motivo do bug-074 (parser de CLI rejeita BOM).
    [System.IO.File]::WriteAllText(
        $Path, ($data | ConvertTo-Json -Depth 20), [System.Text.UTF8Encoding]::new($false)
    )
    Write-Host ("[OK] {0}: sessao roda como '{1}' ({2})." -f $Label, $Value, $Key)
}

Set-DefaultAgentKey -Path (Join-Path $projectRoot '.claude\settings.json') `
    -Key 'agent' -Value $agentName -Label 'claude code' -WhatIfDryRun:$DryRun

# opencode le opencode.json na RAIZ do projeto (precedencia maxima entre os
# arquivos de config padrao). So faz sentido quando o subagente existe.
if (Test-Path -LiteralPath (Join-Path $projectRoot '.opencode\agent\orquestrador.md')) {
    Set-DefaultAgentKey -Path (Join-Path $projectRoot 'opencode.json') `
        -Key 'default_agent' -Value $agentName -Label 'opencode' -WhatIfDryRun:$DryRun
}

exit 0
