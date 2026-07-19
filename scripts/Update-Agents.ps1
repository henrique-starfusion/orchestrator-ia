#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [switch]$Force,
    [switch]$DryRun,
    [switch]$UpdateAgents
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'

. (Join-Path $PSScriptRoot 'Orchestrator.Common.ps1')

if (-not $UpdateAgents) {
    Write-Host '[INFO] Update-Agents ignorado (use -UpdateAgents para atualizar).'
    exit 0
}

$projectRoot = Get-ProjectRoot -ProjectPath $ProjectPath
$orchestratorRoot = Get-OrchestratorRoot -ProjectPath $projectRoot
$detectedPath = Join-Path $orchestratorRoot 'agents\detected.json'

if (-not (Test-Path -LiteralPath $detectedPath)) {
    Write-Host '[AVISO] detected.json ausente; execute Detect-Agents primeiro.'
    exit 0
}

$detected = Get-JsonFileContent -Path $detectedPath
$npmMap = Get-AgentNpmPackageMap
$npmCmd = Get-Command npm -ErrorAction SilentlyContinue

foreach ($agent in $detected.agents) {
    if ($agent.status -ne 'available') {
        continue
    }

    $name = $agent.name

    if ($name -eq 'codex') {
        $cmd = Get-Command codex -ErrorAction SilentlyContinue
        if ($cmd) {
            Write-Host "[INFO] Tentando 'codex update'..."
            if ($DryRun) {
                Write-Host '[DRY-RUN] codex update'
            }
            else {
                $result = Invoke-ExternalCommand -FilePath $cmd.Source -ArgumentList 'update' -TimeoutSeconds 120 -WorkingDirectory $projectRoot
                if ($result.exit_code -ne 0) {
                    Write-Host "[AVISO] codex update falhou: $($result.stderr)"
                }
            }
        }
    }

    if ($name -eq 'claude') {
        $cmd = Get-Command claude -ErrorAction SilentlyContinue
        if ($cmd) {
            Write-Host "[INFO] Tentando 'claude update'..."
            if ($DryRun) {
                Write-Host '[DRY-RUN] claude update'
            }
            else {
                $result = Invoke-ExternalCommand -FilePath $cmd.Source -ArgumentList 'update' -TimeoutSeconds 120 -WorkingDirectory $projectRoot
                if ($result.exit_code -ne 0) {
                    Write-Host "[AVISO] claude update falhou: $($result.stderr)"
                }
            }
        }
    }

    if ($Force -and $npmCmd -and $npmMap.ContainsKey($name) -and $agent.installation_method -eq 'npm') {
        $packageName = $npmMap[$name]
        Write-Host "[INFO] npm install -g $packageName"
        if ($DryRun) {
            Write-Host "[DRY-RUN] npm install -g $packageName"
        }
        else {
            $result = Invoke-ExternalCommand -FilePath $npmCmd.Source -ArgumentList "install -g $packageName" -TimeoutSeconds 300 -WorkingDirectory $projectRoot
            if ($result.exit_code -ne 0) {
                Write-Host "[AVISO] npm install falhou para ${name}: $($result.stderr)"
            }
        }
    }
}

Write-Host '[OK] Update-Agents concluido (falhas reportadas como avisos).'
exit 0
