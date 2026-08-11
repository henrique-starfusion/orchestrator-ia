#Requires -Version 5.1
<#
.SYNOPSIS
    Publica docs/ na Wiki GitHub derivada do repositorio.

.DESCRIPTION
    Gera uma pagina para cada Markdown em docs/, cria Home.md a partir de
    docs/README.md, converte links locais e sincroniza o repositorio Git da Wiki.
    Commit e push so acontecem quando o conteudo gerado muda.
#>
[CmdletBinding(DefaultParameterSetName = 'Publish')]
param(
    [string]$ProjectRoot,
    [string]$WikiRepositoryUrl = 'https://github.com/henrique-starfusion/orchestrator-ia.wiki.git',
    [string]$RepositoryUrl = 'https://github.com/henrique-starfusion/orchestrator-ia',
    [string]$RepositoryRef = 'develop',
    [string]$CommitMessage = 'docs: synchronize wiki from docs/',
    [Parameter(ParameterSetName = 'Generate')]
    [switch]$GenerateOnly,
    [Parameter(Mandatory = $true, ParameterSetName = 'Generate')]
    [string]$OutputDirectory
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$script:InlineLinkPattern = '(?<bang>!?)\[(?<label>[^\]\r\n]+)\]\((?<destination><[^>\r\n]+>|[^)\s\r\n]+)(?<title>\s+(?:"[^"\r\n]*"|''[^''\r\n]*''|\([^)]+\)))?\)'
$script:ReferenceLinkPattern = '^(?<prefix>\s*\[[^\]]+\]:\s*)(?<destination><[^>]+>|\S+)(?<suffix>.*)$'

function Get-FullNormalizedPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    return [System.IO.Path]::GetFullPath($Path).TrimEnd([System.IO.Path]::DirectorySeparatorChar)
}

function Get-RelativeUnixPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$BasePath,
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $baseFull = Get-FullNormalizedPath -Path $BasePath
    $pathFull = [System.IO.Path]::GetFullPath($Path)
    $baseUri = New-Object System.Uri(($baseFull + [System.IO.Path]::DirectorySeparatorChar))
    $pathUri = New-Object System.Uri($pathFull)
    return [System.Uri]::UnescapeDataString($baseUri.MakeRelativeUri($pathUri).ToString()).Replace('\', '/')
}

function ConvertTo-Slug {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    $decomposed = $Value.Normalize([System.Text.NormalizationForm]::FormD)
    $builder = New-Object System.Text.StringBuilder
    foreach ($character in $decomposed.ToCharArray()) {
        $category = [System.Globalization.CharUnicodeInfo]::GetUnicodeCategory($character)
        if ($category -ne [System.Globalization.UnicodeCategory]::NonSpacingMark) {
            [void]$builder.Append($character)
        }
    }
    $ascii = $builder.ToString().Normalize([System.Text.NormalizationForm]::FormC).ToLowerInvariant()
    $slug = ($ascii -replace '[^a-z0-9]+', '-').Trim('-')
    if (-not $slug) {
        throw ('Nao foi possivel gerar slug para: {0}' -f $Value)
    }
    return $slug
}

function ConvertTo-UrlPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    return (($Value.Replace('\', '/') -split '/') | ForEach-Object {
            [System.Uri]::EscapeDataString($_)
        }) -join '/'
}

function Get-WikiPageName {
    param(
        [Parameter(Mandatory = $true)]
        [string]$DocsRelativePath
    )

    $pathWithoutExtension = $DocsRelativePath.Substring(0, $DocsRelativePath.Length - 3)
    $segments = @($pathWithoutExtension -split '/')
    if ($segments.Count -eq 1) {
        if ($segments[0] -ceq 'README') {
            return 'README'
        }
        return ConvertTo-Slug -Value $segments[0]
    }
    return 'historico-{0}' -f (ConvertTo-Slug -Value ($segments -join '-'))
}

function Get-RepositoryRelativePath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root,
        [Parameter(Mandatory = $true)]
        [string]$Candidate
    )

    $rootFull = Get-FullNormalizedPath -Path $Root
    $candidateFull = [System.IO.Path]::GetFullPath($Candidate)
    $rootPrefix = $rootFull + [System.IO.Path]::DirectorySeparatorChar
    if (-not $candidateFull.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        if (-not $candidateFull.Equals($rootFull, [System.StringComparison]::OrdinalIgnoreCase)) {
            return $null
        }
    }
    return Get-RelativeUnixPath -BasePath $rootFull -Path $candidateFull
}

function Get-LinkParts {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Destination
    )

    $value = $Destination
    $wasWrapped = $value.StartsWith('<') -and $value.EndsWith('>')
    if ($wasWrapped) {
        $value = $value.Substring(1, $value.Length - 2)
    }

    $fragment = ''
    $fragmentIndex = $value.IndexOf('#')
    if ($fragmentIndex -ge 0) {
        $fragment = $value.Substring($fragmentIndex)
        $value = $value.Substring(0, $fragmentIndex)
    }

    $query = ''
    $queryIndex = $value.IndexOf('?')
    if ($queryIndex -ge 0) {
        $query = $value.Substring($queryIndex)
        $value = $value.Substring(0, $queryIndex)
    }

    return [pscustomobject]@{
        Path       = [System.Uri]::UnescapeDataString($value)
        Query      = $query
        Fragment   = $fragment
        WasWrapped = $wasWrapped
    }
}

function Resolve-LocalMarkdownLink {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Destination,
        [Parameter(Mandatory = $true)]
        [string]$SourcePath,
        [Parameter(Mandatory = $true)]
        [string]$Root,
        [Parameter(Mandatory = $true)]
        [string]$DocsRoot,
        [Parameter(Mandatory = $true)]
        [hashtable]$PageMap,
        [Parameter(Mandatory = $true)]
        [hashtable]$DirectoryMap,
        [Parameter(Mandatory = $true)]
        [string]$PublicRepositoryUrl,
        [Parameter(Mandatory = $true)]
        [string]$Ref,
        [bool]$IsImage = $false
    )

    if ($Destination -match '^[a-z][a-z0-9+.-]*:' -or $Destination.StartsWith('//') -or $Destination.StartsWith('#')) {
        return $Destination
    }

    $parts = Get-LinkParts -Destination $Destination
    if (-not $parts.Path) {
        return $Destination
    }

    $pathForWindows = $parts.Path.Replace('/', [System.IO.Path]::DirectorySeparatorChar)
    $candidates = New-Object System.Collections.Generic.List[string]
    if ($parts.Path.StartsWith('/') -or $parts.Path -match '^docs/') {
        $candidates.Add((Join-Path $Root $pathForWindows.TrimStart('/', '\')))
    }
    else {
        $sourceDirectory = Split-Path -Parent $SourcePath
        $candidates.Add((Join-Path $sourceDirectory $pathForWindows))
        $candidates.Add((Join-Path $DocsRoot $pathForWindows))
        $candidates.Add((Join-Path $Root $pathForWindows))
    }

    $seen = @{}
    foreach ($candidate in $candidates) {
        $candidateFull = [System.IO.Path]::GetFullPath($candidate)
        if ($seen.ContainsKey($candidateFull)) {
            continue
        }
        $seen[$candidateFull] = $true

        $repositoryRelative = Get-RepositoryRelativePath -Root $Root -Candidate $candidateFull
        if ($null -eq $repositoryRelative) {
            continue
        }

        if ($PageMap.ContainsKey($repositoryRelative)) {
            $pageName = [string]$PageMap[$repositoryRelative]
            return '{0}/wiki/{1}{2}{3}' -f $PublicRepositoryUrl, (ConvertTo-UrlPath -Value $pageName), $parts.Query, $parts.Fragment
        }

        if ($DirectoryMap.ContainsKey($repositoryRelative.TrimEnd('/'))) {
            return '{0}/wiki/Home#{1}' -f $PublicRepositoryUrl, $DirectoryMap[$repositoryRelative.TrimEnd('/')]
        }

        if (Test-Path -LiteralPath $candidateFull -PathType Leaf) {
            $encodedPath = ConvertTo-UrlPath -Value $repositoryRelative
            $encodedRef = ConvertTo-UrlPath -Value $Ref
            if ($IsImage -and $PublicRepositoryUrl -match '^https://github\.com/(?<owner>[^/]+)/(?<repo>[^/]+)$') {
                return 'https://raw.githubusercontent.com/{0}/{1}/{2}/{3}{4}{5}' -f $Matches.owner, $Matches.repo, $encodedRef, $encodedPath, $parts.Query, $parts.Fragment
            }
            return '{0}/blob/{1}/{2}{3}{4}' -f $PublicRepositoryUrl, $encodedRef, $encodedPath, $parts.Query, $parts.Fragment
        }

        if (Test-Path -LiteralPath $candidateFull -PathType Container) {
            return '{0}/tree/{1}/{2}{3}{4}' -f $PublicRepositoryUrl, (ConvertTo-UrlPath -Value $Ref), (ConvertTo-UrlPath -Value $repositoryRelative), $parts.Query, $parts.Fragment
        }
    }

    throw ('Link local nao resolvido em {0}: {1}' -f (Get-RelativeUnixPath -BasePath $Root -Path $SourcePath), $Destination)
}

function Convert-MarkdownContent {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Content,
        [Parameter(Mandatory = $true)]
        [string]$SourcePath,
        [Parameter(Mandatory = $true)]
        [string]$Root,
        [Parameter(Mandatory = $true)]
        [string]$DocsRoot,
        [Parameter(Mandatory = $true)]
        [hashtable]$PageMap,
        [Parameter(Mandatory = $true)]
        [hashtable]$DirectoryMap,
        [Parameter(Mandatory = $true)]
        [string]$PublicRepositoryUrl,
        [Parameter(Mandatory = $true)]
        [string]$Ref
    )

    $normalized = $Content.Replace("`r`n", "`n").Replace("`r", "`n")
    $lines = @($normalized -split "`n", -1)
    $insideFence = $false
    $inlineRegex = New-Object System.Text.RegularExpressions.Regex($script:InlineLinkPattern)
    $referenceRegex = New-Object System.Text.RegularExpressions.Regex($script:ReferenceLinkPattern)

    for ($index = 0; $index -lt $lines.Count; $index++) {
        $line = $lines[$index]
        if ($line -match '^\s*(```|~~~)') {
            $insideFence = -not $insideFence
            continue
        }
        if ($insideFence) {
            continue
        }

        $inlineEvaluator = [System.Text.RegularExpressions.MatchEvaluator]{
            param($match)
            $destination = $match.Groups['destination'].Value
            $isImage = $match.Groups['bang'].Value -eq '!'
            $converted = Resolve-LocalMarkdownLink -Destination $destination -SourcePath $SourcePath -Root $Root -DocsRoot $DocsRoot -PageMap $PageMap -DirectoryMap $DirectoryMap -PublicRepositoryUrl $PublicRepositoryUrl -Ref $Ref -IsImage $isImage
            return '{0}[{1}]({2}{3})' -f $match.Groups['bang'].Value, $match.Groups['label'].Value, $converted, $match.Groups['title'].Value
        }
        $line = $inlineRegex.Replace($line, $inlineEvaluator)

        $referenceMatch = $referenceRegex.Match($line)
        if ($referenceMatch.Success) {
            $convertedReference = Resolve-LocalMarkdownLink -Destination $referenceMatch.Groups['destination'].Value -SourcePath $SourcePath -Root $Root -DocsRoot $DocsRoot -PageMap $PageMap -DirectoryMap $DirectoryMap -PublicRepositoryUrl $PublicRepositoryUrl -Ref $Ref
            $line = '{0}{1}{2}' -f $referenceMatch.Groups['prefix'].Value, $convertedReference, $referenceMatch.Groups['suffix'].Value
        }
        $lines[$index] = $line
    }

    return (($lines -join "`n").TrimEnd("`n") + "`n")
}

function Write-Utf8NoBom {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Content
    )

    [System.IO.File]::WriteAllText($Path, $Content, $script:Utf8NoBom)
}

function New-WikiPageCatalog {
    param(
        [Parameter(Mandatory = $true)]
        [System.IO.FileInfo[]]$SourceFiles,
        [Parameter(Mandatory = $true)]
        [string]$Root,
        [Parameter(Mandatory = $true)]
        [string]$DocsRoot
    )

    $pageMap = @{}
    $entries = New-Object System.Collections.Generic.List[object]
    $pageNames = @{}
    foreach ($sourceFile in $SourceFiles) {
        $docsRelative = Get-RelativeUnixPath -BasePath $DocsRoot -Path $sourceFile.FullName
        $repositoryRelative = Get-RelativeUnixPath -BasePath $Root -Path $sourceFile.FullName
        $pageName = Get-WikiPageName -DocsRelativePath $docsRelative
        if ($pageName -ieq 'Home') {
            throw ('Nome de pagina reservado para Home: {0}' -f $repositoryRelative)
        }
        if ($pageNames.ContainsKey($pageName)) {
            throw ('Colisao de paginas Wiki: {0} e {1} -> {2}' -f $pageNames[$pageName], $repositoryRelative, $pageName)
        }
        $pageNames[$pageName] = $repositoryRelative
        $pageMap[$repositoryRelative] = $pageName
        $entries.Add([pscustomobject]@{
                SourceFile        = $sourceFile
                DocsRelativePath  = $docsRelative
                RepositoryPath    = $repositoryRelative
                PageName          = $pageName
                Historical        = $docsRelative.Contains('/')
                HistoricalSection = if ($docsRelative.Contains('/')) { ($docsRelative -split '/')[0] } else { $null }
            }) | Out-Null
    }
    return [pscustomobject]@{
        Entries = $entries.ToArray()
        PageMap = $pageMap
    }
}

function New-WikiDirectoryMap {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Entries,
        [Parameter(Mandatory = $true)]
        [string]$DocsRoot,
        [Parameter(Mandatory = $true)]
        [string]$Root
    )

    $directoryMap = @{}
    $docsRepositoryPath = Get-RelativeUnixPath -BasePath $Root -Path $DocsRoot
    $directoryMap[$docsRepositoryPath] = 'documentos-base'
    foreach ($entry in $Entries | Where-Object { $_.Historical }) {
        $segments = @($entry.DocsRelativePath -split '/')
        for ($count = 1; $count -lt $segments.Count; $count++) {
            $relativeDirectory = ($segments[0..($count - 1)] -join '/')
            $repositoryDirectory = '{0}/{1}' -f $docsRepositoryPath, $relativeDirectory
            $directoryMap[$repositoryDirectory] = 'historico-{0}' -f (ConvertTo-Slug -Value $relativeDirectory)
        }
    }
    return $directoryMap
}

function Get-GeneratedHeader {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SourcePath,
        [bool]$Historical = $false
    )

    $header = "<!-- Pagina gerada de $SourcePath. Edicoes manuais serao sobrescritas. -->`n`n"
    if ($Historical) {
        $header += "> **Material historico.** Este documento e preservado para consulta e pode nao refletir o estado atual do codigo.`n`n"
    }
    return $header
}

function New-HomeIndex {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ReadmeContent,
        [Parameter(Mandatory = $true)]
        [object[]]$Entries,
        [Parameter(Mandatory = $true)]
        [string]$PublicRepositoryUrl
    )

    $builder = New-Object System.Text.StringBuilder
    [void]$builder.Append((Get-GeneratedHeader -SourcePath 'docs/README.md'))
    [void]$builder.Append($ReadmeContent.TrimEnd("`r", "`n"))
    [void]$builder.Append("`n`n---`n`n## Paginas publicadas`n`n")
    [void]$builder.Append("A Wiki e gerada de ``docs/``; use este indice para navegar por todo o conteudo publicado.`n`n")
    [void]$builder.Append('<a id="documentos-base"></a>')
    [void]$builder.Append("`n### Documentos-base`n`n")

    foreach ($entry in $Entries | Where-Object { -not $_.Historical } | Sort-Object DocsRelativePath) {
        [void]$builder.Append(('- [{0}]({1}/wiki/{2})' -f $entry.DocsRelativePath, $PublicRepositoryUrl, (ConvertTo-UrlPath -Value $entry.PageName)))
        [void]$builder.Append("`n")
    }

    foreach ($section in @($Entries | Where-Object { $_.Historical } | Group-Object HistoricalSection | Sort-Object Name)) {
        $anchor = 'historico-{0}' -f (ConvertTo-Slug -Value $section.Name)
        [void]$builder.Append(("`n<a id=`"{0}`"></a>`n### Material historico: {1}/`n`n" -f $anchor, $section.Name))
        foreach ($entry in $section.Group | Sort-Object DocsRelativePath) {
            [void]$builder.Append(('- [{0}]({1}/wiki/{2})' -f $entry.DocsRelativePath, $PublicRepositoryUrl, (ConvertTo-UrlPath -Value $entry.PageName)))
            [void]$builder.Append("`n")
        }
    }

    return ($builder.ToString().TrimEnd("`r", "`n") + "`n")
}

function Clear-GeneratedMarkdownFiles {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Directory
    )

    $directoryFull = Get-FullNormalizedPath -Path $Directory
    Get-ChildItem -LiteralPath $directoryFull -Recurse -File -Filter '*.md' |
        Where-Object { $_.FullName -notmatch '[\\/]\.git[\\/]' } |
        ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force }
}

function Write-WikiPages {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root,
        [Parameter(Mandatory = $true)]
        [string]$Destination,
        [Parameter(Mandatory = $true)]
        [string]$PublicRepositoryUrl,
        [Parameter(Mandatory = $true)]
        [string]$Ref
    )

    $docsRoot = Join-Path $Root 'docs'
    if (-not (Test-Path -LiteralPath $docsRoot -PathType Container)) {
        throw ('Diretorio docs ausente: {0}' -f $docsRoot)
    }
    $readmePath = Join-Path $docsRoot 'README.md'
    if (-not (Test-Path -LiteralPath $readmePath -PathType Leaf)) {
        throw ('Indice docs/README.md ausente: {0}' -f $readmePath)
    }

    $sourceFiles = @(Get-ChildItem -LiteralPath $docsRoot -Recurse -File -Filter '*.md' | Sort-Object FullName)
    $catalog = New-WikiPageCatalog -SourceFiles $sourceFiles -Root $Root -DocsRoot $docsRoot
    $directoryMap = New-WikiDirectoryMap -Entries $catalog.Entries -DocsRoot $docsRoot -Root $Root

    if (-not (Test-Path -LiteralPath $Destination)) {
        New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    }
    Clear-GeneratedMarkdownFiles -Directory $Destination

    $convertedReadme = $null
    foreach ($entry in $catalog.Entries) {
        $sourceContent = [System.IO.File]::ReadAllText($entry.SourceFile.FullName)
        $converted = Convert-MarkdownContent -Content $sourceContent -SourcePath $entry.SourceFile.FullName -Root $Root -DocsRoot $docsRoot -PageMap $catalog.PageMap -DirectoryMap $directoryMap -PublicRepositoryUrl $PublicRepositoryUrl -Ref $Ref
        $pageContent = (Get-GeneratedHeader -SourcePath $entry.RepositoryPath -Historical $entry.Historical) + $converted
        Write-Utf8NoBom -Path (Join-Path $Destination ($entry.PageName + '.md')) -Content $pageContent
        if ($entry.RepositoryPath -ieq 'docs/README.md') {
            $convertedReadme = $converted
        }
    }

    if ($null -eq $convertedReadme) {
        throw 'docs/README.md nao entrou no catalogo da Wiki'
    }
    $homeContent = New-HomeIndex -ReadmeContent $convertedReadme -Entries $catalog.Entries -PublicRepositoryUrl $PublicRepositoryUrl
    Write-Utf8NoBom -Path (Join-Path $Destination 'Home.md') -Content $homeContent

    return [pscustomobject]@{
        SourceCount = $catalog.Entries.Count
        PageCount   = $catalog.Entries.Count + 1
    }
}

function Invoke-GitCommand {
    param(
        [string]$Repository,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [int[]]$AllowedExitCodes = @(0),
        [string]$SensitiveValue
    )

    $git = Get-Command git -ErrorAction Stop
    $commandArguments = @()
    if ($Repository) {
        $commandArguments += @('-C', $Repository)
    }
    $commandArguments += $Arguments

    $previousEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = @(& $git.Source @commandArguments 2>&1)
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousEap
    }

    $text = ($output | ForEach-Object { $_.ToString() }) -join "`n"
    if ($SensitiveValue) {
        $text = $text.Replace($SensitiveValue, '<wiki-repository>')
    }
    if ($AllowedExitCodes -notcontains $exitCode) {
        throw ('git {0} falhou com exit={1}: {2}' -f ($Arguments -join ' '), $exitCode, $text.Trim())
    }
    return [pscustomobject]@{
        ExitCode = $exitCode
        Output   = $text.Trim()
    }
}

if (-not $ProjectRoot) {
    $ProjectRoot = Join-Path $PSScriptRoot '..'
}
$ProjectRoot = Get-FullNormalizedPath -Path $ProjectRoot
$RepositoryUrl = $RepositoryUrl.TrimEnd('/') -replace '\.git$', ''
if ($RepositoryUrl -notmatch '^https://github\.com/[^/]+/[^/]+$') {
    throw ('RepositoryUrl deve ser URL publica GitHub no formato https://github.com/owner/repo: {0}' -f $RepositoryUrl)
}
if (-not $RepositoryRef.Trim()) {
    throw 'RepositoryRef nao pode ser vazio'
}

if ($GenerateOnly) {
    $destinationFull = [System.IO.Path]::GetFullPath($OutputDirectory)
    $docsFull = Get-FullNormalizedPath -Path (Join-Path $ProjectRoot 'docs')
    if ($destinationFull.Equals($ProjectRoot, [System.StringComparison]::OrdinalIgnoreCase) -or
        $destinationFull.Equals($docsFull, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'OutputDirectory nao pode ser a raiz do projeto nem docs/'
    }
    $result = Write-WikiPages -Root $ProjectRoot -Destination $destinationFull -PublicRepositoryUrl $RepositoryUrl -Ref $RepositoryRef
    Write-Host ('Wiki gerada: {0} documentos-fonte, {1} paginas em {2}' -f $result.SourceCount, $result.PageCount, $destinationFull)
    return
}

$tempParent = Get-FullNormalizedPath -Path ([System.IO.Path]::GetTempPath())
$tempRoot = Join-Path $tempParent ('orchestrator-wiki-{0}' -f [guid]::NewGuid().ToString('N'))
$wikiRoot = Join-Path $tempRoot 'wiki'
New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null

try {
    Write-Host 'Clonando repositorio temporario da Wiki...'
    [void](Invoke-GitCommand -Arguments @('clone', '--quiet', '--', $WikiRepositoryUrl, $wikiRoot) -SensitiveValue $WikiRepositoryUrl)

    $result = Write-WikiPages -Root $ProjectRoot -Destination $wikiRoot -PublicRepositoryUrl $RepositoryUrl -Ref $RepositoryRef
    [void](Invoke-GitCommand -Repository $wikiRoot -Arguments @('add', '--all', '--', '.'))
    $stagedDiff = Invoke-GitCommand -Repository $wikiRoot -Arguments @('diff', '--cached', '--quiet') -AllowedExitCodes @(0, 1)
    if ($stagedDiff.ExitCode -eq 0) {
        Write-Host ('Wiki ja sincronizada: {0} documentos-fonte, {1} paginas. Nenhum commit criado.' -f $result.SourceCount, $result.PageCount)
        return
    }

    [void](Invoke-GitCommand -Repository $wikiRoot -Arguments @('commit', '--quiet', '-m', $CommitMessage))
    [void](Invoke-GitCommand -Repository $wikiRoot -Arguments @('push', '--quiet', 'origin', 'HEAD'))
    $commit = Invoke-GitCommand -Repository $wikiRoot -Arguments @('rev-parse', '--short', 'HEAD')
    Write-Host ('Wiki publicada: commit {0}, {1} documentos-fonte, {2} paginas.' -f $commit.Output, $result.SourceCount, $result.PageCount)
}
finally {
    $resolvedTemp = [System.IO.Path]::GetFullPath($tempRoot)
    $expectedPrefix = $tempParent + [System.IO.Path]::DirectorySeparatorChar + 'orchestrator-wiki-'
    if ($resolvedTemp.StartsWith($expectedPrefix, [System.StringComparison]::OrdinalIgnoreCase) -and
        (Test-Path -LiteralPath $resolvedTemp)) {
        Remove-Item -LiteralPath $resolvedTemp -Recurse -Force -ErrorAction SilentlyContinue
    }
}
