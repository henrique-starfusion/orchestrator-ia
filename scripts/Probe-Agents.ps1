#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [int]$TimeoutSeconds = 30,
    [switch]$SkipAgentProbes
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Orchestrator.Common.ps1')

$projectRoot = Get-ProjectRoot -ProjectPath $ProjectPath
$orchestratorRoot = Get-OrchestratorRoot -ProjectPath $projectRoot
$resultsPath = Join-Path $orchestratorRoot 'agents\probe-results.json'
Ensure-Directory -Path (Join-Path $orchestratorRoot 'agents') | Out-Null

$now = (Get-Date).ToString('o')
$results = @()

if ($SkipAgentProbes) {
    Write-Host '[INFO] Probes de agentes ignorados (-SkipAgentProbes).'
    Write-JsonFile -Path $resultsPath -Object @{
        probed_at = $now
        skipped   = $true
        reason    = 'SkipAgentProbes'
        agents    = @()
    }
    exit 0
}

$detectedPath = Join-Path $orchestratorRoot 'agents\detected.json'
if (-not (Test-Path -LiteralPath $detectedPath)) {
    Write-Host '[AVISO] detected.json ausente; probes ignorados.'
    Write-JsonFile -Path $resultsPath -Object @{
        probed_at = $now
        skipped   = $true
        reason    = 'no_detected_json'
        agents    = @()
    }
    exit 0
}

$detected = Get-JsonFileContent -Path $detectedPath
foreach ($agent in $detected.agents) {
    if ($agent.status -ne 'available') {
        continue
    }

    if (Test-IsIdeAgent -Name $agent.name) {
        $results += [pscustomobject]@{
            name   = $agent.name
            status = 'skipped_ide'
            detail = 'ide_agent_sem_exec_probe'
        }
        continue
    }

    $cmd = Get-Command $agent.name -ErrorAction SilentlyContinue
    if (-not $cmd) {
        $results += [pscustomobject]@{
            name   = $agent.name
            status = 'skipped_safe'
            detail = 'command_not_found'
        }
        continue
    }

    # O help tem que ser o do comando que o profile REALMENTE invoca: as flags do
    # codex (--sandbox, --skip-git-repo-check) so aparecem em `codex exec --help`,
    # nao no help de topo. Pedir o help errado gera falso "flag ausente".
    $profilePath = Join-Path $orchestratorRoot ("agents\profiles\{0}.json" -f $agent.name)
    $profile = $null
    if (Test-Path -LiteralPath $profilePath) { $profile = Get-JsonFileContent -Path $profilePath }
    $helpArgs = @()
    if ($profile -and $profile.PSObject.Properties['invoke'] -and $profile.invoke `
            -and $profile.invoke.PSObject.Properties['subcommand'] -and $profile.invoke.subcommand) {
        $helpArgs += @($profile.invoke.subcommand | ForEach-Object { [string]$_ })
    }
    $helpArgs += '--help'

    $probeResult = Invoke-ExternalCommand -FilePath $cmd.Source -ArgumentList $helpArgs -TimeoutSeconds $TimeoutSeconds -WorkingDirectory $projectRoot
    if ($probeResult.timed_out) {
        $results += [pscustomobject]@{
            name   = $agent.name
            status = 'timeout'
            detail = 'help_command_timeout'
        }
        continue
    }

    # 0.4.32 — `--help` sair 0 nunca provou nada sobre COMO invocar o agente.
    # O profile do kimi passava aqui e mesmo assim mandava o prompt como
    # argumento nu, que o CLI recusa ("unknown command"). Agora as flags que o
    # profile VAI usar sao conferidas contra o help do CLI instalado.
    $helpText = ("{0}`n{1}" -f $probeResult.stdout, $probeResult.stderr)
    $expected = @()
    $profileVerified = $null
    if ($profile) {
        if ($profile.PSObject.Properties['verified']) { $profileVerified = $profile.verified }
        if ($profile.PSObject.Properties['invoke'] -and $profile.invoke) {
            $inv = $profile.invoke
            if ($inv.PSObject.Properties['prompt_flag'] -and $inv.prompt_flag) {
                $expected += [string]$inv.prompt_flag
            }
            if ($inv.PSObject.Properties['sandbox_flags'] -and $inv.sandbox_flags) {
                foreach ($f in @($inv.sandbox_flags)) {
                    if ([string]$f -like '-*') { $expected += [string]$f }
                }
            }
        }
    }

    $missing = @()
    foreach ($flag in ($expected | Select-Object -Unique)) {
        # Fronteira a esquerda evita casar "-p" dentro de "--prompt-file".
        if ($helpText -notmatch ('(?<![\w-])' + [regex]::Escape($flag) + '(?![\w-])')) {
            $missing += $flag
        }
    }

    $status = 'ok'
    $detail = 'flags do profile conferidas contra --help'
    if ($missing.Count -gt 0) {
        $status = 'profile_mismatch'
        $detail = ('flags ausentes no CLI instalado: {0}' -f ($missing -join ', '))
        Write-Host ("[AVISO] {0}: {1}" -f $agent.name, $detail)
    }
    elseif ($expected.Count -eq 0) {
        # Sem flag a conferir. Prompt posicional e legitimo (`opencode run "..."`),
        # entao o alarme cabe a quem NAO se declara conferido contra o CLI real —
        # que era exatamente o estado do kimi quando ele invocava errado.
        if ($profileVerified -eq $true) {
            $status = 'ok_unchecked'
            $detail = 'prompt posicional; profile declara verified=true'
        }
        else {
            $status = 'unverified'
            $detail = 'profile nao conferido contra o CLI e sem flag para checar'
            Write-Host ("[AVISO] {0}: {1}" -f $agent.name, $detail)
        }
    }
    elseif ($profileVerified -ne $true) {
        Write-Host ("[AVISO] {0}: flags conferem, mas o profile nao esta marcado verified=true" -f $agent.name)
    }

    $results += [pscustomobject]@{
        name             = $agent.name
        status           = $status
        detail           = $detail
        exit_code        = $probeResult.exit_code
        version          = [string]$agent.version
        expected_flags   = @($expected | Select-Object -Unique)
        missing_flags    = @($missing)
        profile_verified = $profileVerified
    }
}

Write-JsonFile -Path $resultsPath -Object @{
    probed_at = $now
    skipped   = $false
    read_only = $true
    agents    = @($results)
}

$mismatch = @($results | Where-Object { $_.status -in @('profile_mismatch', 'unverified', 'timeout') })
Write-Host ("[OK] Probe-Agents concluido: {0} registros ({1} com profile suspeito)." -f `
        $results.Count, $mismatch.Count)
foreach ($m in $mismatch) {
    Write-Host ("[ACAO] profile de {0}: {1}" -f $m.name, $m.detail)
}
exit 0
