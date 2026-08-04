#Requires -Version 5.1
<#
.SYNOPSIS
    Pre-aquece o trust do claude para o projeto (bug-076).

.DESCRIPTION
    bug-076 — o claude CLI trava em workspace sem trust aceito: o spawn
    nao-interativo fica pendurado no trust dialog (validador do smoke kimi
    pendurado >15min sem heartbeat em sandbox novo; backlog "planner claude
    timeout ~9% com stdout vazio"). O proprio warning do claude indica a
    saida: projects["<path>"].hasTrustDialogAccepted no ~/.claude.json.

    Por que cirurgia de TEXTO e nao ConvertFrom/To-Json: o ~/.claude.json
    real tem chaves de projeto DUPLICADAS que diferem so por caixa
    (D:/StarFusion/printbee vs D:/starfusion/printbee) — o ConvertFrom-Json
    do PS 5.1 quebra com duplicata case-insensitive, e o round-trip
    descartaria uma das entradas (perda de estado do usuario). A edicao e
    textual, byte a byte, so nos pontos necessarios.

    Garante trust nos DOIS formatos de path que o claude grava (D:/x e
    D:\x). Backup unico (.bak-bug076). Idempotente.

    NOTA DE SEGURANCA: pre-aceitar o trust dialog concede ao claude acesso
    pleno de ferramentas no workspace sem o clique do usuario. Pedido
    explicito do dono (2026-07-31); os projetos da frota ja tinham trust
    aceito manualmente — isto elimina o hang em projetos novos.
#>
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Orchestrator.Common.ps1')

$projectRoot = Get-ProjectRoot -ProjectPath $ProjectPath
$claudeJsonPath = Join-Path $HOME '.claude.json'
if (-not (Test-Path -LiteralPath $claudeJsonPath)) { exit 0 }

$raw = [System.IO.File]::ReadAllText($claudeJsonPath)
if ([string]::IsNullOrWhiteSpace($raw)) { exit 0 }
if ($raw -notmatch '"projects"\s*:\s*\{') { exit 0 }

$forms = @(
    ($projectRoot -replace '\\', '/'),
    ($projectRoot -replace '/', '\')
) | Select-Object -Unique

$changed = $false
foreach ($form in $forms) {
    # Chave como aparece no TEXTO do JSON (barra invertida vem escapada \\)
    $key = $form.Replace('\', '\\')
    $keyPattern = '"' + [regex]::Escape($key) + '"\s*:\s*\{'
    $m = [regex]::Match($raw, $keyPattern)

    if ($m.Success) {
        # Janela da entrada: ate a proxima chave irma (indent 4) ou o fim do objeto projects
        $start = $m.Index + $m.Length
        $rest = $raw.Substring($start)
        $next = [regex]::Match($rest, "`n    \x22")
        $end = if ($next.Success) { $next.Index } else { [Math]::Min($rest.Length, 3000) }
        $entryText = $rest.Substring(0, [Math]::Min($end, 3000))

        if ($entryText -match '"hasTrustDialogAccepted"\s*:\s*true') {
            # já confiável — mas bug-079: enabledMcpjsonServers pode estar vazio
        }
        elseif ($entryText -match '"hasTrustDialogAccepted"\s*:\s*false') {
            $newEntry = [regex]::Replace($entryText, '"hasTrustDialogAccepted"\s*:\s*false', '"hasTrustDialogAccepted": true', 1)
            $raw = $raw.Substring(0, $start) + $newEntry + $rest.Substring($entryText.Length)
            $changed = $true
            continue
        }
        else {
            # Entrada existe sem a chave: insere logo apos a abertura do objeto da entrada
            $raw = $raw.Substring(0, $start) + "`r`n      " + '"hasTrustDialogAccepted": true,' + $raw.Substring($start)
            $changed = $true
            continue
        }

        # bug-079 — MCP do orquestrador REGISTRADO no .mcp.json mas nao
        # HABILITADO: claude exige aprovação do usuário para servers de projeto;
        # sem enabledMcpjsonServers a tool nunca aparece (sessão printbee de
        # 56k linhas com 1.385 edits e ZERO chamadas orchestrator_*). Mesma
        # família do trust: pré-aprova só o NOSSO server, demais seguem ask.
        $mcpListRe = '"enabledMcpjsonServers"\s*:\s*\[(?<list>[^\]]*)\]'
        $mm = [regex]::Match($entryText, $mcpListRe)
        if ($mm.Success) {
            $list = $mm.Groups['list'].Value
            if ($list -notmatch 'orchestrator-ia') {
                $trimmed = $list.Trim()
                $newList = if ($trimmed.Length -eq 0) { '"orchestrator-ia"' } else { $trimmed + ', "orchestrator-ia"' }
                $newEntry = $entryText.Replace($mm.Value, '"enabledMcpjsonServers": [' + $newList + ']')
                $raw = $raw.Substring(0, $start) + $newEntry + $rest.Substring($entryText.Length)
                $changed = $true
            }
        }
        else {
            # entrada sem a chave: insere após a abertura do objeto da entrada
            $raw = $raw.Substring(0, $start) + "`r`n      " + '"enabledMcpjsonServers": ["orchestrator-ia"],' + $raw.Substring($start)
            $changed = $true
        }
    }
    else {
        # Entrada nova logo apos "projects": {
        $pm = [regex]::Match($raw, '"projects"\s*:\s*\{')
        if (-not $pm.Success) { continue }
        $insertAt = $pm.Index + $pm.Length
        $entryText = "`r`n    " + '"' + $key + '": {' + "`r`n      " + '"hasTrustDialogAccepted": true' + "`r`n    },"
        $raw = $raw.Substring(0, $insertAt) + $entryText + $raw.Substring($insertAt)
        $changed = $true
    }
}

if (-not $changed) { exit 0 }

if ($DryRun) {
    Write-Host ("[DRY-RUN] claude trust pre-aquecido para {0}" -f $projectRoot)
    exit 0
}

$backupPath = "$claudeJsonPath.bak-bug076"
if (-not (Test-Path -LiteralPath $backupPath)) {
    Copy-Item -LiteralPath $claudeJsonPath -Destination $backupPath -Force
}
[System.IO.File]::WriteAllText($claudeJsonPath, $raw, [System.Text.UTF8Encoding]::new($false))
Write-Host ("[OK] claude trust pre-aquecido: {0}" -f $projectRoot)
exit 0
