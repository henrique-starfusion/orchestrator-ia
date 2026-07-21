#Requires -Version 5.1
<#
.SYNOPSIS
  Migration 0.2.0 -> 0.3.0: Cursor MCP rule + config scaffolding.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectPath,
    [string]$PackageRoot,
    [string]$FromVersion,
    [string]$ToVersion
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($PackageRoot) {
    $script = Join-Path $PackageRoot 'scripts\Configure-CursorMcp.ps1'
    if (Test-Path -LiteralPath $script) {
        & $script -ProjectPath $ProjectPath -PackageRoot $PackageRoot -CursorTransport stdio
        if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) {
            Write-Host ("[AVISO] Configure-CursorMcp exit {0}" -f $LASTEXITCODE)
        }
    }
}

Write-Host ("[OK] migration 0.2.0-to-0.3.0 (from={0} to={1})" -f $FromVersion, $ToVersion)
exit 0
