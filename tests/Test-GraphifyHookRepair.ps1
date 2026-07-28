#Requires -Version 5.1
# bug-055 — Repair-GraphifyHooks: pythonw no interpretador pinado +
# CREATE_NO_WINDOW no Popen destacado, idempotente, raiz + repo filho.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$scriptPath = Join-Path $repoRoot 'scripts\Repair-GraphifyHooks.ps1'

$failures = New-Object System.Collections.Generic.List[string]
function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { $failures.Add($Message) | Out-Null; Write-Host ("[FAIL] {0}" -f $Message) }
    else { Write-Host ("[OK] {0}" -f $Message) }
}

$work = Join-Path $env:TEMP ("gfyhook-{0}" -f ([guid]::NewGuid().ToString('N').Substring(0, 8)))
$env:GIT_CEILING_DIRECTORIES = $work
$rootHooks = Join-Path $work '.git\hooks'
$childHooks = Join-Path $work 'travelex-api\.git\hooks'
New-Item -ItemType Directory -Force -Path $rootHooks, $childHooks | Out-Null

# Fragmentos reais do hook do graphify (formato do .bak original do PrintBee).
$hookBody = @'
#!/bin/sh
# graphify-hook-start
# Installed by: graphify hook install
_GFY_PROBE="import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('graphify') else 1)"
GRAPHIFY_PYTHON=""
_PINNED='C:\Users\henrique\AppData\Roaming\uv\tools\graphifyy\Scripts\python.exe'
if [ -n "$_PINNED" ] && [ -x "$_PINNED" ] && "$_PINNED" -c "$_GFY_PROBE" 2>/dev/null; then
    GRAPHIFY_PYTHON="$_PINNED"
fi
"$GRAPHIFY_PYTHON" -c "import os, subprocess, sys
if os.name == 'nt':
    _flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(_cmd, creationflags=_flags)
"
# graphify-hook-end
'@ -replace "`r`n", "`n"

$rootHook = Join-Path $rootHooks 'post-commit'
$childHook = Join-Path $childHooks 'post-commit'
$plainHook = Join-Path $rootHooks 'post-checkout'
$utf8 = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($rootHook, $hookBody, $utf8)
[System.IO.File]::WriteAllText($childHook, $hookBody, $utf8)
[System.IO.File]::WriteAllText($plainHook, "#!/bin/sh`nexit 0`n", $utf8)

try {
    # --- rodada 1: aplica os dois patches na raiz e no filho -------------
    $out1 = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $scriptPath -ProjectPath $work 2>&1 | Out-String
    Write-Host $out1

    foreach ($pair in @(@('raiz', $rootHook), @('filho', $childHook))) {
        $label, $path = $pair
        $c = [System.IO.File]::ReadAllText($path)
        Assert-True ($c -match [regex]::Escape("_PINNED_W='C:\Users\henrique\AppData\Roaming\uv\tools\graphifyy\Scripts\pythonw.exe'")) "$($label): _PINNED_W aponta para pythonw.exe"
        Assert-True ($c.Contains('GRAPHIFY_PYTHON="$_PINNED_W"')) "$($label): pythonw vira o interpretador preferido"
        Assert-True ($c.Contains('elif [ -n "$_PINNED" ]')) "$($label): fallback python.exe preservado como elif"
        Assert-True ($c.Contains('0x08000000')) "$($label): CREATE_NO_WINDOW nas creationflags"
        Assert-True (-not $c.Contains("`r`n")) "$($label): line endings LF preservados"
    }
    Assert-True (@(Get-ChildItem $rootHooks -Filter 'post-commit.bak-orchestrator-*').Count -eq 1) 'backup criado ao lado do hook'

    $plain = [System.IO.File]::ReadAllText($plainHook)
    Assert-True ($plain -eq "#!/bin/sh`nexit 0`n") 'hook sem graphify fica intocado'

    # sh -n: sintaxe valida apos o patch (se sh do Git Bash existir)
    $sh = Get-Command sh -ErrorAction SilentlyContinue
    if ($sh) {
        & $sh.Source -n $rootHook 2>$null
        Assert-True ($LASTEXITCODE -eq 0) 'sh -n passa no hook corrigido'
    }

    # --- rodada 2: idempotente -------------------------------------------
    $before = [System.IO.File]::ReadAllText($rootHook)
    $out2 = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $scriptPath -ProjectPath $work 2>&1 | Out-String
    $after = [System.IO.File]::ReadAllText($rootHook)
    Assert-True ($before -eq $after) 'segunda rodada nao altera o hook'
    Assert-True ($out2 -match 'fix ja aplicado') 'segunda rodada reporta fix ja aplicado'
    Assert-True (@(Get-ChildItem $rootHooks -Filter 'post-commit.bak-orchestrator-*').Count -eq 1) 'segunda rodada nao cria novo backup'

    # --- graphify hook install sobrescreve: reparo reaplica ----------------
    [System.IO.File]::WriteAllText($rootHook, $hookBody, $utf8)
    $null = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $scriptPath -ProjectPath $work 2>&1 | Out-String
    $c3 = [System.IO.File]::ReadAllText($rootHook)
    Assert-True ($c3.Contains('_PINNED_W=')) 'hook reinstalado pelo graphify e corrigido de novo'
}
finally {
    Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue
    Remove-Item Env:GIT_CEILING_DIRECTORIES -ErrorAction SilentlyContinue
}

if ($failures.Count -gt 0) {
    Write-Host ("FAIL: Test-GraphifyHookRepair - {0} falha(s)." -f $failures.Count)
    exit 1
}
Write-Host 'PASS: Test-GraphifyHookRepair'
exit 0
