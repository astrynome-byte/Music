# SPDX-License-Identifier: GPL-3.0-only
[CmdletBinding()]
param(
    [string] $BuildPath,
    [string] $ResultsPath,
    [ValidateSet('Visual Studio 17 2022', 'Ninja')][string] $Generator = 'Visual Studio 17 2022',
    [string] $PythonExecutable = 'python',
    [switch] $RequireDecode
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
if (-not [Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([Runtime.InteropServices.OSPlatform]::Windows)) {
    throw 'The native AAC probe requires Windows. Linux checks cannot validate the system AAC MFT.'
}
if (-not [Environment]::Is64BitProcess) { throw 'Run this script with a 64-bit Windows PowerShell process.' }
$sourcePath = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if (-not $BuildPath) { $BuildPath = Join-Path ([IO.Path]::GetTempPath()) ('cadence-mf-aac-build-' + [guid]::NewGuid()) }
$BuildPath = [IO.Path]::GetFullPath($BuildPath)
if (-not $ResultsPath) { $ResultsPath = Join-Path $BuildPath 'probe-results' }
$ResultsPath = [IO.Path]::GetFullPath($ResultsPath)
foreach ($path in @($BuildPath, $ResultsPath)) {
    if ($path.Contains(';') -or $path -eq $sourcePath) { throw 'Use separate safe source/build/results directories; semicolons are not supported by CMake paths.' }
    if ((Test-Path -LiteralPath $path) -and @(Get-ChildItem -LiteralPath $path -Force).Count) {
        throw "Choose a new empty directory; existing files are preserved: $path"
    }
}
New-Item -ItemType Directory -Path $BuildPath -Force | Out-Null
New-Item -ItemType Directory -Path $ResultsPath -Force | Out-Null
$reportPath = Join-Path $ResultsPath 'run.json'
$report = [ordered]@{
    schema_version = 1; probe_version = '0.1.0'; status = 'failed'; passed = $false
    started_utc = [DateTime]::UtcNow.ToString('o'); os = [Runtime.InteropServices.RuntimeInformation]::OSDescription
    os_architecture = [Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
    build_path = $BuildPath; results_path = $ResultsPath; generator = $Generator
    windows_media_foundation_encoded = $false; native_cases_completed = 0; decoded_signal_validated = $false
    integrated_into_cadence = $false; errors = @(); cases = @()
}
function Invoke-ProbeNative([string] $Executable, [string[]] $Arguments, [string] $LogPath) {
    Write-Host ($Executable + ' ' + ($Arguments -join ' '))
    $captured = @(& $Executable @Arguments 2>&1)
    $exitCode = $LASTEXITCODE
    $captured | Out-File -LiteralPath $LogPath -Encoding utf8
    $captured | ForEach-Object { Write-Host $_ }
    if ($exitCode -ne 0) { throw "Native command failed with exit code $exitCode; see $LogPath" }
}
try {
    # A developer environment can expose several installations of one command.
    # Keep PATH precedence and pass one executable, never an array of paths.
    $pythonPath = (Get-Command $PythonExecutable -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
    $cmakePath = (Get-Command 'cmake' -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
    $ctestPath = (Get-Command 'ctest' -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
    $ffmpegCommand = Get-Command 'ffmpeg' -CommandType Application -ErrorAction SilentlyContinue
    $report.python_executable = $pythonPath
    $report.ffmpeg_available = [bool]$ffmpegCommand
    if ($RequireDecode -and -not $ffmpegCommand) { throw 'Decode is required but FFmpeg is not already available on PATH; no encoder/decoder is downloaded.' }
    Invoke-ProbeNative $cmakePath @('--version') (Join-Path $ResultsPath 'cmake-version.log')
    Invoke-ProbeNative $pythonPath @('--version') (Join-Path $ResultsPath 'python-version.log')
    $arguments = @('-S', $sourcePath, '-B', $BuildPath, '-G', $Generator,
        '-DCMAKE_BUILD_TYPE=Release', '-DMF_AAC_PROBE_TESTS=ON',
        "-DPython3_EXECUTABLE=$pythonPath", "-DMF_AAC_PROBE_RESULTS_DIR=$ResultsPath")
    if ($Generator -eq 'Visual Studio 17 2022') { $arguments += @('-A', 'x64') }
    Invoke-ProbeNative $cmakePath $arguments (Join-Path $ResultsPath 'configure.log')
    Invoke-ProbeNative $cmakePath @('--build', $BuildPath, '--config', 'Release', '--parallel', '2') (Join-Path $ResultsPath 'build.log')
    Invoke-ProbeNative $ctestPath @('--test-dir', $BuildPath, '-C', 'Release', '--output-on-failure', '--timeout', '60') (Join-Path $ResultsPath 'ctest.log')
    $cases = @(Get-ChildItem -LiteralPath $ResultsPath -Filter 'case.json' -Recurse -File | ForEach-Object {
        Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json
    })
    if ($cases.Count -ne 2 -or @($cases | Where-Object { -not $_.passed -or -not $_.native_encoding_completed }).Count) {
        throw 'Expected exactly two successful real system-encoder cases; see the individual case reports.'
    }
    if ((@($cases.sample_rate | Sort-Object -Unique) -join ',') -ne '44100,48000') { throw 'The two required sample rates were not tested.' }
    $report.cases = $cases
    $report.windows_media_foundation_encoded = $true
    $report.decoded_signal_validated = @($cases | Where-Object { $_.validation_level -ne 'decoded_signal' }).Count -eq 0
    if ($RequireDecode -and -not $report.decoded_signal_validated) { throw 'Both decoded tone checks are required but were not validated.' }
    $report.status = if ($report.decoded_signal_validated) { 'passed_with_decode' } else { 'passed_structure_only' }
    $report.passed = $true
} catch {
    $report.errors = @($_.Exception.Message)
    Write-Host ('FAIL: ' + $_.Exception.Message)
} finally {
    # Keep partial evidence if CTest failed after one rate succeeded.
    $observedCases = @()
    foreach ($file in Get-ChildItem -LiteralPath $ResultsPath -Filter 'case.json' -Recurse -File) {
        try { $observedCases += Get-Content -LiteralPath $file.FullName -Raw | ConvertFrom-Json }
        catch {
            $report.passed = $false; $report.status = 'failed'
            $report.errors += "Unreadable case report: $($file.FullName)"
        }
    }
    $report.cases = $observedCases
    $report.native_cases_completed = @($observedCases | Where-Object { $_.native_encoding_completed }).Count
    $report.finished_utc = [DateTime]::UtcNow.ToString('o')
    $report | ConvertTo-Json -Depth 15 | Set-Content -LiteralPath $reportPath -Encoding utf8
    Write-Host "Probe report: $reportPath"
}
if (-not $report.passed) { exit 1 }
Write-Host "Probe $($report.status). This does not validate Cadence integration or listening quality."
exit 0
