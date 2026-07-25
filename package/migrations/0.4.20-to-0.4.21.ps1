#Requires -Version 5.1
# Migration 0.4.20 -> 0.4.21
# models.json é mode=merge (não sobrescreve se existir). Este script aplica o patch
# de roteamento: executor/corrector = modelo forte; validator = intermediário.
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [string]$PackageRoot,
    [string]$FromVersion,
    [string]$ToVersion,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($ProjectPath)) {
    Write-Host '[SKIP] Migration 0.4.20-to-0.4.21: ProjectPath vazio.'
    exit 0
}

$modelsPath = Join-Path $ProjectPath '.orchestrator\config\models.json'
if (-not (Test-Path -LiteralPath $modelsPath)) {
    Write-Host "[SKIP] Migration 0.4.20-to-0.4.21: models.json ausente em $ProjectPath"
    exit 0
}

if ($DryRun) {
    Write-Host "[DRY-RUN] Patch role_model_preferences + task_map em $modelsPath"
    exit 0
}

$py = @'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
changed = False

clients = data.setdefault("clients", {})
claude = clients.setdefault("claude", {})
task_map = claude.setdefault("task_map", {})
for key in ("implementation", "refactor_simple"):
    if task_map.get(key) != "opus":
        task_map[key] = "opus"
        changed = True
if claude.get("invoke_example") == 'claude --model sonnet -p "..."':
    claude["invoke_example"] = 'claude --model opus -p "..."'
    changed = True

prefs = data.setdefault("role_model_preferences", {})
desired = {
    "executor": {
        "claude": ["opus", "sonnet"],
        "codex": ["deep", "balanced", "gpt-5.6-sol"],
        "opencode": ["deep", "balanced"],
        "cursor": ["deep", "max"],
        "kimi": ["max", "balanced"],
    },
    "corrector": {
        "claude": ["opus", "sonnet"],
        "codex": ["deep", "balanced", "gpt-5.6-sol"],
        "opencode": ["deep", "balanced"],
        "cursor": ["deep", "max"],
    },
    "validator": {
        "claude": ["sonnet", "haiku"],
        "codex": ["balanced", "fast"],
        "opencode": ["balanced", "fast"],
        "cursor": ["balanced", "fast"],
        "kimi": ["balanced", "fast"],
    },
}
for role, mapping in desired.items():
    if prefs.get(role) != mapping:
        prefs[role] = mapping
        changed = True

if changed:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("patched")
else:
    print("noop")
'@

$tmp = Join-Path $env:TEMP ("orch-models-patch-{0}.py" -f ([guid]::NewGuid().ToString('N')))
try {
    Set-Content -LiteralPath $tmp -Value $py -Encoding UTF8
    $out = & python $tmp $modelsPath 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERRO] Patch models.json falhou: $out"
        exit 1
    }
    Write-Host ("[OK] Migration 0.4.20-to-0.4.21 models.json ({0}): {1}" -f $ProjectPath, $out)
}
finally {
    Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
}

exit 0
