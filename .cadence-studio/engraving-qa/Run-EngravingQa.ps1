# SPDX-License-Identifier: GPL-3.0-only
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $SourcePath,
    [Parameter(Mandatory)][string] $BootstrapResultPath,
    [Parameter(Mandatory)][string] $QtPath,
    [Parameter(Mandatory)][string] $DependenciesPath,
    [Parameter(Mandatory)][string] $OutputDirectory
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitProcess -or
    $env:GITHUB_ACTIONS -ne 'true' -or $env:CI -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted') {
    throw 'Only disposable GitHub-hosted native Windows x64 runners are permitted.'
}
$SourcePath = [IO.Path]::GetFullPath($SourcePath)
$QtPath = [IO.Path]::GetFullPath($QtPath)
$DependenciesPath = [IO.Path]::GetFullPath($DependenciesPath)
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
$tempRoot = [IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
if (-not $OutputDirectory.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $OutputDirectory)) {
    throw 'OutputDirectory must be new and strictly below RUNNER_TEMP.'
}
. (Join-Path $SourcePath 'scripts/windows/Common.ps1')
$selection = Get-Content (Join-Path $PSScriptRoot 'selection.json') -Raw | ConvertFrom-Json
$bootstrap = Get-Content -LiteralPath $BootstrapResultPath -Raw | ConvertFrom-Json
if ($bootstrap.original_source_commit -ne $selection.original_source_commit -or $bootstrap.source_tree -ne $selection.source_tree) { throw 'Bootstrap differs from reviewed candidate 76b51af.' }
if ((Get-GitText $SourcePath @('rev-parse', 'HEAD')) -ne $bootstrap.ci_source_commit -or
    (Get-GitText $SourcePath @('rev-parse', 'HEAD^{tree}')) -ne $selection.source_tree -or
    (Get-GitText $SourcePath @('status', '--porcelain', '--untracked-files=all'))) { throw 'Only the exact clean reconstructed candidate tree may be tested.' }
$lock = Get-CadenceLock
$winDeps = Join-Path $DependenciesPath 'win-deps'
if ((Get-GitText $winDeps @('rev-parse', 'HEAD')) -ne $lock.windows_prebuilt.commit -or (Get-GitText $winDeps @('status', '--porcelain', '--untracked-files=all'))) { throw 'Windows dependencies do not match the clean pinned source.' }
$sdks = Get-Content (Join-Path $DependenciesPath 'prepared-sdks.json') -Raw | ConvertFrom-Json
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
$build = Join-Path $OutputDirectory 'build'
$work = Join-Path $OutputDirectory 'work'
New-Item -ItemType Directory -Path $work | Out-Null
$savedEnvironment = @{}
foreach ($name in @('PATH', 'QT_QPA_PLATFORM', 'MU_QT_QPA_PLATFORM', 'GTEST_FILTER', 'GTEST_OUTPUT', 'ASAN_OPTIONS')) { $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
$report = [ordered]@{
    schema_version = 1; status = 'prepared'; phase = 'preflight'; error = $null
    scope = 'Upstream engraving model assertions in native Windows QGuiApplication/noGui test mode; no editor gestures or audio'
    original_source_commit = $selection.original_source_commit; source_tree = $selection.source_tree; ci_source_commit = $bootstrap.ci_source_commit
    upstream_commit = $lock.upstream.commit; qt_version = $lock.qt.version; windows_prebuilt_commit = $lock.windows_prebuilt.commit
    configuration = 'utest'; build_type = 'RelWithDebInfo'; asan_enabled = $false; asan_runtime = $null; asan_runtime_sha256 = $null
    diff_executable = $null; msvc_link_executable = $null; executable = $null; executable_sha256 = $null
    expected_count = 11; actual_count = 0; editing_gestures_tested = $false; audio_tested = $false; installation_tested = $false
}
try {
    $report.status = 'blocked_prerequisite'
    if (-not $env:VCToolsInstallDir) { $report.status = 'blocked_prerequisite'; throw 'Active MSVC VCToolsInstallDir missing.' }
    $toolRoot = [IO.Path]::GetFullPath($env:VCToolsInstallDir)
    $msvcBin = Join-Path $toolRoot 'bin/Hostx64/x64'
    $link = (Get-Command link.exe -ErrorAction Stop).Source
    if ([IO.Path]::GetFullPath($link) -ine (Join-Path $msvcBin 'link.exe')) { $report.status = 'blocked_prerequisite'; throw 'Active linker is not the x64 MSVC linker; do not allow MSYS link.exe to shadow it.' }
    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
    $asanInstallations = @(Get-CheckedNativeOutput $vswhere @('-all', '-products', '*', '-requires', 'Microsoft.VisualStudio.Component.VC.ASAN', '-property', 'installationPath'))
    if (-not @($asanInstallations | Where-Object { $toolRoot.StartsWith($_.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase) }).Count) { $report.status = 'blocked_prerequisite'; throw 'Active Visual Studio installation lacks the registered VC.ASAN component.' }
    $asanRuntime = Join-Path $msvcBin 'clang_rt.asan_dynamic-x86_64.dll'
    if (-not (Test-Path -LiteralPath $asanRuntime -PathType Leaf)) { $report.status = 'blocked_prerequisite'; throw 'Active MSVC x64 ASAN runtime DLL is absent; ASAN is not disabled as a workaround.' }
    $report.asan_runtime = $asanRuntime
    $report.asan_runtime_sha256 = (Get-FileHash $asanRuntime -Algorithm SHA256).Hash.ToLowerInvariant()
    $gitPath = (Get-Command git.exe -ErrorAction Stop).Source
    $gitRoot = Split-Path (Split-Path $gitPath -Parent) -Parent
    $diff = Join-Path $gitRoot 'usr/bin/diff.exe'
    if (-not (Test-Path -LiteralPath $diff -PathType Leaf)) { $report.status = 'blocked_prerequisite'; throw 'GNU diff from Git for Windows is unavailable at the expected Git installation.' }
    # Qt/ASAN are worker-only runtime paths. Append Git usr/bin LAST, never ahead
    # of MSVC, because Git also ships an incompatible link.exe.
    $env:PATH = (Join-Path $QtPath 'bin') + ';' + $msvcBin + ';' + $env:PATH + ';' + (Split-Path $diff -Parent)
    if ((Get-Command link.exe).Source -ine $link -or (Get-Command diff.exe).Source -ine $diff) { throw 'PATH selected an unexpected MSVC linker or GNU diff.' }
    $report.diff_executable = $diff; $report.msvc_link_executable = $link
    Invoke-CheckedNative $diff @('--version') (Join-Path $OutputDirectory 'diff-version.log')
    $left = Join-Path $work 'diff-left.txt'; $right = Join-Path $work 'diff-right.txt'
    [IO.File]::WriteAllText($left, "same`r`n"); [IO.File]::WriteAllText($right, "same`n")
    Invoke-CheckedNative $diff @('-u', '--strip-trailing-cr', $left, $right) (Join-Path $OutputDirectory 'diff-functional.log')
    $report.status = 'prepared'
    Invoke-CheckedNative python @('-I', (Join-Path $PSScriptRoot 'verify.py'), 'source', '--selection', (Join-Path $PSScriptRoot 'selection.json'), '--input', $SourcePath, '--output', (Join-Path $OutputDirectory 'source-test-declarations.json')) (Join-Path $OutputDirectory 'source-test-declarations.log')
    $report.phase = 'configure'
    $arguments = @('-S', $SourcePath, '-B', $build, '-G', 'Ninja',
        '-DCMAKE_BUILD_TYPE=RelWithDebInfo', '-DCMAKE_C_COMPILER=cl.exe', '-DCMAKE_CXX_COMPILER=cl.exe',
        "-DCMAKE_PREFIX_PATH=$QtPath", "-DFETCHCONTENT_SOURCE_DIR_MUSESCORE_PREBUILD_WIN_DEPS=$winDeps",
        '-DMUSESCORE_BUILD_CONFIGURATION=utest', '-DMUSE_APP_BUILD_MODE=dev', '-DCADENCE_BUILD=ON',
        '-DMUSE_COMPILE_ASAN=ON', '-DMUSE_ENABLE_UNIT_TESTS=ON', '-DMUE_BUILD_ENGRAVING_TESTS=ON',
        '-DMUE_DOWNLOAD_SOUNDFONT=OFF', '-DMUE_INSTALL_SOUNDFONT=OFF', '-DMUE_RUN_WINDEPLOYQT=OFF',
        '-DMUSE_MODULE_DIAGNOSTICS_CRASHPAD_CLIENT=OFF', "-DMUSE_MODULE_AUDIO_ASIO_SDK_PATH=$($sdks.asio_sdk_path)",
        '-DCMAKE_EXE_LINKER_FLAGS_RELWITHDEBINFO=/DEBUG /INCREMENTAL:NO',
        '-DCMAKE_SHARED_LINKER_FLAGS_RELWITHDEBINFO=/DEBUG /INCREMENTAL:NO',
        '-DCMAKE_MODULE_LINKER_FLAGS_RELWITHDEBINFO=/DEBUG /INCREMENTAL:NO')
    Invoke-CheckedNative cmake $arguments (Join-Path $OutputDirectory 'configure.log')
    $commands = @(Get-Content (Join-Path $build 'compile_commands.json') -Raw | ConvertFrom-Json)
    $engravingCommands = @($commands | Where-Object { ($_.command -replace '\\', '/') -match 'engraving(?:_tests)?\.dir/' })
    if (-not $engravingCommands.Count -or @($engravingCommands | Where-Object { $_.command -notmatch '(?i)/fsanitize=address' }).Count) { throw 'Actual engraving compile commands are missing ASAN instrumentation.' }
    $report.asan_enabled = $true
    $report.phase = 'build-target'
    Invoke-CheckedNative cmake @('--build', $build, '--target', 'engraving_tests', '--parallel', '2') (Join-Path $OutputDirectory 'build.log')
    $report.phase = 'discover'
    $ctestJson = (Get-CheckedNativeOutput ctest @('--test-dir', $build, '-R', '^engraving_tests$', '--show-only=json-v1')) -join "`n"
    [IO.File]::WriteAllText((Join-Path $OutputDirectory 'ctest-discovery.json'), $ctestJson)
    $ctestMetadata = $ctestJson | ConvertFrom-Json
    $targets = @($ctestMetadata.tests | Where-Object { $_.name -eq 'engraving_tests' })
    if ($targets.Count -ne 1 -or -not $targets[0].command.Count) { throw 'CTest did not register exactly one engraving_tests target.' }
    $exe = [string]$targets[0].command[0]
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw 'Actual engraving_tests executable missing.' }
    $report.executable = $exe; $report.executable_sha256 = (Get-FileHash $exe -Algorithm SHA256).Hash.ToLowerInvariant()
    $env:QT_QPA_PLATFORM = 'offscreen'; $env:MU_QT_QPA_PLATFORM = 'offscreen'
    $env:ASAN_OPTIONS = 'halt_on_error=1'
    $filter = (@($selection.tests | ForEach-Object { $_.name }) -join ':')
    $env:GTEST_FILTER = $filter
    [Environment]::SetEnvironmentVariable('GTEST_OUTPUT', $null, 'Process')
    Push-Location $work
    try {
        $listed = (Get-CheckedNativeOutput $exe @('--gtest_list_tests', "--gtest_filter=$filter")) -join "`n"
        [IO.File]::WriteAllText((Join-Path $OutputDirectory 'gtest-list.log'), $listed)
    } finally { Pop-Location }
    Invoke-CheckedNative python @('-I', (Join-Path $PSScriptRoot 'verify.py'), 'list', '--selection', (Join-Path $PSScriptRoot 'selection.json'), '--input', (Join-Path $OutputDirectory 'gtest-list.log'), '--output', (Join-Path $OutputDirectory 'discovered-tests.json')) (Join-Path $OutputDirectory 'list-validation.log')
    $report.phase = 'execute-eleven-cases'
    $env:GTEST_OUTPUT = 'xml:' + (Join-Path $OutputDirectory 'engraving-gtest.xml')
    # CTest's registered working directory is inside the separate build tree;
    # upstream tests write only their generated comparison files there.
    $testFailure = $null
    try { Invoke-CheckedNative ctest @('--test-dir', $build, '-R', '^engraving_tests$', '--output-on-failure', '--verbose', '--timeout', '600', '--output-junit', (Join-Path $OutputDirectory 'ctest-junit.xml')) (Join-Path $OutputDirectory 'ctest.log') }
    catch { $testFailure = $_ }
    Invoke-CheckedNative python @('-I', (Join-Path $PSScriptRoot 'verify.py'), 'results', '--selection', (Join-Path $PSScriptRoot 'selection.json'), '--input', (Join-Path $OutputDirectory 'engraving-gtest.xml'), '--output', (Join-Path $OutputDirectory 'executed-tests.json')) (Join-Path $OutputDirectory 'result-validation.log')
    if ($null -ne $testFailure) { throw $testFailure }
    $executed = Get-Content (Join-Path $OutputDirectory 'executed-tests.json') -Raw | ConvertFrom-Json
    $report.actual_count = $executed.executed_count
    if ($report.actual_count -ne 11 -or -not $executed.passed) { throw 'Eleven executed successful cases required.' }
    if ((Get-GitText $SourcePath @('status', '--porcelain', '--untracked-files=all'))) { throw 'Source checkout changed during the test; originals must remain unchanged.' }
    $report.phase = 'completed'; $report.status = 'passed'
} catch {
    $report.error = $_.Exception.Message
    if ($report.status -ne 'blocked_prerequisite') { $report.status = 'failed' }
    throw
} finally {
    $report | ConvertTo-Json -Depth 10 | Set-Content (Join-Path $OutputDirectory 'engraving-qa-report.json') -Encoding UTF8
    foreach ($name in $savedEnvironment.Keys) { [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name], 'Process') }
}
Write-Host 'PASS: eleven named upstream engraving model tests executed with ASAN. GUI gestures, editing workflow, sound and installation were not tested.'
