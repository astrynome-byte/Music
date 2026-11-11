# SPDX-License-Identifier: GPL-3.0-only
#Requires -Version 7.0
[CmdletBinding()]
param([Parameter(Mandatory)][string] $WorkPath, [string] $SourceArchivePath)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitProcess -or $env:VSCMD_ARG_TGT_ARCH -ne 'x64') {
    throw 'Native Windows x64 and an MSVC x64 developer shell are required.'
}
$WorkPath = [IO.Path]::GetFullPath($WorkPath)
if ($WorkPath -match '[;\r\n"]' -or (Test-Path -LiteralPath $WorkPath)) { throw 'WorkPath must be a new directory without list separators/quotes.' }
$lock = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'zlib.lock.json') -Raw | ConvertFrom-Json
if (-not $env:VisualStudioVersion -or ([version]$env:VisualStudioVersion).Major -ne 17) { throw 'Select Visual Studio 2022 / v143 explicitly before building this profile.' }
$selectedSdk = ([string]$env:WindowsSDKVersion).Trim() -replace '[/\\]+$', ''
if ($selectedSdk -ne $lock.windows_profile.windows_sdk) { throw "Expected Windows SDK $($lock.windows_profile.windows_sdk); got $selectedSdk." }
function ToolPath([string] $Name) {
    # Select before accessing Source: discovery may report several installations.
    (Get-Command $Name -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
}
foreach ($tool in @('cmake', 'ctest', 'ninja', 'cl.exe', 'dumpbin.exe')) { [void](ToolPath $tool) }
$cmakeTool = ToolPath cmake; $ninjaTool = ToolPath ninja
$cmakeVersion = @(& $cmakeTool --version); if ($LASTEXITCODE -ne 0 -or $cmakeVersion[0] -ne "cmake version $($lock.cmake_version)") { throw 'Use the exact CMake version from zlib.lock.json.' }
$ninjaVersion = @(& $ninjaTool --version); if ($LASTEXITCODE -ne 0 -or ($ninjaVersion -join '').Trim() -ne $lock.ninja_version) { throw 'Use the exact Ninja version from zlib.lock.json.' }
if ($SourceArchivePath) { $SourceArchivePath = [IO.Path]::GetFullPath($SourceArchivePath) }
New-Item -ItemType Directory -Path $WorkPath | Out-Null
$commands = [Collections.Generic.List[object]]::new()
function Native([string] $Tool, [string[]] $Arguments, [string] $Log) {
    $command = ToolPath $Tool
    ($command + ' ' + ($Arguments -join ' ')) | Add-Content -LiteralPath (Join-Path $WorkPath 'commands.log')
    $commands.Add([ordered]@{ executable = $command; arguments = @($Arguments); utc = [DateTime]::UtcNow.ToString('o') })
    $commands.ToArray() | ConvertTo-Json -Depth 6 -AsArray | Set-Content (Join-Path $WorkPath 'commands.json') -Encoding utf8
    $previous = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    try { & $command @Arguments 2>&1 | Tee-Object -FilePath $Log -Append | Out-Host; $code = $LASTEXITCODE }
    finally { $ErrorActionPreference = $previous }
    if ($code -ne 0) { throw "$Tool failed with exit code $code; see $Log" }
}
function Hash([string] $Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Inventory([string] $Directory) {
    $files = [ordered]@{}
    foreach ($file in Get-ChildItem -LiteralPath $Directory -Recurse -File | Sort-Object FullName) {
        $files[[IO.Path]::GetRelativePath($Directory, $file.FullName) -replace '\\', '/'] = Hash $file.FullName
    }
    $files
}
$fetchArguments = @("-DZLIB_SOURCE_OUTPUT=$(Join-Path $WorkPath 'sources')")
if ($SourceArchivePath) { $fetchArguments += "-DZLIB_SOURCE_ARCHIVE=$SourceArchivePath" }
$fetchArguments += @('-P', (Join-Path $PSScriptRoot 'FetchSource.cmake'))
Native cmake $fetchArguments (Join-Path $WorkPath 'fetch.log')
$source = (Get-Content -LiteralPath (Join-Path $WorkPath 'sources/source-path.txt') -Raw).Trim()
$before = Inventory $source
$before | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $WorkPath 'source-file-sha256.json') -Encoding utf8
$build = Join-Path $WorkPath 'build'; $stage = Join-Path $WorkPath 'stage'; $probe = Join-Path $WorkPath 'probe'
$report = [ordered]@{
    schema_version = 1; component = 'zlib'; version = $lock.version; status = 'pending'
    upstream_tag = $lock.tag; upstream_commit = $lock.commit; archive_sha256 = $lock.archive_sha256
    source_origin = 'Official release archive retained byte-for-byte; no Git checkout or source patch'
    target_platform = 'Windows x64'; linkage = 'static'; runtime = '/MD'; configuration = 'Release'
    compiler = (Get-Item -LiteralPath (ToolPath cl.exe)).VersionInfo.FileVersion
    compiler_path = ToolPath cl.exe; windows_sdk = $env:WindowsSDKVersion
    cmake = $lock.cmake_version; ninja = $lock.ninja_version
    ci_run_id = $env:GITHUB_RUN_ID; ci_run_attempt = $env:GITHUB_RUN_ATTEMPT
    created_utc = [DateTime]::UtcNow.ToString('o'); source_unchanged = $false; upstream_tests_passed = $false
    installed_api_probe_passed = $false; artifact_sha256 = @{}; cadence_application_link_tested = $false
    retained_stage7_changed = $false; error = $null
}
try {
    Native cmake @('-S', $source, '-B', $build, '-G', 'Ninja', '-DCMAKE_C_COMPILER=cl.exe',
        '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreadedDLL',
        '-DZLIB_BUILD_STATIC=ON', '-DZLIB_BUILD_SHARED=OFF', '-DZLIB_BUILD_TESTING=ON', '-DZLIB_INSTALL=ON', '-DZLIB_PREFIX=OFF',
        '-DCMAKE_INSTALL_LIBDIR=lib', "-DCMAKE_INSTALL_PREFIX=$stage") (Join-Path $WorkPath 'configure.log')
    Native cmake @('--build', $build, '--parallel', '2') (Join-Path $WorkPath 'build.log')
    Native ctest @('--test-dir', $build, '--output-on-failure', '--no-tests=error', '--output-junit', (Join-Path $WorkPath 'upstream-tests.xml')) (Join-Path $WorkPath 'upstream-tests.log')
    $report.upstream_tests_passed = $true
    Native cmake @('--install', $build) (Join-Path $WorkPath 'install.log')
    $library = Join-Path $stage $lock.windows_profile.library_relative_path
    foreach ($relative in @($lock.windows_profile.library_relative_path, 'include/zlib.h', 'include/zconf.h')) {
        $file = Join-Path $stage $relative
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Installed profile file missing: $relative" }
        $report.artifact_sha256[$relative] = Hash $file
    }
    Native dumpbin.exe @('/headers', $library) (Join-Path $WorkPath 'archive-headers.log')
    Native dumpbin.exe @('/directives', $library) (Join-Path $WorkPath 'archive-directives.log')
    $headers = Get-Content (Join-Path $WorkPath 'archive-headers.log') -Raw
    $directives = Get-Content (Join-Path $WorkPath 'archive-directives.log') -Raw
    if ($headers -notmatch '(?i)8664 machine' -or $directives -notmatch '(?i)MSVCRT' -or $directives -match '(?i)LIBCMT|MSVCRTD') { throw 'Static library is not the required x64 /MD Release build.' }
    Native cmake @('-S', (Join-Path $PSScriptRoot 'tests'), '-B', $probe, '-G', 'Ninja', '-DCMAKE_C_COMPILER=cl.exe',
        '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreadedDLL', "-DZLIB_PROFILE_PREFIX=$stage") (Join-Path $WorkPath 'probe-configure.log')
    Native cmake @('--build', $probe, '--parallel', '2') (Join-Path $WorkPath 'probe-build.log')
    Native ctest @('--test-dir', $probe, '--output-on-failure', '--no-tests=error', '--output-junit', (Join-Path $WorkPath 'profile-api-tests.xml')) (Join-Path $WorkPath 'profile-api-tests.log')
    $report.installed_api_probe_passed = $true
    Copy-Item -LiteralPath (Join-Path $source 'LICENSE') -Destination (Join-Path $WorkPath 'LICENSE.zlib.txt')
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'zlib.lock.json') -Destination $WorkPath
    $recipe = Join-Path $WorkPath 'profile-recipe'
    New-Item -ItemType Directory -Path $recipe | Out-Null
    foreach ($relative in @('Build-Windows.ps1', 'FetchSource.cmake', 'README.md', 'COMPONENTS.json', 'zlib.lock.json', 'LICENSE.txt', 'LICENSE.zlib.txt', 'tests', 'integration')) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot $relative) -Destination $recipe -Recurse
    }
    $report['build_recipe_sha256'] = Inventory $recipe
    $report.status = 'component-tested-awaiting-Cadence-link-and-file-compatibility-tests'
} catch { $report.status = 'failed'; $report.error = $_.Exception.Message; throw }
finally {
    $report.source_unchanged = (ConvertTo-Json $before -Compress -Depth 4) -eq (ConvertTo-Json (Inventory $source) -Compress -Depth 4)
    if (-not $report.source_unchanged) { $report.status = 'failed'; $report.error = 'Upstream source bytes changed during the profile build.' }
    $report | ConvertTo-Json -Depth 12 | Set-Content (Join-Path $WorkPath 'zlib-profile-manifest.json') -Encoding utf8
}
if (-not $report.source_unchanged) { throw 'Source integrity check failed.' }
Get-ChildItem -LiteralPath $WorkPath -File -Recurse | Where-Object { $_.FullName -notmatch '[/\\](build|probe)[/\\]' } | Sort-Object FullName | ForEach-Object {
    '{0}  {1}' -f (Hash $_.FullName), ([IO.Path]::GetRelativePath($WorkPath, $_.FullName) -replace '\\', '/')
} | Set-Content (Join-Path $WorkPath 'SHA256SUMS.txt') -Encoding ascii
Write-Host "Component profile tested at $stage; no Cadence executable or retained stage was changed."
