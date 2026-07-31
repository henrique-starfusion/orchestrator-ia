#Requires -Version 5.1
<#
.SYNOPSIS
    Propaga update do pacote @starfusion/orchestrator para projetos registrados.
    Chamado só quando o update corre no workspace do pacote (0.4.20).
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$PackageRoot,

    [string]$PackageVersion,

    [switch]$Discover,

    [switch]$DryRun,

    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Orchestrator.Common.ps1')

if ([string]::IsNullOrWhiteSpace($PackageVersion)) {
    $PackageVersion = Read-PackageVersion -PackageRoot $PackageRoot
}

$pkgResolved = (Resolve-Path -LiteralPath $PackageRoot).Path
# 0.4.24 — limpa fixtures Temp mortas antes de propagar
Prune-OrchestratorProjectRegistry -DryRun:$DryRun | Out-Null
$reg = Read-ProjectRegistry

if ($Discover.IsPresent) {
    $roots = [System.Collections.Generic.List[string]]::new()
    foreach ($r in @($reg.discover_roots)) {
        if (-not [string]::IsNullOrWhiteSpace($r)) { $roots.Add([string]$r) | Out-Null }
    }
    $parent = Split-Path -Parent $pkgResolved
    if (-not [string]::IsNullOrWhiteSpace($parent) -and -not $roots.Contains($parent)) {
        $roots.Add($parent) | Out-Null
    }
    Write-Host ("[ETAPA] Discover projetos (.orchestrator) em: {0}" -f ($roots -join ', '))
    foreach ($found in (Find-OrchestratorProjects -Roots @($roots.ToArray()))) {
        if ([string]::Equals($found, $pkgResolved, [StringComparison]::OrdinalIgnoreCase)) {
            continue
        }
        Register-OrchestratorProject -ProjectPath $found -DryRun:$DryRun | Out-Null
    }
    $reg = Read-ProjectRegistry
}

$targets = @()
foreach ($p in @($reg.projects)) {
    if ($null -eq $p -or [string]::IsNullOrWhiteSpace([string]$p.path)) { continue }
    $targets += [string]$p.path
}
$targets = @($targets | Select-Object -Unique)

if ($targets.Count -eq 0) {
    Write-Host '[INFO] Nenhum projeto registrado para propagar.'
    exit 0
}

Write-Host ("[ETAPA] Propagar update {0} -> {1} projeto(s)" -f $PackageVersion, $targets.Count)
$installer = Join-Path $PSScriptRoot 'Install-Orchestrator.ps1'
$results = New-Object System.Collections.Generic.List[object]

foreach ($target in $targets) {
    $row = [pscustomobject]@{
        path   = $target
        from   = $null
        to     = $PackageVersion
        status = 'SKIP'
        detail = ''
    }

    if (-not (Test-Path -LiteralPath $target)) {
        $row.status = 'SKIP'
        $row.detail = 'path missing'
        $results.Add($row) | Out-Null
        Write-Host ("[SKIP] {0} - path inexistente" -f $target)
        continue
    }

    if (-not (Test-Path -LiteralPath (Join-Path $target '.orchestrator\VERSION'))) {
        $row.status = 'SKIP'
        $row.detail = 'no .orchestrator/VERSION'
        $results.Add($row) | Out-Null
        Write-Host ("[SKIP] {0} - sem .orchestrator/VERSION" -f $target)
        continue
    }

    if ([string]::Equals(
            (Resolve-Path -LiteralPath $target).Path.TrimEnd('\', '/'),
            $pkgResolved.TrimEnd('\', '/'),
            [StringComparison]::OrdinalIgnoreCase)) {
        $row.status = 'SKIP'
        $row.detail = 'package workspace'
        $results.Add($row) | Out-Null
        continue
    }

    $from = Read-WorkspaceVersion -ProjectPath $target
    $row.from = $from
    $cmp = Compare-SemVer -Left $from -Right $PackageVersion
    if ($cmp -eq 'equal' -and -not $Force.IsPresent) {
        $row.status = 'SKIP'
        $row.detail = 'already current'
        $results.Add($row) | Out-Null
        Write-Host ("[SKIP] {0} - ja em {1}" -f $target, $from)
        # bug-075 — o SKIP por versao igual tambem pulava os REPAIRS
        # idempotentes: o alias kimi-latest ficou congelado nos 12 projetos
        # (merge do manifest preserva o valor do projeto) e so saiu com
        # Repair-ModelsJson rodado na mao. Reparos de conteudo rodam mesmo
        # sem bump de versao.
        if (-not $DryRun.IsPresent) {
            & (Join-Path $PSScriptRoot 'Repair-ModelsJson.ps1') -ProjectPath $target | Out-Null
        }
        # ainda assim atualiza last_seen/version no registry
        Register-OrchestratorProject -ProjectPath $target -Version $from -DryRun:$DryRun | Out-Null
        continue
    }
    if ($cmp -eq 'newer' -and -not $Force.IsPresent) {
        $row.status = 'SKIP'
        $row.detail = 'workspace newer than package'
        $results.Add($row) | Out-Null
        Write-Host ("[SKIP] {0} - workspace {1} > pacote {2}" -f $target, $from, $PackageVersion)
        continue
    }

    if ($DryRun.IsPresent) {
        $row.status = 'DRY-RUN'
        $row.detail = 'would update'
        $results.Add($row) | Out-Null
        Write-Host ("[DRY-RUN] update {0} ({1} -> {2})" -f $target, $from, $PackageVersion)
        continue
    }

    Write-Host ("[ETAPA] Propagando -> {0} ({1} -> {2})" -f $target, $from, $PackageVersion)
    $prev = $env:ORCHESTRATOR_PROPAGATING
    $env:ORCHESTRATOR_PROPAGATING = '1'
    try {
        & $installer `
            -Command update `
            -ProjectPath $target `
            -PackageRoot $pkgResolved `
            -SkipAgentUpdates `
            -NoPropagate `
            -NonInteractive `
            -SkipGlobalTools `
            -CursorMcpScope project
        $code = $LASTEXITCODE
    }
    finally {
        if ($null -eq $prev) {
            Remove-Item Env:ORCHESTRATOR_PROPAGATING -ErrorAction SilentlyContinue
        }
        else {
            $env:ORCHESTRATOR_PROPAGATING = $prev
        }
    }

    if ($code -ne 0) {
        $row.status = 'ERRO'
        $row.detail = "exit $code"
        $results.Add($row) | Out-Null
        Write-Host ("[ERRO] Propagacao falhou: {0} (exit {1})" -f $target, $code)
        continue
    }

    $newVer = Read-WorkspaceVersion -ProjectPath $target
    $row.to = $newVer
    $row.status = 'OK'
    $row.detail = "$from -> $newVer"
    # bug-068 — .orchestrator versionado no git do projeto: a propagacao
    # escreve na working tree, mas checkout/restore do PROJETO reverte para a
    # versao commitada (printbee regrediu 0.4.44 -> 0.4.42 assim; commit
    # 849379b0b congelou a 0.4.42 no repo). Todas as guardas anti-downgrade
    # (install/update/propagate) protegem o CLI, nao o git alheio: avisar.
    $gitTracked = $false
    try {
        git -C $target ls-files --error-unmatch .orchestrator/VERSION 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $gitTracked = $true }
    }
    catch { $gitTracked = $false }
    if ($gitTracked) {
        $row.detail = "$from -> $newVer | AVISO: .orchestrator versionado no git do projeto; commitar ou o update pode regredir"
        Write-Host ("[AVISO] {0} - .orchestrator rastreado pelo git do projeto; checkout/restore pode regredir a versao" -f $target)
    }
    $results.Add($row) | Out-Null
    Register-OrchestratorProject -ProjectPath $target -Version $newVer | Out-Null
    Write-Host ("[OK] Propagado: {0} ({1})" -f $target, $row.detail)
}

Write-Host ''
Write-Host '[OK] Relatorio de propagacao:'
foreach ($r in $results) {
    Write-Host ("  - [{0}] {1}  {2}" -f $r.status, $r.path, $r.detail)
}

$reportDir = Join-Path $pkgResolved '.orchestrator\runtime\reports'
if (-not $DryRun.IsPresent -and (Test-Path -LiteralPath (Join-Path $pkgResolved '.orchestrator'))) {
    try {
        Ensure-Directory -Path $reportDir | Out-Null
        $reportPath = Join-Path $reportDir 'propagate-update.json'
        $payload = [ordered]@{
            package_version = [string]$PackageVersion
            generated       = (Get-Date).ToUniversalTime().ToString('o')
            results         = @($results.ToArray())
        }
        ($payload | ConvertTo-Json -Depth 6) | Set-Content -LiteralPath $reportPath -Encoding UTF8
        Write-Host ("[OK] Relatorio: {0}" -f $reportPath)
    }
    catch {
        Write-Host ("[AVISO] Nao foi possivel gravar propagate-update.json: {0}" -f $_.Exception.Message)
    }
}

# Propagacao parcial nao falha o update do pacote
exit 0

