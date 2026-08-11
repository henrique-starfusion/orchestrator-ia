#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Test-Helpers.ps1')

$TestName = 'Test-PackageSyncHistory'
$tempDir = $null
$exitCode = 1

function Invoke-FixtureGit {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $previousEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = & $script:git.Source @Arguments 2>$null | Out-String
        $gitExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousEap
    }
    if ($gitExitCode -ne 0) {
        throw ('git {0} failed: {1}' -f ($Arguments -join ' '), $output.Trim())
    }
    return $output.Trim()
}

function Get-FixtureGitValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Repository,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    return (Invoke-FixtureGit -Arguments (@('-C', $Repository) + $Arguments)).Trim()
}

try {
    $repoRoot = Get-TestRepoRoot
    . (Join-Path $repoRoot 'scripts\Orchestrator.Common.ps1')

    $git = Get-Command git -ErrorAction Stop
    $tempDir = New-TestProjectDirectory
    $origin = Join-Path $tempDir 'origin.git'
    $seed = Join-Path $tempDir 'seed'
    $fullBehind = Join-Path $tempDir 'full-behind'
    $fullCurrent = Join-Path $tempDir 'full-current'
    $cacheCurrent = Join-Path $tempDir 'cache-current'
    $shallowCurrent = Join-Path $tempDir 'shallow-current'

    Invoke-FixtureGit -Arguments @('init', '--bare', $origin) | Out-Null
    Invoke-FixtureGit -Arguments @('init', $seed) | Out-Null
    Invoke-FixtureGit -Arguments @('-C', $seed, 'config', 'user.email', 'test@example.invalid') | Out-Null
    Invoke-FixtureGit -Arguments @('-C', $seed, 'config', 'user.name', 'Regression Test') | Out-Null
    Invoke-FixtureGit -Arguments @('-C', $seed, 'switch', '-c', 'develop') | Out-Null
    1..3 | ForEach-Object {
        Invoke-FixtureGit -Arguments @('-C', $seed, 'commit', '--allow-empty', '-m', "commit $_") | Out-Null
    }
    Invoke-FixtureGit -Arguments @('-C', $seed, 'remote', 'add', 'origin', $origin) | Out-Null
    Invoke-FixtureGit -Arguments @('-C', $seed, 'push', '-u', 'origin', 'develop') | Out-Null
    Invoke-FixtureGit -Arguments @('--git-dir', $origin, 'symbolic-ref', 'HEAD', 'refs/heads/develop') | Out-Null
    Invoke-FixtureGit -Arguments @('clone', $origin, $fullBehind) | Out-Null

    Invoke-FixtureGit -Arguments @('-C', $seed, 'commit', '--allow-empty', '-m', 'commit 4') | Out-Null
    Invoke-FixtureGit -Arguments @('-C', $seed, 'push', 'origin', 'develop') | Out-Null
    Invoke-FixtureGit -Arguments @('clone', $origin, $fullCurrent) | Out-Null
    Invoke-FixtureGit -Arguments @('clone', $origin, $cacheCurrent) | Out-Null

    $originUri = ([Uri]$origin).AbsoluteUri
    Invoke-FixtureGit -Arguments @('clone', '--depth', '1', '--branch', 'develop', $originUri, $shallowCurrent) | Out-Null

    # O cache existente tambem decide pelo estado real; clone novo segue raso.
    New-Item -ItemType Directory -Path (Join-Path $cacheCurrent 'scripts') -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $cacheCurrent 'package\template\.orchestrator') -Force | Out-Null
    New-Item -ItemType File -Path (Join-Path $cacheCurrent 'scripts\Install-Orchestrator.ps1') -Force | Out-Null
    New-Item -ItemType File -Path (Join-Path $cacheCurrent 'package\template\.orchestrator\VERSION') -Force | Out-Null
    $getSource = Get-Content -LiteralPath (Join-Path $repoRoot 'get.ps1') -Raw -Encoding UTF8
    $cacheFunctionsStart = $getSource.IndexOf('function Test-IsPackageRoot')
    $cacheFunctionsEnd = $getSource.IndexOf('# Se este script ja esta dentro', $cacheFunctionsStart)
    Assert-Test -Condition ($cacheFunctionsStart -ge 0 -and $cacheFunctionsEnd -gt $cacheFunctionsStart) -Message 'funcoes de cache nao localizadas em get.ps1'
    Invoke-Expression $getSource.Substring($cacheFunctionsStart, $cacheFunctionsEnd - $cacheFunctionsStart)

    $beforeCacheCount = [int](Get-FixtureGitValue -Repository $cacheCurrent -Arguments @('rev-list', '--count', 'HEAD'))
    $previousEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        Sync-PackageCache -CachePath $cacheCurrent -RepoName 'unused/fixture' -BranchName 'develop'
    }
    finally {
        $ErrorActionPreference = $previousEap
    }
    Assert-Test -Condition ((Get-FixtureGitValue -Repository $cacheCurrent -Arguments @('rev-parse', '--is-shallow-repository')) -eq 'false') -Message 'sync do cache criou estado shallow em clone completo'
    Assert-Test -Condition ((Get-FixtureGitValue -Repository $cacheCurrent -Arguments @('rev-list', '--count', 'HEAD')) -eq $beforeCacheCount) -Message 'sync do cache truncou historia completa'

    # Regressao principal: fetch do pacote nao pode rasar clone de trabalho completo.
    $beforeFullCount = [int](Get-FixtureGitValue -Repository $fullCurrent -Arguments @('rev-list', '--count', 'HEAD'))
    $fullSyncResult = Sync-PackageSource -PackageRoot $fullCurrent -Branch 'develop'
    $afterFullCount = [int](Get-FixtureGitValue -Repository $fullCurrent -Arguments @('rev-list', '--count', 'HEAD'))
    Assert-Test -Condition ($fullSyncResult -eq $true) -Message 'sync do clone completo retornou falha'
    Assert-Test -Condition ((Get-FixtureGitValue -Repository $fullCurrent -Arguments @('rev-parse', '--is-shallow-repository')) -eq 'false') -Message 'sync criou estado shallow em clone completo'
    Assert-Test -Condition (-not (Test-Path -LiteralPath (Join-Path $fullCurrent '.git\shallow'))) -Message 'sync criou .git/shallow em clone completo'
    Assert-Test -Condition ($afterFullCount -eq $beforeFullCount) -Message (
        'sync alterou contagem do clone completo: antes={0}, depois={1}' -f $beforeFullCount, $afterFullCount
    )

    # O merge ff-only seguinte precisa enxergar a ancestralidade e avancar o clone.
    $remoteHead = Get-FixtureGitValue -Repository $seed -Arguments @('rev-parse', 'HEAD')
    $behindSyncResult = Sync-PackageSource -PackageRoot $fullBehind -Branch 'develop'
    Assert-Test -Condition ($behindSyncResult -eq $true) -Message 'sync do clone completo atrasado retornou falha'
    Assert-Test -Condition ((Get-FixtureGitValue -Repository $fullBehind -Arguments @('rev-parse', 'HEAD')) -eq $remoteHead) -Message 'merge ff-only nao avancou clone completo ate origin/develop'
    Assert-Test -Condition ((Get-FixtureGitValue -Repository $fullBehind -Arguments @('rev-list', '--count', 'HEAD')) -eq '4') -Message 'merge ff-only perdeu ancestralidade do clone completo'

    # Clone ja raso acompanha novo tip sem unshallow/deepen implicito.
    Invoke-FixtureGit -Arguments @('-C', $seed, 'commit', '--allow-empty', '-m', 'commit 5') | Out-Null
    Invoke-FixtureGit -Arguments @('-C', $seed, 'push', 'origin', 'develop') | Out-Null
    $latestRemoteHead = Get-FixtureGitValue -Repository $seed -Arguments @('rev-parse', 'HEAD')
    $beforeShallowCount = Get-FixtureGitValue -Repository $shallowCurrent -Arguments @('rev-list', '--count', 'HEAD')
    $shallowOutput = @(Sync-PackageSource -PackageRoot $shallowCurrent -Branch 'develop' 6>&1)
    $shallowSyncResult = @($shallowOutput | Where-Object { $_ -is [bool] })[-1]
    $shallowOutputText = ($shallowOutput | ForEach-Object { $_.ToString() }) -join "`n"
    Assert-Test -Condition ($shallowSyncResult -eq $true) -Message 'sync do clone shallow retornou falha'
    Assert-Test -Condition ((Get-FixtureGitValue -Repository $shallowCurrent -Arguments @('rev-parse', '--is-shallow-repository')) -eq 'true') -Message 'sync aprofundou clone shallow sozinho'
    Assert-Test -Condition ((Get-FixtureGitValue -Repository $shallowCurrent -Arguments @('rev-list', '--count', 'HEAD')) -eq $beforeShallowCount) -Message 'sync alterou profundidade do clone shallow'
    Assert-Test -Condition ((Get-FixtureGitValue -Repository $shallowCurrent -Arguments @('rev-parse', 'HEAD')) -eq $latestRemoteHead) -Message 'sync shallow nao avancou para o novo tip remoto'
    Assert-Test -Condition ($shallowOutputText -match 'historia truncada') -Message 'sync shallow nao tornou truncamento visivel'
    Assert-Test -Condition ($shallowOutputText -match 'git fetch --unshallow origin') -Message 'sync shallow nao informou como restaurar historia completa'

    # Instalacao nova/descartavel continua economizando banda no bootstrap.
    Assert-Test -Condition ($getSource -match 'clone --depth 1 -b \$BranchName') -Message 'bootstrap deixou de clonar cache novo com --depth 1'

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
