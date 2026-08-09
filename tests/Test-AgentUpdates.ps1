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

    # Instalador oficial: a URL vem de mapa curado, NUNCA da saida do CLI —
    # executar texto vindo de stdout seria injecao de comando.
    . (Join-Path $repoRoot 'scripts\Orchestrator.Common.ps1')
    $installerMap = Get-AgentNativeInstallerMap
    Assert-Test -Condition ($installerMap.ContainsKey('kimi')) -Message 'kimi ausente no mapa de instaladores nativos'
    Assert-Test -Condition ($installerMap['kimi'].url -like 'https://*') -Message 'instalador do kimi nao e HTTPS'
    Assert-Test -Condition (-not ($srcText -match '(?m)iex\s*\(')) -Message (
        'Update-Agents nao pode canalizar saida para iex; instalador vai para arquivo e e executado'
    )
    Assert-Test -Condition ($srcText -match 'Get-FileHash') -Message (
        'instalador baixado tem que ter hash registrado no log (auditoria)'
    )

    # -NoNativeInstaller: reporta o comando e nao baixa nada.
    $noInstallerCode = Invoke-TestScript -ScriptName 'Update-Agents.ps1' -Arguments @{
        ProjectPath       = $tempDir
        DryRun            = [switch]::Present
        NoNativeInstaller = [switch]::Present
    }
    Assert-Test -Condition ($noInstallerCode -eq 0) -Message (
        'Update-Agents -NoNativeInstaller exited with code {0}' -f $noInstallerCode
    )

    # 0.4.32 — todo update reconfere os agentes da maquina. O branch update nao
    # chamava Probe-Agents, entao o probe-results.json dos projetos propagados
    # ficava congelado na data da INSTALACAO (medido na frota: 21/07, seis dias
    # atras, enquanto a versao ja tinha avancado varias vezes).
    $probePath = Join-Path $tempDir '.orchestrator\agents\probe-results.json'
    if (Test-Path -LiteralPath $probePath) { Remove-Item -LiteralPath $probePath -Force }

    $updCode = Invoke-TestScript -ScriptName 'Install-Orchestrator.ps1' -Arguments @{
        Command     = 'update'
        ProjectPath = $tempDir
        PackageRoot = $repoRoot
        NoPropagate = [switch]::Present
        SkipAgentUpdates = [switch]::Present
    }
    Assert-Test -Condition ($updCode -eq 0) -Message ('update exited with code {0}' -f $updCode)
    Assert-Test -Condition (Test-Path -LiteralPath $probePath) -Message (
        'update nao gerou probe-results.json: agentes nao foram reconferidos'
    )
    $probe = Get-Content -LiteralPath $probePath -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-Test -Condition ($probe.skipped -ne $true) -Message (
        'update gravou probe-results com skipped=true; probe deve rodar por padrao'
    )

    # --- bug-099: CLI em execucao nao pode ter o binario substituido -------
    # Substituir .exe em uso no Windows nao "pula o update": o npm baixa, falha
    # o move final com EBUSY e deixa instalacao PARCIAL — foi assim que o codex
    # ficou dois dias saindo exit=1 com zero byte na frota inteira.
    # Teste real: um processo de verdade chamado `codex` (ping renomeado).
    # O ambiente pode ter um codex REAL rodando (executor de outra task da
    # frota). Nesse caso o guard adia de verdade e o caso negativo nao se
    # aplica — medir antes em vez de assumir.
    $codexRealRodando = @(Get-Process -Name 'codex' -ErrorAction SilentlyContinue).Count -gt 0

    $fakeExe = Join-Path $env:TEMP 'codex.exe'
    $fakeProc = $null
    try {
        Copy-Item -LiteralPath (Join-Path $env:SystemRoot 'System32\ping.exe') `
            -Destination $fakeExe -Force
        $fakeProc = Start-Process -FilePath $fakeExe `
            -ArgumentList '-n', '60', '127.0.0.1' -PassThru -WindowStyle Hidden
        Start-Sleep -Milliseconds 400

        $outBusy = & powershell.exe -NoProfile -ExecutionPolicy Bypass `
            -File (Join-Path $repoRoot 'scripts\Update-Agents.ps1') `
            -ProjectPath $tempDir -DryRun 2>&1 | Out-String

        Assert-Test -Condition ($outBusy -match '\[ADIADO\] codex') -Message (
            'update NAO adiou o codex com processo em execucao (risco de EBUSY e instalacao parcial)'
        )
        # Contagem >= 1: `claude` tambem aparece adiado quando a suite roda de
        # dentro do Claude Code — e isso esta CERTO, o binario dele tambem esta
        # em uso. Nao fixar o numero para o teste nao depender do harness.
        $mAdiados = [regex]::Match($outBusy, 'adiados=(\d+)')
        Assert-Test -Condition ($mAdiados.Success -and [int]$mAdiados.Groups[1].Value -ge 1) `
            -Message 'resumo do Update-Agents nao contabilizou agente adiado'
    }
    finally {
        if ($fakeProc) { Stop-Process -Id $fakeProc.Id -Force -ErrorAction SilentlyContinue }
        Start-Sleep -Milliseconds 200
        Remove-Item -LiteralPath $fakeExe -Force -ErrorAction SilentlyContinue
    }

    # Sem processo do agente, o update volta a acontecer normalmente.
    if ($codexRealRodando) {
        Write-Host '[SKIP] caso negativo: ha um codex REAL rodando nesta maquina (executor de outra task).'
    }
    else {
        $outLivre = & powershell.exe -NoProfile -ExecutionPolicy Bypass `
            -File (Join-Path $repoRoot 'scripts\Update-Agents.ps1') `
            -ProjectPath $tempDir -DryRun 2>&1 | Out-String
        Assert-Test -Condition ($outLivre -notmatch '\[ADIADO\] codex') -Message (
            'update adiou o codex mesmo sem processo em execucao — guard cedo demais'
        )
    }

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
