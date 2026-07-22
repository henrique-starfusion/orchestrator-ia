#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Test-Helpers.ps1')

$TestName = 'Test-ModelRouting'
$tempDir = $null
$exitCode = 1

try {
    $repoRoot = Get-TestRepoRoot
    $tempDir = New-TestProjectDirectory

    # fixture minima: models.json do template + detected.json real (formato do Detect-Agents: SO campo status, sem 'available' e sem 'id')
    New-Item -ItemType Directory -Path (Join-Path $tempDir '.orchestrator\config') -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $tempDir '.orchestrator\agents') -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $repoRoot 'package\template\.orchestrator\config\models.json') `
        -Destination (Join-Path $tempDir '.orchestrator\config\models.json') -Force

    $detected = @{
        version     = '0.1.0'
        detected_at = '2026-07-20T00:00:00'
        agents      = @(
            @{ name = 'claude'; status = 'available'; command = 'claude.cmd' },
            @{ name = 'cursor'; status = 'installed_failed'; command = 'cursor.cmd' }
        )
    }
    $detected | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $tempDir '.orchestrator\agents\detected.json') -Encoding UTF8

    # -Client auto com detected.json real nao pode explodir (bug-002: StrictMode em $a.available/$a.id)
    $routeScript = Join-Path $repoRoot 'scripts\Resolve-ModelRoute.ps1'
    $output = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $routeScript `
        -ProjectPath $tempDir -TaskClass docs -Client auto -Json 2>&1 | Out-String
    $code = $LASTEXITCODE

    Assert-Test -Condition ($code -eq 0) -Message ('Resolve-ModelRoute auto saiu com codigo {0}: {1}' -f $code, $output)
    Assert-Test -Condition ($output -notmatch 'PropertyNotFound') -Message ('StrictMode explodiu: {0}' -f $output)

    $route = $output | ConvertFrom-Json
    Assert-Test -Condition ($route.client -eq 'claude') -Message ('client = {0} (esperado claude: unico available na fixture)' -f $route.client)
    Assert-Test -Condition ($route.model -eq 'claude-sonnet-5') -Message ('model = {0} (esperado claude-sonnet-5 para docs)' -f $route.model)

    Write-Host ('PASS: {0}' -f $TestName) -ForegroundColor Green
    $exitCode = 0
}
catch {
    Write-Host ('FAIL: {0} - {1}' -f $TestName, $_.Exception.Message) -ForegroundColor Red
}
finally {
    if ($tempDir) {
        Remove-TestProjectDirectory -Path $tempDir
    }
}

exit $exitCode
