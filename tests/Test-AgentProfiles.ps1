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

        Assert-Test -Condition ($profile.id -eq $id) -Message ("id divergente em {0}.json" -f $id)
        Assert-Test -Condition ($profile.kind -in @('cli', 'ide-hint')) -Message ("kind invalido em {0}.json" -f $id)

        if ($profile.kind -eq 'ide-hint') {
            Assert-Test -Condition ($null -ne $profile.PSObject.Properties['hint'] -and -not [string]::IsNullOrWhiteSpace([string]$profile.hint)) -Message ("hint ausente em {0}.json" -f $id)
            continue
        }

        # kind = cli: campos obrigatorios
        Assert-Test -Condition ($null -ne $profile.PSObject.Properties['verified']) -Message ("verified ausente em {0}.json" -f $id)
        Assert-Test -Condition ($null -ne $profile.PSObject.Properties['invoke']) -Message ("invoke ausente em {0}.json" -f $id)
        Assert-Test -Condition ($null -ne $profile.invoke.PSObject.Properties['subcommand']) -Message ("invoke.subcommand ausente em {0}.json" -f $id)
        Assert-Test -Condition ($profile.invoke.prompt_via -eq 'arg') -Message ("invoke.prompt_via != arg em {0}.json (v1 so suporta arg)" -f $id)
        Assert-Test -Condition ($null -ne $profile.invoke.PSObject.Properties['prompt_flag']) -Message ("invoke.prompt_flag ausente em {0}.json" -f $id)
        Assert-Test -Condition ($null -ne $profile.invoke.PSObject.Properties['sandbox_flags']) -Message ("invoke.sandbox_flags ausente em {0}.json" -f $id)
        Assert-Test -Condition ($null -ne $profile.PSObject.Properties['output']) -Message ("output ausente em {0}.json" -f $id)
        Assert-Test -Condition ($profile.exit_codes.success -eq 0) -Message ("exit_codes.success != 0 em {0}.json" -f $id)
        Assert-Test -Condition ([int]$profile.timeout_default_s -gt 0) -Message ("timeout_default_s invalido em {0}.json" -f $id)
    }

    # schema existe e e JSON valido
    $schemaPath = Join-Path $repoRoot 'package\schemas\agent-profile.schema.json'
    Assert-Test -Condition (Test-Path -LiteralPath $schemaPath) -Message 'agent-profile.schema.json ausente'
    $null = Get-Content -LiteralPath $schemaPath -Raw | ConvertFrom-Json

    Write-Host ('PASS: {0}' -f $TestName) -ForegroundColor Green
    $exitCode = 0
}
catch {
    Write-Host ('FAIL: {0} - {1}' -f $TestName, $_.Exception.Message) -ForegroundColor Red
}

exit $exitCode
