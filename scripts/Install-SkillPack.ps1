#Requires -Version 5.1
<#
.SYNOPSIS
    Instala um PACOTE DE SKILLS curado em .orchestrator/skills/ do projeto.

.DESCRIPTION
    0.4.68 — o `skills/discovery.py` ja varre `.orchestrator/skills/**/SKILL.md`
    e o `skill_selector` (haiku) escolhe as mais relevantes por task. Faltava a
    porta de entrada: um jeito versionado e idempotente de trazer colecoes
    externas para dentro, em vez de copiar pasta a mao.

    O mapa de pacotes e CURADO neste arquivo, de proposito. Mesma regra de
    seguranca do Update-Agents: NUNCA buscar URL vinda da saida de um agente ou
    de argumento livre — so nomes desta lista.

    Instalacao e POR PROJETO. Nao instale um pacote de marketing num backend:
    o seletor de skills recebe a lista inteira e cada descricao extra encarece
    TODA task, inclusive as de codigo.

.EXAMPLE
    Install-SkillPack.ps1 -List
    Install-SkillPack.ps1 -Pack marketing -ProjectPath D:\StarFusion\vavi
#>
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [string]$Pack,
    [switch]$List,
    [switch]$Force,
    [switch]$DryRun,
    # Origem alternativa (usada pelos testes; evita rede). Caminho local.
    [string]$SourceOverride
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Orchestrator.Common.ps1')

# name -> { url; subdir dentro do repo; licenca; descricao }
function Get-SkillPackMap {
    return @{
        'marketing' = @{
            url      = 'https://github.com/coreyhaines31/marketingskills.git'
            subdir   = 'skills'
            license  = 'MIT (Corey Haines)'
            summary  = '49 skills de marketing: CRO, copy, SEO, ads, pricing, lancamento, RevOps'
        }
    }
}

$map = Get-SkillPackMap

if ($List -or -not $Pack) {
    Write-Host 'Pacotes de skills disponiveis:'
    foreach ($name in ($map.Keys | Sort-Object)) {
        $spec = $map[$name]
        Write-Host ("  {0,-12} {1}" -f $name, $spec.summary)
        Write-Host ("  {0,-12} licenca: {1}" -f '', $spec.license)
    }
    Write-Host ''
    Write-Host 'Uso: orchestrator skills install <pacote> (ou -Pack <pacote> -ProjectPath <projeto>)'
    exit 0
}

$packName = $Pack.Trim().ToLowerInvariant()
if (-not $map.ContainsKey($packName)) {
    Write-Host ("[ERRO] pacote desconhecido: '{0}'. Conhecidos: {1}" -f $packName, ($map.Keys -join ', '))
    exit 2
}

$spec = $map[$packName]
$projectRoot = Get-ProjectRoot -ProjectPath $ProjectPath
$orchestratorRoot = Get-OrchestratorRoot -ProjectPath $projectRoot
$destino = Join-Path $orchestratorRoot ("skills\{0}" -f $packName)

if ((Test-Path -LiteralPath $destino) -and -not $Force) {
    $n = @(Get-ChildItem -LiteralPath $destino -Recurse -Filter 'SKILL.md' -ErrorAction SilentlyContinue).Count
    Write-Host ("[OK] pacote '{0}' ja instalado ({1} skills) em {2}. Use -Force para reinstalar." -f $packName, $n, $destino)
    exit 0
}

if ($DryRun) {
    Write-Host ("[DRY-RUN] instalaria '{0}' de {1} em {2}" -f $packName, $spec.url, $destino)
    exit 0
}

# Origem: repo git curado, ou caminho local (testes).
$staging = $null
try {
    if ($SourceOverride) {
        if (-not (Test-Path -LiteralPath $SourceOverride)) {
            Write-Host ("[ERRO] SourceOverride inexistente: {0}" -f $SourceOverride)
            exit 2
        }
        $origem = $SourceOverride
    }
    else {
        $git = Get-Command git -ErrorAction SilentlyContinue
        if (-not $git) {
            Write-Host '[ERRO] git nao encontrado no PATH; nao da para buscar o pacote.'
            exit 2
        }
        $staging = Join-Path $env:TEMP ("skillpack-{0}" -f ([guid]::NewGuid().ToString('N').Substring(0, 8)))
        Write-Host ("[INFO] baixando '{0}' de {1}" -f $packName, $spec.url)
        # --depth 1: so o conteudo atual interessa; historico seria desperdicio.
        $out = & git clone --depth 1 --quiet $spec.url $staging 2>&1 | Out-String
        if ($LASTEXITCODE -ne 0) {
            Write-Host ("[ERRO] clone falhou: {0}" -f $out.Trim())
            exit 1
        }
        $origem = Join-Path $staging $spec.subdir
        if (-not (Test-Path -LiteralPath $origem)) {
            Write-Host ("[ERRO] subdiretorio '{0}' ausente no repositorio." -f $spec.subdir)
            exit 1
        }
    }

    $skills = @(Get-ChildItem -LiteralPath $origem -Recurse -Filter 'SKILL.md' -ErrorAction SilentlyContinue)
    if ($skills.Count -eq 0) {
        Write-Host '[ERRO] nenhum SKILL.md encontrado na origem; nada instalado.'
        exit 1
    }

    if (Test-Path -LiteralPath $destino) {
        Remove-Item -LiteralPath $destino -Recurse -Force
    }
    Ensure-Directory -Path (Split-Path -Parent $destino) | Out-Null
    Copy-Item -LiteralPath $origem -Destination $destino -Recurse -Force

    # Procedencia junto do conteudo: quem auditar depois precisa saber a origem.
    $manifest = [ordered]@{
        pack         = $packName
        source       = $spec.url
        license      = $spec.license
        installed_at = (Get-Date).ToString('o')
        skills       = $skills.Count
    }
    [System.IO.File]::WriteAllText(
        (Join-Path $destino 'SKILLPACK.json'),
        ($manifest | ConvertTo-Json -Depth 5),
        [System.Text.UTF8Encoding]::new($false)
    )
    Write-Host ("[OK] pacote '{0}' instalado: {1} skills em {2}" -f $packName, $skills.Count, $destino)
    Write-Host ("[INFO] licenca: {0}" -f $spec.license)
    Write-Host '[INFO] o skill_selector passa a considera-las na proxima task deste projeto.'
}
finally {
    if ($staging -and (Test-Path -LiteralPath $staging)) {
        Remove-Item -LiteralPath $staging -Recurse -Force -ErrorAction SilentlyContinue
    }
}

exit 0
