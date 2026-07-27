#Requires -Version 5.1
<#
.SYNOPSIS
    Normaliza hooks de agente em .claude/settings.json do projeto.

.DESCRIPTION
    bug-033: os hooks `graphify hook-guard` disparavam um processo a CADA
    chamada de Bash/Grep/Read/Glob. No Windows cada disparo pisca uma janela de
    console — em uma sessao normal (100+ chamadas) o usuario ve dezenas de
    telas abrindo. O guard e apenas consultivo (0,18s, sem saida, exit 0) e o
    Graphify continua disponivel por MCP e CLI.

    Remove somente entradas de hook cujo comando referencia `graphify` +
    `hook-guard`. Todo o resto do settings.json e preservado. Idempotente.
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
$removedTotal = 0

function Test-IsNoisyHookCommand {
    param([string]$Command)
    if ([string]::IsNullOrWhiteSpace($Command)) { return $false }
    $lowered = $Command.ToLowerInvariant()
    return ($lowered -match 'graphify' -and $lowered -match 'hook-guard')
}

foreach ($leaf in @('settings.json', 'settings.local.json')) {
    $settingsPath = Join-Path $projectRoot (Join-Path '.claude' $leaf)
    if (-not (Test-Path -LiteralPath $settingsPath)) { continue }

    try {
        $settings = Get-Content -LiteralPath $settingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        Write-Host ("[AVISO] {0} invalido; hooks nao normalizados." -f $leaf)
        continue
    }
    if ($null -eq $settings -or -not $settings.PSObject.Properties['hooks']) { continue }
    if ($null -eq $settings.hooks) { continue }

    $removedHere = 0
    foreach ($eventProp in @($settings.hooks.PSObject.Properties)) {
        $groups = @($eventProp.Value)
        $keptGroups = New-Object System.Collections.Generic.List[object]

        foreach ($group in $groups) {
            if ($null -eq $group -or -not $group.PSObject.Properties['hooks']) {
                $keptGroups.Add($group) | Out-Null
                continue
            }
            $keptHooks = New-Object System.Collections.Generic.List[object]
            foreach ($hook in @($group.hooks)) {
                $command = ''
                if ($null -ne $hook -and $hook.PSObject.Properties['command']) {
                    $command = [string]$hook.command
                }
                if (Test-IsNoisyHookCommand -Command $command) {
                    $removedHere++
                    continue
                }
                $keptHooks.Add($hook) | Out-Null
            }
            if ($keptHooks.Count -gt 0) {
                $group.hooks = @($keptHooks.ToArray())
                $keptGroups.Add($group) | Out-Null
            }
        }
        $eventProp.Value = @($keptGroups.ToArray())
    }

    if ($removedHere -eq 0) { continue }
    $removedTotal += $removedHere

    if ($DryRun) {
        Write-Host ("[DRY-RUN] {0}: {1} hook(s) ruidoso(s) seriam removidos." -f $leaf, $removedHere)
        continue
    }

    $backupDir = Join-Path (Get-OrchestratorRoot -ProjectPath $projectRoot) 'backups'
    Ensure-Directory -Path $backupDir | Out-Null
    $backupPath = Join-Path $backupDir ("{0}-{1}.bak" -f (Get-Date -Format 'yyyyMMdd-HHmmss'), $leaf)
    Copy-Item -LiteralPath $settingsPath -Destination $backupPath -Force

    ($settings | ConvertTo-Json -Depth 12) | Set-Content -LiteralPath $settingsPath -Encoding UTF8
    Write-Host ("[OK] {0}: {1} hook(s) ruidoso(s) removidos (backup: {2})" -f $leaf, $removedHere, (Split-Path -Leaf $backupPath))
}

if ($removedTotal -eq 0) {
    Write-Host '[OK] Repair-AgentHooks: nenhum hook ruidoso encontrado.'
}
else {
    Write-Host ("[OK] Repair-AgentHooks: {0} hook(s) removidos." -f $removedTotal)
}

# ---------------------------------------------------------------------------
# 0.4.27 — instala o guard do orquestrador (PreToolUse em Write|Edit|MultiEdit).
# Sem ponto de interceptacao, "orquestrar e o modo padrao" fica so no texto do
# CLAUDE.md e o agente edita direto assim mesmo.
# ---------------------------------------------------------------------------
$guardRelative = '.orchestrator/hooks/active/orchestrator-guard.js'
$guardPath = Join-Path $projectRoot ($guardRelative -replace '/', '\')
if (-not (Test-Path -LiteralPath $guardPath)) {
    Write-Host '[INFO] Guard do orquestrador ausente no workspace; instalacao do hook ignorada.'
    exit 0
}

$guardCommand = 'node "$CLAUDE_PROJECT_DIR/' + $guardRelative + '"'
$settingsPath = Join-Path $projectRoot '.claude\settings.json'

if (-not (Test-Path -LiteralPath $settingsPath)) {
    $settings = [pscustomobject]@{ hooks = [pscustomobject]@{} }
}
else {
    try {
        $settings = Get-Content -LiteralPath $settingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        Write-Host '[AVISO] settings.json invalido; guard nao instalado.'
        exit 0
    }
}
if ($null -eq $settings) { $settings = [pscustomobject]@{} }
if (-not $settings.PSObject.Properties['hooks'] -or $null -eq $settings.hooks) {
    $settings | Add-Member -NotePropertyName hooks -NotePropertyValue ([pscustomobject]@{}) -Force
}
if (-not $settings.hooks.PSObject.Properties['PreToolUse'] -or $null -eq $settings.hooks.PreToolUse) {
    $settings.hooks | Add-Member -NotePropertyName PreToolUse -NotePropertyValue @() -Force
}

$already = $false
foreach ($group in @($settings.hooks.PreToolUse)) {
    if ($null -eq $group -or -not $group.PSObject.Properties['hooks']) { continue }
    foreach ($hook in @($group.hooks)) {
        if ($null -ne $hook -and $hook.PSObject.Properties['command'] `
                -and ([string]$hook.command) -like '*orchestrator-guard.js*') {
            $already = $true
        }
    }
}

if ($already) {
    Write-Host '[OK] Guard do orquestrador ja registrado.'
    exit 0
}

if ($DryRun) {
    Write-Host '[DRY-RUN] registraria orchestrator-guard em PreToolUse (Write|Edit|MultiEdit).'
    exit 0
}

$newGroup = [pscustomobject]@{
    matcher = 'Write|Edit|MultiEdit'
    hooks   = @([pscustomobject]@{ type = 'command'; command = $guardCommand; timeout = 5 })
}
$settings.hooks.PreToolUse = @(@($settings.hooks.PreToolUse) + $newGroup)

Ensure-Directory -Path (Split-Path -Parent $settingsPath) | Out-Null
($settings | ConvertTo-Json -Depth 12) | Set-Content -LiteralPath $settingsPath -Encoding UTF8
Write-Host '[OK] Guard do orquestrador registrado em .claude/settings.json.'
exit 0
