#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$ProjectPath,
    [string]$PackageRoot,
    [switch]$Force,
    [switch]$AllAdapters
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Orchestrator.Common.ps1')

$projectRoot = Get-ProjectRoot -ProjectPath $ProjectPath
$packageRootResolved = Get-PackageRoot -PackageRoot $PackageRoot
$vendorMap = Get-AdapterVendorMap
$adapterRoot = Join-Path $packageRootResolved 'package\template\adapters'

$vendorsToCopy = New-Object System.Collections.Generic.List[string]

if ($AllAdapters) {
    if (Test-Path -LiteralPath $adapterRoot) {
        Get-ChildItem -LiteralPath $adapterRoot -Directory -Force | ForEach-Object {
            $vendorsToCopy.Add($_.Name) | Out-Null
        }
    }
}
else {
    $detectedPath = Join-Path (Get-OrchestratorRoot -ProjectPath $projectRoot) 'agents\detected.json'
    if (Test-Path -LiteralPath $detectedPath) {
        $detected = Get-JsonFileContent -Path $detectedPath
        foreach ($agent in $detected.agents) {
            if ($agent.status -ne 'available') { continue }
            if ($vendorMap.ContainsKey($agent.name)) {
                $vendor = $vendorMap[$agent.name]
                if (-not $vendorsToCopy.Contains($vendor)) {
                    $vendorsToCopy.Add($vendor) | Out-Null
                }
            }
        }
    }
}

$copied = 0
$skipped = 0

foreach ($vendor in $vendorsToCopy) {
    $sourceDir = Join-Path $adapterRoot $vendor
    if (-not (Test-Path -LiteralPath $sourceDir)) {
        Write-Host "[AVISO] Adapter template ausente: $vendor"
        continue
    }

    Get-ChildItem -LiteralPath $sourceDir -Recurse -File -Force | ForEach-Object {
        $relative = $_.FullName.Substring($sourceDir.Length).TrimStart('\', '/')

        if ($_.Name -like '*.section.md') {
            # convencao: X.section.md -> anexa em X.md na raiz do projeto, se o marcador (1a linha) nao existir.
            # Qualificador opcional para varias secoes no mesmo alvo: X.<vendor>.section.md -> X.md
            $targetName = $_.Name -replace '(\.[A-Za-z0-9_-]+)?\.section\.md$', '.md'
            $destPath = Join-Path $projectRoot $targetName
            # -Encoding UTF8 obrigatorio na LEITURA: sem isso o PS 5.1 decodifica
            # os bytes UTF-8 como ANSI (CP1252) e o Add-Content -Encoding UTF8
            # re-encoda o resultado, gravando dupla codificacao (documentacao ->
            # documentaAAo). Medido em 2026-07-26: 65 sequencias corrompidas por
            # arquivo em 9 projetos da frota.
            $sectionContent = Get-Content -LiteralPath $_.FullName -Raw -Encoding UTF8
            $marker = ($sectionContent -split "`r?`n")[0].Trim()

            if (Test-Path -LiteralPath $destPath) {
                $existing = Get-Content -LiteralPath $destPath -Raw -Encoding UTF8
                if ($existing.Contains($marker)) {
                    # Marcador presente: SINCRONIZA o bloco em vez de pular.
                    # Sem isto, toda atualizacao do texto (ex.: loops de execucao
                    # em 0.4.27) ficava presa no template e nunca chegava aos
                    # projetos ja instalados.
                    $start = $existing.IndexOf($marker)
                    $head = $existing.Substring(0, $start)
                    $rest = $existing.Substring($start + $marker.Length)
                    $nextRel = $rest.IndexOf('<!-- orchestrator:')
                    $tail = ''
                    if ($nextRel -ge 0) { $tail = $rest.Substring($nextRel) }
                    $rebuilt = $head + $sectionContent.TrimEnd()
                    if ($tail) { $rebuilt = $rebuilt + "`r`n`r`n" + $tail }
                    else { $rebuilt = $rebuilt + "`r`n" }
                    if ($rebuilt -eq $existing) {
                        $skipped++
                        return
                    }
                    Set-Content -LiteralPath $destPath -Value $rebuilt -Encoding UTF8 -NoNewline
                    $copied++
                    return
                }
                Add-Content -LiteralPath $destPath -Value ("`r`n" + $sectionContent) -Encoding UTF8
            }
            else {
                Set-Content -LiteralPath $destPath -Value $sectionContent -Encoding UTF8
            }
            $copied++
            return
        }

        $destPath = Join-Path $projectRoot $relative

        if ((Test-Path -LiteralPath $destPath) -and -not $Force) {
            $skipped++
            return
        }

        $parent = Split-Path -Parent $destPath
        if (-not [string]::IsNullOrWhiteSpace($parent)) {
            Ensure-Directory -Path $parent | Out-Null
        }

        Copy-Item -LiteralPath $_.FullName -Destination $destPath -Force:(-not (Test-Path -LiteralPath $destPath) -or $Force)
        $copied++
    }
}

Write-Host "[OK] Generate-Adapters: $copied copiados, $skipped ignorados."
exit 0
