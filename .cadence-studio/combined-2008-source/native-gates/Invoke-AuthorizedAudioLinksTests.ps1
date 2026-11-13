# SPDX-License-Identifier: GPL-3.0-only
# Compile and run the existing real Qt HTTPS suite; no application or system trust changes.
#Requires -Version 7.2
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$SourceRoot,
    [Parameter(Mandatory)][string]$QtKit,
    [Parameter(Mandatory)][string]$OutputDirectory
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (-not [OperatingSystem]::IsWindows() -or -not [Environment]::Is64BitProcess -or
    $env:GITHUB_ACTIONS -cne 'true' -or $env:CI -cne 'true' -or
    $env:RUNNER_ENVIRONMENT -cne 'github-hosted') {
    throw 'Disposable hosted Windows x64 required for this qualification.'
}
foreach ($value in @($SourceRoot, $QtKit, $OutputDirectory)) {
    if (-not [IO.Path]::IsPathFullyQualified($value) -or $value.StartsWith('\\') -or
        '..' -in ($value -split '[/\\]')) { throw 'Explicit absolute local paths required.' }
}
$SourceRoot = [IO.Path]::GetFullPath($SourceRoot)
$QtKit = [IO.Path]::GetFullPath($QtKit)
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
$tempPrefix = [IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\','/') + [IO.Path]::DirectorySeparatorChar
if (-not $OutputDirectory.StartsWith($tempPrefix, [StringComparison]::OrdinalIgnoreCase) -or
    (Test-Path -LiteralPath $OutputDirectory)) { throw 'New qualification output beneath RUNNER_TEMP required.' }
$qtBin = Join-Path $QtKit 'bin'
$qtPlugins = Join-Path $QtKit 'plugins'
if (-not (Test-Path -LiteralPath (Join-Path $qtBin 'Qt6Network.dll') -PathType Leaf) -or
    -not (Test-Path -LiteralPath (Join-Path $qtPlugins 'tls') -PathType Container)) {
    throw 'The actual configured Qt Network DLL and TLS plugins are required.'
}
$pythonExe = (Get-Command python -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
$opensslExe = (Get-Command openssl -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
if (-not (Test-Path -LiteralPath $pythonExe -PathType Leaf) -or
    -not (Test-Path -LiteralPath $opensslExe -PathType Leaf)) { throw 'Single real Python and OpenSSL executables required.' }
[void][IO.Directory]::CreateDirectory($OutputDirectory)
$oldPath = $env:PATH
$oldPlugins = $env:QT_PLUGIN_PATH
$env:PATH = $qtBin + ';' + [IO.Path]::GetDirectoryName($opensslExe) + ';' + $oldPath
$env:QT_PLUGIN_PATH = $qtPlugins
$report = [ordered]@{
    schema_version=1; status='running'; source_root=$SourceRoot; qt_kit=$QtKit
    python_executable=$pythonExe; openssl_executable=$opensslExe; openssl_version=$null
    tested_source_sha256=@{}; prerequisite_probe=$null; pass_groups=@(); error=$null
    application_executed=$false; GUI_validated=$false; system_trust_changed=$false
    physical_audio_or_MIDI_tested=$false; cleanup_changes_to_source=$false
}
function Native([string]$Program, [string[]]$Arguments, [string]$Log) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $Program @Arguments 2>&1 | Tee-Object -FilePath $Log | Out-Host; $code=$LASTEXITCODE }
    finally { $ErrorActionPreference=$previous }
    if ($code -ne 0) { throw "Native qualification command failed with exit $code; see $Log" }
}
try {
    Native $opensslExe @('version') (Join-Path $OutputDirectory 'openssl-version.log')
    $report.openssl_version=[IO.File]::ReadAllText((Join-Path $OutputDirectory 'openssl-version.log')).Trim()
    foreach ($relative in @(
        'test/cadence/authorized_audio_links/CMakeLists.txt',
        'test/cadence/authorized_audio_links/download_tests.cpp',
        'test/cadence/authorized_audio_links/run_https.py',
        'src/project/qml/MuseScore/Project/internal/LocalAudioTranscription/authorizedwavedownload.cpp',
        'src/project/qml/MuseScore/Project/internal/LocalAudioTranscription/authorizedwavedownload.h',
        'src/importexport/audiotranscription/audiotranscription.cpp',
        'src/importexport/audiotranscription/audiotranscription.h')) {
        $report.tested_source_sha256[$relative]=(Get-FileHash -LiteralPath (Join-Path $SourceRoot $relative) -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $probeSource = Join-Path $OutputDirectory 'probe-source'
    [void][IO.Directory]::CreateDirectory($probeSource)
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'qt_tls_and_links_probe.cpp') -Destination $probeSource
    @'
cmake_minimum_required(VERSION 3.22)
project(cadence_qt_tls_links_probe LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
find_package(Qt6 REQUIRED COMPONENTS Core Network)
add_executable(cadence_qt_tls_links_probe qt_tls_and_links_probe.cpp)
target_link_libraries(cadence_qt_tls_links_probe PRIVATE Qt6::Core Qt6::Network)
target_compile_options(cadence_qt_tls_links_probe PRIVATE /utf-8 /EHsc)
'@ | Set-Content -LiteralPath (Join-Path $probeSource 'CMakeLists.txt') -Encoding utf8NoBOM
    $probeBuild=Join-Path $OutputDirectory 'probe-build'
    Native 'cmake' @('-S',$probeSource,'-B',$probeBuild,'-G','Ninja','-DCMAKE_BUILD_TYPE=Release',"-DCMAKE_PREFIX_PATH=$QtKit",'-DCMAKE_CXX_COMPILER=cl.exe') (Join-Path $OutputDirectory 'probe-configure.log')
    Native 'cmake' @('--build',$probeBuild,'--parallel','2') (Join-Path $OutputDirectory 'probe-build.log')
    Native (Join-Path $probeBuild 'cadence_qt_tls_links_probe.exe') @() (Join-Path $OutputDirectory 'prerequisite-probe.original.json')
    $report.prerequisite_probe=Get-Content -LiteralPath (Join-Path $OutputDirectory 'prerequisite-probe.original.json') -Raw | ConvertFrom-Json
    if ($report.prerequisite_probe.passed -cne $true) { throw 'Actual Qt TLS or Windows symbolic links unavailable; no skipped link tests accepted.' }
    $build=Join-Path $OutputDirectory 'test-build'
    Native 'cmake' @('-S',(Join-Path $SourceRoot 'test/cadence/authorized_audio_links'),'-B',$build,'-G','Ninja','-DCMAKE_BUILD_TYPE=Release','-DCMAKE_CXX_COMPILER=cl.exe',"-DCMAKE_PREFIX_PATH=$QtKit","-DPython3_EXECUTABLE=$pythonExe") (Join-Path $OutputDirectory 'configure.log')
    Native 'cmake' @('--build',$build,'--parallel','2') (Join-Path $OutputDirectory 'build.log')
    $ctestLog=Join-Path $OutputDirectory 'ctest.log'
    Native 'ctest' @('--test-dir',$build,'--verbose','--output-on-failure','--timeout','45','--output-junit',(Join-Path $OutputDirectory 'ctest-results.xml')) $ctestLog
    $report.pass_groups=@([IO.File]::ReadAllLines($ctestLog) | ForEach-Object {
        if ($_ -match '^\s*1:\s+(PASS .+)$') { $Matches[1] }
    })
    if ($report.pass_groups.Count -ne 14 -or
        ([IO.File]::ReadAllText($ctestLog) -notmatch '1:\s+ALL TESTS PASSED')) {
        throw 'The existing real HTTPS suite did not report exactly14 reviewed groups.'
    }
    foreach ($relative in @($report.tested_source_sha256.Keys)) {
        if ((Get-FileHash -LiteralPath (Join-Path $SourceRoot $relative) -Algorithm SHA256).Hash.ToLowerInvariant() -cne
            $report.tested_source_sha256[$relative]) { throw 'Tested source changed during qualification.' }
    }
    $report.status='passed-Windows-native-authorized-WAV-HTTPS-only'
} catch { $report.status='failed-or-blocked'; $report.error=$_.Exception.Message }
finally {
    $env:PATH=$oldPath
    $env:QT_PLUGIN_PATH=$oldPlugins
    $report | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $OutputDirectory 'qualification-report.json') -Encoding utf8NoBOM
    Write-Host 'CADENCE_AUTHORIZED_WAV_HTTPS_QUALIFICATION_BEGIN'
    $report | ConvertTo-Json -Depth 12 -Compress | Write-Host
    Write-Host 'CADENCE_AUTHORIZED_WAV_HTTPS_QUALIFICATION_END'
}
if ($report.status -cne 'passed-Windows-native-authorized-WAV-HTTPS-only') {
    throw 'Native authorized WAV HTTPS qualification failed or was blocked; no GUI or application result inferred.'
}
