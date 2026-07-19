#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [string]$PackageRoot,
    [switch]$Force,
    [switch]$AllAdapters
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Orchestrator.Common.ps1')

$projectRoot = Get-ProjectRoot -ProjectPath $ProjectPath
$packageRootResolved = Get-PackageRoot -PackageRoot $PackageRoot
$vendorMap = Get-AdapterVendorMap
$adapterRoot = Join-Path $packageRootResolved 'package\template\adapters'

$vendorsToCopy = New-Object System.Collections.Generic.List[string]

if ($AllAdapters) {
    if (Test-Path -LiteralPath $adapterRoot) {
        Get-ChildItem -LiteralPath $adapterRoot -Directory -Force | ForEach-Object {
            $vendorsToCopy.Add($_.Name) | Out-Null
        }
    }
}
else {
    $detectedPath = Join-Path (Get-OrchestratorRoot -ProjectPath $projectRoot) 'agents\detected.json'
    if (Test-Path -LiteralPath $detectedPath) {
        $detected = Get-JsonFileContent -Path $detectedPath
        foreach ($agent in $detected.agents) {
            if ($agent.status -ne 'available') { continue }
            if ($vendorMap.ContainsKey($agent.name)) {
                $vendor = $vendorMap[$agent.name]
                if (-not $vendorsToCopy.Contains($vendor)) {
                    $vendorsToCopy.Add($vendor) | Out-Null
                }
            }
        }
    }
}

$copied = 0
$skipped = 0

foreach ($vendor in $vendorsToCopy) {
    $sourceDir = Join-Path $adapterRoot $vendor
    if (-not (Test-Path -LiteralPath $sourceDir)) {
        Write-Host "[AVISO] Adapter template ausente: $vendor"
        continue
    }

    Get-ChildItem -LiteralPath $sourceDir -Recurse -File -Force | ForEach-Object {
        $relative = $_.FullName.Substring($sourceDir.Length).TrimStart('\', '/')
        $destPath = Join-Path $projectRoot $relative

        if ((Test-Path -LiteralPath $destPath) -and -not $Force) {
            $skipped++
            return
        }

        $parent = Split-Path -Parent $destPath
        if (-not [string]::IsNullOrWhiteSpace($parent)) {
            Ensure-Directory -Path $parent | Out-Null
        }

        Copy-Item -LiteralPath $_.FullName -Destination $destPath -Force:(-not (Test-Path -LiteralPath $destPath) -or $Force)
        $copied++
    }
}

Write-Host "[OK] Generate-Adapters: $copied copiados, $skipped ignorados."
exit 0
