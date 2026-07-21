#Requires -Version 5.1
<#
.SYNOPSIS
  Funcoes compartilhadas para deteccao/classificacao/limpeza de legado.
#>

# Dot-source Orchestrator.Common.ps1 before this file.

function Test-LegacyPathInsideProject {
    param(
        [Parameter(Mandatory = $true)][string]$ProjectRoot,
        [Parameter(Mandatory = $true)][string]$CandidatePath
    )
    try {
        $rootFull = [System.IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\', '/')
        $candFull = [System.IO.Path]::GetFullPath($CandidatePath)
    }
    catch {
        return $false
    }
    if ($candFull -eq $rootFull) { return $true }
    $prefix = $rootFull + [System.IO.Path]::DirectorySeparatorChar
    return $candFull.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)
}

function Get-LegacyKnownCatalog {
    # Paths relativos (forward slash) com classificacao padrao safe-mode
    return @(
        @{ Path = '.ai'; Type = 'directory'; Classification = 'delete'; SafeToRemove = $true; Reason = 'fonte canonica antiga substituida por .orchestrator' }
        @{ Path = '.ai-bootstrap'; Type = 'directory'; Classification = 'delete'; SafeToRemove = $true; Reason = 'bootstrap antigo' }
        @{ Path = '.ai-backups'; Type = 'directory'; Classification = 'delete'; SafeToRemove = $true; Reason = 'backups do bootstrap antigo' }
        @{ Path = 'orchestrator'; Type = 'directory'; Classification = 'delete'; SafeToRemove = $true; Reason = 'pasta orchestrator/ nao canonica (use .orchestrator/)' }
        @{ Path = 'graphify-out'; Type = 'directory'; Classification = 'delete'; SafeToRemove = $true; Reason = 'saida gerada do graphify' }
        @{ Path = '.codegraph'; Type = 'directory'; Classification = 'delete'; SafeToRemove = $true; Reason = 'codegraph legado' }
        @{ Path = 'AI.md'; Type = 'file'; Classification = 'replace'; SafeToRemove = $true; Reason = 'adaptador legado; substituido por CLAUDE.md/AGENTS.md' }
        @{ Path = '.cursorrules'; Type = 'file'; Classification = 'delete'; SafeToRemove = $true; Reason = 'substituido por .cursor/rules/*.mdc' }
        @{ Path = 'mcp.json'; Type = 'file'; Classification = 'unknown'; SafeToRemove = $false; Reason = 'pode ser config de usuario na raiz' }
        @{ Path = '.mcp.json'; Type = 'file'; Classification = 'unknown'; SafeToRemove = $false; Reason = 'pode ser config de usuario' }
        @{ Path = '.mcp'; Type = 'directory'; Classification = 'unknown'; SafeToRemove = $false; Reason = 'estrutura MCP nao padrao; revisar' }
        @{ Path = '.claude'; Type = 'directory'; Classification = 'adapter-current'; SafeToRemove = $false; Reason = 'adaptador vendor; preservar salvo filhos legado' }
        @{ Path = '.codex'; Type = 'directory'; Classification = 'adapter-current'; SafeToRemove = $false; Reason = 'adaptador vendor' }
        @{ Path = '.cursor'; Type = 'directory'; Classification = 'adapter-current'; SafeToRemove = $false; Reason = 'adaptador IDE; limpar so filhos legado conhecidos' }
        @{ Path = '.gemini'; Type = 'directory'; Classification = 'adapter-current'; SafeToRemove = $false; Reason = 'adaptador vendor' }
        @{ Path = '.kimi'; Type = 'directory'; Classification = 'adapter-current'; SafeToRemove = $false; Reason = 'adaptador vendor' }
        @{ Path = '.opencode'; Type = 'directory'; Classification = 'adapter-current'; SafeToRemove = $false; Reason = 'adaptador vendor' }
        @{ Path = '.openai'; Type = 'directory'; Classification = 'unknown'; SafeToRemove = $false; Reason = 'pode conter config exclusiva' }
        @{ Path = '.agents'; Type = 'directory'; Classification = 'migrate'; SafeToRemove = $false; Reason = 'skills podem migrar para legacy-import' }
        @{ Path = '.agent'; Type = 'directory'; Classification = 'unknown'; SafeToRemove = $false; Reason = 'estrutura generica; revisar' }
        @{ Path = '.aider'; Type = 'directory'; Classification = 'user-owned'; SafeToRemove = $false; Reason = 'ferramenta externa' }
        @{ Path = '.continue'; Type = 'directory'; Classification = 'user-owned'; SafeToRemove = $false; Reason = 'ferramenta externa' }
        @{ Path = '.cline'; Type = 'directory'; Classification = 'user-owned'; SafeToRemove = $false; Reason = 'ferramenta externa' }
        @{ Path = '.roo'; Type = 'directory'; Classification = 'user-owned'; SafeToRemove = $false; Reason = 'ferramenta externa' }
        @{ Path = '.roocode'; Type = 'directory'; Classification = 'user-owned'; SafeToRemove = $false; Reason = 'ferramenta externa' }
        @{ Path = '.windsurf'; Type = 'directory'; Classification = 'user-owned'; SafeToRemove = $false; Reason = 'ferramenta externa' }
        @{ Path = '.wolf'; Type = 'directory'; Classification = 'runtime'; SafeToRemove = $false; Reason = 'runtime OpenWolf opt-in' }
        @{ Path = '.graphify'; Type = 'directory'; Classification = 'runtime'; SafeToRemove = $false; Reason = 'runtime Graphify opt-in' }
        @{ Path = 'CLAUDE.md'; Type = 'file'; Classification = 'adapter-current'; SafeToRemove = $false; Reason = 'adaptador atual' }
        @{ Path = 'AGENTS.md'; Type = 'file'; Classification = 'adapter-current'; SafeToRemove = $false; Reason = 'adaptador atual' }
        @{ Path = 'CODEX.md'; Type = 'file'; Classification = 'adapter-current'; SafeToRemove = $false; Reason = 'adaptador atual' }
        @{ Path = 'GEMINI.md'; Type = 'file'; Classification = 'adapter-current'; SafeToRemove = $false; Reason = 'adaptador atual' }
        @{ Path = 'KIMI.md'; Type = 'file'; Classification = 'adapter-current'; SafeToRemove = $false; Reason = 'adaptador atual' }
        @{ Path = 'CURSOR.md'; Type = 'file'; Classification = 'adapter-current'; SafeToRemove = $false; Reason = 'adaptador atual' }
        @{ Path = 'OPENAI.md'; Type = 'file'; Classification = 'unknown'; SafeToRemove = $false; Reason = 'pode ser user-owned' }
        @{ Path = 'copilot-instructions.md'; Type = 'file'; Classification = 'user-owned'; SafeToRemove = $false; Reason = 'instrucoes Copilot do usuario' }
    )
}

function Get-LegacyChildHotspots {
    # Filhos conhecidos dentro de adaptadores — so estes podem ser migrate/delete em safe
    return @(
        @{ Path = '.claude/memory'; Type = 'directory'; Classification = 'migrate'; SafeToRemove = $false; Reason = 'memoria legada'; MigrationTarget = '.orchestrator/memory/legacy-import/claude' }
        @{ Path = '.claude/rules'; Type = 'directory'; Classification = 'migrate'; SafeToRemove = $false; Reason = 'rules legadas'; MigrationTarget = '.orchestrator/rules/legacy-import/claude' }
        @{ Path = '.claude/VERSION'; Type = 'file'; Classification = 'delete'; SafeToRemove = $true; Reason = 'VERSION legado; canonico e .orchestrator/VERSION' }
        @{ Path = '.claude/skills'; Type = 'directory'; Classification = 'adapter-legacy'; SafeToRemove = $false; Reason = 'skills vendor; stubs atuais podem coexistir' }
        @{ Path = '.cursor/rules/openwolf.mdc'; Type = 'file'; Classification = 'delete'; SafeToRemove = $true; Reason = 'rule gerada localmente pelo OpenWolf' }
        @{ Path = '.agents/skills'; Type = 'directory'; Classification = 'migrate'; SafeToRemove = $false; Reason = 'skills antigas'; MigrationTarget = '.orchestrator/skills/legacy-import' }
        @{ Path = '.codex/config.toml'; Type = 'file'; Classification = 'keep'; SafeToRemove = $false; Reason = 'config exclusiva Codex' }
    )
}

function New-LegacyInventoryItem {
    param(
        [string]$Path,
        [string]$Type,
        [string]$Classification,
        [string]$Reason,
        [bool]$SafeToRemove,
        [string]$MigrationTarget = $null,
        [bool]$Exists = $true,
        [object[]]$Evidence = @()
    )
    return [pscustomobject]@{
        path                 = ($Path -replace '\\', '/')
        type                 = $Type
        classification       = $Classification
        reason               = $Reason
        source_version       = $null
        contains_user_content = ($Classification -in @('user-owned', 'unknown', 'keep'))
        migration_target     = $MigrationTarget
        safe_to_remove       = [bool]$SafeToRemove
        exists               = [bool]$Exists
        evidence             = @($Evidence)
    }
}

function Get-LegacyInventory {
    param(
        [Parameter(Mandatory = $true)][string]$ProjectPath
    )

    $projectRoot = Get-ProjectRoot -ProjectPath $ProjectPath
    $items = New-Object System.Collections.Generic.List[object]
    $seen = @{}

    foreach ($entry in (@(Get-LegacyKnownCatalog) + @(Get-LegacyChildHotspots))) {
        $rel = ($entry.Path -replace '/', '\')
        $full = Join-Path $projectRoot $rel
        if (-not (Test-Path -LiteralPath $full)) { continue }
        if (-not (Test-LegacyPathInsideProject -ProjectRoot $projectRoot -CandidatePath $full)) { continue }
        $key = ($entry.Path -replace '\\', '/').ToLowerInvariant()
        if ($seen.ContainsKey($key)) { continue }
        $seen[$key] = $true

        $mig = $null
        if ($entry.ContainsKey('MigrationTarget')) { $mig = $entry.MigrationTarget }

        $items.Add((New-LegacyInventoryItem `
            -Path $entry.Path `
            -Type $entry.Type `
            -Classification $entry.Classification `
            -Reason $entry.Reason `
            -SafeToRemove ([bool]$entry.SafeToRemove) `
            -MigrationTarget $mig `
            -Exists $true `
            -Evidence @('catalog-match'))) | Out-Null
    }

    return $items.ToArray()
}

function Get-LegacyRemovableItems {
    param(
        [Parameter(Mandatory = $true)]$Inventory,
        [ValidateSet('safe', 'aggressive', 'report-only')]
        [string]$Mode = 'safe'
    )
    if ($Mode -eq 'report-only') { return @() }

    $out = @()
    foreach ($item in @($Inventory)) {
        if (-not $item.exists) { continue }
        if ($item.classification -in @('unknown', 'user-owned', 'runtime', 'adapter-current', 'keep')) { continue }
        if ($Mode -eq 'safe') {
            if ($item.safe_to_remove -and $item.classification -in @('delete', 'replace')) {
                $out += $item
            }
        }
        elseif ($Mode -eq 'aggressive') {
            if ($item.classification -in @('delete', 'replace', 'adapter-legacy') -and $item.safe_to_remove) {
                $out += $item
            }
        }
    }
    return $out
}

function Get-LegacyMigratableItems {
    param([Parameter(Mandatory = $true)]$Inventory)
    $out = @()
    foreach ($item in @($Inventory)) {
        if (-not $item.exists) { continue }
        if ($item.classification -eq 'migrate' -and -not [string]::IsNullOrWhiteSpace([string]$item.migration_target)) {
            $out += $item
        }
    }
    return $out
}

function Write-LegacyCleanupState {
    param(
        [Parameter(Mandatory = $true)][string]$ProjectPath,
        [Parameter(Mandatory = $true)][hashtable]$State
    )
    $root = Get-OrchestratorRoot -ProjectPath $ProjectPath
    $dir = Join-Path $root 'runtime'
    Ensure-Directory -Path $dir | Out-Null
    $path = Join-Path $dir 'legacy-cleanup-state.json'
    Write-JsonFile -Path $path -Object $State
    return $path
}

function Read-LegacyCleanupState {
    param([Parameter(Mandatory = $true)][string]$ProjectPath)
    $path = Join-Path (Get-OrchestratorRoot -ProjectPath $ProjectPath) 'runtime\legacy-cleanup-state.json'
    if (-not (Test-Path -LiteralPath $path)) { return $null }
    return Get-JsonFileContent -Path $path
}
