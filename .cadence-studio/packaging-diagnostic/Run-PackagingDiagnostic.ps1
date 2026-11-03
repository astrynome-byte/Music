# SPDX-License-Identifier: GPL-3.0-only
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $SourcePath,
    [Parameter(Mandatory)][string] $WorkPath,
    [int] $BuildNumber = 4,
    [switch] $ConfigureOnly
)
. (Join-Path $SourcePath 'scripts/windows/Common.ps1')
if (-not $ConfigureOnly) { Assert-Windows64 }
$SourcePath = Resolve-CadencePath $SourcePath
$WorkPath = Resolve-CadencePath $WorkPath
if (Test-Path -LiteralPath $WorkPath) { throw 'Diagnostic WorkPath must be new; existing files are never removed.' }
$projectPath = Join-Path $WorkPath 'fixture-project'
$buildPath = Join-Path $WorkPath 'fixture-build'
$stagePath = Join-Path $WorkPath 'fixture-stage'
New-Item -ItemType Directory -Path $projectPath, $buildPath | Out-Null
foreach ($file in @('CMakeLists.txt', 'diagnostic.cpp', 'DIAGNOSTIC-ONLY.txt')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $file) -Destination $projectPath
}
$assetPaths = @(
    'buildscripts/packaging/Windows/Installer/WIX.template.in',
    'buildscripts/packaging/Windows/Installer/LICENSE.rtf',
    'buildscripts/packaging/Windows/Installer/installer_banner_wix.png',
    'buildscripts/packaging/Windows/Installer/installer_background_wix.png',
    'share/icons/AppIcon/MS4_AppIcon.ico'
)
$assetHashes = [ordered]@{}
foreach ($relativePath in $assetPaths) {
    $original = Join-Path $SourcePath $relativePath
    $copy = Join-Path $projectPath $relativePath
    New-Item -ItemType Directory -Path (Split-Path $copy) -Force | Out-Null
    Copy-Item -LiteralPath $original -Destination $copy
    $originalHash = (Get-FileHash -LiteralPath $original -Algorithm SHA256).Hash.ToLowerInvariant()
    if ((Get-FileHash -LiteralPath $copy -Algorithm SHA256).Hash.ToLowerInvariant() -ne $originalHash) { throw "Changed packaging asset: $relativePath" }
    $assetHashes[$relativePath] = $originalHash
}
$lock = Get-CadenceLock
$manifest = [ordered]@{
    schema_version = 1; purpose = 'CPack/WiX diagnostic fixture; never an application delivery'
    source_commit = (Get-GitText $SourcePath @('rev-parse', 'HEAD'))
    source_tree = (Get-GitText $SourcePath @('rev-parse', 'HEAD^{tree}'))
    source_dirty = [bool](Get-GitText $SourcePath @('status', '--porcelain', '--untracked-files=all'))
    upstream_commit = $lock.upstream.commit; configuration = 'Release'; build_number = $BuildNumber
    packaging_module_sha256 = (Get-FileHash (Join-Path $SourcePath 'buildscripts/packaging/Windows/SetupWindowsPackaging.cmake') -Algorithm SHA256).Hash.ToLowerInvariant()
    version_module_sha256 = (Get-FileHash (Join-Path $SourcePath 'version.cmake') -Algorithm SHA256).Hash.ToLowerInvariant()
    muse_app_build_mode = 'release'; muse_app_unstable = $false; muse_app_is_prerelease = $false
    asset_sha256 = $assetHashes; diagnostic_installed = $false; diagnostic_published = $false
    windows_wix_executed = $false; cases = @()
}
Write-CadenceJson $manifest (Join-Path $WorkPath 'diagnostic-manifest.json')
Copy-Item -LiteralPath (Join-Path $SourcePath 'scripts/config/dependencies.lock.json') -Destination $WorkPath
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'DIAGNOSTIC-ONLY.txt') -Destination $WorkPath
$configureArguments = @('-S', $projectPath, '-B', $buildPath, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
    "-DCADENCE_SOURCE_ROOT=$SourcePath", "-DCMAKE_BUILD_NUMBER=$BuildNumber", "-DCMAKE_INSTALL_PREFIX=$stagePath")
if ($ConfigureOnly) { $configureArguments += '-DCADENCE_DIAGNOSTIC_CONFIGURE_ONLY=ON' }
Invoke-CheckedNative cmake $configureArguments (Join-Path $WorkPath 'configure.log')
if ($ConfigureOnly) {
    Write-Host 'Configuration-only check complete; Windows compiler, candle and light have not run.'
    exit 0
}
foreach ($tool in @('cmake', 'cpack', 'candle', 'light', 'cl')) {
    Write-Host "Diagnostic tool: $tool -> $((Get-Command $tool -ErrorAction Stop).Source)"
}
$cmakeVersion = Get-CheckedNativeVersion -File cmake -ArgumentList @('--version') `
    -Pattern '^cmake version (?<version>\d+\.\d+\.\d+)(?:\D.*)?$' -DisplayName CMake
if ($cmakeVersion -ne [version]$lock.tools.cmake_recommended) { throw "Expected CMake $($lock.tools.cmake_recommended), got $cmakeVersion" }
foreach ($tool in @('candle', 'light')) {
    $toolVersion = (Get-Item -LiteralPath (Get-Command $tool).Source).VersionInfo.FileVersion
    Write-Host "Diagnostic $tool executable version: $toolVersion"
    if ($toolVersion -notmatch ('^' + [regex]::Escape($lock.tools.wix) + '(\.|$)')) { throw "Expected WiX $($lock.tools.wix), got $toolVersion" }
}
Invoke-CheckedNative cmake @('--build', $buildPath, '--config', 'Release', '--parallel', '2') (Join-Path $WorkPath 'build.log')
Invoke-CheckedNative cmake @('--install', $buildPath, '--config', 'Release') (Join-Path $WorkPath 'install.log')
Invoke-CheckedNative cmake @('-S', $projectPath, '-B', $buildPath, '-DMUE_PACK_INSTALL_DIR=ON') (Join-Path $WorkPath 'package-configure.log')
$cases = @(
    @{ name = 'unchanged-release'; config = $null },
    @{ name = 'omit-empty-contact-only'; config = (Join-Path $PSScriptRoot 'OmitEmptyContact.cmake') }
)
$hadFailure = $false
foreach ($case in $cases) {
    $casePath = Join-Path $WorkPath $case.name
    New-Item -ItemType Directory -Path $casePath | Out-Null
    $arguments = @('--config', (Join-Path $buildPath 'CPackConfig.cmake'), '-G', 'WIX', '-C', 'Release', '-B', $casePath, '--verbose', '--debug')
    if ($case.config) { $arguments += @('-D', "CPACK_PROJECT_CONFIG_FILE=$($case.config)") }
    $passed = $false
    $failure = $null
    try {
        Invoke-CheckedNative cpack $arguments (Join-Path $casePath 'cpack-verbose.log')
        $passed = $true
    } catch {
        $hadFailure = $true
        $failure = $_.Exception.Message
        Write-Host "Diagnostic case $($case.name) failed: $failure"
    } finally {
        $manifest.windows_wix_executed = $true
        $manifest.cases += [ordered]@{ name = $case.name; cpack_succeeded = $passed; error = $failure }
        Write-CadenceJson $manifest (Join-Path $WorkPath 'diagnostic-manifest.json')
        # Print the true failure evidence as well as retaining it: artifact downloads
        # may be inaccessible to the agent, while GitHub job logs remain readable.
        if (-not $passed) {
            $details = @(Get-ChildItem -LiteralPath $casePath -Recurse -File | Where-Object { $_.Name -eq 'wix.log' -or $_.Extension -in @('.wxs', '.wxi') } | Sort-Object FullName)
            foreach ($detail in $details) {
                Write-Host "::group::WiX diagnostic $($case.name): $($detail.FullName)"
                Get-Content -LiteralPath $detail.FullName | Out-Host
                Write-Host '::endgroup::'
            }
        }
        # A diagnostic MSI must never be confused with the real application.
        Get-ChildItem -LiteralPath $casePath -Recurse -File -Filter '*.msi' | Remove-Item -Force
    }
}
if ($hadFailure) { throw 'At least one diagnostic case failed. Inspect the case comparison and printed wix.log; no diagnostic MSI is a deliverable.' }
Write-Host 'Both packaging diagnostic cases passed. This does not validate an application installer.'
