#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$testsRoot = $PSScriptRoot
$testScripts = @(Get-ChildItem -LiteralPath $testsRoot -Filter 'Test-*.ps1' -File |
    Where-Object { $_.Name -ne 'Test-Helpers.ps1' } |
    Sort-Object Name)

$results = New-Object System.Collections.Generic.List[object]
$failed = 0
$passed = 0

Write-Host ''
Write-Host '=== Orchestrator Test Suite ==='
Write-Host ''

foreach ($testScript in $testScripts) {
    $testName = $testScript.BaseName
    Write-Host ('--- Running {0} ---' -f $testName)

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $testScript.FullName
    $code = $LASTEXITCODE
    if ($null -eq $code) { $code = 1 }

    $status = if ($code -eq 0) { 'PASS' } else { 'FAIL' }
    if ($status -eq 'PASS') {
        $passed++
    }
    else {
        $failed++
    }

    $results.Add([pscustomobject]@{
            Test   = $testName
            Status = $status
            Exit   = $code
        }) | Out-Null

    Write-Host ''
}

Write-Host '=== Summary ==='
$results | Format-Table -AutoSize | Out-String | Write-Host

Write-Host ('Total: {0} | Passed: {1} | Failed: {2}' -f $results.Count, $passed, $failed)

if ($failed -gt 0) {
    exit 1
}

exit 0
