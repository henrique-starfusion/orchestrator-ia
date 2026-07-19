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

    $cmd = Get-Command $agent.name -ErrorAction SilentlyContinue
    if (-not $cmd) {
        $results += [pscustomobject]@{
            name   = $agent.name
            status = 'skipped_safe'
            detail = 'command_not_found'
        }
        continue
    }

    $probeResult = Invoke-ExternalCommand -FilePath $cmd.Source -ArgumentList '--help' -TimeoutSeconds $TimeoutSeconds -WorkingDirectory $projectRoot
    if ($probeResult.timed_out) {
        $results += [pscustomobject]@{
            name   = $agent.name
            status = 'timeout'
            detail = 'help_command_timeout'
        }
    }
    else {
        $results += [pscustomobject]@{
            name      = $agent.name
            status    = 'skipped_safe'
            detail    = 'read_only_probe'
            exit_code = $probeResult.exit_code
        }
    }
}

Write-JsonFile -Path $resultsPath -Object @{
    probed_at = $now
    skipped   = $false
    read_only = $true
    agents    = @($results)
}

Write-Host "[OK] Probe-Agents concluido: $($results.Count) registros."
exit 0
