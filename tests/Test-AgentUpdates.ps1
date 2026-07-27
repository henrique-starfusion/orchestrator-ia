#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Test-Helpers.ps1')

$TestName = 'Test-AgentUpdates'
$tempDir = $null
$exitCode = 1

try {
    $repoRoot = Get-TestRepoRoot
    $tempDir = New-TestProjectDirectory

    Invoke-TestInstall -ProjectPath $tempDir -PackageRoot $repoRoot

    # Dry-run: atualiza (ou tenta) agentes available — exit 0
    $dryRunCode = Invoke-TestScript -ScriptName 'Update-Agents.ps1' -Arguments @{
        ProjectPath  = $tempDir
        UpdateAgents = [switch]::Present
        DryRun       = [switch]::Present
    }
    Assert-Test -Condition ($dryRunCode -eq 0) -Message ('Update-Agents -DryRun exited with code {0}' -f $dryRunCode)

    # Sem UpdateAgents ainda atualiza (0.4.17+ default no script quando invocado)
    $defaultCode = Invoke-TestScript -ScriptName 'Update-Agents.ps1' -Arguments @{
        ProjectPath = $tempDir
        DryRun      = [switch]::Present
    }
    Assert-Test -Condition ($defaultCode -eq 0) -Message (
        'Update-Agents default dry-run exited with code {0}' -f $defaultCode
    )

    # Pipeline install com -SkipAgentUpdates nao deve falhar
    $skipCode = Invoke-TestScript -ScriptName 'Install-Orchestrator.ps1' -Arguments @{
        Command          = 'verify'
        ProjectPath      = $tempDir
        PackageRoot      = $repoRoot
        SkipAgentUpdates = [switch]::Present
    }
    Assert-Test -Condition ($skipCode -eq 0) -Message (
        'verify -SkipAgentUpdates exited with code {0}' -f $skipCode
    )

    # 0.4.31 — CLI que nao sabe se auto-atualizar (kimi instalado nativo no
    # Windows) reporta isso ele mesmo. Nao pode virar "falhou", e o comando
    # manual que ele imprime tem que sobreviver ate o relatorio.
    $updateAgentsSrc = Join-Path $repoRoot 'scripts\Update-Agents.ps1'
    $srcText = Get-Content -LiteralPath $updateAgentsSrc -Raw -Encoding UTF8
    $fnStart = $srcText.IndexOf('function Get-ManualUpdateHint')
    Assert-Test -Condition ($fnStart -ge 0) -Message 'Get-ManualUpdateHint ausente em Update-Agents.ps1'
    $fnEnd = $srcText.IndexOf("`nfunction Invoke-AgentUpdateAttempt", $fnStart)
    Invoke-Expression $srcText.Substring($fnStart, $fnEnd - $fnStart)

    $kimiOutput = @'
A newer version of @moonshot-ai/kimi-code is available (0.29.0 -> 0.29.1).
Detected install source: native (windows). Auto-update is not supported on this platform.
To update manually, run: irm https://code.kimi.com/kimi-code/install.ps1 | iex
'@
    $hint = Get-ManualUpdateHint -Output $kimiOutput
    Assert-Test -Condition ($hint -eq 'irm https://code.kimi.com/kimi-code/install.ps1 | iex') -Message (
        'comando manual do kimi nao extraido: {0}' -f $hint
    )

    # Falha comum de rede NAO pode virar "manual" — perderia o fallback.
    $transient = Get-ManualUpdateHint -Output 'error: failed to check for updates: This operation was aborted'
    Assert-Test -Condition ($null -eq $transient) -Message 'falha transitoria classificada como manual_required'

    # Update normal tambem nao.
    $okOutput = Get-ManualUpdateHint -Output 'Already up to date.'
    Assert-Test -Condition ($null -eq $okOutput) -Message 'update bem-sucedido classificado como manual_required'

    # Anuncia sem imprimir comando: ainda e manual, com texto generico.
    $noCmd = Get-ManualUpdateHint -Output 'Auto-update is not supported on this platform.'
    Assert-Test -Condition ($noCmd -eq 'consulte a documentacao do CLI') -Message (
        'anuncio sem comando nao caiu no texto generico: {0}' -f $noCmd
    )

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
