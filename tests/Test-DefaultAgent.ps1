#Requires -Version 5.1
# bug-083 — agente padrao da sessao: .claude/settings.json "agent" e
# opencode.json "default_agent" apontam para o subagente orquestrador.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$script = Join-Path $repoRoot 'scripts\Configure-AgentMcp.ps1'

$failures = New-Object System.Collections.Generic.List[string]
function Assert-Test {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { $failures.Add($Message) | Out-Null; Write-Host ("[FAIL] {0}" -f $Message) }
    else { Write-Host ("[OK] {0}" -f $Message) }
}

$work = Join-Path $env:TEMP ("defagent-{0}" -f ([guid]::NewGuid().ToString('N').Substring(0, 8)))
New-Item -ItemType Directory -Force -Path $work | Out-Null
$utf8 = New-Object System.Text.UTF8Encoding($false)

function Invoke-Configure {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $script `
        -ProjectPath $work -PackageRoot $repoRoot 2>&1 | Out-String
}

try {
    # --- 1a rodada: settings.json inexistente -------------------------------
    $out1 = Invoke-Configure
    Write-Host $out1

    $settingsPath = Join-Path $work '.claude\settings.json'
    Assert-Test (Test-Path -LiteralPath $settingsPath) '.claude/settings.json criado'
    $s = Get-Content -LiteralPath $settingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-Test ($s.agent -eq 'orquestrador') 'claude: "agent" = orquestrador'

    $bytes = [System.IO.File]::ReadAllBytes($settingsPath)
    $hasBom = ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)
    Assert-Test (-not $hasBom) 'settings.json gravado sem BOM'

    $ocPath = Join-Path $work 'opencode.json'
    Assert-Test (Test-Path -LiteralPath $ocPath) 'opencode.json criado (subagente opencode presente)'
    $oc = Get-Content -LiteralPath $ocPath -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-Test ($oc.default_agent -eq 'orquestrador') 'opencode: "default_agent" = orquestrador'

    # opencode exige agente PRIMARY: subagent puro cai no fallback "build".
    $ocAgent = Get-Content -LiteralPath (Join-Path $work '.opencode\agent\orquestrador.md') -Raw -Encoding UTF8
    Assert-Test ($ocAgent -match '(?m)^mode:\s*all\s*$') 'subagente opencode com mode: all (serve como primary)'

    # --- idempotencia --------------------------------------------------------
    $before = [System.IO.File]::ReadAllText($settingsPath)
    $out2 = Invoke-Configure
    $after = [System.IO.File]::ReadAllText($settingsPath)
    Assert-Test ($before -eq $after) '2a rodada nao altera settings.json'
    Assert-Test ($out2 -match "agente padrao ja e 'orquestrador'") '2a rodada reporta ja configurado'

    # --- preserva conteudo do usuario ---------------------------------------
    $rich = [ordered]@{
        hooks       = [ordered]@{ PreToolUse = @(@{ matcher = 'Write'; hooks = @() }) }
        permissions = [ordered]@{ allow = @('Bash(terraform plan:*)') }
    }
    [System.IO.File]::WriteAllText($settingsPath, ($rich | ConvertTo-Json -Depth 10), $utf8)
    $null = Invoke-Configure
    $s2 = Get-Content -LiteralPath $settingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-Test ($s2.agent -eq 'orquestrador') 'agent adicionado a settings.json existente'
    Assert-Test ($null -ne $s2.hooks -and $null -ne $s2.permissions) 'hooks e permissions preservados'
    Assert-Test ($s2.permissions.allow -contains 'Bash(terraform plan:*)') 'valores do usuario intactos'

    # --- valor do usuario diferente e PRESERVADO ----------------------------
    $custom = [ordered]@{ agent = 'meu-agente' }
    [System.IO.File]::WriteAllText($settingsPath, ($custom | ConvertTo-Json -Depth 5), $utf8)
    $out3 = Invoke-Configure
    $s3 = Get-Content -LiteralPath $settingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-Test ($s3.agent -eq 'meu-agente') 'agent customizado do usuario NAO e sobrescrito'
    Assert-Test ($out3 -match 'preservado') 'aviso emitido sobre agent customizado'

    # --- settings.json corrompido nao derruba o install ---------------------
    [System.IO.File]::WriteAllText($settingsPath, '{ isso nao e json', $utf8)
    $out4 = Invoke-Configure
    Assert-Test ($LASTEXITCODE -eq 0) 'settings.json invalido nao quebra o script'
    Assert-Test ($out4 -match 'invalido') 'aviso emitido para settings.json invalido'
}
finally {
    Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue
}

if ($failures.Count -gt 0) {
    Write-Host ("FAIL: Test-DefaultAgent - {0} falha(s)." -f $failures.Count)
    exit 1
}
Write-Host 'PASS: Test-DefaultAgent'
exit 0
