#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Test-Helpers.ps1')

$TestName = 'Test-WikiPublishing'
$tempDir = $null
$exitCode = 1

function Invoke-WikiTestGit {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $previousEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = & git @Arguments 2>&1 | Out-String
        $gitExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousEap
    }
    if ($gitExitCode -ne 0) {
        throw ('git {0} falhou: {1}' -f ($Arguments -join ' '), $output.Trim())
    }
    return $output.Trim()
}

try {
    $repoRoot = Get-TestRepoRoot
    $publisher = Join-Path $repoRoot 'scripts\Publish-Wiki.ps1'
    $tempDir = New-TestProjectDirectory
    $fixtureRoot = Join-Path $tempDir 'fixture'
    $docsRoot = Join-Path $fixtureRoot 'docs'
    $outputRoot = Join-Path $tempDir 'wiki-output'
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)

    New-Item -ItemType Directory -Path (Join-Path $docsRoot 'audits') -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $fixtureRoot 'runtime\src') -Force | Out-Null

    [System.IO.File]::WriteAllText(
        (Join-Path $docsRoot 'README.md'),
        "# Indice`n`n[Guia](guide.md)`n",
        $utf8NoBom
    )
    [System.IO.File]::WriteAllText(
        (Join-Path $docsRoot 'guide.md'),
        @'
# Guia

[Documento relativo](reference.md)
[Documento desde a raiz](docs/reference.md)
[Codigo](../runtime/src/example.py#L2)
[Externo](https://example.com/reference?from=wiki#section)
'@,
        $utf8NoBom
    )
    [System.IO.File]::WriteAllText(
        (Join-Path $docsRoot 'reference.md'),
        "# Referencia`n",
        $utf8NoBom
    )
    [System.IO.File]::WriteAllText(
        (Join-Path $docsRoot 'audits\record.md'),
        "# Registro`n",
        $utf8NoBom
    )
    [System.IO.File]::WriteAllText(
        (Join-Path $fixtureRoot 'runtime\src\example.py'),
        "print('example')`n",
        $utf8NoBom
    )

    $arguments = @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', $publisher,
        '-ProjectRoot', $fixtureRoot,
        '-RepositoryUrl', 'https://github.com/henrique-starfusion/orchestrator-ia',
        '-RepositoryRef', 'develop',
        '-GenerateOnly',
        '-OutputDirectory', $outputRoot
    )
    $publisherOutput = & powershell.exe @arguments 2>&1 | Out-String
    $publisherExitCode = $LASTEXITCODE
    Assert-Test -Condition ($publisherExitCode -eq 0) -Message (
        'publicador falhou com exit={0}: {1}' -f $publisherExitCode, $publisherOutput.Trim()
    )

    $guide = Get-Content -LiteralPath (Join-Path $outputRoot 'guide.md') -Raw -Encoding UTF8
    $wikiReference = 'https://github.com/henrique-starfusion/orchestrator-ia/wiki/reference'
    $blobCode = 'https://github.com/henrique-starfusion/orchestrator-ia/blob/develop/runtime/src/example.py#L2'
    $external = 'https://example.com/reference?from=wiki#section'

    Assert-Test -Condition ($guide -match [regex]::Escape("[Documento relativo]($wikiReference)")) -Message 'link relativo entre documentos nao virou link de Wiki'
    Assert-Test -Condition ($guide -match [regex]::Escape("[Documento desde a raiz]($wikiReference)")) -Message 'link docs/... nao virou link de Wiki'
    Assert-Test -Condition ($guide -match [regex]::Escape("[Codigo]($blobCode)")) -Message 'link para codigo nao virou URL blob'
    Assert-Test -Condition ($guide -match [regex]::Escape("[Externo]($external)")) -Message 'link externo foi alterado'
    Assert-Test -Condition (Test-Path -LiteralPath (Join-Path $outputRoot 'historico-audits-record.md')) -Message 'documento historico nao recebeu pagina distinta'
    Assert-Test -Condition (Test-Path -LiteralPath (Join-Path $outputRoot 'Home.md')) -Message 'Home nao foi gerada'
    Assert-Test -Condition ((Get-ChildItem -LiteralPath $outputRoot -File -Filter '*.md').Count -eq 5) -Message 'quantidade de paginas geradas diverge de docs mais Home'

    # Regressao de idempotencia: checkout com CRLF pode parecer modificado antes
    # do index normalizar os arquivos. O segundo run precisa consultar o diff
    # staged e nao tentar criar commit vazio.
    $wikiOrigin = Join-Path $tempDir 'wiki.git'
    Invoke-WikiTestGit -Arguments @('init', '--bare', $wikiOrigin) | Out-Null
    $env:GIT_AUTHOR_NAME = 'Wiki Regression Test'
    $env:GIT_AUTHOR_EMAIL = 'wiki-test@example.invalid'
    $env:GIT_COMMITTER_NAME = 'Wiki Regression Test'
    $env:GIT_COMMITTER_EMAIL = 'wiki-test@example.invalid'
    $env:GIT_CONFIG_COUNT = '1'
    $env:GIT_CONFIG_KEY_0 = 'core.autocrlf'
    $env:GIT_CONFIG_VALUE_0 = 'true'

    $publishArguments = @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', $publisher,
        '-ProjectRoot', $fixtureRoot,
        '-WikiRepositoryUrl', $wikiOrigin,
        '-RepositoryUrl', 'https://github.com/henrique-starfusion/orchestrator-ia',
        '-RepositoryRef', 'develop'
    )
    $firstPublishOutput = & powershell.exe @publishArguments 2>&1 | Out-String
    $firstPublishExitCode = $LASTEXITCODE
    Assert-Test -Condition ($firstPublishExitCode -eq 0) -Message ('primeira publicacao local falhou: {0}' -f $firstPublishOutput.Trim())
    $commitsAfterFirstRun = [int](Invoke-WikiTestGit -Arguments @('--git-dir', $wikiOrigin, 'rev-list', '--count', '--all'))

    $secondPublishOutput = & powershell.exe @publishArguments 2>&1 | Out-String
    $secondPublishExitCode = $LASTEXITCODE
    Assert-Test -Condition ($secondPublishExitCode -eq 0) -Message ('segunda publicacao local tentou commit vazio: {0}' -f $secondPublishOutput.Trim())
    $commitsAfterSecondRun = [int](Invoke-WikiTestGit -Arguments @('--git-dir', $wikiOrigin, 'rev-list', '--count', '--all'))
    Assert-Test -Condition ($commitsAfterFirstRun -eq 1) -Message 'primeira publicacao local nao criou exatamente um commit'
    Assert-Test -Condition ($commitsAfterSecondRun -eq $commitsAfterFirstRun) -Message 'segunda publicacao local criou commit adicional'
    Assert-Test -Condition ($secondPublishOutput -match 'Nenhum commit criado') -Message 'segunda publicacao local nao informou idempotencia'

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
