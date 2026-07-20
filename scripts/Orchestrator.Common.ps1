#Requires -Version 5.1
<#
.SYNOPSIS
    Shared helpers for orchestrator installer scripts (PowerShell 5.1 compatible).
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-PackageRoot {
    param(
        [string]$PackageRoot
    )

    if (-not [string]::IsNullOrWhiteSpace($PackageRoot)) {
        return (Resolve-Path -LiteralPath $PackageRoot).Path
    }

    $scriptsRoot = $PSScriptRoot
    if ([string]::IsNullOrWhiteSpace($scriptsRoot)) {
        throw 'Unable to determine package root: PSScriptRoot is empty.'
    }

    return (Resolve-Path -LiteralPath (Join-Path $scriptsRoot '..')).Path
}

function Get-ProjectRoot {
    param(
        [string]$ProjectPath
    )

    if (-not [string]::IsNullOrWhiteSpace($ProjectPath)) {
        return (Resolve-Path -LiteralPath $ProjectPath).Path
    }

    return (Get-Location).Path
}

function Get-OrchestratorRoot {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectPath
    )

    return (Join-Path (Get-ProjectRoot -ProjectPath $ProjectPath) '.orchestrator')
}

function Read-PackageVersion {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PackageRoot
    )

    $versionFile = Join-Path $PackageRoot 'VERSION'
    if (-not (Test-Path -LiteralPath $versionFile)) {
        $versionFile = Join-Path $PackageRoot 'package\template\.orchestrator\VERSION'
    }

    if (-not (Test-Path -LiteralPath $versionFile)) {
        return $null
    }

    return ((Get-Content -LiteralPath $versionFile -Raw -Encoding UTF8).Trim())
}

function Read-WorkspaceVersion {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectPath
    )

    $versionFile = Join-Path (Get-OrchestratorRoot -ProjectPath $ProjectPath) 'VERSION'
    if (-not (Test-Path -LiteralPath $versionFile)) {
        return $null
    }

    return ((Get-Content -LiteralPath $versionFile -Raw -Encoding UTF8).Trim())
}

function Compare-SemVer {
    param(
        [AllowNull()]
        [string]$Left,
        [AllowNull()]
        [string]$Right
    )

    if ([string]::IsNullOrWhiteSpace($Left) -or [string]::IsNullOrWhiteSpace($Right)) {
        return 'invalid'
    }

    $parseLeft = $null
    $parseRight = $null
    $leftOk = [System.Version]::TryParse($Left.Trim(), [ref]$parseLeft)
    $rightOk = [System.Version]::TryParse($Right.Trim(), [ref]$parseRight)

    if (-not $leftOk -or -not $rightOk) {
        if ($Left.Trim() -eq $Right.Trim()) { return 'equal' }
        return 'invalid'
    }

    if ($parseLeft -eq $parseRight) { return 'equal' }
    if ($parseLeft -lt $parseRight) { return 'older' }
    return 'newer'
}

function Ensure-Directory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        $null = New-Item -ItemType Directory -Force -Path $Path
    }

    return (Resolve-Path -LiteralPath $Path).Path
}

function Get-FileSha256 {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }

    $hash = Get-FileHash -LiteralPath $Path -Algorithm SHA256
    return $hash.Hash.ToLowerInvariant()
}

function Write-OrchestratorLog {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectPath,
        [Parameter(Mandatory = $true)]
        [string]$Message,
        [string]$Level = 'INFO',
        [string]$LogFile
    )

    $validationsDir = Join-Path (Get-OrchestratorRoot -ProjectPath $ProjectPath) 'runtime\validations'
    Ensure-Directory -Path $validationsDir | Out-Null

    if ([string]::IsNullOrWhiteSpace($LogFile)) {
        $timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        $LogFile = Join-Path $validationsDir ("orchestrator-{0}-{1}.log" -f $timestamp, (Get-Random -Minimum 1000 -Maximum 9999))
    }

    $line = '[{0}] [{1}] {2}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Level, $Message
    Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
    return $LogFile
}

function Get-InstallationLockPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectPath
    )

    return (Join-Path (Get-OrchestratorRoot -ProjectPath $ProjectPath) 'runtime\install.lock')
}

function New-InstallationLock {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectPath
    )

    $runtimeDir = Join-Path (Get-OrchestratorRoot -ProjectPath $ProjectPath) 'runtime'
    Ensure-Directory -Path $runtimeDir | Out-Null

    $lockPath = Get-InstallationLockPath -ProjectPath $ProjectPath
    if (Test-Path -LiteralPath $lockPath) {
        throw ('Installation lock already exists: {0}' -f $lockPath)
    }

    $lockBody = @{
        pid        = $PID
        started_at = (Get-Date).ToString('o')
        host       = $env:COMPUTERNAME
    } | ConvertTo-Json -Compress

    Set-Content -LiteralPath $lockPath -Value $lockBody -Encoding UTF8
    return $lockPath
}

function Remove-InstallationLock {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectPath
    )

    $lockPath = Get-InstallationLockPath -ProjectPath $ProjectPath
    if (Test-Path -LiteralPath $lockPath) {
        Remove-Item -LiteralPath $lockPath -Force
    }
}

function Test-InstallationLockAvailable {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectPath
    )

    $lockPath = Get-InstallationLockPath -ProjectPath $ProjectPath
    return (-not (Test-Path -LiteralPath $lockPath))
}

function Import-Manifest {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PackageRoot
    )

    $manifestPath = Join-Path $PackageRoot 'package\manifest.json'
    if (-not (Test-Path -LiteralPath $manifestPath)) {
        throw ('Manifest not found: {0}' -f $manifestPath)
    }

    $raw = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8
    return ($raw | ConvertFrom-Json)
}

function Get-ManagedChecksumRecord {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PackageRoot,
        [Parameter(Mandatory = $true)]
        [string]$RelativePath
    )

    $checksumPath = Join-Path $PackageRoot 'package\checksums.json'
    if (-not (Test-Path -LiteralPath $checksumPath)) {
        return $null
    }

    $checksums = Get-Content -LiteralPath $checksumPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($null -eq $checksums.files) {
        return $null
    }

    $normalized = $RelativePath -replace '\\', '/'
    foreach ($entry in $checksums.files) {
        if ($entry.path -eq $normalized) {
            return $entry
        }
    }

    return $null
}

function Copy-ManagedFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SourcePath,
        [Parameter(Mandatory = $true)]
        [string]$DestinationPath,
        [ValidateSet('managed', 'merge', 'user-owned', 'generated', 'runtime')]
        [string]$Mode = 'managed',
        [switch]$Force,
        [switch]$DryRun
    )

    $destExists = Test-Path -LiteralPath $DestinationPath

    switch ($Mode) {
        'user-owned' {
            if ($destExists) {
                return @{ action = 'skipped_user_owned'; copied = $false }
            }
        }
        'merge' {
            if ($destExists) {
                return @{ action = 'skipped_merge'; copied = $false }
            }
        }
        'generated' {
            if ($destExists -and -not $Force.IsPresent) {
                return @{ action = 'skipped_generated'; copied = $false }
            }
        }
        'runtime' {
            if ($destExists -and -not $Force.IsPresent) {
                return @{ action = 'skipped_runtime'; copied = $false }
            }
        }
        'managed' {
            if ($destExists -and -not $Force.IsPresent) {
                return @{ action = 'skipped_managed_exists'; copied = $false }
            }
        }
    }

    if (-not (Test-Path -LiteralPath $SourcePath)) {
        throw ('Source file not found: {0}' -f $SourcePath)
    }

    $destParent = Split-Path -Parent $DestinationPath
    if (-not [string]::IsNullOrWhiteSpace($destParent)) {
        Ensure-Directory -Path $destParent | Out-Null
    }

    if ($DryRun.IsPresent) {
        return @{ action = 'dry_run_copy'; copied = $false; source = $SourcePath; destination = $DestinationPath }
    }

    Copy-Item -LiteralPath $SourcePath -Destination $DestinationPath -Force
    return @{ action = 'copied'; copied = $true; source = $SourcePath; destination = $DestinationPath }
}

function Apply-Manifest {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectPath,
        [Parameter(Mandatory = $true)]
        [string]$PackageRoot,
        [switch]$Force,
        [switch]$DryRun
    )

    $manifest = Import-Manifest -PackageRoot $PackageRoot
    $projectRoot = Get-ProjectRoot -ProjectPath $ProjectPath
    $results = New-Object System.Collections.Generic.List[object]

    foreach ($entry in $manifest.files) {
        $sourceRelative = $entry.source
        $destRelative = $entry.destination
        $mode = $entry.mode

        $sourcePath = Join-Path $PackageRoot ('package\' + ($sourceRelative -replace '/', '\'))
        $destPath = Join-Path $projectRoot ($destRelative -replace '/', '\')

        if (-not (Test-Path -LiteralPath $sourcePath)) {
            throw ('Manifest source missing: {0}' -f $sourcePath)
        }

        $shouldCopy = $true
        $destExists = Test-Path -LiteralPath $destPath

        if ($mode -eq 'user-owned' -and $destExists) {
            $shouldCopy = $false
        }
        elseif ($mode -eq 'merge' -and $destExists) {
            $shouldCopy = $false
        }
        elseif ($mode -eq 'managed' -and $destExists -and -not $Force.IsPresent) {
            $shouldCopy = $false
        }
        elseif (($mode -eq 'generated' -or $mode -eq 'runtime') -and $destExists -and -not $Force.IsPresent) {
            $shouldCopy = $false
        }

        if (-not $shouldCopy) {
            $results.Add([pscustomobject]@{
                    destination = $destRelative
                    mode        = $mode
                    action      = 'skipped'
                }) | Out-Null
            continue
        }

        $copyParams = @{
            SourcePath      = $sourcePath
            DestinationPath = $destPath
            Mode            = [string]$mode
        }
        if ($Force.IsPresent) { $copyParams.Force = $true }
        if ($DryRun.IsPresent) { $copyParams.DryRun = $true }
        try {
            $copyResult = Copy-ManagedFile @copyParams
        }
        catch {
            throw ('Copy failed for {0}: {1}' -f $destRelative, $_.Exception.Message)
        }
        $results.Add([pscustomobject]@{
                destination = $destRelative
                mode        = $mode
                action      = $copyResult.action
                copied      = $copyResult.copied
            }) | Out-Null
    }

    return $results.ToArray()
}

function Copy-TemplateTree {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectPath,
        [Parameter(Mandatory = $true)]
        [string]$PackageRoot,
        [switch]$Force,
        [switch]$DryRun
    )

    $sourceRoot = Join-Path $PackageRoot 'package\template\.orchestrator'
    $destRoot = Get-OrchestratorRoot -ProjectPath $ProjectPath

    if (-not (Test-Path -LiteralPath $sourceRoot)) {
        throw ('Template root not found: {0}' -f $sourceRoot)
    }

    Ensure-Directory -Path $destRoot | Out-Null
    $copied = 0
    $skipped = 0

    Get-ChildItem -LiteralPath $sourceRoot -Recurse -File -Force | ForEach-Object {
        $relative = $_.FullName.Substring($sourceRoot.Length).TrimStart('\', '/')
        $destPath = Join-Path $destRoot $relative
        $destExists = Test-Path -LiteralPath $destPath

        if ($destExists -and -not $Force.IsPresent) {
            $skipped++
            return
        }

        if ($DryRun.IsPresent) {
            $copied++
            return
        }

        $parent = Split-Path -Parent $destPath
        if (-not [string]::IsNullOrWhiteSpace($parent)) {
            Ensure-Directory -Path $parent | Out-Null
        }

        Copy-Item -LiteralPath $_.FullName -Destination $destPath -Force
        $copied++
    }

    return @{ copied = $copied; skipped = $skipped }
}

function Test-ShouldExcludeFromOrchestratorBackup {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RelativePath
    )

    $normalized = ($RelativePath -replace '\\', '/').TrimStart([char]'/', [char]'\')
    if ($normalized -eq 'backups' -or $normalized.StartsWith('backups/', [System.StringComparison]::Ordinal)) {
        return $true
    }

    return $false
}

function Copy-BackupTree {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SourceRoot,
        [Parameter(Mandatory = $true)]
        [string]$DestinationRoot,
        [Parameter(Mandatory = $true)]
        [string]$RootRelative
    )

    $excludeBackups = ($RootRelative -replace '\\', '/') -eq '.orchestrator'

    Get-ChildItem -LiteralPath $SourceRoot -Recurse -Force | ForEach-Object {
        $relative = $_.FullName.Substring($SourceRoot.Length).TrimStart('\', '/')
        if ($excludeBackups -and (Test-ShouldExcludeFromOrchestratorBackup -RelativePath $relative)) {
            return
        }

        $destPath = Join-Path $DestinationRoot $relative
        if ($_.PSIsContainer) {
            Ensure-Directory -Path $destPath | Out-Null
            return
        }

        $parent = Split-Path -Parent $destPath
        if (-not [string]::IsNullOrWhiteSpace($parent)) {
            Ensure-Directory -Path $parent | Out-Null
        }

        Copy-Item -LiteralPath $_.FullName -Destination $destPath -Force
    }
}

function New-BackupBundle {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectPath,
        [Parameter(Mandatory = $true)]
        [string[]]$Paths,
        [string]$Label = 'manual'
    )

    $orchestratorRoot = Get-OrchestratorRoot -ProjectPath $ProjectPath
    $timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $backupRoot = Join-Path $orchestratorRoot ("backups\{0}-{1}" -f $timestamp, $Label)
    Ensure-Directory -Path $backupRoot | Out-Null

    $projectRoot = Get-ProjectRoot -ProjectPath $ProjectPath
    $manifestEntries = New-Object System.Collections.Generic.List[object]

    foreach ($relative in $Paths) {
        $normalized = $relative -replace '/', '\'
        $sourcePath = Join-Path $projectRoot $normalized
        if (-not (Test-Path -LiteralPath $sourcePath)) {
            continue
        }

        $destPath = Join-Path $backupRoot $normalized
        $parent = Split-Path -Parent $destPath
        if (-not [string]::IsNullOrWhiteSpace($parent)) {
            Ensure-Directory -Path $parent | Out-Null
        }

        $rootRelative = ($relative -replace '\\', '/').TrimEnd([char]'/')
        $sha256 = $null
        $itemType = 'file'

        if (Test-Path -LiteralPath $sourcePath -PathType Container) {
            $itemType = 'directory'
            Ensure-Directory -Path $destPath | Out-Null
            Copy-BackupTree -SourceRoot $sourcePath -DestinationRoot $destPath -RootRelative $rootRelative
        }
        else {
            Copy-Item -LiteralPath $sourcePath -Destination $destPath -Force
            $sha256 = Get-FileSha256 -Path $sourcePath
        }

        $manifestEntries.Add([pscustomobject]@{
                path         = ($relative -replace '\\', '/')
                item_type    = $itemType
                sha256       = $sha256
                backed_up_at = (Get-Date).ToString('o')
            }) | Out-Null
    }

    $manifest = @{
        label      = $Label
        created_at = (Get-Date).ToString('o')
        project    = $projectRoot
        entries    = $manifestEntries.ToArray()
    }

    $manifestPath = Join-Path $backupRoot 'manifest.json'
    Set-Content -LiteralPath $manifestPath -Value ($manifest | ConvertTo-Json -Depth 6) -Encoding UTF8
    return $backupRoot
}

function Test-PackageIntegrity {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PackageRoot
    )

    $errors = New-Object System.Collections.Generic.List[string]

    $manifestPath = Join-Path $PackageRoot 'package\manifest.json'
    if (-not (Test-Path -LiteralPath $manifestPath)) {
        $errors.Add('Missing package/manifest.json') | Out-Null
    }

    $templateRoot = Join-Path $PackageRoot 'package\template\.orchestrator'
    if (-not (Test-Path -LiteralPath $templateRoot)) {
        $errors.Add('Missing package/template/.orchestrator') | Out-Null
    }

    if ($errors.Count -eq 0) {
        try {
            $manifest = Import-Manifest -PackageRoot $PackageRoot
            foreach ($entry in $manifest.files) {
                $sourcePath = Join-Path $PackageRoot ('package\' + ($entry.source -replace '/', '\'))
                if (-not (Test-Path -LiteralPath $sourcePath)) {
                    $errors.Add(('Manifest source missing: {0}' -f $entry.source)) | Out-Null
                }
            }
        }
        catch {
            $errors.Add(('Manifest parse error: {0}' -f $_.Exception.Message)) | Out-Null
        }
    }

    return @{
        ok     = ($errors.Count -eq 0)
        errors = @($errors)
    }
}

# Agentes classe IDE (Electron GUI): exec-probe boota a interface em vez de responder (bug-001).
# Presenca via Get-Command basta; nunca executar --version/--help nesses binarios.
$script:IdeAgents = @('cursor', 'kiro')

function Test-IsIdeAgent {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )
    return ($script:IdeAgents -contains $Name.ToLowerInvariant())
}

function Resolve-CommandExecutable {
    <#
    .SYNOPSIS
        Prefere shims .cmd/.exe no Windows (evita openwolf.ps1 que trava via Process.Start).
        Tambem procura em ~/.local/bin e npm global quando o PATH da sessao esta incompleto.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $all = @(Get-Command $Name -All -ErrorAction SilentlyContinue)

    if ($all.Count -eq 0) {
        $candidates = @(
            (Join-Path $env:USERPROFILE ".local\bin\$Name.exe"),
            (Join-Path $env:USERPROFILE ".local\bin\$Name.cmd"),
            (Join-Path $env:USERPROFILE ".local\bin\$Name"),
            (Join-Path $env:APPDATA "npm\$Name.cmd"),
            (Join-Path $env:APPDATA "npm\$Name.exe"),
            (Join-Path $env:APPDATA "npm\$Name.ps1")
        )
        foreach ($c in $candidates) {
            if (Test-Path -LiteralPath $c) {
                return [pscustomobject]@{
                    Name   = $Name
                    Source = $c
                }
            }
        }
        return $null
    }

    $preferred = $all | Where-Object {
        $ext = [IO.Path]::GetExtension($_.Source).ToLowerInvariant()
        $ext -in @('.cmd', '.exe', '.bat')
    } | Select-Object -First 1

    if ($preferred) { return $preferred }

    # Evita .ps1 como primeira escolha
    $nonPs1 = $all | Where-Object {
        [IO.Path]::GetExtension($_.Source).ToLowerInvariant() -ne '.ps1'
    } | Select-Object -First 1

    if ($nonPs1) { return $nonPs1 }
    return $all[0]
}

function Invoke-ExternalCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        $ArgumentList = @(),
        [int]$TimeoutSeconds = 30,
        [string]$WorkingDirectory
    )

    # Normaliza argumentos (string unica ou array)
    $argArray = @()
    if ($ArgumentList -is [System.Array]) {
        $argArray = @($ArgumentList | ForEach-Object { [string]$_ })
    }
    elseif (-not [string]::IsNullOrWhiteSpace([string]$ArgumentList)) {
        $argArray = @([string]$ArgumentList)
    }

    function Quote-Arg([string]$Value) {
        if ($Value -match '[\s"]') {
            return '"' + ($Value -replace '"', '\"') + '"'
        }
        return $Value
    }

    $fileName = $FilePath
    $argsFinal = $argArray

    # Shims npm (.ps1/.cmd) nao sao PE — executar via host adequado
    $ext = [IO.Path]::GetExtension($FilePath).ToLowerInvariant()
    if ($ext -eq '.ps1') {
        $psHost = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
        if (-not (Test-Path -LiteralPath $psHost)) {
            $psCmd = Get-Command powershell.exe -ErrorAction SilentlyContinue
            if ($psCmd) { $psHost = $psCmd.Source }
        }
        $fileName = $psHost
        $argsFinal = @('-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', $FilePath) + $argArray
    }
    elseif ($ext -eq '.cmd' -or $ext -eq '.bat') {
        $fileName = Join-Path $env:SystemRoot 'System32\cmd.exe'
        $tail = (@(Quote-Arg $FilePath) + ($argArray | ForEach-Object { Quote-Arg $_ })) -join ' '
        $argsFinal = @('/d', '/c', $tail)
    }

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $fileName
    $psi.Arguments = (($argsFinal | ForEach-Object { Quote-Arg ([string]$_) }) -join ' ')
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true

    if (-not [string]::IsNullOrWhiteSpace($WorkingDirectory)) {
        $psi.WorkingDirectory = $WorkingDirectory
    }

    try {
        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $psi
        $null = $process.Start()
    }
    catch {
        return @{
            timed_out = $false
            exit_code = 1
            stdout    = ''
            stderr    = $_.Exception.Message
        }
    }

    $completed = $process.WaitForExit($TimeoutSeconds * 1000)

    if (-not $completed) {
        try { $process.Kill() } catch { }
        return @{
            timed_out = $true
            exit_code = -1
            stdout    = ''
            stderr    = 'Process timed out'
        }
    }

    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()

    return @{
        timed_out = $false
        exit_code = $process.ExitCode
        stdout    = $stdout
        stderr    = $stderr
    }
}

function Get-JsonFileContent {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }

    $raw = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
    return ($raw | ConvertFrom-Json)
}

function Write-JsonFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        $Object,
        [int]$Depth = 8
    )

    $parent = Split-Path -Parent $Path
    if (-not [string]::IsNullOrWhiteSpace($parent)) {
        Ensure-Directory -Path $parent | Out-Null
    }

    Set-Content -LiteralPath $Path -Value ($Object | ConvertTo-Json -Depth $Depth) -Encoding UTF8
}

function Get-AgentNpmPackageMap {
    return @{
        'claude'          = '@anthropic-ai/claude-code'
        'codex'           = '@openai/codex'
        'gemini'          = '@google/gemini-cli'
        'opencode'        = 'opencode-ai'
        'qwen'            = '@qwen-code/qwen-code'
        'qwen-code'       = '@qwen-code/qwen-code'
        'copilot'         = '@github/copilot'
        'github-copilot'  = '@github/copilot'
        'aider'           = 'aider'
        'continue'        = '@continuedev/cli'
    }
}

function Get-AdapterVendorMap {
    return @{
        'claude'     = 'claude'
        'codex'      = 'codex'
        'gemini'     = 'gemini'
        'kimi'       = 'kimi'
        'kimi-code'  = 'kimi'
        'cursor'     = 'cursor'
        'opencode'   = 'opencode'
    }
}

function Guess-InstallationMethod {
    param(
        [Parameter(Mandatory = $true)]
        [string]$CommandPath
    )

    $normalized = $CommandPath.ToLowerInvariant()

    if ($normalized -match '\\appdata\\roaming\\npm\\') { return 'npm' }
    if ($normalized -match '\\node_modules\\') { return 'npm' }
    if ($normalized -match '\\scoop\\') { return 'scoop' }
    if ($normalized -match '\\chocolatey\\') { return 'chocolatey' }
    if ($normalized -match '\\program files\\') { return 'program_files' }
    if ($normalized -match '\\.cargo\\bin\\') { return 'cargo' }
    if ($normalized -match '\\pipx\\') { return 'pipx' }
    if ($normalized -match '\\winget\\') { return 'winget' }

    return 'unknown'
}

function Sync-WorkspaceVersion {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectPath,
        [Parameter(Mandatory = $true)]
        [string]$Version,
        [switch]$DryRun
    )

    $versionPath = Join-Path (Get-OrchestratorRoot -ProjectPath $ProjectPath) 'VERSION'
    if ($DryRun.IsPresent) {
        return $versionPath
    }

    Set-Content -LiteralPath $versionPath -Value $Version -Encoding UTF8
    return $versionPath
}

function Sync-PackageSource {
    <#
    .SYNOPSIS
        Atualiza o pacote local quando PackageRoot for um clone git (cache ou repo).
        Nunca aborta o update do workspace — falhas viram aviso.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$PackageRoot,
        [string]$Branch = 'develop',
        [switch]$DryRun
    )

    $gitDir = Join-Path $PackageRoot '.git'
    if (-not (Test-Path -LiteralPath $gitDir)) {
        Write-Host '[INFO] Pacote sem .git; sync remoto ignorado.'
        return $false
    }

    $git = Get-Command git -ErrorAction SilentlyContinue
    if (-not $git) {
        Write-Host '[AVISO] git nao encontrado; sync do pacote ignorado.'
        return $false
    }

    Write-Host ("[INFO] Sincronizando pacote git ({0})..." -f $Branch)
    if ($DryRun.IsPresent) {
        Write-Host ('[DRY-RUN] git -C {0} fetch/pull {1}' -f $PackageRoot, $Branch)
        return $true
    }

    $previousEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $null = & $git.Source -C $PackageRoot fetch --depth 1 origin $Branch 2>&1
        $fetchCode = $LASTEXITCODE
        if ($fetchCode -eq 0) {
            $null = & $git.Source -C $PackageRoot merge --ff-only "origin/$Branch" 2>&1
            if ($LASTEXITCODE -ne 0) {
                $null = & $git.Source -C $PackageRoot pull --ff-only origin $Branch 2>&1
            }
        }
        else {
            $null = & $git.Source -C $PackageRoot pull --ff-only 2>&1
        }

        if ($LASTEXITCODE -ne 0) {
            Write-Host '[AVISO] Nao foi possivel atualizar o pacote via git; continuando com a copia local.'
            return $false
        }

        Write-Host '[OK] Pacote sincronizado.'
        return $true
    }
    catch {
        Write-Host ("[AVISO] Sync do pacote ignorado: {0}" -f $_.Exception.Message)
        return $false
    }
    finally {
        $ErrorActionPreference = $previousEap
    }
}
