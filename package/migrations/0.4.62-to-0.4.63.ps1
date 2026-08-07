#Requires -Version 5.1
# Migration 0.4.62 -> 0.4.63
# - bug-090: deadlock de pipe no CliExecutor (stdin escrito antes das leitoras).
#   Correcao so de codigo; nenhuma chave de config.
# - bug-093: reaper de task NAO-TERMINAL. Nova chave "stale_execution_grace_s"
#   (900) — margem SOBRE o maximum_duration_seconds da propria task. 0 desliga.
# - bug-094: auto-reparo de CLI de agente quebrado. Novas chaves
#   "agent_auto_repair" (true) e "agent_repair_timeout_s" (300).
# - .gitignore com o estado local de agentes passa a ser escrito pelo install
#   (Configure-GitIgnore.ps1), em bloco delimitado. Se o projeto JA versiona
#   .orchestrator/ (printbee, adzora, trustsafe), o ignore nao desfaz o
#   rastreamento — o script avisa e sugere `git rm -r --cached`.
#
# Ausencia das chaves nao quebra nada (config.py tem os mesmos padroes), mas
# gravar deixa o valor visivel para quem for ajustar.
param(
    [string]$ProjectPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = if ($ProjectPath) { $ProjectPath } else { (Get-Location).Path }
$policiesPath = Join-Path $root '.orchestrator\config\policies.json'

if (-not (Test-Path -LiteralPath $policiesPath)) {
    Write-Host '[INFO] policies.json ausente; nada a migrar.'
    Write-Host '[OK] Migration 0.4.62-to-0.4.63 applied.'
    exit 0
}

$defaults = [ordered]@{
    stale_execution_grace_s = 900
    agent_auto_repair       = $true
    agent_repair_timeout_s  = 300
}

try {
    $raw = Get-Content -LiteralPath $policiesPath -Raw -Encoding UTF8
    $data = $raw | ConvertFrom-Json
}
catch {
    Write-Host ('[AVISO] policies.json invalido; chaves novas nao adicionadas: {0}' -f $_.Exception.Message)
    Write-Host '[OK] Migration 0.4.62-to-0.4.63 applied.'
    exit 0
}

$added = @()
foreach ($key in $defaults.Keys) {
    if (-not $data.PSObject.Properties[$key]) {
        $data | Add-Member -NotePropertyName $key -NotePropertyValue $defaults[$key] -Force
        $added += $key
    }
}

if ($added.Count -gt 0) {
    # UTF8 sem BOM: o runtime le com json.loads e um BOM quebra o parse.
    [System.IO.File]::WriteAllText(
        $policiesPath, ($data | ConvertTo-Json -Depth 20), [System.Text.UTF8Encoding]::new($false)
    )
    Write-Host ('[OK] policies.json: {0} chave(s) adicionada(s) -> {1}' -f $added.Count, ($added -join ', '))
}
else {
    Write-Host '[OK] policies.json ja tem as chaves da 0.4.63.'
}

Write-Host '[OK] Migration 0.4.62-to-0.4.63 applied.'
exit 0
