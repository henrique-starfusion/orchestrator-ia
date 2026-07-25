#Requires -Version 5.1
<#
.SYNOPSIS
    0.4.20 — registry de projetos + propagacao so no update do pacote.
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Test-Helpers.ps1')
. (Join-Path (Get-TestScriptsRoot) 'Orchestrator.Common.ps1')

$failed = 0
function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) {
        Write-Host ("[FAIL] {0}" -f $Message)
        $script:failed++
    }
    else {
        Write-Host ("[OK] {0}" -f $Message)
    }
}

$registryFile = Join-Path $env:TEMP ("orch-registry-{0}.json" -f [guid]::NewGuid().ToString('n'))
$env:ORCHESTRATOR_PROJECTS_REGISTRY = $registryFile
$env:ORCHESTRATOR_SKIP_PACKAGE_SYNC = '1'
$packageRoot = Get-TestRepoRoot
$installer = Join-Path (Get-TestScriptsRoot) 'Install-Orchestrator.ps1'
$propagate = Join-Path (Get-TestScriptsRoot) 'Propagate-OrchestratorUpdate.ps1'

try {
    # AC1: register on install
    $projA = New-TestProjectDirectory
    Invoke-TestInstall -ProjectPath $projA -PackageRoot $packageRoot | Out-Null
    $reg = Read-ProjectRegistry
    $paths = @($reg.projects | ForEach-Object { $_.path })
    Assert-True ($paths -contains (Resolve-Path $projA).Path) 'install registra projeto no registry'

    # AC3: update em consumidor NAO propaga
    $projB = New-TestProjectDirectory
    Invoke-TestInstall -ProjectPath $projB -PackageRoot $packageRoot | Out-Null
    Set-Content -LiteralPath (Join-Path $projB '.orchestrator\VERSION') -Value '0.4.0' -Encoding UTF8
    Register-OrchestratorProject -ProjectPath $projB -Version '0.4.0' | Out-Null

    & $installer `
        -Command update `
        -ProjectPath $projA `
        -PackageRoot $packageRoot `
        -SkipAgentUpdates `
        -SkipGlobalTools `
        -NonInteractive `
        -CursorMcpScope project | Out-Null
    $bVer = Read-WorkspaceVersion -ProjectPath $projB
    Assert-True ($bVer -eq '0.4.0') 'update em consumidor nao propaga para outros'

    # AC2: propagate script (equivalente ao gancho do update do pacote)
    $pkgVer = Read-PackageVersion -PackageRoot $packageRoot
    & $propagate -PackageRoot $packageRoot -PackageVersion $pkgVer
    $bVer2 = Read-WorkspaceVersion -ProjectPath $projB
    Assert-True ($bVer2 -eq $pkgVer) ("propagate atualiza registrado ({0} == {1})" -f $bVer2, $pkgVer)

    # Pacote workspace detectado
    Assert-True (
        (Test-IsOrchestratorPackageWorkspace -ProjectPath $packageRoot -PackageRoot $packageRoot)
    ) 'bootstrap-agents e workspace do pacote'
    Assert-True (
        -not (Test-IsOrchestratorPackageWorkspace -ProjectPath $projA -PackageRoot $packageRoot)
    ) 'consumidor nao e workspace do pacote'

    # AC4: --no-propagate no update do pacote
    Set-Content -LiteralPath (Join-Path $projB '.orchestrator\VERSION') -Value '0.4.0' -Encoding UTF8
    Register-OrchestratorProject -ProjectPath $projB -Version '0.4.0' | Out-Null
    & $installer `
        -Command update `
        -ProjectPath $packageRoot `
        -PackageRoot $packageRoot `
        -SkipAgentUpdates `
        -SkipGlobalTools `
        -NonInteractive `
        -CursorMcpScope project `
        -NoPropagate `
        -Force | Out-Null
    $bVer3 = Read-WorkspaceVersion -ProjectPath $projB
    Assert-True ($bVer3 -eq '0.4.0') '--no-propagate impede leva'

    # Discover
    $discRoot = New-TestProjectDirectory
    $hidden = Join-Path $discRoot 'nested-app'
    New-Item -ItemType Directory -Path (Join-Path $hidden '.orchestrator') -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $hidden '.orchestrator\VERSION') -Value '0.4.1' -Encoding UTF8
    $found = Find-OrchestratorProjects -Roots @($discRoot)
    Assert-True ($found -contains (Resolve-Path $hidden).Path) 'discover encontra .orchestrator aninhado'

    Remove-TestProjectDirectory -Path $projA
    Remove-TestProjectDirectory -Path $projB
    Remove-TestProjectDirectory -Path $discRoot
}
finally {
    Remove-Item Env:ORCHESTRATOR_PROJECTS_REGISTRY -ErrorAction SilentlyContinue
    Remove-Item Env:ORCHESTRATOR_SKIP_PACKAGE_SYNC -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $registryFile) {
        Remove-Item -LiteralPath $registryFile -Force -ErrorAction SilentlyContinue
    }
}

if ($failed -gt 0) {
    Write-Host ("[FAIL] Test-ProjectPropagate: {0} falha(s)" -f $failed)
    exit 1
}
Write-Host '[PASS] Test-ProjectPropagate'
exit 0
