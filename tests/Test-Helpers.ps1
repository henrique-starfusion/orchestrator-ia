#Requires -Version 5.1
Set-StrictMode -Version Latest

function Get-TestRepoRoot {
    return (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
}

function Get-TestScriptsRoot {
    return (Join-Path (Get-TestRepoRoot) 'scripts')
}

function New-TestProjectDirectory {
    $path = Join-Path $env:TEMP ('orchestrator-tests-{0}' -f [guid]::NewGuid().ToString())
    New-Item -ItemType Directory -Path $path -Force | Out-Null
    return (Resolve-Path -LiteralPath $path).Path
}

function Remove-TestProjectDirectory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Get-PackageVersion {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PackageRoot
    )

    $versionFile = Join-Path $PackageRoot 'VERSION'
    if (-not (Test-Path -LiteralPath $versionFile)) {
        throw ('Package VERSION not found: {0}' -f $versionFile)
    }

    return (Get-Content -LiteralPath $versionFile -Raw -Encoding UTF8).Trim()
}

function Invoke-TestInstall {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectPath,
        [Parameter(Mandatory = $true)]
        [string]$PackageRoot,
        [string[]]$ExtraArgs = @()
    )

    $installer = Join-Path (Get-TestScriptsRoot) 'Install-Orchestrator.ps1'

    if ($ExtraArgs.Count -gt 0) {
        & $installer install -ProjectPath $ProjectPath -PackageRoot $PackageRoot -NonInteractive -SkipGlobalTools @ExtraArgs
    }
    else {
        & $installer install -ProjectPath $ProjectPath -PackageRoot $PackageRoot -NonInteractive -SkipGlobalTools
    }

    if ($LASTEXITCODE -ne 0) {
        throw ('Install failed with exit code {0}' -f $LASTEXITCODE)
    }
}

function Invoke-TestOrchestratorCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Command,
        [Parameter(Mandatory = $true)]
        [string]$ProjectPath,
        [Parameter(Mandatory = $true)]
        [string]$PackageRoot,
        [switch]$Force,
        [switch]$DryRun
    )

    $installer = Join-Path (Get-TestScriptsRoot) 'Install-Orchestrator.ps1'

    if ($Force -and $DryRun) {
        & $installer $Command -ProjectPath $ProjectPath -PackageRoot $PackageRoot -NonInteractive -SkipGlobalTools -Force -DryRun
    }
    elseif ($Force) {
        & $installer $Command -ProjectPath $ProjectPath -PackageRoot $PackageRoot -NonInteractive -SkipGlobalTools -Force
    }
    elseif ($DryRun) {
        & $installer $Command -ProjectPath $ProjectPath -PackageRoot $PackageRoot -NonInteractive -SkipGlobalTools -DryRun
    }
    else {
        & $installer $Command -ProjectPath $ProjectPath -PackageRoot $PackageRoot -NonInteractive -SkipGlobalTools
    }

    return $LASTEXITCODE
}

function Invoke-TestScript {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ScriptName,
        [hashtable]$Arguments = @{}
    )

    $scriptPath = Join-Path (Get-TestScriptsRoot) $ScriptName
    if (-not (Test-Path -LiteralPath $scriptPath)) {
        throw ('Script not found: {0}' -f $scriptPath)
    }

    $params = @{}
    foreach ($key in $Arguments.Keys) {
        $value = $Arguments[$key]
        if ($value -is [switch]) {
            if ($value.IsPresent) {
                $params[$key] = $true
            }
        }
        elseif ($null -ne $value) {
            $params[$key] = $value
        }
    }

    & $scriptPath @params
    return $LASTEXITCODE
}

function Assert-Test {
    param(
        [Parameter(Mandatory = $true)]
        [bool]$Condition,
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    if (-not $Condition) {
        throw $Message
    }
}

function Get-TestFileSha256 {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        throw ('File not found: {0}' -f $Path)
    }

    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-OrchestratorPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectPath,
        [Parameter(Mandatory = $true)]
        [string]$RelativePath
    )

    return Join-Path $ProjectPath ('.orchestrator\' + ($RelativePath -replace '/', '\'))
}
