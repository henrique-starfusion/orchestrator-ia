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

# 0.4.31 — CLI instalado por instalador nativo (kimi no Windows, por ex.) nao
# sabe se auto-atualizar: ele mesmo diz isso e imprime o comando manual. Antes
# isso virava "[AVISO] native:kimi falhou" e, com -Force, caia no fallback npm —
# que instalaria uma SEGUNDA copia por cima da nativa.
function Get-ManualUpdateHint {
    param([string]$Output)
    if ([string]::IsNullOrWhiteSpace($Output)) { return $null }
    if ($Output -notmatch '(?im)auto[-\s]?update\s+is\s+not\s+supported') { return $null }
    $hint = 'consulte a documentacao do CLI'
    $m = [regex]::Match($Output, '(?im)^\s*To update manually,\s*run:\s*(.+?)\s*$')
    if ($m.Success) { $hint = $m.Groups[1].Value }
    return $hint
}

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
        return @{ ok = $true; exit_code = 0; method = $Label; dry_run = $true; stderr = ''; manual_hint = $null }
    }
    $result = Invoke-ExternalCommand -FilePath $FilePath -ArgumentList $ArgumentList `
        -TimeoutSeconds $TimeoutSeconds -WorkingDirectory $projectRoot
    $ok = ($result.exit_code -eq 0)
    # O CLI anuncia "auto-update is not supported" em stdout OU stderr, e pode
    # sair 0 ou != 0 — o que decide nao e o exit code, e o que ele disse.
    $manualHint = Get-ManualUpdateHint -Output (("{0}`n{1}" -f $result.stdout, $result.stderr))
    if ($manualHint) {
        Write-Host ("[INFO] {0}: auto-update nao suportado neste instalador. Atualize manualmente: {1}" -f `
                $Label, $manualHint)
    }
    elseif (-not $ok) {
        Write-Host ("[AVISO] {0} falhou (exit {1}): {2}" -f $Label, $result.exit_code, $result.stderr)
    }
    return @{
        ok          = $ok
        exit_code   = $result.exit_code
        method      = $Label
        dry_run     = $false
        stderr      = [string]$result.stderr
        manual_hint = $manualHint
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
    $manualHint = $null

    # 1) Subcomando nativo
    if ($nativeUpdate.ContainsKey($name)) {
        $argsNative = $nativeUpdate[$name]
        $attempt = Invoke-AgentUpdateAttempt -Label ("native:{0}" -f $name) `
            -FilePath $cmd.Source -ArgumentList $argsNative -TimeoutSeconds 180
        $methodUsed = $attempt.method
        $exitCode = $attempt.exit_code
        if ($attempt.manual_hint) {
            $manualHint = $attempt.manual_hint
            $notes += ('auto-update nao suportado; atualize manualmente: {0}' -f $manualHint)
        }
        elseif ($attempt.ok) {
            $updated = $true
            $notes += 'native update ok'
        }
        else {
            $notes += ("native update failed exit={0}" -f $attempt.exit_code)
        }
    }

    # Instalacao nativa nao se atualiza sozinha E nao deve ser coberta por npm/
    # choco/scoop: o gerenciador instalaria uma copia paralela, e o PATH passaria
    # a resolver uma versao diferente da que o usuario instalou.
    if ($manualHint) {
        $results += [pscustomobject]@{
            agent     = $name
            status    = 'manual_required'
            method    = $methodUsed
            exit_code = $exitCode
            installation_method = [string]$agent.installation_method
            manual_command = $manualHint
            notes     = ($notes -join '; ')
        }
        continue
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
        manual_command = $null
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
$manualList = @($results | Where-Object { $_.status -eq 'manual_required' })
Write-Host ("[OK] Update-Agents concluido (updated={0} failed={1} manual={2} total={3}; falhas = avisos)." -f `
        $updatedCount, $failedCount, $manualList.Count, $results.Count)
# Comando manual no fim: e a unica saida acionavel, e no meio do log some.
foreach ($item in $manualList) {
    Write-Host ("[ACAO] {0}: atualize manualmente -> {1}" -f $item.agent, $item.manual_command)
}
exit 0
