#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Test-Helpers.ps1')

$TestName = 'Test-AgentProfiles'
$exitCode = 1

$expectedIds = @('claude', 'codex', 'gemini', 'opencode', 'kimi', 'cursor')

try {
    $repoRoot = Get-TestRepoRoot
    $templateDir = Join-Path $repoRoot 'package\template\.orchestrator\agents\profiles'
    $liveDir = Join-Path $repoRoot '.orchestrator\agents\profiles'

    foreach ($id in $expectedIds) {
        $templatePath = Join-Path $templateDir ("{0}.json" -f $id)
        $livePath = Join-Path $liveDir ("{0}.json" -f $id)

        Assert-Test -Condition (Test-Path -LiteralPath $templatePath) -Message ("profile template ausente: {0}" -f $id)
        Assert-Test -Condition (Test-Path -LiteralPath $livePath) -Message ("profile live ausente: {0}" -f $id)

        # template e live identicos (byte a byte)
        $hashTemplate = (Get-FileHash -LiteralPath $templatePath -Algorithm SHA256).Hash
        $hashLive = (Get-FileHash -LiteralPath $livePath -Algorithm SHA256).Hash
        Assert-Test -Condition ($hashTemplate -eq $hashLive) -Message ("template != live: {0}.json" -f $id)

        $profile = Get-Content -LiteralPath $templatePath -Raw | ConvertFrom-Json

        Assert-Test -Condition ($null -ne $profile.PSObject.Properties['id']) -Message ("id ausente em {0}.json" -f $id)
        Assert-Test -Condition ($profile.id -eq $id) -Message ("id divergente em {0}.json" -f $id)
        Assert-Test -Condition ($null -ne $profile.PSObject.Properties['kind']) -Message ("kind ausente em {0}.json" -f $id)
        Assert-Test -Condition ($profile.kind -in @('cli', 'ide-hint', 'ide-client')) -Message ("kind invalido em {0}.json" -f $id)

        if ($profile.kind -in @('ide-hint', 'ide-client')) {
            Assert-Test -Condition ($null -ne $profile.PSObject.Properties['hint'] -and -not [string]::IsNullOrWhiteSpace([string]$profile.hint)) -Message ("hint ausente em {0}.json" -f $id)
            continue
        }

        # kind = cli: campos obrigatorios
        Assert-Test -Condition ($null -ne $profile.PSObject.Properties['verified']) -Message ("verified ausente em {0}.json" -f $id)
        Assert-Test -Condition ($null -ne $profile.PSObject.Properties['invoke']) -Message ("invoke ausente em {0}.json" -f $id)
        Assert-Test -Condition ($null -ne $profile.invoke.PSObject.Properties['subcommand']) -Message ("invoke.subcommand ausente em {0}.json" -f $id)
        Assert-Test -Condition ($null -ne $profile.invoke.PSObject.Properties['prompt_via']) -Message ("invoke.prompt_via ausente em {0}.json" -f $id)
        Assert-Test -Condition ($profile.invoke.prompt_via -eq 'arg') -Message ("invoke.prompt_via != arg em {0}.json (v1 so suporta arg)" -f $id)
        Assert-Test -Condition ($null -ne $profile.invoke.PSObject.Properties['prompt_flag']) -Message ("invoke.prompt_flag ausente em {0}.json" -f $id)
        Assert-Test -Condition ($null -ne $profile.invoke.PSObject.Properties['sandbox_flags']) -Message ("invoke.sandbox_flags ausente em {0}.json" -f $id)
        Assert-Test -Condition ($null -ne $profile.PSObject.Properties['output']) -Message ("output ausente em {0}.json" -f $id)
        Assert-Test -Condition ($null -ne $profile.PSObject.Properties['exit_codes']) -Message ("exit_codes ausente em {0}.json" -f $id)
        Assert-Test -Condition ($null -ne $profile.exit_codes.PSObject.Properties['success']) -Message ("exit_codes.success ausente em {0}.json" -f $id)
        Assert-Test -Condition ($profile.exit_codes.success -eq 0) -Message ("exit_codes.success != 0 em {0}.json" -f $id)
        Assert-Test -Condition ($null -ne $profile.PSObject.Properties['timeout_default_s']) -Message ("timeout_default_s ausente em {0}.json" -f $id)
        Assert-Test -Condition ([int]$profile.timeout_default_s -gt 0) -Message ("timeout_default_s invalido em {0}.json" -f $id)
    }

    # schema existe e e JSON valido
    $schemaPath = Join-Path $repoRoot 'package\schemas\agent-profile.schema.json'
    Assert-Test -Condition (Test-Path -LiteralPath $schemaPath) -Message 'agent-profile.schema.json ausente'
    $null = Get-Content -LiteralPath $schemaPath -Raw | ConvertFrom-Json

    # --- golden: dispatch monta a linha certa por profile (DryRun, sem CLI no PATH) ---
    $tempDir = New-TestProjectDirectory
    try {
        Invoke-TestInstall -ProjectPath $tempDir -PackageRoot $repoRoot

        $invokeScript = Join-Path $repoRoot 'scripts\Invoke-RoutedAgent.ps1'

        $goldens = @(
            @{ Client = 'claude';   TaskClass = 'docs';  Pattern = '\[ETAPA\] claude --model sonnet -p PING' },
            @{ Client = 'codex';    TaskClass = 'docs';  Pattern = '\[ETAPA\] codex exec -m gpt-5\.6-sol PING' },
            @{ Client = 'gemini';   TaskClass = 'docs';  Pattern = '\[ETAPA\] gemini -m gemini-3\.1-pro -p PING'; ExpectAviso = $true },
            @{ Client = 'opencode'; TaskClass = 'docs';  Pattern = '\[ETAPA\] opencode run --model default PING' }
        )

        foreach ($g in $goldens) {
            $output = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $invokeScript `
                -ProjectPath $tempDir -TaskClass $g.TaskClass -Client $g.Client -Prompt 'PING' -DryRun 2>&1 | Out-String
            Assert-Test -Condition ($output -match $g.Pattern) -Message ("golden falhou para {0}: esperado /{1}/ em: {2}" -f $g.Client, $g.Pattern, $output)
            if ($g.ContainsKey('ExpectAviso') -and $g.ExpectAviso) {
                Assert-Test -Condition ($output -match '\[AVISO\]') -Message ("golden {0}: esperado [AVISO] (verified=false) na saida" -f $g.Client)
            }
        }

        # cursor (ide-client): orienta runtime; nao executa CLI
        $cursorOut = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $invokeScript `
            -ProjectPath $tempDir -TaskClass 'docs' -Client 'cursor' -Prompt 'PING' -DryRun 2>&1 | Out-String
        Assert-Test -Condition ($cursorOut -match 'orchestrator run' -or $cursorOut -match 'model=') -Message 'cursor ide-client nao imprimiu orientacao de runtime/model='
        Assert-Test -Condition ($cursorOut -match 'DEPRECADO' -or $cursorOut -match 'nao e worker') -Message 'cursor ide-client deveria sinalizar deprecacao/nao-worker'
    }
    finally {
        Remove-TestProjectDirectory -Path $tempDir
    }

    Write-Host ('PASS: {0}' -f $TestName) -ForegroundColor Green
    $exitCode = 0
}
catch {
    Write-Host ('FAIL: {0} - {1}' -f $TestName, $_.Exception.Message) -ForegroundColor Red
}

exit $exitCode
