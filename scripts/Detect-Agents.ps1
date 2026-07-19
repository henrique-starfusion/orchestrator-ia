#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [int]$TimeoutSeconds = 5
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Orchestrator.Common.ps1')

$projectRoot = Get-ProjectRoot -ProjectPath $ProjectPath
$orchestratorRoot = Get-OrchestratorRoot -ProjectPath $projectRoot
Ensure-Directory -Path (Join-Path $orchestratorRoot 'agents') | Out-Null

$agentNames = @(
    'claude', 'codex', 'gemini', 'kimi', 'kimi-code', 'opencode',
    'qwen', 'qwen-code', 'copilot', 'github-copilot', 'aider', 'goose',
    'amp', 'kiro', 'cursor', 'continue', 'openhands', 'openclaw', 'droid', 'factory'
)

$detected = @()
$now = (Get-Date).ToString('o')

foreach ($name in $agentNames) {
    $record = [ordered]@{
        name                = $name
        status              = 'not_installed'
        command             = $null
        command_path        = $null
        version             = $null
        installation_method = 'unknown'
        detected_at         = $now
        version_error       = $null
    }

    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) {
        $record.status = 'available'
        $record.command = $cmd.Name
        $record.command_path = $cmd.Source
        $record.installation_method = Guess-InstallationMethod -CommandPath $cmd.Source

        try {
            $result = Invoke-ExternalCommand -FilePath $cmd.Source -ArgumentList '--version' -TimeoutSeconds $TimeoutSeconds -WorkingDirectory $projectRoot
            if ($result.timed_out) {
                $record.status = 'installed_failed'
                $record.version_error = 'timeout'
            }
            elseif ($result.exit_code -eq 0) {
                $versionText = ($result.stdout + $result.stderr).Trim()
                if (-not [string]::IsNullOrWhiteSpace($versionText)) {
                    $record.version = ($versionText -split "`r?`n")[0].Trim()
                }
            }
            else {
                $record.status = 'installed_failed'
                $record.version_error = ($result.stderr + $result.stdout).Trim()
            }
        }
        catch {
            $record.status = 'installed_failed'
            $record.version_error = $_.Exception.Message
        }
    }

    $detected += [pscustomobject]$record
}

$detectedPath = Join-Path $orchestratorRoot 'agents\detected.json'
Write-JsonFile -Path $detectedPath -Object @{
    version     = '0.1.0'
    detected_at = $now
    agents      = @($detected)
}

$registryPath = Join-Path $orchestratorRoot 'agents\registry.json'
$registry = Get-JsonFileContent -Path $registryPath
if ($null -eq $registry) {
    $registry = [pscustomobject]@{
        version = '0.1.0'
        agents  = @()
    }
}

$existingAgents = @{}
if ($registry.agents) {
    foreach ($item in $registry.agents) {
        if ($item.name) {
            $existingAgents[$item.name] = $item
        }
    }
}

foreach ($item in $detected) {
    $existingAgents[$item.name] = [pscustomobject]@{
        name                = $item.name
        status              = $item.status
        command             = $item.command
        command_path        = $item.command_path
        version             = $item.version
        installation_method = $item.installation_method
        updated_at          = $now
    }
}

Write-JsonFile -Path $registryPath -Object @{
    version    = '0.1.0'
    updated_at = $now
    agents     = @($existingAgents.Values)
}

$availableCount = @($detected | Where-Object { $_.status -eq 'available' }).Count
Write-Host "[OK] Agentes detectados: $availableCount disponiveis de $($detected.Count) verificados."
exit 0
