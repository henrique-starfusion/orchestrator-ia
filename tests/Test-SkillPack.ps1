#Requires -Version 5.1
# 0.4.68 — instalador de pacote de skills. Sem rede: usa -SourceOverride.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$script = Join-Path $repoRoot 'scripts\Install-SkillPack.ps1'

$failures = New-Object System.Collections.Generic.List[string]
function Assert-Test {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { $failures.Add($Message) | Out-Null; Write-Host ("[FAIL] {0}" -f $Message) }
    else { Write-Host ("[OK] {0}" -f $Message) }
}

$work = Join-Path $env:TEMP ("skillpack-t-{0}" -f ([guid]::NewGuid().ToString('N').Substring(0, 8)))
$fonte = Join-Path $env:TEMP ("skillpack-src-{0}" -f ([guid]::NewGuid().ToString('N').Substring(0, 8)))
New-Item -ItemType Directory -Force -Path (Join-Path $work '.orchestrator\skills') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $fonte 'cro') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $fonte 'copywriting') | Out-Null
$utf8 = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText((Join-Path $fonte 'cro\SKILL.md'), "---`nname: cro`ndescription: otimizacao de conversao`n---`n", $utf8)
[System.IO.File]::WriteAllText((Join-Path $fonte 'copywriting\SKILL.md'), "---`nname: copywriting`ndescription: copy`n---`n", $utf8)

function Invoke-Install {
    param([switch]$Force, [switch]$DryRun)
    $args = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $script,
        '-ProjectPath', $work, '-Pack', 'marketing', '-SourceOverride', $fonte)
    if ($Force) { $args += '-Force' }
    if ($DryRun) { $args += '-DryRun' }
    & powershell.exe @args 2>&1 | Out-String
}

try {
    # --- listagem nao precisa de projeto -------------------------------------
    $outList = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $script -List 2>&1 | Out-String
    Assert-Test ($outList -match 'marketing') '-List mostra o pacote marketing'
    Assert-Test ($outList -match 'MIT') '-List declara a licenca'

    # --- pacote desconhecido e recusado --------------------------------------
    $null = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $script `
        -ProjectPath $work -Pack 'nao-existe' 2>&1 | Out-String
    Assert-Test ($LASTEXITCODE -eq 2) 'pacote fora do mapa curado e recusado (exit 2)'

    # --- dry-run nao escreve --------------------------------------------------
    $outDry = Invoke-Install -DryRun
    $destino = Join-Path $work '.orchestrator\skills\marketing'
    Assert-Test ($outDry -match 'DRY-RUN') '-DryRun reporta o que faria'
    Assert-Test (-not (Test-Path -LiteralPath $destino)) '-DryRun nao instalou nada'

    # --- instalacao ------------------------------------------------------------
    $out1 = Invoke-Install
    Write-Host $out1
    Assert-Test (Test-Path -LiteralPath $destino) 'pacote instalado em .orchestrator/skills/marketing'
    $encontradas = @(Get-ChildItem -LiteralPath $destino -Recurse -Filter 'SKILL.md')
    Assert-Test ($encontradas.Count -eq 2) ("2 skills copiadas (achou {0})" -f $encontradas.Count)

    $manifestPath = Join-Path $destino 'SKILLPACK.json'
    Assert-Test (Test-Path -LiteralPath $manifestPath) 'manifest de procedencia gravado'
    $m = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-Test ($m.pack -eq 'marketing') 'manifest identifica o pacote'
    Assert-Test ($m.license -match 'MIT') 'manifest registra a licenca'
    Assert-Test ($m.skills -eq 2) 'manifest conta as skills'

    # --- idempotencia ----------------------------------------------------------
    $out2 = Invoke-Install
    Assert-Test ($out2 -match 'ja instalado') '2a rodada nao reinstala sem -Force'

    # --- -Force reinstala ------------------------------------------------------
    [System.IO.File]::WriteAllText((Join-Path $destino 'lixo.txt'), 'sujeira', $utf8)
    $null = Invoke-Install -Force
    Assert-Test (-not (Test-Path -LiteralPath (Join-Path $destino 'lixo.txt'))) `
        '-Force limpa o destino antes de recopiar'
}
finally {
    Remove-Item -Recurse -Force $work, $fonte -ErrorAction SilentlyContinue
}

if ($failures.Count -gt 0) {
    Write-Host ("FAIL: Test-SkillPack - {0} falha(s)." -f $failures.Count)
    exit 1
}
Write-Host 'PASS: Test-SkillPack'
exit 0
