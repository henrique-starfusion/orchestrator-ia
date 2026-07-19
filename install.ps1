#Requires -Version 5.1
& (Join-Path $PSScriptRoot 'scripts\Install-Orchestrator.ps1') @args
exit $LASTEXITCODE
