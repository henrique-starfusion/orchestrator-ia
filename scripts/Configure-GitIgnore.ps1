#Requires -Version 5.1
<#
.SYNOPSIS
    Garante que o .gitignore do projeto ignore as pastas/arquivos de agentes.

.DESCRIPTION
    0.4.63 — a instalacao espalha estado local de agente pelo projeto
    (.claude/, .codex/, .cursor/, .orchestrator/, .wolf/, graphify-out/, .mcp.json
    com caminhos ABSOLUTOS desta maquina...). Sem .gitignore isso vaza para o
    commit: o proximo checkout REGRIDE a versao instalada e o .mcp.json de outra
    maquina quebra o registro do MCP. Foi exatamente o que aconteceu em printbee,
    adzora e trustsafe, que versionam .orchestrator/ no git do projeto.

    Escreve um BLOCO DELIMITADO e so ele: linhas do usuario fora do bloco nunca
    sao tocadas, e reinstalar/atualizar apenas reescreve o bloco. Arquivo ja
    rastreado pelo git NAO e afetado por .gitignore — para esses, o dono decide
    entre `git rm --cached` e manter versionado; este script nao remove nada.
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
$gitignorePath = Join-Path $projectRoot '.gitignore'

# Mesma excecao do bug-091: o repositorio DO PROPRIO pacote nao recebe o bloco.
# Aqui .cursor/rules/ e .orchestrator/ (profiles, skills) sao CONTEUDO
# VERSIONADO — sao o que o pacote distribui. Ignora-los faria arquivo novo
# desses diretorios parar de aparecer no git em silencio.
if (Test-Path -LiteralPath (Join-Path $projectRoot 'runtime\src\orchestrator_runtime')) {
    Write-Host '[SKIP] repositorio do proprio orquestrador: .gitignore nao alterado (versiona .cursor/rules e .orchestrator).'
    exit 0
}

$beginMarker = '# >>> orchestrator: estado local de agentes (bloco gerenciado) >>>'
$endMarker = '# <<< orchestrator <<<'

# Somente ESTADO LOCAL. Adaptadores em markdown (AGENTS.md, CLAUDE.md,
# GEMINI.md, CURSOR.md) ficam de fora de proposito: sao instrucoes de projeto
# que o time le e revisa, nao cache de ferramenta.
$entries = @(
    '.agents/'
    '.claude/'
    '.codex/'
    '.cursor/'
    '.gemini/'
    '.kimi/'
    '.kimi-code/'
    '.opencode/'
    '.orchestrator/'
    '.remember/'
    '.vscode/'
    '.wolf/'
    'graphify-out/'
    # Caminhos absolutos desta maquina — inuteis (e quebrados) em outra.
    '.mcp.json'
    'opencode.json'
)

$block = @($beginMarker) + $entries + @($endMarker)
$blockText = ($block -join "`n")

$existing = ''
if (Test-Path -LiteralPath $gitignorePath) {
    $existing = [System.IO.File]::ReadAllText($gitignorePath)
}

$lines = @()
if (-not [string]::IsNullOrEmpty($existing)) {
    $lines = @($existing -split "`r?`n")
}

# Remove o bloco anterior (se houver) preservando todo o resto.
$kept = New-Object System.Collections.Generic.List[string]
$inBlock = $false
$hadBlock = $false
foreach ($line in $lines) {
    if ($line -eq $beginMarker) { $inBlock = $true; $hadBlock = $true; continue }
    if ($inBlock) {
        if ($line -eq $endMarker) { $inBlock = $false }
        continue
    }
    $kept.Add($line) | Out-Null
}
# Bloco aberto sem fim (arquivo editado a mao): o loop acima ja descartou o
# resto; nao ha o que restaurar, e o bloco novo entra limpo.

# Tira linhas vazias do fim para nao acumular uma a cada update.
while ($kept.Count -gt 0 -and [string]::IsNullOrWhiteSpace($kept[$kept.Count - 1])) {
    $kept.RemoveAt($kept.Count - 1) | Out-Null
}

$final = @()
if ($kept.Count -gt 0) { $final += $kept; $final += '' }
$final += $block
$newText = ($final -join "`n") + "`n"

if ($existing -eq $newText) {
    Write-Host '[OK] .gitignore: bloco do orquestrador ja atualizado.'
    exit 0
}
if ($DryRun) {
    $verb = if ($hadBlock) { 'atualizaria' } else { 'adicionaria' }
    Write-Host ("[DRY-RUN] .gitignore: {0} {1} entradas de agentes." -f $verb, $entries.Count)
    exit 0
}

# UTF8 sem BOM: git le .gitignore como bytes e um BOM vira parte do 1o padrao.
[System.IO.File]::WriteAllText(
    $gitignorePath, $newText, [System.Text.UTF8Encoding]::new($false)
)
$verb = if ($hadBlock) { 'atualizado' } else { 'criado' }
Write-Host ("[OK] .gitignore {0}: {1} entradas de estado local de agentes." -f $verb, $entries.Count)

# Aviso acionavel: .gitignore nao desfaz rastreamento ja existente.
$tracked = @()
if (Get-Command git -ErrorAction SilentlyContinue) {
    try {
        Push-Location $projectRoot
        foreach ($entry in $entries) {
            $probe = $entry.TrimEnd('/')
            $out = & git ls-files --error-unmatch -- $probe 2>$null
            if ($LASTEXITCODE -eq 0 -and $out) { $tracked += $probe }
        }
    }
    catch { }
    finally { Pop-Location }
}
if ($tracked.Count -gt 0) {
    Write-Host ("[ACAO] ja rastreado(s) pelo git (o ignore NAO se aplica): {0}" -f ($tracked -join ', '))
    Write-Host "[ACAO] para parar de versionar sem apagar do disco: git rm -r --cached <caminho>"
}

exit 0
