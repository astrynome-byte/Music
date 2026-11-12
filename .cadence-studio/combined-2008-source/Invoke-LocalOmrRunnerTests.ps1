# SPDX-License-Identifier: GPL-3.0-only
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $SourceRoot,
    [Parameter(Mandatory)][string] $QtKit,
    [Parameter(Mandatory)][string] $OutputDirectory
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$source = (Resolve-Path -LiteralPath $SourceRoot).Path
$qt = (Resolve-Path -LiteralPath $QtKit).Path
. (Join-Path $source 'scripts/windows/Common.ps1')
Assert-Windows64
$output = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $output) { throw 'Use a fresh OMR runner qualification directory.' }
New-Item -ItemType Directory -Path $output | Out-Null
$expectedSources = @{
    'src/importexport/omr/localomrjob.cpp' = '9f931ea77f6300020cd01990b2746415abe593de76e49820f77c1151a2d55dbb'
    'src/importexport/omr/localomrjob.h' = '738c8c7620b5f3dab4f08ab4c74a0305f9353be78c7cb8733b93f4bd88dbabe8'
    'test/cadence/local_omr/CMakeLists.txt' = '7183e95cc22bc0322c5a9286ea6fd803618de1ceefc969c303575dd3888f63bd'
    'test/cadence/local_omr/job_tests.cpp' = '96a85f2750f2f7a6098708b774b6c033c3645319de286b169772f813ae48f6ae'
    'test/cadence/local_omr/fake_engine.cpp' = '2af7bd5c874053a672a6c4728537d7846c907d5665984e52803f84a0cf279748'
}
$sourceFacts = @()
foreach ($entry in $expectedSources.GetEnumerator()) {
    $file = Join-Path $source $entry.Key
    $actual = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $entry.Value) { throw "Reviewed OMR source differs: $($entry.Key). Update the source plan after review." }
    $sourceFacts += @{ path = $entry.Key; sha256 = $actual }
}
$english = Join-Path $output 'eng.traineddata'
$url = 'https://raw.githubusercontent.com/tesseract-ocr/tessdata/ced78752cc61322fb554c280d13360b35b8684e4/eng.traineddata'
Invoke-WebRequest -Uri $url -OutFile $english -MaximumRedirection 5 -TimeoutSec 120
$modelInfo = Get-Item -LiteralPath $english
$modelHash = (Get-FileHash -LiteralPath $english -Algorithm SHA256).Hash.ToLowerInvariant()
if ($modelInfo.Length -ne 23466654 -or $modelHash -ne 'daa0c97d651c19fba3b25e81317cd697e9908c8208090c94c3905381c23fc047') {
    throw 'Pinned English model size or SHA-256 differs.'
}
$previousPath = $env:PATH
$hadData = Test-Path Env:CADENCE_OMR_ENGLISH_DATA
$previousData = $env:CADENCE_OMR_ENGLISH_DATA
try {
    $env:PATH = (Join-Path $qt 'bin') + ';' + $env:PATH
    $env:CADENCE_OMR_ENGLISH_DATA = $english
    $build = Join-Path $output 'build with spaces'
    Invoke-CheckedNative cmake @('-S', (Join-Path $source 'test/cadence/local_omr'), '-B', $build,
        '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_CXX_COMPILER=cl.exe',
        "-DCMAKE_PREFIX_PATH=$qt", '-DCMAKE_CXX_FLAGS_INIT=/utf-8') (Join-Path $output 'configure.log')
    Invoke-CheckedNative cmake @('--build', $build, '--parallel', '2') (Join-Path $output 'build.log')
    $ctestLog = Join-Path $output 'ctest.log'
    Invoke-CheckedNative ctest @('--test-dir', $build, '-C', 'Release', '--output-on-failure', '--verbose',
        '--timeout', '45', '--output-junit', (Join-Path $output 'ctest-results.xml')) $ctestLog
    $text = Get-Content -LiteralPath $ctestLog -Raw -Encoding UTF8
    $matchesFound = [regex]::Matches($text, '(?m)^\d+:\s+PASS\s+(15|17)\s+actual Qt process-boundary groups; external fixture is not OMR\s*$')
    $counts = @($matchesFound | ForEach-Object { [int] $_.Groups[1].Value } | Sort-Object)
    if ($counts.Count -ne 2 -or $counts[0] -ne 15 -or $counts[1] -ne 17) {
        throw "Both reviewed Windows scenario sets must pass (15 without model and 17 with model), got $($counts -join ',')."
    }
    if ((Get-FileHash -LiteralPath $english -Algorithm SHA256).Hash.ToLowerInvariant() -ne $modelHash) {
        throw 'The model changed during the actual import tests.'
    }
    $report = @{
        schema_version = 1
        status = 'passed-native-Windows-OMR-runner-boundary'
        scope = 'Production LocalOmrJob with controlled external process; this fixture performs no recognition'
        source = $sourceFacts
        build = $build
        test_group_counts = $counts
        windows_job_descendant_terminated = $true
        copied_input_with_spaces_accents_metacharacters = $true
        model = @{ bytes = $modelInfo.Length; sha256 = $modelHash; url = $url; unchanged = $true }
        real_Audiveris_executed = $false
        integrated_dialog_executed = $false
        application_recompiled_by_this_step = $false
        listening_performed = $false
    }
    $report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $output 'runner-report.json') -Encoding UTF8
    Write-Host 'CADENCE_OMR_RUNNER_REPORT_BEGIN'
    $report | ConvertTo-Json -Depth 10 -Compress | Write-Host
    Write-Host 'CADENCE_OMR_RUNNER_REPORT_END'
} finally {
    $env:PATH = $previousPath
    if ($hadData) { $env:CADENCE_OMR_ENGLISH_DATA = $previousData }
    else { Remove-Item Env:CADENCE_OMR_ENGLISH_DATA -ErrorAction SilentlyContinue }
}
