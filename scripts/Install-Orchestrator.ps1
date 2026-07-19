#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('init', 'install', 'verify', 'update', 'upgrade', 'repair', 'uninstall', 'status', 'analyze', 'skills')]
    [string]$Command = 'install',

    [Alias('Project')]
    [string]$ProjectPath,

    [string]$PackageRoot,

    [switch]$DryRun,
    [switch]$NonInteractive,
    [switch]$UpdateAgents,
    [switch]$InstallMissingAgents,
    [switch]$SkipAgentProbes,
    [switch]$SkipTools,
    [switch]$RefreshTools,
    [switch]$InitTools,
    [switch]$SkipToolInit,
    [switch]$ConfigureMcps,
    [switch]$RunSmokeTest,
    [switch]$RunProjectTests,
    [switch]$LegacyCleanup,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Orchestrator.Common.ps1')

function Invoke-ChildScript {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [hashtable]$Arguments = @{}
    )

    $scriptPath = Join-Path $PSScriptRoot $Name
    if (-not (Test-Path -LiteralPath $scriptPath)) {
        throw ("Script not found: {0}" -f $scriptPath)
    }

    $params = @{}
    foreach ($key in $Arguments.Keys) {
        $value = $Arguments[$key]
        if ($value -is [switch]) {
            if ($value.IsPresent) {
                $params[$key] = $true
            }
        }
        elseif ($value -is [bool]) {
            if ($value) {
                $params[$key] = $true
            }
        }
        elseif ($null -ne $value -and -not [string]::IsNullOrWhiteSpace([string]$value)) {
            $params[$key] = $value
        }
    }

    if ($VerbosePreference -eq 'Continue') {
        & $scriptPath @params -Verbose
    }
    else {
        & $scriptPath @params
    }

    return $LASTEXITCODE
}

$projectRoot = Get-ProjectRoot -ProjectPath $ProjectPath
$packageRootResolved = Get-PackageRoot -PackageRoot $PackageRoot
$packageVersion = Read-PackageVersion -PackageRoot $packageRootResolved
$workspaceVersion = Read-WorkspaceVersion -ProjectPath $projectRoot
$logFile = $null
$lockCreated = $false

if ($Command -eq 'init') {
    $Command = 'install'
}

# upgrade permanece como alias legado de update
if ($Command -eq 'upgrade') {
    $Command = 'update'
}

try {
    switch ($Command) {
        'verify' {
            Write-Host '[INFO] Modo: verify'
            $code = Invoke-ChildScript -Name 'Detect-Environment.ps1' -Arguments @{
                ProjectPath = $projectRoot
                PackageRoot = $packageRootResolved
                DryRun      = $DryRun
            }
            if ($code -ne 0) { exit $code }

            $code = Invoke-ChildScript -Name 'Validate-Orchestrator.ps1' -Arguments @{
                ProjectPath = $projectRoot
                PackageRoot = $packageRootResolved
            }
            if ($code -ne 0) { exit $code }

            $code = Invoke-ChildScript -Name 'Validate-Hooks.ps1' -Arguments @{
                ProjectPath = $projectRoot
            }
            exit $code
        }

        'update' {
            Write-Host '[INFO] Modo: update'
            $preflightArgs = @{
                ProjectPath = $projectRoot
                PackageRoot = $packageRootResolved
            }
            if ($DryRun) { $preflightArgs.DryRun = $true }
            $code = Invoke-ChildScript -Name 'Detect-Environment.ps1' -Arguments $preflightArgs
            if ($code -ne 0) { exit $code }

            # Atualiza o pacote (git pull) quando PackageRoot for um clone
            if ($DryRun) {
                Sync-PackageSource -PackageRoot $packageRootResolved -DryRun | Out-Null
            }
            else {
                Sync-PackageSource -PackageRoot $packageRootResolved | Out-Null
            }
            $packageVersion = Read-PackageVersion -PackageRoot $packageRootResolved

            if (-not $DryRun) {
                New-InstallationLock -ProjectPath $projectRoot | Out-Null
                $lockCreated = $true
            }

            $updateParams = @{
                ProjectPath = $projectRoot
                PackageRoot = $packageRootResolved
            }
            if ($Force) { $updateParams.Force = $true }
            if ($DryRun) { $updateParams.DryRun = $true }
            & (Join-Path $PSScriptRoot 'Update-Orchestrator.ps1') @updateParams
            $updateExit = $LASTEXITCODE
            if ($updateExit -ne 0) { exit $updateExit }

            # Refresh de deteccao/adaptadores apos sync estrutural
            Invoke-ChildScript -Name 'Detect-Agents.ps1' -Arguments @{ ProjectPath = $projectRoot } | Out-Null

            $adapterArgs = @{ ProjectPath = $projectRoot; PackageRoot = $packageRootResolved }
            if ($Force) { $adapterArgs.Force = $true }
            Invoke-ChildScript -Name 'Generate-Adapters.ps1' -Arguments $adapterArgs | Out-Null

            if (-not $SkipTools) {
                $toolsArgs = @{ ProjectPath = $projectRoot }
                if ($RefreshTools) { $toolsArgs.RefreshTools = $true }
                # update: inicializa tools por padrao (exceto -SkipToolInit)
                $doInitTools = $true
                if ($SkipToolInit) { $doInitTools = $false }
                if ($PSBoundParameters.ContainsKey('InitTools')) { $doInitTools = $InitTools.IsPresent }
                if ($doInitTools) { $toolsArgs.InitTools = $true }
                if ($DryRun) { $toolsArgs.DryRun = $true }
                Invoke-ChildScript -Name 'Install-Tools.ps1' -Arguments $toolsArgs | Out-Null
            }

            if ($UpdateAgents) {
                $ua = @{ ProjectPath = $projectRoot; UpdateAgents = $true }
                if ($Force) { $ua.Force = $true }
                if ($DryRun) { $ua.DryRun = $true }
                Invoke-ChildScript -Name 'Update-Agents.ps1' -Arguments $ua | Out-Null
            }

            $code = Invoke-ChildScript -Name 'Validate-Orchestrator.ps1' -Arguments @{
                ProjectPath = $projectRoot
                PackageRoot = $packageRootResolved
            }
            if ($code -ne 0) { exit $code }

            $reportData = @{
                agents      = @()
                adapters    = @()
                tools       = @()
                limitations = @()
            }
            $detectedPath = Join-Path (Get-OrchestratorRoot -ProjectPath $projectRoot) 'agents\detected.json'
            if (Test-Path -LiteralPath $detectedPath) {
                $detectedObj = Get-JsonFileContent -Path $detectedPath
                if ($detectedObj.PSObject.Properties['agents']) {
                    $reportData.agents = @($detectedObj.agents)
                }
            }

            Invoke-ChildScript -Name 'Write-InstallationReport.ps1' -Arguments @{
                ProjectPath = $projectRoot
                Mode        = 'update'
                ReportData  = $reportData
            } | Out-Null

            Write-Host '[OK] Update concluido.'
            Write-Host ("[OK] Workspace: {0} | Pacote: {1}" -f (Read-WorkspaceVersion -ProjectPath $projectRoot), $packageVersion)
            exit 0
        }

        'repair' {
            Write-Host '[INFO] Modo: repair'
            $repairParams = @{ ProjectPath = $projectRoot; PackageRoot = $packageRootResolved }
            if ($Force) { $repairParams.Force = $true }
            if ($DryRun) { $repairParams.DryRun = $true }
            & (Join-Path $PSScriptRoot 'Repair-Orchestrator.ps1') @repairParams
            exit $LASTEXITCODE
        }

        'uninstall' {
            Write-Host '[INFO] Modo: uninstall'
            $uninstallParams = @{ ProjectPath = $projectRoot; PackageRoot = $packageRootResolved }
            if ($Force) { $uninstallParams.Force = $true }
            if ($DryRun) { $uninstallParams.DryRun = $true }
            & (Join-Path $PSScriptRoot 'Uninstall-Orchestrator.ps1') @uninstallParams
            exit $LASTEXITCODE
        }

        'status' {
            Write-Host '=== Orchestrator Status ==='
            Write-Host "Project:           $projectRoot"
            Write-Host "Package version:   $packageVersion"
            Write-Host "Workspace version: $workspaceVersion"

            $detectedPath = Join-Path (Get-OrchestratorRoot -ProjectPath $projectRoot) 'agents\detected.json'
            if (Test-Path -LiteralPath $detectedPath) {
                $detected = Get-JsonFileContent -Path $detectedPath
                $available = @($detected.agents | Where-Object { $_.status -eq 'available' })
                Write-Host ("Agents available:  {0}" -f $available.Count)
                foreach ($agent in $available) {
                    Write-Host ("  - {0} ({1})" -f $agent.name, $agent.installation_method)
                }
            }
            else {
                Write-Host 'Agents available:  (not detected yet)'
            }

            $toolsPath = Join-Path (Get-OrchestratorRoot -ProjectPath $projectRoot) 'tools\registry.json'
            if (Test-Path -LiteralPath $toolsPath) {
                $tools = Get-JsonFileContent -Path $toolsPath
                Write-Host ("Tools registered:  {0}" -f @($tools.tools).Count)
            }

            exit 0
        }

        'analyze' {
            Write-Host '[INFO] Modo analyze: executando detect + validate.'
            $code = Invoke-ChildScript -Name 'Detect-Environment.ps1' -Arguments @{
                ProjectPath = $projectRoot
                PackageRoot = $packageRootResolved
            }
            if ($code -ne 0) { exit $code }

            Invoke-ChildScript -Name 'Detect-Agents.ps1' -Arguments @{ ProjectPath = $projectRoot } | Out-Null
            Invoke-ChildScript -Name 'Validate-Orchestrator.ps1' -Arguments @{
                ProjectPath = $projectRoot
                PackageRoot = $packageRootResolved
            } | Out-Null
            exit 0
        }

        'skills' {
            Write-Host '[INFO] Modo skills: listando skills registradas.'
            $skillsRegistry = Join-Path (Get-OrchestratorRoot -ProjectPath $projectRoot) 'skills\registry.json'
            if (-not (Test-Path -LiteralPath $skillsRegistry)) {
                Write-Host '[AVISO] skills/registry.json ausente.'
                exit 1
            }
            $skills = Get-JsonFileContent -Path $skillsRegistry
            if ($skills.skills) {
                foreach ($skill in $skills.skills) {
                    Write-Host (" - {0}" -f $skill.id)
                }
            }
            exit 0
        }

        'install' {
            Write-Host '[INFO] Modo: install'
            break
        }

        default {
            Write-Host "[ERRO] Comando invalido: $Command"
            exit 2
        }
    }

    if ($Command -ne 'install') {
        exit 0
    }

    $comparison = Compare-SemVer -Left $workspaceVersion -Right $packageVersion
    if ($comparison -eq 'newer') {
        Write-Host '[ERRO] Workspace mais novo que o pacote.'
        exit 6
    }

    $preflightArgs = @{
        ProjectPath = $projectRoot
        PackageRoot = $packageRootResolved
    }
    if ($DryRun) { $preflightArgs.DryRun = $true }
    $code = Invoke-ChildScript -Name 'Detect-Environment.ps1' -Arguments $preflightArgs
    if ($code -ne 0) { exit $code }

    if (-not $DryRun) {
        New-InstallationLock -ProjectPath $projectRoot | Out-Null
        $lockCreated = $true
    }

    $legacyVersion = Join-Path $projectRoot '.claude\VERSION'
    $orchestratorVersion = Join-Path (Get-OrchestratorRoot -ProjectPath $projectRoot) 'VERSION'
    if ((Test-Path -LiteralPath $legacyVersion) -and -not (Test-Path -LiteralPath $orchestratorVersion)) {
        Write-Host '[ETAPA] Migracao legada .claude -> .orchestrator'
        $migrationArgs = @{ ProjectPath = $projectRoot }
        if ($Force) { $migrationArgs.Force = $true }
        if ($DryRun) { $migrationArgs.DryRun = $true }
        $code = Invoke-ChildScript -Name 'Migrate-LegacyClaude.ps1' -Arguments $migrationArgs
        if ($code -ne 0) { exit $code }
    }

    Write-Host '[ETAPA] Copiar template .orchestrator'
    if (-not $DryRun) {
        $treeParams = @{ ProjectPath = $projectRoot; PackageRoot = $packageRootResolved }
        if ($Force) { $treeParams.Force = $true }
        Copy-TemplateTree @treeParams | Out-Null
    }
    else {
        Write-Host '[DRY-RUN] Copy-TemplateTree'
    }

    Write-Host '[ETAPA] Aplicar manifest'
    $applyParams = @{ ProjectPath = $projectRoot; PackageRoot = $packageRootResolved }
    if ($Force) { $applyParams.Force = $true }
    if ($DryRun) { $applyParams.DryRun = $true }
    Apply-Manifest @applyParams | Out-Null

    if (-not (Test-Path -LiteralPath $orchestratorVersion) -and -not $DryRun) {
        Sync-WorkspaceVersion -ProjectPath $projectRoot -Version $packageVersion | Out-Null
    }

    Invoke-ChildScript -Name 'Detect-Agents.ps1' -Arguments @{ ProjectPath = $projectRoot } | Out-Null

    $adapterArgs = @{
        ProjectPath = $projectRoot
        PackageRoot = $packageRootResolved
    }
    if ($Force) { $adapterArgs.Force = $true }
    Invoke-ChildScript -Name 'Generate-Adapters.ps1' -Arguments $adapterArgs | Out-Null

    if (-not $SkipTools) {
        $toolsArgs = @{ ProjectPath = $projectRoot }
        if ($RefreshTools) { $toolsArgs.RefreshTools = $true }
        # install/init: inicializa OpenWolf/Graphify por padrao
        $doInitTools = $true
        if ($SkipToolInit) { $doInitTools = $false }
        if ($PSBoundParameters.ContainsKey('InitTools')) { $doInitTools = $InitTools.IsPresent }
        if ($doInitTools) { $toolsArgs.InitTools = $true }
        if ($DryRun) { $toolsArgs.DryRun = $true }
        Invoke-ChildScript -Name 'Install-Tools.ps1' -Arguments $toolsArgs | Out-Null
    }

    if ($ConfigureMcps) {
        $mcpArgs = @{
            ProjectPath   = $projectRoot
            ConfigureMcps = $true
        }
        if ($Force) { $mcpArgs.Force = $true }
        Invoke-ChildScript -Name 'Configure-Mcps.ps1' -Arguments $mcpArgs | Out-Null
    }

    $code = Invoke-ChildScript -Name 'Validate-Orchestrator.ps1' -Arguments @{
        ProjectPath = $projectRoot
        PackageRoot = $packageRootResolved
    }
    if ($code -ne 0) { exit $code }

    $code = Invoke-ChildScript -Name 'Validate-Hooks.ps1' -Arguments @{ ProjectPath = $projectRoot }
    if ($code -ne 0) { exit $code }

    if ($UpdateAgents) {
        $updateArgs = @{
            ProjectPath  = $projectRoot
            UpdateAgents = $true
        }
        if ($Force) { $updateArgs.Force = $true }
        if ($DryRun) { $updateArgs.DryRun = $true }
        Invoke-ChildScript -Name 'Update-Agents.ps1' -Arguments $updateArgs | Out-Null
    }

    $shouldSkipProbes = $true
    if ($RunSmokeTest) {
        $shouldSkipProbes = $false
    }
    elseif ($PSBoundParameters.ContainsKey('SkipAgentProbes')) {
        $shouldSkipProbes = $SkipAgentProbes.IsPresent
    }

    if (-not $shouldSkipProbes) {
        Invoke-ChildScript -Name 'Probe-Agents.ps1' -Arguments @{
            ProjectPath    = $projectRoot
            TimeoutSeconds = 30
        } | Out-Null
    }
    else {
        Invoke-ChildScript -Name 'Probe-Agents.ps1' -Arguments @{
            ProjectPath     = $projectRoot
            SkipAgentProbes = $true
        } | Out-Null
    }

    $reportData = @{
        agents      = @()
        adapters    = @()
        tools       = @()
        limitations = @()
    }

    $detectedPath = Join-Path (Get-OrchestratorRoot -ProjectPath $projectRoot) 'agents\detected.json'
    if (Test-Path -LiteralPath $detectedPath) {
        $reportData.agents = @(Get-JsonFileContent -Path $detectedPath).agents
    }

    if ($InstallMissingAgents) {
        $reportData.limitations += 'InstallMissingAgents solicitado, mas instalacao automatica de agentes ainda nao implementada.'
    }

    if ($RunProjectTests) {
        $reportData.limitations += 'RunProjectTests solicitado, mas runner generico nao esta incluido neste pacote.'
    }

    if ($LegacyCleanup) {
        $reportData.limitations += 'LegacyCleanup solicitado, mas limpeza legada opt-in ainda nao implementada neste instalador.'
    }

    Invoke-ChildScript -Name 'Write-InstallationReport.ps1' -Arguments @{
        ProjectPath = $projectRoot
        Mode        = 'install'
        ReportData  = $reportData
    } | Out-Null

    Write-Host '[OK] Install-Orchestrator concluido.'
    exit 0
}
catch {
    Write-Host "[ERRO] $($_.Exception.Message)"
    exit 1
}
finally {
    if ($lockCreated) {
        try {
            Remove-InstallationLock -ProjectPath $projectRoot
        }
        catch {
            Write-Host "[AVISO] Falha ao remover lock: $($_.Exception.Message)"
        }
    }
}
