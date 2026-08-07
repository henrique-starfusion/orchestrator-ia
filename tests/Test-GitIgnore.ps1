#Requires -Version 5.1
# 0.4.63 — .gitignore com o estado local de agentes. Sem ele, .orchestrator/,
# .claude/ e o .mcp.json (caminhos ABSOLUTOS desta maquina) vao para o commit e
# o proximo checkout regride a versao instalada — foi o que aconteceu em
# printbee, adzora e trustsafe.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$script = Join-Path $repoRoot 'scripts\Configure-GitIgnore.ps1'

$failures = New-Object System.Collections.Generic.List[string]
function Assert-Test {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { $failures.Add($Message) | Out-Null; Write-Host ("[FAIL] {0}" -f $Message) }
    else { Write-Host ("[OK] {0}" -f $Message) }
}

$work = Join-Path $env:TEMP ("gitignore-{0}" -f ([guid]::NewGuid().ToString('N').Substring(0, 8)))
New-Item -ItemType Directory -Force -Path $work | Out-Null
$utf8 = New-Object System.Text.UTF8Encoding($false)
$gitignore = Join-Path $work '.gitignore'

function Invoke-Configure {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $script -ProjectPath $work 2>&1 | Out-String
}

try {
    # --- 1a rodada: arquivo inexistente --------------------------------------
    $out1 = Invoke-Configure
    Write-Host $out1
    Assert-Test (Test-Path -LiteralPath $gitignore) '.gitignore criado'

    $text = [System.IO.File]::ReadAllText($gitignore)
    foreach ($entry in @('.claude/', '.codex/', '.cursor/', '.kimi/', '.kimi-code/',
            '.opencode/', '.orchestrator/', '.vscode/', '.wolf/', 'graphify-out/',
            '.agents/', '.mcp.json')) {
        Assert-Test ($text -match [regex]::Escape($entry)) ("entrada presente: {0}" -f $entry)
    }

    $bytes = [System.IO.File]::ReadAllBytes($gitignore)
    $hasBom = ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)
    Assert-Test (-not $hasBom) '.gitignore sem BOM (git leria o BOM como parte do 1o padrao)'

    # Adaptadores em markdown NAO sao ignorados: sao instrucoes de projeto.
    Assert-Test ($text -notmatch '(?m)^CLAUDE\.md') 'CLAUDE.md nao e ignorado'
    Assert-Test ($text -notmatch '(?m)^AGENTS\.md') 'AGENTS.md nao e ignorado'

    # --- idempotencia --------------------------------------------------------
    $before = [System.IO.File]::ReadAllText($gitignore)
    $out2 = Invoke-Configure
    $after = [System.IO.File]::ReadAllText($gitignore)
    Assert-Test ($before -eq $after) '2a rodada nao altera o arquivo'
    Assert-Test ($out2 -match 'ja atualizado') '2a rodada reporta ja configurado'

    # --- conteudo do usuario preservado --------------------------------------
    $user = "node_modules/`n*.log`ndist/`n"
    [System.IO.File]::WriteAllText($gitignore, $user, $utf8)
    $null = Invoke-Configure
    $merged = [System.IO.File]::ReadAllText($gitignore)
    Assert-Test ($merged -match '(?m)^node_modules/$') 'linha do usuario preservada (node_modules)'
    Assert-Test ($merged -match '(?m)^\*\.log$') 'linha do usuario preservada (*.log)'
    Assert-Test ($merged -match '(?m)^dist/$') 'linha do usuario preservada (dist)'
    Assert-Test ($merged -match '\.orchestrator/') 'bloco do orquestrador anexado'

    # --- bloco antigo e SUBSTITUIDO, nao duplicado ---------------------------
    $null = Invoke-Configure
    $twice = [System.IO.File]::ReadAllText($gitignore)
    $blockCount = ([regex]::Matches($twice, [regex]::Escape('# <<< orchestrator <<<'))).Count
    Assert-Test ($blockCount -eq 1) 'bloco gerenciado aparece uma unica vez'
    $orchCount = ([regex]::Matches($twice, '(?m)^\.orchestrator/$')).Count
    Assert-Test ($orchCount -eq 1) 'entrada nao duplica a cada rodada'

    # --- dry-run nao escreve --------------------------------------------------
    [System.IO.File]::WriteAllText($gitignore, "so-do-usuario`n", $utf8)
    $outDry = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $script `
        -ProjectPath $work -DryRun 2>&1 | Out-String
    $stillUser = [System.IO.File]::ReadAllText($gitignore)
    Assert-Test ($stillUser -eq "so-do-usuario`n") '-DryRun nao escreve no arquivo'
    Assert-Test ($outDry -match 'DRY-RUN') '-DryRun reporta o que faria'

    # --- repo do PROPRIO orquestrador nao recebe o bloco (mesma excecao do
    # bug-091): la .cursor/rules/ e .orchestrator/ sao conteudo VERSIONADO.
    $selfRepo = Join-Path $env:TEMP ("gitignore-self-{0}" -f ([guid]::NewGuid().ToString('N').Substring(0, 8)))
    New-Item -ItemType Directory -Force -Path (Join-Path $selfRepo 'runtime\src\orchestrator_runtime') | Out-Null
    [System.IO.File]::WriteAllText((Join-Path $selfRepo '.gitignore'), "node_modules/`n", $utf8)
    $outSelf = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $script -ProjectPath $selfRepo 2>&1 | Out-String
    $selfText = [System.IO.File]::ReadAllText((Join-Path $selfRepo '.gitignore'))
    Assert-Test ($selfText -eq "node_modules/`n") 'repo do orquestrador: .gitignore intacto'
    Assert-Test ($outSelf -match 'repositorio do proprio orquestrador') 'motivo do skip reportado'
    Remove-Item -Recurse -Force $selfRepo -ErrorAction SilentlyContinue
}
finally {
    Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue
}

if ($failures.Count -gt 0) {
    Write-Host ("FAIL: Test-GitIgnore - {0} falha(s)." -f $failures.Count)
    exit 1
}
Write-Host 'PASS: Test-GitIgnore'
exit 0
