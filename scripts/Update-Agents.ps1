#Requires -Version 5.1
<#
.SYNOPSIS
    Atualiza CLIs de agentes ja detectados (available) no PATH.

.DESCRIPTION
    Chamado por padrao em install/update do orquestrador.
    Nao instala agentes ausentes. Falhas viram avisos (exit 0).
    Estrategia: subcomando nativo (update/upgrade) → fallback por
    installation_method (npm / chocolatey / scoop).
#>
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [switch]$Force,
    [switch]$DryRun,
    # Compat: pai sempre passa -UpdateAgents:$true; sozinho sem flag ainda atualiza (0.4.17+)
    [switch]$UpdateAgents
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'

. (Join-Path $PSScriptRoot 'Orchestrator.Common.ps1')

$projectRoot = Get-ProjectRoot -ProjectPath $ProjectPath
$orchestratorRoot = Get-OrchestratorRoot -ProjectPath $projectRoot
$detectedPath = Join-Path $orchestratorRoot 'agents\detected.json'
$reportPath = Join-Path $orchestratorRoot 'runtime\reports\agent-updates.json'

if (-not (Test-Path -LiteralPath $detectedPath)) {
    Write-Host '[AVISO] detected.json ausente; execute Detect-Agents primeiro.'
    exit 0
}

$detected = Get-JsonFileContent -Path $detectedPath
$npmMap = Get-AgentNpmPackageMap
$chocoMap = Get-AgentChocolateyPackageMap
$scoopMap = Get-AgentScoopPackageMap
$npmCmd = Get-Command npm -ErrorAction SilentlyContinue
$chocoCmd = Get-Command choco -ErrorAction SilentlyContinue
$scoopCmd = Get-Command scoop -ErrorAction SilentlyContinue

# name → argumentos do subcomando nativo de update
$nativeUpdate = @{
    'claude'    = @('update')
    'codex'     = @('update')
    'kimi'      = @('update')
    'kimi-code' = @('update')
    'gemini'    = @('update')
}

$results = @()

function Invoke-AgentUpdateAttempt {
    param(
        [string]$Label,
        [string]$FilePath,
        [string[]]$ArgumentList,
        [int]$TimeoutSeconds = 300
    )
    Write-Host ("[INFO] {0}: {1} {2}" -f $Label, $FilePath, ($ArgumentList -join ' '))
    if ($DryRun) {
        Write-Host ("[DRY-RUN] {0} {1}" -f $FilePath, ($ArgumentList -join ' '))
        return @{ ok = $true; exit_code = 0; method = $Label; dry_run = $true; stderr = '' }
    }
    $result = Invoke-ExternalCommand -FilePath $FilePath -ArgumentList $ArgumentList `
        -TimeoutSeconds $TimeoutSeconds -WorkingDirectory $projectRoot
    $ok = ($result.exit_code -eq 0)
    if (-not $ok) {
        Write-Host ("[AVISO] {0} falhou (exit {1}): {2}" -f $Label, $result.exit_code, $result.stderr)
    }
    return @{
        ok        = $ok
        exit_code = $result.exit_code
        method    = $Label
        dry_run   = $false
        stderr    = [string]$result.stderr
    }
}

foreach ($agent in @($detected.agents)) {
    if ($agent.status -ne 'available') { continue }
    $name = [string]$agent.name
    if ([string]::IsNullOrWhiteSpace($name)) { continue }
    if (Test-IsIdeAgent -Name $name) {
        $results += [pscustomobject]@{
            agent  = $name
            status = 'skipped_ide'
            method = $null
            exit_code = $null
            notes  = 'IDE client — CLI update nao aplicavel'
        }
        continue
    }

    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if (-not $cmd) {
        $results += [pscustomobject]@{
            agent = $name; status = 'skipped_missing'; method = $null; exit_code = $null
            notes = 'Get-Command nao encontrou executavel'
        }
        continue
    }

    $methodUsed = $null
    $exitCode = $null
    $notes = @()
    $updated = $false

    # 1) Subcomando nativo
    if ($nativeUpdate.ContainsKey($name)) {
        $argsNative = $nativeUpdate[$name]
        $attempt = Invoke-AgentUpdateAttempt -Label ("native:{0}" -f $name) `
            -FilePath $cmd.Source -ArgumentList $argsNative -TimeoutSeconds 180
        $methodUsed = $attempt.method
        $exitCode = $attempt.exit_code
        if ($attempt.ok) {
            $updated = $true
            $notes += 'native update ok'
        }
        else {
            $notes += ("native update failed exit={0}" -f $attempt.exit_code)
        }
    }

    $installMethod = [string]$agent.installation_method

    # 2) Fallback npm (sempre se nativo falhou/ausente e method=npm, ou -Force)
    if (-not $updated -and $npmCmd -and $npmMap.ContainsKey($name)) {
        $useNpm = ($installMethod -eq 'npm') -or $Force.IsPresent
        if ($useNpm) {
            $packageName = $npmMap[$name]
            $attempt = Invoke-AgentUpdateAttempt -Label ("npm:{0}" -f $packageName) `
                -FilePath $npmCmd.Source -ArgumentList @('install', '-g', $packageName) -TimeoutSeconds 300
            $methodUsed = $attempt.method
            $exitCode = $attempt.exit_code
            if ($attempt.ok) {
                $updated = $true
                $notes += 'npm install -g ok'
            }
            else {
                $notes += ("npm failed exit={0}" -f $attempt.exit_code)
            }
        }
    }

    # 3) Fallback Chocolatey
    if (-not $updated -and $chocoCmd -and $chocoMap.ContainsKey($name)) {
        $useChoco = ($installMethod -eq 'chocolatey') -or $Force.IsPresent
        if ($useChoco) {
            $pkg = $chocoMap[$name]
            $attempt = Invoke-AgentUpdateAttempt -Label ("choco:{0}" -f $pkg) `
                -FilePath $chocoCmd.Source -ArgumentList @('upgrade', $pkg, '-y') -TimeoutSeconds 600
            $methodUsed = $attempt.method
            $exitCode = $attempt.exit_code
            if ($attempt.ok) {
                $updated = $true
                $notes += 'choco upgrade ok'
            }
            else {
                $notes += ("choco failed exit={0}" -f $attempt.exit_code)
            }
        }
    }

    # 4) Fallback Scoop
    if (-not $updated -and $scoopCmd -and $scoopMap.ContainsKey($name)) {
        $useScoop = ($installMethod -eq 'scoop') -or $Force.IsPresent
        if ($useScoop) {
            $app = $scoopMap[$name]
            $attempt = Invoke-AgentUpdateAttempt -Label ("scoop:{0}" -f $app) `
                -FilePath $scoopCmd.Source -ArgumentList @('update', $app) -TimeoutSeconds 600
            $methodUsed = $attempt.method
            $exitCode = $attempt.exit_code
            if ($attempt.ok) {
                $updated = $true
                $notes += 'scoop update ok'
            }
            else {
                $notes += ("scoop failed exit={0}" -f $attempt.exit_code)
            }
        }
    }

    if (-not $updated -and -not $methodUsed) {
        $notes += 'nenhuma estrategia de update aplicavel (sem nativo/npm/choco/scoop)'
    }

    $results += [pscustomobject]@{
        agent     = $name
        status    = $(if ($updated) { 'updated' } elseif ($methodUsed) { 'failed' } else { 'skipped' })
        method    = $methodUsed
        exit_code = $exitCode
        installation_method = $installMethod
        notes     = ($notes -join '; ')
    }
}

$report = [pscustomobject]@{
    generated_at = (Get-Date).ToString('o')
    dry_run      = [bool]$DryRun
    agents       = $results
}
Ensure-Directory -Path (Split-Path -Parent $reportPath) | Out-Null
if (-not $DryRun) {
    Set-Content -LiteralPath $reportPath -Value ($report | ConvertTo-Json -Depth 6) -Encoding UTF8
}
else {
    Write-Host ("[DRY-RUN] report → {0}" -f $reportPath)
}

$updatedCount = @($results | Where-Object { $_.status -eq 'updated' }).Count
$failedCount = @($results | Where-Object { $_.status -eq 'failed' }).Count
Write-Host ("[OK] Update-Agents concluido (updated={0} failed={1} total={2}; falhas = avisos)." -f `
        $updatedCount, $failedCount, $results.Count)
exit 0
