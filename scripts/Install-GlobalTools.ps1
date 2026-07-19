#Requires -Version 5.1
<#
.SYNOPSIS
    Instala MCPs, plugins, skills e CLIs no perfil do usuario (global).

.DESCRIPTION
    Nao grava credenciais. Falhas por item sao avisos — nunca abortam o bootstrap.
    Alvo: ~/.claude, ~/.cursor/mcp.json, ~/.agents (via skills -g), npm -g.
#>
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [string]$PackageRoot,
    [switch]$SkipGlobalTools,
    [switch]$Force,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'

. (Join-Path $PSScriptRoot 'Orchestrator.Common.ps1')

if ($SkipGlobalTools) {
    Write-Host '[INFO] Install-GlobalTools ignorado (-SkipGlobalTools).'
    exit 0
}

$packageRootResolved = Get-PackageRoot -PackageRoot $PackageRoot
$projectRoot = Get-ProjectRoot -ProjectPath $ProjectPath
$catalogPath = Join-Path $packageRootResolved 'package\global-tools\catalog.json'

if (-not (Test-Path -LiteralPath $catalogPath)) {
    Write-Host "[AVISO] Catalogo global ausente: $catalogPath"
    exit 0
}

$catalog = Get-JsonFileContent -Path $catalogPath
if ($null -eq $catalog) {
    Write-Host '[AVISO] Catalogo global invalido.'
    exit 0
}

$report = [ordered]@{
    version    = '0.1.0'
    updated_at = (Get-Date).ToString('o')
    npm        = @()
    mcp        = @()
    plugins    = @()
    skills     = @()
    notes      = @()
}

function Add-ReportItem {
    param([string]$Bucket, [hashtable]$Item)
    $script:report[$Bucket] = @($script:report[$Bucket]) + @([pscustomobject]$Item)
}

function Test-CommandAvailable {
    param([string]$Name)
    return $null -ne (Resolve-CommandExecutable -Name $Name)
}

function Install-NpmGlobalIfMissing {
    param(
        [string]$Id,
        [string]$PackageName,
        [string]$CheckCommand
    )

    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $npm) {
        Add-ReportItem -Bucket 'npm' -Item @{ id = $Id; status = 'skipped'; reason = 'npm ausente' }
        Write-Host "[AVISO] npm ausente; nao foi possivel instalar $PackageName"
        return
    }

    if ((Test-CommandAvailable -Name $CheckCommand) -and -not $Force) {
        Write-Host "[OK] CLI global ja presente: $CheckCommand"
        Add-ReportItem -Bucket 'npm' -Item @{ id = $Id; status = 'present'; package = $PackageName }
        return
    }

    Write-Host "[ETAPA] npm install -g $PackageName"
    if ($DryRun) {
        Write-Host "[DRY-RUN] npm install -g $PackageName"
        Add-ReportItem -Bucket 'npm' -Item @{ id = $Id; status = 'dry-run'; package = $PackageName }
        return
    }

    $result = Invoke-ExternalCommand -FilePath $npm.Source -ArgumentList @('install', '-g', $PackageName) -TimeoutSeconds 300
    if ($result.exit_code -eq 0) {
        Write-Host "[OK] Instalado: $PackageName"
        Add-ReportItem -Bucket 'npm' -Item @{ id = $Id; status = 'installed'; package = $PackageName }
    }
    else {
        Write-Host "[AVISO] Falha npm -g $PackageName (exit $($result.exit_code))"
        Add-ReportItem -Bucket 'npm' -Item @{ id = $Id; status = 'failed'; package = $PackageName; exit_code = $result.exit_code }
    }
}

function Get-CursorMcpPath {
    return (Join-Path $env:USERPROFILE '.cursor\mcp.json')
}

function Ensure-CursorMcp {
    param($Server)

    $path = Get-CursorMcpPath
    Ensure-Directory -Path (Split-Path -Parent $path) | Out-Null

    $doc = $null
    if (Test-Path -LiteralPath $path) {
        $doc = Get-JsonFileContent -Path $path
    }
    if ($null -eq $doc) {
        $doc = [pscustomobject]@{ mcpServers = [pscustomobject]@{} }
    }
    if (-not $doc.PSObject.Properties['mcpServers'] -or $null -eq $doc.mcpServers) {
        $doc | Add-Member -NotePropertyName mcpServers -NotePropertyValue ([pscustomobject]@{}) -Force
    }

    $id = [string]$Server.id
    $existing = $doc.mcpServers.PSObject.Properties[$id]
    if ($existing -and -not $Force) {
        Write-Host "[OK] Cursor MCP ja configurado: $id"
        Add-ReportItem -Bucket 'mcp' -Item @{ id = $id; client = 'cursor'; status = 'present' }
        return
    }

    $entry = [ordered]@{
        command = 'cmd'
        args    = @('/c', 'npx') + @($Server.args)
        enabled = $true
    }

    Write-Host "[ETAPA] Cursor MCP: $id"
    if ($DryRun) {
        Write-Host "[DRY-RUN] upsert Cursor mcpServers.$id"
        Add-ReportItem -Bucket 'mcp' -Item @{ id = $id; client = 'cursor'; status = 'dry-run' }
        return
    }

    $serversHash = @{}
    foreach ($p in $doc.mcpServers.PSObject.Properties) {
        $serversHash[$p.Name] = $p.Value
    }
    $serversHash[$id] = [pscustomobject]$entry
    Write-JsonFile -Path $path -Object @{ mcpServers = $serversHash }
    Write-Host "[OK] Cursor MCP configurado: $id"
    Add-ReportItem -Bucket 'mcp' -Item @{ id = $id; client = 'cursor'; status = 'configured' }
}

function Ensure-ClaudeMcp {
    param($Server)

    $claude = Resolve-CommandExecutable -Name 'claude'
    if (-not $claude) {
        Add-ReportItem -Bucket 'mcp' -Item @{ id = [string]$Server.id; client = 'claude'; status = 'skipped'; reason = 'claude ausente' }
        return
    }

    $id = [string]$Server.id
    $list = Invoke-ExternalCommand -FilePath $claude.Source -ArgumentList @('mcp', 'list') -TimeoutSeconds 60
    $already = ($list.exit_code -eq 0) -and ($list.stdout -match ("(?im)^\s*{0}\b" -f [regex]::Escape($id)))
    if ($already -and -not $Force) {
        Write-Host "[OK] Claude MCP ja configurado: $id"
        Add-ReportItem -Bucket 'mcp' -Item @{ id = $id; client = 'claude'; status = 'present' }
        return
    }

    $args = @('mcp', 'add', '-s', 'user', $id, '--', 'npx') + @($Server.args)
    Write-Host "[ETAPA] Claude MCP user: $id"
    if ($DryRun) {
        Write-Host ("[DRY-RUN] claude {0}" -f ($args -join ' '))
        Add-ReportItem -Bucket 'mcp' -Item @{ id = $id; client = 'claude'; status = 'dry-run' }
        return
    }

    if ($already -and $Force) {
        $null = Invoke-ExternalCommand -FilePath $claude.Source -ArgumentList @('mcp', 'remove', $id) -TimeoutSeconds 60
    }

    $result = Invoke-ExternalCommand -FilePath $claude.Source -ArgumentList $args -TimeoutSeconds 120
    if ($result.exit_code -eq 0) {
        Write-Host "[OK] Claude MCP: $id"
        Add-ReportItem -Bucket 'mcp' -Item @{ id = $id; client = 'claude'; status = 'configured' }
    }
    else {
        # ja existe / conflito nao e fatal
        Write-Host ("[AVISO] Claude MCP {0}: exit {1}" -f $id, $result.exit_code)
        Add-ReportItem -Bucket 'mcp' -Item @{ id = $id; client = 'claude'; status = 'failed'; exit_code = $result.exit_code }
    }
}

function Ensure-ClaudePlugin {
    param([string]$PluginSpec)

    $claude = Resolve-CommandExecutable -Name 'claude'
    if (-not $claude) {
        Add-ReportItem -Bucket 'plugins' -Item @{ id = $PluginSpec; status = 'skipped'; reason = 'claude ausente' }
        return
    }

    $shortName = ($PluginSpec -split '@')[0]
    $list = Invoke-ExternalCommand -FilePath $claude.Source -ArgumentList @('plugin', 'list') -TimeoutSeconds 90
    $already = ($list.exit_code -eq 0) -and ($list.stdout -match ("(?im)>\s*{0}@" -f [regex]::Escape($shortName)))
    if ($already -and -not $Force) {
        Write-Host "[OK] Claude plugin ja instalado: $shortName"
        Add-ReportItem -Bucket 'plugins' -Item @{ id = $PluginSpec; status = 'present' }
        return
    }

    Write-Host "[ETAPA] claude plugin install $PluginSpec -s user"
    if ($DryRun) {
        Write-Host "[DRY-RUN] claude plugin install $PluginSpec -s user"
        Add-ReportItem -Bucket 'plugins' -Item @{ id = $PluginSpec; status = 'dry-run' }
        return
    }

    $result = Invoke-ExternalCommand -FilePath $claude.Source -ArgumentList @('plugin', 'install', $PluginSpec, '-s', 'user') -TimeoutSeconds 180
    if ($result.exit_code -eq 0) {
        Write-Host "[OK] Plugin: $PluginSpec"
        Add-ReportItem -Bucket 'plugins' -Item @{ id = $PluginSpec; status = 'installed' }
    }
    else {
        Write-Host ("[AVISO] Plugin {0}: exit {1}" -f $PluginSpec, $result.exit_code)
        Add-ReportItem -Bucket 'plugins' -Item @{ id = $PluginSpec; status = 'failed'; exit_code = $result.exit_code }
    }
}

function Ensure-SkillPackage {
    param(
        [string]$Id,
        [string]$Source
    )

    $npx = Get-Command npx -ErrorAction SilentlyContinue
    if (-not $npx) {
        Add-ReportItem -Bucket 'skills' -Item @{ id = $Id; status = 'skipped'; reason = 'npx ausente' }
        return
    }

    $homeSkills = Join-Path $env:USERPROFILE ".agents\skills"
    $markerCandidates = @(
        (Join-Path $homeSkills $Id),
        (Join-Path $homeSkills 'using-superpowers'),
        (Join-Path $homeSkills 'find-skills'),
        (Join-Path $homeSkills 'firecrawl')
    )
    $present = $false
    if ($Id -eq 'superpowers') { $present = Test-Path -LiteralPath (Join-Path $homeSkills 'using-superpowers') }
    elseif ($Id -eq 'find-skills') { $present = Test-Path -LiteralPath (Join-Path $homeSkills 'find-skills') }
    elseif ($Id -eq 'firecrawl') { $present = Test-Path -LiteralPath (Join-Path $homeSkills 'firecrawl') }
    else { $present = Test-Path -LiteralPath (Join-Path $homeSkills $Id) }

    if ($present -and -not $Force) {
        Write-Host "[OK] Skill global ja presente: $Id"
        Add-ReportItem -Bucket 'skills' -Item @{ id = $Id; status = 'present'; source = $Source }
        return
    }

    Write-Host "[ETAPA] skills add $Source -g (perfil do usuario)"
    if ($DryRun) {
        Write-Host "[DRY-RUN] npx skills add $Source -g"
        Add-ReportItem -Bucket 'skills' -Item @{ id = $Id; status = 'dry-run'; source = $Source }
        return
    }

    # Executa a partir do HOME para evitar instalar skills no projeto atual
    $home = $env:USERPROFILE
    $result = Invoke-ExternalCommand -FilePath $npx.Source -ArgumentList @('--yes', 'skills', 'add', $Source, '-g') -TimeoutSeconds 300 -WorkingDirectory $home
    if ($result.exit_code -eq 0) {
        Write-Host "[OK] Skills: $Source"
        Add-ReportItem -Bucket 'skills' -Item @{ id = $Id; status = 'installed'; source = $Source }
    }
    else {
        Write-Host ("[AVISO] skills add {0}: exit {1}" -f $Source, $result.exit_code)
        Add-ReportItem -Bucket 'skills' -Item @{ id = $Id; status = 'failed'; source = $Source; exit_code = $result.exit_code }
    }

    $null = $markerCandidates
}

Write-Host '[INFO] Install-GlobalTools: CLIs, MCPs, plugins e skills no perfil do usuario...'

# 1) npm globals
if ($catalog.npm_globals) {
    foreach ($pkg in @($catalog.npm_globals)) {
        Install-NpmGlobalIfMissing -Id ([string]$pkg.id) -PackageName ([string]$pkg.package) -CheckCommand ([string]$pkg.check_command)
    }
}

# 2) MCPs por cliente
if ($catalog.mcp_servers) {
    foreach ($server in @($catalog.mcp_servers)) {
        $clients = @($server.clients)
        if ($clients -contains 'cursor') { Ensure-CursorMcp -Server $server }
        if ($clients -contains 'claude') { Ensure-ClaudeMcp -Server $server }
        if ($clients -contains 'codex') {
            # Codex ja usa plugins oficiais; MCP stdio via config.toml e sensivel — apenas nota
            Add-ReportItem -Bucket 'mcp' -Item @{
                id     = [string]$server.id
                client = 'codex'
                status = 'manual'
                notes  = 'Preferir plugin oficial Codex (ex.: playwright@claude-plugins-official)'
            }
        }
    }
}

# 3) Claude plugins (user scope)
if ($catalog.claude_plugins) {
    foreach ($plugin in @($catalog.claude_plugins)) {
        Ensure-ClaudePlugin -PluginSpec ([string]$plugin)
    }
}

# 4) Skills globais (~/.agents)
if ($catalog.skill_packages) {
    foreach ($skill in @($catalog.skill_packages)) {
        Ensure-SkillPackage -Id ([string]$skill.id) -Source ([string]$skill.source)
    }
}

# Relatorio no workspace (sem segredos)
$toolsDir = Join-Path (Get-OrchestratorRoot -ProjectPath $projectRoot) 'tools'
Ensure-Directory -Path $toolsDir | Out-Null
$statusPath = Join-Path $toolsDir 'global-status.json'
if (-not $DryRun) {
    Write-JsonFile -Path $statusPath -Object $report
    Write-Host "[OK] Relatorio: $statusPath"
}
else {
    Write-Host '[DRY-RUN] Relatorio global-status.json nao gravado.'
}

Write-Host '[OK] Install-GlobalTools concluido (perfil do usuario).'
exit 0
