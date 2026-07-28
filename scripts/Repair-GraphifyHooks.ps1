#Requires -Version 5.1
<#
.SYNOPSIS
    Silencia a janela de console dos hooks git do graphify (post-commit/checkout).

.DESCRIPTION
    bug-055: a cada `git commit`, o hook post-commit do graphify relanca o
    rebuild do grafo via python.exe — executavel do subsistema de CONSOLE do
    Windows, que aloca uma janela ao nascer. Lancado detached sem supressao de
    janela, o console pisca na tela a cada commit/checkout.

    Dois pontos, aplicados de forma idempotente (mesmo fix validado a mao no
    PrintBee):
      1. Preferir pythonw.exe (subsistema GUI, nunca cria console) no
         interpretador pinado do hook — o mesmo GRAPHIFY_PYTHON e usado no
         probe e no lancador do rebuild, entao a escolha vale para os dois.
      2. CREATE_NO_WINDOW (0x08000000) nas creationflags do Popen destacado —
         defesa em profundidade quando algum fallback resolve para python.exe.

    `graphify hook install` sobrescreve os hooks e desfaz o fix; por isso este
    reparo roda em TODO install/update/propagate do orquestrador. Cobre o repo
    raiz e os repos git filhos imediatos (layout pasta-mae, ex.: GuardLine.BR).
    So toca arquivos com o marcador do graphify. Backup ao lado do hook.
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

$script:PatchedTotal = 0
$script:AlreadyTotal = 0

$PinnedIfLine = 'if [ -n "$_PINNED" ] && [ -x "$_PINNED" ] && "$_PINNED" -c "$_GFY_PROBE" 2>/dev/null; then'
$PythonwComment = @(
    '# pythonw.exe is the windowless twin of python.exe (GUI subsystem, no console',
    '# ever allocated). Prefer it here: this same GRAPHIFY_PYTHON value is reused',
    '# below both for the probe and for the detached-rebuild launcher, so picking',
    '# it once here silences the console flicker at both call sites (#1868).'
)

function Get-GitHooksDir {
    param([string]$RepoPath)
    $git = Get-Command git -ErrorAction SilentlyContinue
    if ($git) {
        $previousEap = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            $hooksRel = (& $git.Source -C $RepoPath rev-parse --git-path hooks 2>$null)
            if ($LASTEXITCODE -eq 0 -and $hooksRel) {
                $hooksRel = [string]$hooksRel
                if ([System.IO.Path]::IsPathRooted($hooksRel)) { return $hooksRel }
                return (Join-Path $RepoPath $hooksRel)
            }
        }
        finally {
            $ErrorActionPreference = $previousEap
        }
    }
    $fallback = Join-Path $RepoPath '.git\hooks'
    if (Test-Path -LiteralPath $fallback -PathType Container) { return $fallback }
    return $null
}

function Repair-GraphifyHookFile {
    param([string]$HookPath)

    $content = [System.IO.File]::ReadAllText($HookPath)
    if ($content -notmatch 'graphify') { return }

    $needPythonw = ($content -notmatch '_PINNED_W=')
    $needNoWindow = ($content -notmatch '0x08000000')
    if (-not $needPythonw -and -not $needNoWindow) {
        $script:AlreadyTotal++
        return
    }

    $nl = "`n"
    if ($content -match "`r`n") { $nl = "`r`n" }
    $updated = $content
    $applied = @()

    if ($needPythonw) {
        $pinnedMatch = [regex]::Match($updated, "_PINNED='([^']*python\.exe)'", 'IgnoreCase')
        if ($pinnedMatch.Success -and $updated.Contains($PinnedIfLine)) {
            $pinnedW = $pinnedMatch.Groups[1].Value -replace 'python\.exe$', 'pythonw.exe'
            $block = ($PythonwComment -join $nl) + $nl +
                "_PINNED_W='" + $pinnedW + "'" + $nl +
                'if [ -n "$_PINNED_W" ] && [ -x "$_PINNED_W" ] && "$_PINNED_W" -c "$_GFY_PROBE" 2>/dev/null; then' + $nl +
                '    GRAPHIFY_PYTHON="$_PINNED_W"' + $nl +
                'el' + $PinnedIfLine
            $updated = $updated.Replace($PinnedIfLine, $block)
            $applied += 'pythonw'
        }
    }

    if ($needNoWindow) {
        $flagsMatch = [regex]::Match(
            $updated,
            '(?m)^(?<indent>[ \t]*)_flags = 0x00000008 \| 0x00000200[ \t]*(#.*)?\r?$'
        )
        if ($flagsMatch.Success) {
            $lineOld = $flagsMatch.Value.TrimEnd("`r")
            $lineNew = $flagsMatch.Groups['indent'].Value +
                '_flags = 0x00000008 | 0x00000200 | 0x08000000  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW'
            $updated = $updated.Replace($lineOld, $lineNew)
            $applied += 'no-window'
        }
    }

    if ($applied.Count -eq 0) { return }

    $hookLeaf = Split-Path -Leaf $HookPath
    if ($DryRun) {
        Write-Host ("[DRY-RUN] {0}: aplicaria {1}." -f $hookLeaf, ($applied -join ' + '))
        return
    }

    $backupPath = '{0}.bak-orchestrator-{1}' -f $HookPath, (Get-Date -Format 'yyyyMMdd-HHmmss')
    Copy-Item -LiteralPath $HookPath -Destination $backupPath -Force
    [System.IO.File]::WriteAllText(
        $HookPath, $updated, (New-Object System.Text.UTF8Encoding($false))
    )
    $script:PatchedTotal++
    Write-Host ("[OK] Graphify hook sem janela: {0} ({1}; backup: {2})" -f
        $HookPath, ($applied -join ' + '), (Split-Path -Leaf $backupPath))
}

# Repo raiz + repos git filhos imediatos (pasta-mae de repos, ex.: GuardLine.BR).
$repoDirs = New-Object System.Collections.Generic.List[string]
$repoDirs.Add($projectRoot) | Out-Null
try {
    foreach ($child in Get-ChildItem -LiteralPath $projectRoot -Directory -ErrorAction SilentlyContinue) {
        if (Test-Path -LiteralPath (Join-Path $child.FullName '.git')) {
            $repoDirs.Add($child.FullName) | Out-Null
        }
    }
}
catch {}

foreach ($repo in $repoDirs) {
    $hooksDir = Get-GitHooksDir -RepoPath $repo
    if (-not $hooksDir -or -not (Test-Path -LiteralPath $hooksDir)) { continue }
    foreach ($hookName in @('post-commit', 'post-checkout')) {
        $hookPath = Join-Path $hooksDir $hookName
        if (Test-Path -LiteralPath $hookPath -PathType Leaf) {
            Repair-GraphifyHookFile -HookPath $hookPath
        }
    }
}

if ($script:PatchedTotal -gt 0) {
    Write-Host ("[OK] Repair-GraphifyHooks: {0} hook(s) corrigido(s)." -f $script:PatchedTotal)
}
elseif ($script:AlreadyTotal -gt 0) {
    Write-Host '[OK] Repair-GraphifyHooks: fix ja aplicado.'
}
else {
    Write-Host '[OK] Repair-GraphifyHooks: nenhum hook do graphify para corrigir.'
}
exit 0
