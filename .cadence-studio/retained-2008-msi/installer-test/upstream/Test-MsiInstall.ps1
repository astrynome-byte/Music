# SPDX-License-Identifier: GPL-3.0-only
# Destructive ONLY to the new Cadence product installed by this test on a hosted runner.
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $MsiPath,
    [Parameter(Mandatory)][string] $StageBuildResultPath,
    [Parameter(Mandatory)][string] $OutputDirectory,
    [string] $ExpectedVersion = '4.7.6',
    [string] $GuiWrapperPath,
    [string] $GuiProbePath,
    [string] $StageNoticeReportPath,
    [string] $RetainedStageExecutablePath,
    [switch] $RequireSystemIcu,
    [string] $ExpectedProductVersion
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# No mutation, COM activation or output-directory creation before these guards.
if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitProcess) { throw 'Native 64-bit Windows PowerShell is required.' }
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:CI -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted') {
    throw 'This installation test is restricted to disposable GitHub-hosted Actions runners (GITHUB_ACTIONS=true, CI=true, RUNNER_ENVIRONMENT=github-hosted).'
}
if (-not $env:RUNNER_TEMP) { throw 'RUNNER_TEMP is required.' }
if ($ExpectedVersion -notmatch '^\d+\.\d+\.\d+$') { throw 'ExpectedVersion must have three numeric components.' }
if ($ExpectedProductVersion -and $ExpectedProductVersion -cnotmatch '^\d+\.\d+\.\d+\.\d+$') { throw 'ExpectedProductVersion must have exactly four numeric components.' }
$retainedStageRequested = $PSBoundParameters.ContainsKey('RetainedStageExecutablePath')
$MsiPath = [IO.Path]::GetFullPath($MsiPath)
$StageBuildResultPath = [IO.Path]::GetFullPath($StageBuildResultPath)
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
$temporaryRoot = [IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
if (-not $OutputDirectory.StartsWith($temporaryRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'OutputDirectory must be strictly below RUNNER_TEMP.' }
if (Test-Path -LiteralPath $OutputDirectory) { throw 'OutputDirectory already exists; no existing directory will be reused or deleted.' }
if ([IO.Path]::GetExtension($MsiPath) -ine '.msi' -or -not (Test-Path -LiteralPath $MsiPath -PathType Leaf)) { throw 'MsiPath must be the real newly packaged MSI.' }
$guiRequested = -not [string]::IsNullOrWhiteSpace($GuiWrapperPath)
if ($guiRequested -ne (-not [string]::IsNullOrWhiteSpace($GuiProbePath))) { throw 'GuiWrapperPath and GuiProbePath must both be provided or both omitted.' }
if ($guiRequested) {
    $GuiWrapperPath = [IO.Path]::GetFullPath($GuiWrapperPath)
    $GuiProbePath = [IO.Path]::GetFullPath($GuiProbePath)
    foreach ($guiScript in @($GuiWrapperPath, $GuiProbePath)) {
        if ([IO.Path]::GetExtension($guiScript) -ine '.ps1' -or -not (Test-Path -LiteralPath $guiScript -PathType Leaf)) { throw 'GUI wrapper and probe must be existing PowerShell scripts.' }
    }
}
$noticeReport = $null
if ($StageNoticeReportPath) {
    $StageNoticeReportPath = [IO.Path]::GetFullPath($StageNoticeReportPath)
    $noticeReport = Get-Content -LiteralPath $StageNoticeReportPath -Raw -Encoding utf8 | ConvertFrom-Json
    if ($noticeReport.schema_version -ne 1 -or $noticeReport.passed -ne $true -or
        $noticeReport.application_executed -ne $false -or
        $noticeReport.executable_sha256 -cnotmatch '^[a-f0-9]{64}$' -or
        @($noticeReport.notices).Count -eq 0 -or
        @($noticeReport.notices).Count -ne $noticeReport.notice_files_verified) {
        throw 'A completed read-only stage notice report with real file hashes is required.'
    }
}
$installPath = Join-Path $OutputDirectory 'installed'
if (Test-Path -LiteralPath $installPath) { throw 'Installation directory already exists.' }
$expectedUpgradeCode = '{319B992F-470A-465B-9A79-6B0CBFC7D6C7}'

function Assert-NoReparseDataPath([string] $Path) {
    $current = [IO.Path]::GetFullPath($Path)
    while ($current) {
        $item = Get-Item -LiteralPath $current -Force -ErrorAction Stop
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Retained/installed data path contains a reparse point.' }
        $parent = [IO.Path]::GetDirectoryName($current.TrimEnd('\', '/'))
        if (-not $parent -or $parent -eq $current) { break }
        $current = $parent
    }
}
function Assert-RetainedStagePathData([string] $Path, [string] $ExpectedSha256, [string] $TemporaryRoot) {
    if ([string]::IsNullOrWhiteSpace($Path) -or $Path.Length -gt 4096 -or $Path -match '[;"\x00-\x1f]' -or
        -not [IO.Path]::IsPathFullyQualified($Path) -or -not [IO.Path]::IsPathFullyQualified($TemporaryRoot)) {
        throw 'RetainedStageExecutablePath must be an explicit absolute data path.'
    }
    if ($ExpectedSha256 -cnotmatch '^[a-f0-9]{64}$') { throw 'The unchanged producer build result must supply a full executable SHA256.' }
    $full = [IO.Path]::GetFullPath($Path)
    $temporary = [IO.Path]::GetFullPath($TemporaryRoot)
    $prefix = $temporary.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    if (-not $full.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase) -or
        [IO.Path]::GetFileName($full) -cne 'CadenceStudio4.exe') {
        throw 'RetainedStageExecutablePath must name CadenceStudio4.exe strictly below RUNNER_TEMP.'
    }
    Assert-NoReparseDataPath $temporary
    Assert-NoReparseDataPath $full
    $item = Get-Item -LiteralPath $full -Force -ErrorAction Stop
    if ($item.PSIsContainer -or $item.Length -le 0 -or $item.Length -gt 536870912) { throw 'Retained stage executable is not a bounded regular data file.' }
    $actualSha256 = (Get-FileHash -LiteralPath $full -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant()
    if ($actualSha256 -cne $ExpectedSha256) { throw 'Relocated retained executable differs from the unchanged producer build-result SHA256.' }
    [pscustomobject]@{ path=$full; sha256=$actualSha256; bytes=$item.Length }
}
function Resolve-RetainedStageExecutable([string] $Path, [string] $ExpectedSha256, [string] $TemporaryRoot) {
    if (-not [Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([Runtime.InteropServices.OSPlatform]::Windows) -or
        $env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitProcess -or
        $env:GITHUB_ACTIONS -ne 'true' -or $env:CI -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted' -or
        -not $env:RUNNER_TEMP -or [IO.Path]::GetFullPath($TemporaryRoot) -ine [IO.Path]::GetFullPath($env:RUNNER_TEMP)) {
        throw 'Retained stage relocation requires native Windows x64 disposable GitHub-hosted CI and its exact RUNNER_TEMP.'
    }
    Assert-RetainedStagePathData $Path $ExpectedSha256 $TemporaryRoot
}
function Assert-ExpectedProductVersionData([string] $Actual, [string] $Expected) {
    if ($Expected) {
        if ($Expected -cnotmatch '^\d+\.\d+\.\d+\.\d+$') { throw 'ExpectedProductVersion must have exactly four numeric components.' }
        if ($Actual -cne $Expected) { throw 'MSI ProductVersion differs from the exact ExpectedProductVersion.' }
    }
}
function Assert-InstalledSystemIcuData([string] $InstallPath) {
    $bin = [IO.Path]::GetFullPath((Join-Path $InstallPath 'bin'))
    Assert-NoReparseDataPath $bin
    $binItem = Get-Item -LiteralPath $bin -Force -ErrorAction Stop
    if (-not $binItem.PSIsContainer) { throw 'Installed bin directory is missing or is not a directory.' }
    $icu = Join-Path $bin 'icuuc.dll'
    try {
        $item = Get-Item -LiteralPath $icu -Force -ErrorAction Stop
    } catch [System.Management.Automation.ItemNotFoundException] {
        return [pscustomobject]@{ path=$icu; absent=$true }
    }
    # A file, directory or dangling reparse entry all invalidate system-ICU QA.
    throw 'RequireSystemIcu refuses an installed bin/icuuc.dll entry before application execution.'
}

function Get-ComValue($Object, [string] $Name, [object[]] $Arguments = @()) {
    # Keep COM StringList objects intact; PowerShell otherwise enumerates them
    # before the explicit Count/Item reader receives them (including empty lists).
    return ,($Object.GetType().InvokeMember($Name, [Reflection.BindingFlags]::GetProperty, $null, $Object, $Arguments))
}
function Invoke-ComMethod($Object, [string] $Name, [object[]] $Arguments = @()) {
    return ,($Object.GetType().InvokeMember($Name, [Reflection.BindingFlags]::InvokeMethod, $null, $Object, $Arguments))
}
function Release-Com($Object) {
    if ($null -ne $Object -and [Runtime.InteropServices.Marshal]::IsComObject($Object)) {
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($Object)
    }
}
function Get-ComStringItems($List) {
    try {
        $count = [int](Get-ComValue $List 'Count')
        for ($i = 0; $i -lt $count; $i++) { [string](Get-ComValue $List 'Item' @($i)) }
    } finally { Release-Com $List }
}
function Get-MsiProperty($Database, [string] $Name) {
    # Name is an internal constant, never user-provided SQL.
    $view = $null; $record = $null
    try {
        $view = Invoke-ComMethod $Database 'OpenView' @("SELECT ``Value`` FROM ``Property`` WHERE ``Property``='$Name'")
        [void](Invoke-ComMethod $view 'Execute')
        $record = Invoke-ComMethod $view 'Fetch'
        if ($null -eq $record) { throw "MSI property missing: $Name" }
        [string](Get-ComValue $record 'StringData' @(1))
    } finally {
        if ($null -ne $view) { [void](Invoke-ComMethod $view 'Close') }
        Release-Com $record; Release-Com $view
    }
}
function Get-ProductState([string] $Code) { [int](Get-ComValue $script:installer 'ProductState' @($Code)) }
function Normalize-Guid([string] $Value) { '{' + ([guid]$Value).ToString().ToUpperInvariant() + '}' }
function Invoke-Msi([string] $Operation, [string] $Target, [string] $LogPath, [string] $Extra = '') {
    if ($Target.Contains('"') -or $LogPath.Contains('"') -or $installPath.Contains('"')) { throw 'A path must not contain a quote.' }
    $arguments = "$Operation `"$Target`" /qn /norestart REBOOT=ReallySuppress /L*V `"$LogPath`" $Extra"
    Write-Host "msiexec.exe $arguments"
    $process = Start-Process -FilePath (Join-Path $env:SystemRoot 'System32/msiexec.exe') -ArgumentList $arguments -Wait -PassThru
    try { [int]$process.ExitCode } finally { $process.Dispose() }
}

$installer = $null; $database = $null; $summary = $null
$attemptedInstall = $false; $productCode = $null; $failure = $null; $cleanupFailure = $null
$report = [ordered]@{
    schema_version = 1; status = 'pending'; scope = 'Real MSI install, isolated CLI dependency check, exact-product uninstall on disposable runner'
    msi = $MsiPath; msi_sha256 = $null; product_name = $null; product_code = $null; product_version = $null
    upgrade_code = $null; summary_template = $null; install_path = $installPath
    source_commit = $null; installed_executable_sha256 = $null; installed_file_version = $null
    stage_build_result_path = $StageBuildResultPath; stage_build_result_sha256 = $null; producer_stage_executable_path = $null
    retained_stage_relocation_requested = $retainedStageRequested; retained_stage_executable_path = $null; retained_stage_executable_sha256 = $null
    expected_product_version = $ExpectedProductVersion; require_system_icu = [bool]$RequireSystemIcu
    installed_local_icuuc_absent = $null; installed_icu_absence_checks = @()
    install_exit_code = $null; install_reboot_required = $false; cli_exit_code = $null; cli_version_matched = $false
    isolated_path = $null; removed_child_environment_names = @(); parent_environment_modified = $false
    uninstall_exit_code = $null; uninstall_reboot_required = $false; product_removed = $false
    editing_tested = $false; gui_tested = $false; musical_listening_completed = $false; error = $null; cleanup_error = $null
    gui_requested = $guiRequested; gui_status = 'not_requested'; gui_exit_status = $null; gui_report_path = $null
    gui_startup_observed = $false; clean_exit_observed = $false
    notice_verification_requested = $null -ne $noticeReport; installed_notices_verified = 0; installed_notices = @()
}
try {
    $installer = New-Object -ComObject WindowsInstaller.Installer
    $database = Invoke-ComMethod $installer 'OpenDatabase' @($MsiPath, 0)
    $report.product_name = Get-MsiProperty $database 'ProductName'
    $report.product_code = Normalize-Guid (Get-MsiProperty $database 'ProductCode')
    $productCode = $report.product_code
    $report.product_version = Get-MsiProperty $database 'ProductVersion'
    $report.upgrade_code = Normalize-Guid (Get-MsiProperty $database 'UpgradeCode')
    $summary = Get-ComValue $database 'SummaryInformation' @(0)
    $report.summary_template = [string](Get-ComValue $summary 'Property' @(7))
    if ($report.product_name -notmatch '^Cadence Studio(?:\s+4)?$') { throw "Unexpected MSI ProductName: $($report.product_name)" }
    if ($report.upgrade_code -ne $expectedUpgradeCode) { throw 'MSI UpgradeCode is not the independent Cadence identity.' }
    if ($report.summary_template -notmatch '^x64(?:;|$)') { throw "MSI is not x64: $($report.summary_template)" }
    if ($report.product_version -notmatch ('^' + [regex]::Escape($ExpectedVersion) + '(?:\.\d+)?$')) { throw 'MSI ProductVersion differs from ExpectedVersion.' }
    Assert-ExpectedProductVersionData $report.product_version $ExpectedProductVersion
    Release-Com $summary; $summary = $null; Release-Com $database; $database = $null

    # Read-only Windows Installer APIs; never query Win32_Product (it can repair products).
    if ((Get-ProductState $productCode) -ne -1) { throw 'This exact ProductCode is already registered; test aborted without installing or uninstalling anything.' }
    $related = @(Get-ComStringItems (Get-ComValue $installer 'RelatedProducts' @($expectedUpgradeCode)))
    if ($related.Count) { throw 'A product with the Cadence UpgradeCode already exists; test aborted.' }
    foreach ($code in @(Get-ComStringItems (Get-ComValue $installer 'Products'))) {
        $name = [string](Get-ComValue $installer 'ProductInfo' @([string]$code, 'ProductName'))
        if ($name -match '(?i)\bCadence\b') { throw "A Cadence product already exists: $name. Nothing will be installed or uninstalled." }
    }
    foreach ($hive in @([Microsoft.Win32.RegistryHive]::LocalMachine, [Microsoft.Win32.RegistryHive]::CurrentUser)) {
        foreach ($registryView in @([Microsoft.Win32.RegistryView]::Registry64, [Microsoft.Win32.RegistryView]::Registry32)) {
            $baseKey = $null; $uninstallKey = $null
            try {
                $baseKey = [Microsoft.Win32.RegistryKey]::OpenBaseKey($hive, $registryView)
                $uninstallKey = $baseKey.OpenSubKey('SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall', $false)
                if ($null -ne $uninstallKey) {
                    foreach ($subName in $uninstallKey.GetSubKeyNames()) {
                        $entry = $uninstallKey.OpenSubKey($subName, $false)
                        try { if ([string]$entry.GetValue('DisplayName', '') -match '(?i)\bCadence\b') { throw 'An existing Cadence uninstall entry was found; test aborted.' } }
                        finally { $entry.Dispose() }
                    }
                }
            } finally { if ($null -ne $uninstallKey) { $uninstallKey.Dispose() }; if ($null -ne $baseKey) { $baseKey.Dispose() } }
        }
    }
    $buildResult = Get-Content -LiteralPath $StageBuildResultPath -Raw | ConvertFrom-Json
    if ($buildResult.schema_version -ne 1 -or $buildResult.source_dirty_at_build -or $buildResult.source_commit -notmatch '^[a-f0-9]{40}$') { throw 'A clean real Build.ps1 result is required.' }
    if ([IO.Path]::GetFileName($buildResult.executable) -ine 'CadenceStudio4.exe' -or $buildResult.executable_sha256 -notmatch '^[a-f0-9]{64}$') { throw 'Build result must identify the actual staged Cadence executable and its SHA-256.' }
    $report.stage_build_result_sha256 = (Get-FileHash -LiteralPath $StageBuildResultPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $report.producer_stage_executable_path = [string]$buildResult.executable
    $stageExecutableToVerify = [string]$buildResult.executable
    if ($retainedStageRequested) {
        $retained = Resolve-RetainedStageExecutable $RetainedStageExecutablePath $buildResult.executable_sha256 $env:RUNNER_TEMP
        $stageExecutableToVerify = $retained.path
        $report.retained_stage_executable_path = $retained.path
        $report.retained_stage_executable_sha256 = $retained.sha256
    }
    # Never overwrite/reconstruct the producer result or its historical executable path.
    if ((Get-FileHash -LiteralPath $stageExecutableToVerify -Algorithm SHA256).Hash.ToLowerInvariant() -ne $buildResult.executable_sha256) { throw 'Staged executable no longer matches its build result.' }
    $report.source_commit = $buildResult.source_commit
    $report.msi_sha256 = (Get-FileHash -LiteralPath $MsiPath -Algorithm SHA256).Hash.ToLowerInvariant()
    New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
    $attemptedInstall = $true
    $report.install_exit_code = Invoke-Msi '/i' $MsiPath (Join-Path $OutputDirectory 'install-msiexec.log') "INSTALL_ROOT=`"$installPath`" WIXUI_EXITDIALOGOPTIONALCHECKBOX=0"
    $report.install_reboot_required = $report.install_exit_code -eq 3010
    if ($report.install_exit_code -notin @(0, 3010)) { throw "MSI installation failed: $($report.install_exit_code)" }
    if ((Get-ProductState $productCode) -notin @(3, 4, 5)) { throw 'MSI returned success but the exact product is not installed.' }
    $exe = Join-Path $installPath 'bin/CadenceStudio4.exe'
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw 'Installed Cadence executable missing at the requested test location.' }
    $report.installed_executable_sha256 = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($report.installed_executable_sha256 -ne $buildResult.executable_sha256) { throw 'Installed executable differs from the actual staged build.' }
    $versionInfo = [Diagnostics.FileVersionInfo]::GetVersionInfo($exe)
    $report.installed_file_version = $versionInfo.FileVersion
    # This upstream target may omit the PE FileVersion resource. MSI ProductVersion
    # and the mandatory CLI check below establish version; record FileVersion if present.
    if ($versionInfo.FileVersion -and $versionInfo.FileVersion -notmatch ('^' + [regex]::Escape($ExpectedVersion) + '(?:\D|$)')) { throw 'Present executable FileVersion differs from ExpectedVersion.' }

    if ($null -ne $noticeReport) {
        if ($noticeReport.executable_sha256 -cne $buildResult.executable_sha256) {
            throw 'Notice report identifies a different staged executable.'
        }
        $seenNotices = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        $installRoot = [IO.Path]::GetFullPath($installPath).TrimEnd('\','/') + [IO.Path]::DirectorySeparatorChar
        foreach ($notice in @($noticeReport.notices)) {
            $relative = [string]$notice.stage_path
            if (-not $relative -or [IO.Path]::IsPathRooted($relative) -or $relative -match '(^|[/\\])\.\.([/\\]|$)|[:\x00-\x1f]' -or
                $notice.sha256 -cnotmatch '^[a-f0-9]{64}$' -or
                ($notice.bytes -isnot [long] -and $notice.bytes -isnot [int]) -or $notice.bytes -lt 0) {
                throw 'Invalid or duplicate stage notice identity.'
            }
            $installedNotice = [IO.Path]::GetFullPath((Join-Path $installPath $relative))
            if (-not $installedNotice.StartsWith($installRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'Notice path escapes the new installation.' }
            if (-not $seenNotices.Add($installedNotice)) { throw 'Duplicate normalized installed notice path.' }
            $installedItem = Get-Item -LiteralPath $installedNotice
            $current = $installedItem
            while ($current.FullName -ine $installPath) {
                if ($current.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Installed notice contains a linked path.' }
                $current = Get-Item -LiteralPath ([IO.Path]::GetDirectoryName($current.FullName))
            }
            if ($installedItem.PSIsContainer -or $installedItem.Length -ne $notice.bytes -or
                (Get-FileHash -LiteralPath $installedNotice -Algorithm SHA256).Hash.ToLowerInvariant() -cne $notice.sha256) {
                throw "Installed notice differs from the verified stage: $relative"
            }
            $report.installed_notices += [ordered]@{ path=$relative; bytes=$installedItem.Length; sha256=$notice.sha256 }
        }
        $report.installed_notices_verified = $report.installed_notices.Count
    }

    if ($RequireSystemIcu) {
        $icuCheck = Assert-InstalledSystemIcuData $installPath
        $report.installed_local_icuuc_absent = $icuCheck.absent
        $report.installed_icu_absence_checks += [ordered]@{ phase='before-installed-cli'; path=$icuCheck.path; absent=$icuCheck.absent }
    }

    # Sanitize only the child environment; the runner's environment stays intact.
    # No Qt/MSVC SDK path can satisfy missing installed dependencies through PATH.
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $exe; $start.WorkingDirectory = Join-Path $installPath 'bin'
    $start.ArgumentList.Add('--long-version')
    $start.UseShellExecute = $false; $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true; $start.RedirectStandardError = $true
    $report.isolated_path = (Join-Path $installPath 'bin') + ';' + (Join-Path $env:SystemRoot 'System32')
    $start.Environment['PATH'] = $report.isolated_path
    foreach ($name in @($start.Environment.Keys)) {
        if ($name -match '^(?i:QT|QML|CMAKE_|VCPKG_|VSCMD_|VSINSTALLDIR$|VCINSTALLDIR$|VCTools|INCLUDE$|LIB$|LIBPATH$|WindowsSdk|WindowsSDK|UniversalCRTSdkDir$|UCRTVersion$|DevEnvDir$|ExtensionSdkDir$|FrameworkDir|FrameworkVersion)') {
            $report.removed_child_environment_names += $name
            [void]$start.Environment.Remove($name)
        }
    }
    $app = [Diagnostics.Process]::new(); $app.StartInfo = $start
    try {
        if (-not $app.Start()) { throw 'Installed CLI process did not start.' }
        $stdout = $app.StandardOutput.ReadToEndAsync(); $stderr = $app.StandardError.ReadToEndAsync()
        if (-not $app.WaitForExit(60000)) { $app.Kill($true); $app.WaitForExit(); throw 'Installed CLI exceeded 60 seconds.' }
        $outText = $stdout.GetAwaiter().GetResult(); $errText = $stderr.GetAwaiter().GetResult()
        [IO.File]::WriteAllText((Join-Path $OutputDirectory 'installed-long-version.stdout.log'), $outText)
        [IO.File]::WriteAllText((Join-Path $OutputDirectory 'installed-long-version.stderr.log'), $errText)
        $report.cli_exit_code = $app.ExitCode
        Write-Host $outText; if ($errText) { Write-Host $errText }
        if ($app.ExitCode -ne 0) { throw "Installed CLI failed without SDK paths: $($app.ExitCode)" }
        # Upstream's --long-version text can still say MuseScore. MSI identity and
        # SHA establish Cadence identity; this check verifies the actual version.
        $report.cli_version_matched = ($outText + "`n" + $errText) -match ('(?i)Version\s+' + [regex]::Escape($ExpectedVersion) + '(?:\D|$)')
        if (-not $report.cli_version_matched) { throw 'Installed CLI did not report the expected application version.' }
    } finally { $app.Dispose() }
    $report.status = 'installed-cli-passed-awaiting-uninstall'
    if ($guiRequested) {
        $report.scope += '; optional startup/clean-exit observation of the installed GUI, without editing or listening'
        $guiOutput = Join-Path $OutputDirectory 'installed-gui'
        $report.gui_report_path = Join-Path $guiOutput 'gui-report.json'
        $report.gui_status = 'probe_requested'
        $guiFailure = $null
        try {
            # Run only the MSI-installed executable while its exact product is
            # still installed. Wrapper/probe owns and cleans its own processes.
            if ($RequireSystemIcu) {
                $icuCheck = Assert-InstalledSystemIcuData $installPath
                $report.installed_local_icuuc_absent = $icuCheck.absent
                $report.installed_icu_absence_checks += [ordered]@{ phase='before-installed-gui'; path=$icuCheck.path; absent=$icuCheck.absent }
            }
            & $GuiWrapperPath -Executable $exe -ProbePath $GuiProbePath -OutputDirectory $guiOutput
        } catch { $guiFailure = $_ }
        if (Test-Path -LiteralPath $report.gui_report_path -PathType Leaf) {
            $guiReport = Get-Content -LiteralPath $report.gui_report_path -Raw | ConvertFrom-Json
            $report.gui_status = [string]$guiReport.status
            $report.gui_exit_status = [int]$guiReport.exit_status
            if ([IO.Path]::GetFullPath([string]$guiReport.executable) -ine $exe -or $guiReport.executable_sha256 -ne $report.installed_executable_sha256) {
                throw 'Installed GUI report does not identify the MSI-installed executable and its SHA-256.'
            }
            $report.gui_startup_observed = $guiReport.startup.status -eq 'visible_window_responding_observed'
            $report.clean_exit_observed = (
                $guiReport.shutdown.status -in @('closed_after_close_main_window', 'closed_after_owned_window_close') -and
                $guiReport.shutdown.exit_code -eq 0 -and -not $guiReport.shutdown.forced
            )
            $report.gui_tested = (
                $report.gui_exit_status -eq 0 -and $report.gui_status -eq 'startup_observed_closed_cleanly' -and
                $report.gui_startup_observed -and $report.clean_exit_observed -and $null -eq $guiFailure
            )
        } else {
            $report.gui_status = 'report_missing'
            if ($null -eq $guiFailure) { throw 'Installed GUI wrapper returned without a gui-report.json; startup remains unvalidated.' }
        }
        if ($null -ne $guiFailure) { throw $guiFailure }
        if (-not $report.gui_tested) {
            Write-Warning "Installed GUI remains unvalidated: $($report.gui_status) (probe exit $($report.gui_exit_status)). MSI install/CLI/uninstall evidence is separate."
        }
    }
} catch {
    $failure = $_.Exception.Message; $report.error = $failure; $report.status = 'failed'
} finally {
    # Preflight rejects existing products. Only the exact ProductCode read from
    # this MSI can be removed, and only after attempting its new installation.
    if ($attemptedInstall -and $null -ne $installer -and $null -ne $productCode) {
        try {
            if ((Get-ProductState $productCode) -ne -1) {
                $report.uninstall_exit_code = Invoke-Msi '/x' $productCode (Join-Path $OutputDirectory 'uninstall-msiexec.log')
                $report.uninstall_reboot_required = $report.uninstall_exit_code -eq 3010
                if ($report.uninstall_exit_code -notin @(0, 3010)) { throw "Exact-product uninstall failed: $($report.uninstall_exit_code)" }
            }
            $report.product_removed = (Get-ProductState $productCode) -eq -1
            if (-not $report.product_removed) { throw 'The exact test product remains registered after uninstall.' }
        } catch { $cleanupFailure = $_.Exception.Message; $report.cleanup_error = $cleanupFailure; $report.status = 'failed' }
    }
    if (-not $failure -and -not $cleanupFailure -and $report.cli_version_matched -and $report.product_removed) { $report.status = 'passed' }
    if (Test-Path -LiteralPath $OutputDirectory -PathType Container) {
        $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $OutputDirectory 'msi-install-report.json') -Encoding UTF8
    }
    Release-Com $summary; Release-Com $database; Release-Com $installer
}
if ($report.status -ne 'passed') { throw "MSI QA failed. Install/runtime: $failure Cleanup: $cleanupFailure" }
Write-Host 'PASS: real MSI installed, its executable matched the stage and ran without SDK paths, and only its exact ProductCode was uninstalled.'
if ($guiRequested) {
    if ($report.gui_tested) { Write-Host 'Installed GUI startup and clean exit observed; this does not test editing or listening.' }
    else { Write-Warning "Installed GUI startup is not validated: $($report.gui_status)." }
    Write-Host 'Editing, listening, reboot behavior and a consumer Windows machine remain separate tests.'
} else {
    Write-Host 'Editing, interactive GUI, listening, reboot behavior and a consumer Windows machine remain separate tests.'
}
