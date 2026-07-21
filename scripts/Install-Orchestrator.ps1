#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('init', 'install', 'verify', 'update', 'upgrade', 'repair', 'uninstall', 'status', 'analyze', 'skills', 'global-tools', 'route', 'dispatch', 'legacy')]
    [string]$Command = 'install',

    [Alias('Project')]
    [string]$ProjectPath,

    [string]$PackageRoot,

    [string]$TaskClass,
    [string]$Prompt,
    [ValidateSet('claude', 'codex', 'cursor', 'gemini', 'opencode', 'kimi', 'auto')]
    [string]$Client = 'auto',

    [switch]$DryRun,
    [switch]$NonInteractive,
    [switch]$UpdateAgents,
    [switch]$InstallMissingAgents,
    [switch]$SkipAgentProbes,
    [switch]$SkipTools,
    [switch]$RefreshTools,
    [switch]$InitTools,
    [switch]$SkipToolInit,
    [switch]$SkipGlobalTools,
    [switch]$InstallGlobalTools,
    [switch]$ConfigureMcps,
    [switch]$ConfigureCursor,
    [switch]$ConfigureCursorMcp,
    [ValidateSet('stdio', 'http')]
    [string]$CursorTransport = 'stdio',
    [string]$CursorMcpUrl = 'http://127.0.0.1:8765/mcp',
    [switch]$SkipCursor,
    [switch]$RunSmokeTest,
    [switch]$RunProjectTests,
    [switch]$LegacyCleanup,
    [switch]$SkipLegacyCleanup,
    [ValidateSet('safe', 'aggressive', 'report-only')]
    [string]$LegacyCleanupMode = 'safe',
    [switch]$KeepLegacyBackup,
    [string]$LegacyBackupId,
    [ValidateSet('scan', 'cleanup', 'status', 'restore')]
    [string]$LegacyAction = 'scan',
    [switch]$Force,
    [switch]$Json,
    [switch]$PrintOnly
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
        'global-tools' {
            Write-Host '[INFO] Modo: global-tools'
            $gtArgs = @{
                ProjectPath = $projectRoot
                PackageRoot = $packageRootResolved
            }
            if ($Force) { $gtArgs.Force = $true }
            if ($DryRun) { $gtArgs.DryRun = $true }
            if ($SkipGlobalTools) { $gtArgs.SkipGlobalTools = $true }
            $code = Invoke-ChildScript -Name 'Install-GlobalTools.ps1' -Arguments $gtArgs
            exit $code
        }

        'route' {
            Write-Host '[INFO] Modo: route'
            if ([string]::IsNullOrWhiteSpace($TaskClass)) {
                Write-Host '[ERRO] route requer -TaskClass (ex.: docs, implementation, complex_analysis)'
                exit 2
            }
            $routeScript = Join-Path $PSScriptRoot 'Resolve-ModelRoute.ps1'
            $routeParams = @{
                ProjectPath = $projectRoot
                TaskClass   = $TaskClass
                Client      = $Client
            }
            if ($Json) { $routeParams.Json = $true }
            & $routeScript @routeParams
            exit $LASTEXITCODE
        }

        'dispatch' {
            Write-Host '[INFO] Modo: dispatch'
            if ([string]::IsNullOrWhiteSpace($TaskClass)) {
                Write-Host '[ERRO] dispatch requer -TaskClass'
                exit 2
            }
            if ([string]::IsNullOrWhiteSpace($Prompt)) {
                Write-Host '[ERRO] dispatch requer -Prompt'
                exit 2
            }
            $dispatchScript = Join-Path $PSScriptRoot 'Invoke-RoutedAgent.ps1'
            $dispatchParams = @{
                ProjectPath = $projectRoot
                TaskClass   = $TaskClass
                Prompt      = $Prompt
                Client      = $Client
            }
            if ($DryRun) { $dispatchParams.DryRun = $true }
            if ($PrintOnly) { $dispatchParams.PrintOnly = $true }
            & $dispatchScript @dispatchParams
            exit $LASTEXITCODE
        }

        'legacy' {
            Write-Host ('[INFO] Modo: legacy ({0})' -f $LegacyAction)
            switch ($LegacyAction) {
                'scan' {
                    $invPath = Join-Path (Get-OrchestratorRoot -ProjectPath $projectRoot) 'runtime\reports\legacy-inventory.json'
                    Ensure-Directory -Path (Split-Path -Parent $invPath) | Out-Null
                    $scanArgs = @{ ProjectPath = $projectRoot; OutputPath = $invPath }
                    if ($Json) { $scanArgs.Json = $true }
                    & (Join-Path $PSScriptRoot 'Detect-LegacyConfigurations.ps1') @scanArgs
                    exit $LASTEXITCODE
                }
                'status' {
                    $state = $null
                    $statePath = Join-Path (Get-OrchestratorRoot -ProjectPath $projectRoot) 'runtime\legacy-cleanup-state.json'
                    if (Test-Path -LiteralPath $statePath) {
                        Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | Write-Output
                    }
                    else {
                        Write-Host '[INFO] Nenhum legacy-cleanup-state.json ainda.'
                    }
                    $reportPath = Join-Path (Get-OrchestratorRoot -ProjectPath $projectRoot) 'runtime\reports\legacy-cleanup-report.md'
                    if (Test-Path -LiteralPath $reportPath) {
                        Write-Host ('[INFO] Relatorio: {0}' -f $reportPath)
                    }
                    exit 0
                }
                'restore' {
                    if ([string]::IsNullOrWhiteSpace($LegacyBackupId)) {
                        Write-Host '[ERRO] legacy restore requer -LegacyBackupId (ou --backup).'
                        exit 2
                    }
                    $restoreArgs = @{
                        ProjectPath = $projectRoot
                        BackupId    = $LegacyBackupId
                    }
                    if ($Force) { $restoreArgs.Force = $true }
                    if ($DryRun) { $restoreArgs.DryRun = $true }
                    & (Join-Path $PSScriptRoot 'Restore-LegacyBackup.ps1') @restoreArgs
                    exit $LASTEXITCODE
                }
                'cleanup' {
                    $pipeArgs = @{
                        ProjectPath        = $projectRoot
                        PackageRoot        = $packageRootResolved
                        Mode               = $LegacyCleanupMode
                        InstallValidated   = $true
                        AdaptersValidated  = $true
                    }
                    if ($SkipLegacyCleanup) { $pipeArgs.SkipLegacyCleanup = $true }
                    if ($KeepLegacyBackup) { $pipeArgs.KeepLegacyBackup = $true }
                    if ($Force) { $pipeArgs.Force = $true }
                    if ($DryRun) { $pipeArgs.DryRun = $true }
                    & (Join-Path $PSScriptRoot 'Invoke-LegacyCleanupPipeline.ps1') @pipeArgs
                    exit $LASTEXITCODE
                }
            }
        }

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

            # Legacy: detectar/backup/migrar antes do refresh final de adapters
            $legacyPipeEarly = @{
                ProjectPath = $projectRoot
                PackageRoot = $packageRootResolved
                Mode        = $LegacyCleanupMode
                SkipRemove  = $true
            }
            if ($SkipLegacyCleanup) { $legacyPipeEarly.SkipLegacyCleanup = $true }
            if ($KeepLegacyBackup) { $legacyPipeEarly.KeepLegacyBackup = $true }
            if ($Force) { $legacyPipeEarly.Force = $true }
            if ($DryRun) { $legacyPipeEarly.DryRun = $true }
            & (Join-Path $PSScriptRoot 'Invoke-LegacyCleanupPipeline.ps1') @legacyPipeEarly
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

            # Refresh de deteccao/adaptadores apos sync estrutural
            Invoke-ChildScript -Name 'Detect-Agents.ps1' -Arguments @{ ProjectPath = $projectRoot } | Out-Null

            $adapterArgs = @{ ProjectPath = $projectRoot; PackageRoot = $packageRootResolved }
            if ($Force) { $adapterArgs.Force = $true }
            Invoke-ChildScript -Name 'Generate-Adapters.ps1' -Arguments $adapterArgs | Out-Null

            if (-not $SkipTools) {
                $toolsArgs = @{ ProjectPath = $projectRoot }
                if ($RefreshTools) { $toolsArgs.RefreshTools = $true }
                # Nucleo primeiro: init de OpenWolf/Graphify so com -InitTools (opt-in)
                $doInitTools = $false
                if ($InitTools) { $doInitTools = $true }
                if ($SkipToolInit) { $doInitTools = $false }
                if ($doInitTools) { $toolsArgs.InitTools = $true }
                if ($DryRun) { $toolsArgs.DryRun = $true }
                Invoke-ChildScript -Name 'Install-Tools.ps1' -Arguments $toolsArgs | Out-Null
            }

            # Global tools opt-in: -InstallGlobalTools (ou comando global-tools)
            $doGlobalTools = $false
            if ($InstallGlobalTools) { $doGlobalTools = $true }
            if ($SkipGlobalTools) { $doGlobalTools = $false }
            if ($doGlobalTools) {
                $gtArgs = @{
                    ProjectPath = $projectRoot
                    PackageRoot = $packageRootResolved
                }
                if ($Force) { $gtArgs.Force = $true }
                if ($DryRun) { $gtArgs.DryRun = $true }
                Invoke-ChildScript -Name 'Install-GlobalTools.ps1' -Arguments $gtArgs | Out-Null

                $mcpArgs = @{
                    ProjectPath   = $projectRoot
                    ConfigureMcps = $true
                }
                if ($Force) { $mcpArgs.Force = $true }
                Invoke-ChildScript -Name 'Configure-Mcps.ps1' -Arguments $mcpArgs | Out-Null
            }
            elseif ($ConfigureMcps) {
                $mcpArgs = @{
                    ProjectPath   = $projectRoot
                    ConfigureMcps = $true
                }
                if ($Force) { $mcpArgs.Force = $true }
                Invoke-ChildScript -Name 'Configure-Mcps.ps1' -Arguments $mcpArgs | Out-Null
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

            # Legacy: remocao segura apos install/adapters validos
            if (-not $SkipLegacyCleanup -and $LegacyCleanupMode -ne 'report-only') {
                Write-Host '[ETAPA] Legacy cleanup (pos-validacao / remocao)'
                $invPath = Join-Path (Get-OrchestratorRoot -ProjectPath $projectRoot) 'runtime\reports\legacy-inventory.json'
                $removeArgs = @{
                    ProjectPath        = $projectRoot
                    InventoryPath      = $invPath
                    Mode               = $LegacyCleanupMode
                    BackupValidated    = $true
                    MigrationCompleted = $true
                    InstallValidated   = $true
                    AdaptersValidated  = $true
                }
                if ($Force) { $removeArgs.Force = $true }
                if ($DryRun) { $removeArgs.DryRun = $true }
                & (Join-Path $PSScriptRoot 'Remove-LegacyConfigurations.ps1') @removeArgs
                if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
                & (Join-Path $PSScriptRoot 'Validate-LegacyCleanup.ps1') -ProjectPath $projectRoot -InventoryPath $invPath -Mode $LegacyCleanupMode
                if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
            }

            $reportData = @{
                agents      = @()
                adapters    = @()
                tools       = @()
                limitations = @()
                legacy      = @{}
            }
            $detectedPath = Join-Path (Get-OrchestratorRoot -ProjectPath $projectRoot) 'agents\detected.json'
            if (Test-Path -LiteralPath $detectedPath) {
                $detectedObj = Get-JsonFileContent -Path $detectedPath
                if ($detectedObj.PSObject.Properties['agents']) {
                    $reportData.agents = @($detectedObj.agents)
                }
            }
            $legacyReportJson = Join-Path (Get-OrchestratorRoot -ProjectPath $projectRoot) 'runtime\reports\legacy-cleanup-report.json'
            if (Test-Path -LiteralPath $legacyReportJson) {
                $reportData.legacy = Get-JsonFileContent -Path $legacyReportJson
            }

            if (-not $SkipCursor -and ($ConfigureCursor -or $ConfigureCursorMcp)) {
                $cursorArgs = @{
                    ProjectPath     = $projectRoot
                    PackageRoot     = $packageRootResolved
                    CursorTransport = $CursorTransport
                    CursorMcpUrl    = $CursorMcpUrl
                }
                if ($Force) { $cursorArgs.Force = $true }
                Invoke-ChildScript -Name 'Configure-CursorMcp.ps1' -Arguments $cursorArgs | Out-Null
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

    $orchestratorVersion = Join-Path (Get-OrchestratorRoot -ProjectPath $projectRoot) 'VERSION'

    # Garante raiz .orchestrator para backups/relatorios de legado antes do template
    if (-not $DryRun) {
        Ensure-Directory -Path (Get-OrchestratorRoot -ProjectPath $projectRoot) | Out-Null
        Ensure-Directory -Path (Join-Path (Get-OrchestratorRoot -ProjectPath $projectRoot) 'runtime\reports') | Out-Null
    }

    # Pipeline legado (detect/backup/migrate); remocao ocorre apos validacao
    Write-Host '[ETAPA] Legacy cleanup (pre-install)'
    $legacyPipeEarly = @{
        ProjectPath = $projectRoot
        PackageRoot = $packageRootResolved
        Mode        = $LegacyCleanupMode
        SkipRemove  = $true
    }
    if ($SkipLegacyCleanup) { $legacyPipeEarly.SkipLegacyCleanup = $true }
    if ($KeepLegacyBackup) { $legacyPipeEarly.KeepLegacyBackup = $true }
    if ($Force) { $legacyPipeEarly.Force = $true }
    if ($DryRun) { $legacyPipeEarly.DryRun = $true }
    & (Join-Path $PSScriptRoot 'Invoke-LegacyCleanupPipeline.ps1') @legacyPipeEarly
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    # Compat: wrapper Claude se .claude/VERSION e ainda sem VERSION canônica
    $legacyVersion = Join-Path $projectRoot '.claude\VERSION'
    if ((Test-Path -LiteralPath $legacyVersion) -and -not (Test-Path -LiteralPath $orchestratorVersion)) {
        Write-Host '[ETAPA] Migracao legada .claude (wrapper)'
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
        # Nucleo primeiro: init de OpenWolf/Graphify so com -InitTools (opt-in)
        $doInitTools = $false
        if ($InitTools) { $doInitTools = $true }
        if ($SkipToolInit) { $doInitTools = $false }
        if ($doInitTools) { $toolsArgs.InitTools = $true }
        if ($DryRun) { $toolsArgs.DryRun = $true }
        Invoke-ChildScript -Name 'Install-Tools.ps1' -Arguments $toolsArgs | Out-Null
    }

    $doGlobalTools = $false
    if ($InstallGlobalTools) { $doGlobalTools = $true }
    if ($SkipGlobalTools) { $doGlobalTools = $false }
    if ($doGlobalTools) {
        $gtArgs = @{
            ProjectPath = $projectRoot
            PackageRoot = $packageRootResolved
        }
        if ($Force) { $gtArgs.Force = $true }
        if ($DryRun) { $gtArgs.DryRun = $true }
        Invoke-ChildScript -Name 'Install-GlobalTools.ps1' -Arguments $gtArgs | Out-Null
    }

    # Espelho MCP no workspace somente com -ConfigureMcps ou junto de global-tools
    $mcpArgs = @{
        ProjectPath   = $projectRoot
        ConfigureMcps = $true
    }
    if ($Force) { $mcpArgs.Force = $true }
    if ($ConfigureMcps -or $doGlobalTools) {
        Invoke-ChildScript -Name 'Configure-Mcps.ps1' -Arguments $mcpArgs | Out-Null
    }

    $code = Invoke-ChildScript -Name 'Validate-Orchestrator.ps1' -Arguments @{
        ProjectPath = $projectRoot
        PackageRoot = $packageRootResolved
    }
    if ($code -ne 0) { exit $code }

    $code = Invoke-ChildScript -Name 'Validate-Hooks.ps1' -Arguments @{ ProjectPath = $projectRoot }
    if ($code -ne 0) { exit $code }

    # Remocao segura de legado apos install + adapters validos
    if (-not $SkipLegacyCleanup -and $LegacyCleanupMode -ne 'report-only') {
        Write-Host '[ETAPA] Legacy cleanup (pos-validacao / remocao)'
        $invPath = Join-Path (Get-OrchestratorRoot -ProjectPath $projectRoot) 'runtime\reports\legacy-inventory.json'
        $removeArgs = @{
            ProjectPath         = $projectRoot
            InventoryPath       = $invPath
            Mode                = $LegacyCleanupMode
            BackupValidated     = $true
            MigrationCompleted  = $true
            InstallValidated    = $true
            AdaptersValidated   = $true
        }
        if ($Force) { $removeArgs.Force = $true }
        if ($DryRun) { $removeArgs.DryRun = $true }
        & (Join-Path $PSScriptRoot 'Remove-LegacyConfigurations.ps1') @removeArgs
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & (Join-Path $PSScriptRoot 'Validate-LegacyCleanup.ps1') -ProjectPath $projectRoot -InventoryPath $invPath -Mode $LegacyCleanupMode
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

        # Atualiza relatorio final com remocoes efetivas
        $removedPath = Join-Path (Get-OrchestratorRoot -ProjectPath $projectRoot) 'runtime\reports\legacy-removed.json'
        $reportJson = Join-Path (Get-OrchestratorRoot -ProjectPath $projectRoot) 'runtime\reports\legacy-cleanup-report.json'
        if ((Test-Path -LiteralPath $removedPath) -and (Test-Path -LiteralPath $reportJson)) {
            $rep = Get-JsonFileContent -Path $reportJson
            $rem = Get-JsonFileContent -Path $removedPath
            $repHash = @{
                mode           = $LegacyCleanupMode
                skipped        = $false
                detected       = $(if ($rep.PSObject.Properties['detected']) { $rep.detected } else { 0 })
                migrated       = $(if ($rep.PSObject.Properties['migrated']) { @($rep.migrated) } else { @() })
                removed        = $(if ($rem.PSObject.Properties['removed']) { @($rem.removed) } else { @() })
                preserved      = $(if ($rep.PSObject.Properties['preserved']) { @($rep.preserved) } else { @() })
                unknown        = $(if ($rep.PSObject.Properties['unknown']) { @($rep.unknown) } else { @() })
                backup         = $(if ($rep.PSObject.Properties['backup']) { $rep.backup } else { $null })
                validation_ok  = $true
                manual_actions = @()
            }
            Set-Content -LiteralPath $reportJson -Value ($repHash | ConvertTo-Json -Depth 6) -Encoding UTF8
            $md = @(
                '# Legacy cleanup report',
                '',
                ("**Generated:** {0}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')),
                ("**Mode:** {0}" -f $LegacyCleanupMode),
                ("**Detected:** {0}" -f $repHash.detected),
                ("**Migrated:** {0}" -f ($repHash.migrated -join ', ')),
                ("**Removed:** {0}" -f ($repHash.removed -join ', ')),
                ("**Preserved:** {0}" -f ($repHash.preserved -join ', ')),
                ("**Backup:** {0}" -f $repHash.backup),
                '**Validation:** True'
            )
            Set-Content -LiteralPath (Join-Path (Get-OrchestratorRoot -ProjectPath $projectRoot) 'runtime\reports\legacy-cleanup-report.md') -Value ($md -join [Environment]::NewLine) -Encoding UTF8
        }
    }

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
        legacy      = @{}
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
        # Flag legada: cleanup agora e default; manter compat sem limitation
        Write-Host '[INFO] -LegacyCleanup e default desde 0.4.0 (use -SkipLegacyCleanup para pular).'
    }

    if ($SkipLegacyCleanup) {
        $reportData.limitations += 'Legacy cleanup pulado (-SkipLegacyCleanup).'
    }

    $legacyReportJson = Join-Path (Get-OrchestratorRoot -ProjectPath $projectRoot) 'runtime\reports\legacy-cleanup-report.json'
    if (Test-Path -LiteralPath $legacyReportJson) {
        $reportData.legacy = Get-JsonFileContent -Path $legacyReportJson
    }

    if (-not $SkipCursor -and ($ConfigureCursor -or $ConfigureCursorMcp)) {
        $cursorArgs = @{
            ProjectPath     = $projectRoot
            PackageRoot     = $packageRootResolved
            CursorTransport = $CursorTransport
            CursorMcpUrl    = $CursorMcpUrl
        }
        if ($Force) { $cursorArgs.Force = $true }
        Invoke-ChildScript -Name 'Configure-CursorMcp.ps1' -Arguments $cursorArgs | Out-Null
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
