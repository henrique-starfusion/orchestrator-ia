#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$ProjectPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Orchestrator.Common.ps1')

$projectRoot = Get-ProjectRoot -ProjectPath $ProjectPath
$hooksRoot = Join-Path (Get-OrchestratorRoot -ProjectPath $projectRoot) 'hooks'
$testedDir = Join-Path $hooksRoot 'tested'
$activeDir = Join-Path $hooksRoot 'active'

$testedHooks = @()
$activeHooks = @()

if (Test-Path -LiteralPath $testedDir) {
    $testedHooks = @(Get-ChildItem -LiteralPath $testedDir -Filter '*.ps1' -File -ErrorAction SilentlyContinue)
}
if (Test-Path -LiteralPath $activeDir) {
    $activeHooks = @(Get-ChildItem -LiteralPath $activeDir -Filter '*.ps1' -File -ErrorAction SilentlyContinue)
}

if ($testedHooks.Count -eq 0 -and $activeHooks.Count -eq 0) {
    Write-Host '[INFO] Nenhum hook em hooks/tested ou hooks/active; validacao ignorada.'
    exit 0
}

$failures = @()

foreach ($hook in $testedHooks) {
    Write-Host "[INFO] Testando hook: $($hook.Name)"
    $result = Invoke-ExternalCommand -FilePath 'powershell.exe' -ArgumentList "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$($hook.FullName)`"" -TimeoutSeconds 5 -WorkingDirectory $projectRoot

    if ($result.timed_out) {
        $failures += "$($hook.Name): timeout (>5s)"
    }
    elseif ($result.exit_code -ne 0) {
        $failures += "$($hook.Name): exit $($result.exit_code)"
    }
}

if ($failures.Count -gt 0) {
    foreach ($failure in $failures) {
        Write-Host "[ERRO] $failure"
    }
    exit 1
}

Write-Host '[OK] Validate-Hooks concluido.'
exit 0
