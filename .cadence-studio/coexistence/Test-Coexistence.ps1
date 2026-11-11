# SPDX-License-Identifier: GPL-3.0-only
#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $OfficialMsiPath,
    [Parameter(Mandatory)][string] $CadenceMsiPath,
    [Parameter(Mandatory)][string] $OutputDirectory,
    [switch] $EnableGui,
    [string] $GuiWrapperPath,
    [string] $GuiProbePath
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitProcess -or
    $env:GITHUB_ACTIONS -ne 'true' -or $env:CI -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted') {
    throw 'Coexistence installation is restricted to disposable GitHub-hosted Windows x64 CI.'
}
if (-not $env:RUNNER_TEMP) { throw 'RUNNER_TEMP is required.' }
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
$tempRoot = [IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
if (-not $OutputDirectory.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $OutputDirectory)) {
    throw 'OutputDirectory must be new and strictly below RUNNER_TEMP.'
}
. "$PSScriptRoot/MsiReadOnly.ps1"
$lock = Get-Content -LiteralPath "$PSScriptRoot/releases.lock.json" -Raw | ConvertFrom-Json
function Hash([string] $Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Write-Json($Value, [string] $Name) { $Value | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $OutputDirectory $Name) -Encoding utf8 }
foreach ($entry in @(@{ path = $OfficialMsiPath; expected = $lock.official.sha256 }, @{ path = $CadenceMsiPath; expected = $lock.cadence.sha256 })) {
    if (-not (Test-Path -LiteralPath $entry.path -PathType Leaf) -or [IO.Path]::GetExtension($entry.path) -ine '.msi' -or (Hash $entry.path) -ne $entry.expected) {
        throw 'MSI must match the exact official release or previously qualified Cadence artifact SHA-256.'
    }
}
if ((Get-Item -LiteralPath $OfficialMsiPath).Length -ne $lock.official.bytes) { throw 'Official MSI size differs from release metadata.' }
if ($EnableGui) {
    foreach ($scriptPath in @($GuiWrapperPath, $GuiProbePath)) {
        if (-not $scriptPath -or -not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) { throw 'Both existing GUI helper paths are required when EnableGui is used.' }
    }
}
$documents = [Environment]::GetFolderPath([Environment+SpecialFolder]::MyDocuments)
if (-not $documents) { throw 'Windows Documents known folder is unavailable.' }
$profiles = @{
    official = [ordered]@{ ini = (Join-Path $env:APPDATA 'MuseScore/MuseScore4.ini'); local = (Join-Path $env:LOCALAPPDATA 'MuseScore/MuseScore4'); documents = (Join-Path $documents 'MuseScore4') }
    cadence = [ordered]@{ ini = (Join-Path $env:APPDATA 'CadenceStudio/CadenceStudio4.ini'); local = (Join-Path $env:LOCALAPPDATA 'CadenceStudio/CadenceStudio4'); documents = (Join-Path $documents 'CadenceStudio4') }
}
foreach ($profilePaths in $profiles.Values) {
    foreach ($path in $profilePaths.Values) { if (Test-Path -LiteralPath $path) { throw "A score application profile already exists: $path. No installation or profile replacement is permitted." } }
}
foreach ($name in @('ini', 'local', 'documents')) {
    if ($profiles.official[$name] -eq $profiles.cadence[$name]) { throw 'Official and Cadence profile paths must be distinct.' }
}

function Read-RegistryValues([Microsoft.Win32.RegistryHive] $Hive, [string] $Path, [Microsoft.Win32.RegistryView] $View = [Microsoft.Win32.RegistryView]::Registry64) {
    $baseKey = $null; $key = $null
    try {
        $baseKey = [Microsoft.Win32.RegistryKey]::OpenBaseKey($Hive, $View)
        $key = $baseKey.OpenSubKey($Path, $false)
        $values = [ordered]@{}
        if ($null -ne $key) {
            foreach ($name in @($key.GetValueNames() | Sort-Object)) {
                $value = $key.GetValue($name, $null, [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
                if ($value -is [byte[]]) { $value = [Convert]::ToBase64String($value) }
                $values[$name] = [ordered]@{ kind = $key.GetValueKind($name).ToString(); value = $value }
            }
        }
        [pscustomobject]@{ exists = $null -ne $key; values = $values }
    } finally { if ($null -ne $key) { $key.Dispose() }; if ($null -ne $baseKey) { $baseKey.Dispose() } }
}
function Association-Snapshot {
    $snapshot = [ordered]@{}
    foreach ($extension in @('.mscz', '.mscx')) {
        foreach ($hive in @([Microsoft.Win32.RegistryHive]::ClassesRoot, [Microsoft.Win32.RegistryHive]::CurrentUser, [Microsoft.Win32.RegistryHive]::LocalMachine)) {
            $path = if ($hive -eq [Microsoft.Win32.RegistryHive]::ClassesRoot) { $extension } else { 'SOFTWARE\Classes\' + $extension }
            $snapshot["$hive/$extension"] = Read-RegistryValues $hive $path
        }
        $snapshot["UserChoice/$extension"] = Read-RegistryValues CurrentUser "SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\FileExts\$extension\UserChoice"
        $progId = [string]$snapshot["ClassesRoot/$extension"].values[''].value
        foreach ($suffix in @('', '\DefaultIcon', '\shell\open\command')) {
            $snapshot["OfficialProgId/$extension/$suffix"] = Read-RegistryValues ClassesRoot ($progId + $suffix)
        }
    }
    $snapshot
}
function Profile-Snapshot {
    $files = [ordered]@{}
    if (Test-Path -LiteralPath $profiles.official.ini -PathType Leaf) { $files['ini'] = Hash $profiles.official.ini }
    foreach ($kind in @('local', 'documents')) {
        $root = $profiles.official[$kind]
        if (Test-Path -LiteralPath $root -PathType Container) {
            foreach ($file in @(Get-ChildItem -LiteralPath $root -Recurse -File -Force | Sort-Object FullName)) {
                if ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'A profile snapshot must not traverse reparse points.' }
                $files[$kind + '/' + [IO.Path]::GetRelativePath($root, $file.FullName).Replace('\', '/')] = Hash $file.FullName
            }
        }
    }
    $files
}
function Assert-Same($Before, $After, [string] $Label) {
    if (($Before | ConvertTo-Json -Depth 20 -Compress) -cne ($After | ConvertTo-Json -Depth 20 -Compress)) { throw "$Label changed unexpectedly." }
}
function Invoke-CoexistMsi([string] $Operation, [string] $Target, [string] $LogName, [string] $Destination = '') {
    foreach ($value in @($Target, $Destination)) { if ($value.Contains('"')) { throw 'A native argument contains an unsupported quote.' } }
    $arguments = "$Operation `"$Target`" /qn /norestart REBOOT=ReallySuppress /L*V `"$(Join-Path $OutputDirectory $LogName)`""
    if ($Destination) { $arguments += " INSTALL_ROOT=`"$Destination`" WIXUI_EXITDIALOGOPTIONALCHECKBOX=0" }
    $process = Start-Process (Join-Path $env:SystemRoot 'System32/msiexec.exe') -ArgumentList $arguments -Wait -PassThru
    try { $exitCode = [int]$process.ExitCode } finally { $process.Dispose() }
    if ($exitCode -notin @(0, 3010)) { throw "msiexec $Operation failed with exit code $exitCode; see $LogName" }
    $exitCode
}
function Invoke-IsolatedVersion([string] $Executable, [string] $Name) {
    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) { throw "Installed executable missing: $Executable" }
    $start = [Diagnostics.ProcessStartInfo]::new(); $start.FileName = $Executable; $start.WorkingDirectory = Split-Path $Executable
    $start.UseShellExecute = $false; $start.CreateNoWindow = $true; $start.RedirectStandardOutput = $true; $start.RedirectStandardError = $true
    $start.ArgumentList.Add('--long-version')
    $start.Environment['PATH'] = (Split-Path $Executable) + ';' + (Join-Path $env:SystemRoot 'System32')
    foreach ($key in @($start.Environment.Keys)) { if ($key -match '^(?i:QT|QML|CMAKE_|VCPKG_|VSCMD_|VSINSTALLDIR$|VCINSTALLDIR$|VCTools|INCLUDE$|LIB$|LIBPATH$|WindowsSdk|UniversalCRTSdkDir$|UCRTVersion$|DevEnvDir$|Framework)') { [void]$start.Environment.Remove($key) } }
    $process = [Diagnostics.Process]::new(); $process.StartInfo = $start
    try {
        if (-not $process.Start()) { throw 'Version process did not start.' }
        $stdout = $process.StandardOutput.ReadToEndAsync(); $stderr = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(60000)) { $process.Kill($true); $process.WaitForExit(); throw 'Version check timed out.' }
        $text = $stdout.GetAwaiter().GetResult() + "`n" + $stderr.GetAwaiter().GetResult()
        [IO.File]::WriteAllText((Join-Path $OutputDirectory "$Name-version.log"), $text)
        if ($process.ExitCode -ne 0 -or $text -notmatch '(?i)Version\s+4\.7\.6(?:\D|$)') { throw "Unexpected $Name CLI version or exit code." }
        [pscustomobject]@{ exit_code = $process.ExitCode; output = $text; executable_sha256 = Hash $Executable; isolated_path = $start.Environment['PATH'] }
    } finally { $process.Dispose() }
}
function Invoke-SequentialGui([string] $Executable, [string] $Name) {
    & $GuiWrapperPath -Executable $Executable -ProbePath $GuiProbePath -OutputDirectory (Join-Path $OutputDirectory "gui-$Name")
    $gui = Get-Content -LiteralPath (Join-Path $OutputDirectory "gui-$Name/gui-report.json") -Raw | ConvertFrom-Json
    if ($gui.status -ne 'startup_observed_closed_cleanly' -or $gui.exit_status -ne 0) { throw "Requested $Name GUI observation did not close cleanly; runtime profile test remains unvalidated." }
    $gui
}

$installer = $null; $official = $null; $cadence = $null
$officialAttempted = $false; $cadenceAttempted = $false; $baselineAssociations = $null; $baselineProfile = $null
$officialDestination = Join-Path $OutputDirectory 'installed-official'; $cadenceDestination = Join-Path $OutputDirectory 'installed-cadence'
$errors = [Collections.Generic.List[string]]::new()
$report = [ordered]@{
    schema_version = 1; status = 'pending'; scope = 'Sequential Windows coexistence, default associations and official profile preservation'
    official_msi_sha256 = $lock.official.sha256; cadence_msi_sha256 = $lock.cadence.sha256
    official_metadata = $null; cadence_metadata = $null; profiles = $profiles; gui_requested = [bool]$EnableGui
    official_version = $null; cadence_version = $null; official_gui = $null; cadence_gui = $null
    official_profile_observed_before_sentinels = $null; cadence_profile_observed = $null; runtime_profile_isolation_observed = $false
    official_install_exit = $null; cadence_install_exit = $null; cadence_uninstall_exit = $null; official_uninstall_exit = $null
    after_cadence_install_preserved = $false; after_cadence_uninstall_preserved = $false
    official_removed = $false; cadence_removed = $false; errors = @()
    simultaneous_ipc_tested = $false; editing_tested = $false; listening_tested = $false; existing_user_profile_tested = $false
}
try {
    $installer = New-Object -ComObject WindowsInstaller.Installer
    $official = Get-CoexistenceMsiMetadata $installer $OfficialMsiPath; $cadence = Get-CoexistenceMsiMetadata $installer $CadenceMsiPath
    $report.official_metadata = $official; $report.cadence_metadata = $cadence
    if ($official.product_name -notmatch '^MuseScore(?: Studio)?(?:\s+4)?$' -or $official.product_version -notmatch '^4\.7\.6(?:\.|$)' -or $official.summary_template -notmatch '^x64(?:;|$)') { throw 'Authenticated official installer metadata is not the expected standalone MuseScore Studio x64 release.' }
    if ($cadence.product_name -ne 'Cadence Studio 4' -or $cadence.product_version -ne '4.7.6.7' -or $cadence.summary_template -notmatch '^x64(?:;|$)' -or $cadence.upgrade_code -ne $lock.cadence.upgrade_code -or $official.upgrade_code -eq $cadence.upgrade_code -or $official.product_code -eq $cadence.product_code) { throw 'Official and Cadence MSI identities must be independent and match the qualified versions.' }
    foreach ($metadata in @($official, $cadence)) {
        if ((Get-CoexistenceProductState $installer $metadata.product_code) -ne -1 -or @(Get-CoexistenceRelated $installer $metadata.upgrade_code).Count) { throw 'A matching product or upgrade family already exists; nothing will be installed or removed.' }
    }
    if (@(Get-CoexistenceProducts $installer | Where-Object { $_.product_name -match '(?i)MuseScore|Cadence' }).Count) { throw 'A score product is already registered; coexistence requires a fresh runner.' }
    foreach ($hive in @([Microsoft.Win32.RegistryHive]::LocalMachine, [Microsoft.Win32.RegistryHive]::CurrentUser)) {
        foreach ($view in @([Microsoft.Win32.RegistryView]::Registry64, [Microsoft.Win32.RegistryView]::Registry32)) {
            $baseKey = [Microsoft.Win32.RegistryKey]::OpenBaseKey($hive, $view); $key = $null
            try {
                $key = $baseKey.OpenSubKey('SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall', $false)
                if ($null -ne $key) { foreach ($subName in $key.GetSubKeyNames()) { $entry = $key.OpenSubKey($subName, $false); try { if ([string]$entry.GetValue('DisplayName', '') -match '(?i)MuseScore|Cadence') { throw 'An existing MuseScore/Cadence uninstall entry blocks this disposable-runner test.' } } finally { $entry.Dispose() } } }
            } finally { if ($null -ne $key) { $key.Dispose() }; $baseKey.Dispose() }
        }
    }
    foreach ($extension in @('.mscz', '.mscx')) { if ((Read-RegistryValues CurrentUser "SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\FileExts\$extension\UserChoice").exists) { throw 'Existing Windows UserChoice must not be overwritten; a fresh runner is required.' } }
    if (@(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -match '^(MuseScore4|CadenceStudio4)(Development)?$' }).Count) { throw 'An existing score process blocks the test; no existing process is stopped.' }
    New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
    $officialAttempted = $true
    $report.official_install_exit = Invoke-CoexistMsi '/i' $OfficialMsiPath 'official-install.log' $officialDestination
    if ((Get-CoexistenceProductState $installer $official.product_code) -notin @(3, 4, 5)) { throw 'Official MSI returned success without registering the exact product.' }
    $officialExe = Join-Path $officialDestination 'bin/MuseScore4.exe'
    $report.official_version = Invoke-IsolatedVersion $officialExe 'official'
    if ($EnableGui) { $report.official_gui = Invoke-SequentialGui $officialExe 'official' }
    $report.official_profile_observed_before_sentinels = [ordered]@{ ini = (Test-Path -LiteralPath $profiles.official.ini); local = (Test-Path -LiteralPath $profiles.official.local); documents = (Test-Path -LiteralPath $profiles.official.documents) }
    # These sentinels are owned by this fresh-runner test, never existing user data.
    New-Item -ItemType Directory -Path (Split-Path $profiles.official.ini), $profiles.official.local, $profiles.official.documents -Force | Out-Null
    Add-Content -LiteralPath $profiles.official.ini -Value ("`n[CadenceCoexistenceTest]`nSentinel=" + [guid]::NewGuid()) -Encoding utf8
    'Owned official app-data sentinel' | Set-Content -LiteralPath (Join-Path $profiles.official.local 'coexistence-owned.txt') -Encoding utf8
    '<score-partwise version="4.0"><part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list><part id="P1"><measure number="1"><attributes><divisions>1</divisions><time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes><note><rest/><duration>4</duration><type>whole</type></note></measure></part></score-partwise>' | Set-Content -LiteralPath (Join-Path $profiles.official.documents 'coexistence-owned.musicxml') -Encoding utf8
    $baselineAssociations = Association-Snapshot; $baselineProfile = Profile-Snapshot
    foreach ($extension in @('.mscz', '.mscx')) { if ([string]$baselineAssociations["ClassesRoot/$extension"].values[''].value -notmatch '^MuseScore\.') { throw 'Official MSI did not establish its expected file-class default on this fresh runner.' } }
    Write-Json $baselineAssociations 'associations-before-cadence.json'; Write-Json $baselineProfile 'official-profile-before-cadence.json'
    $cadenceAttempted = $true
    $report.cadence_install_exit = Invoke-CoexistMsi '/i' $CadenceMsiPath 'cadence-install.log' $cadenceDestination
    if ((Get-CoexistenceProductState $installer $cadence.product_code) -notin @(3, 4, 5)) { throw 'Cadence MSI returned success without registering the exact product.' }
    $cadenceExe = Join-Path $cadenceDestination 'bin/CadenceStudio4.exe'
    if ((Hash $cadenceExe) -ne $lock.cadence.executable_sha256) { throw 'Installed Cadence differs from the qualified actual executable.' }
    $report.cadence_version = Invoke-IsolatedVersion $cadenceExe 'cadence'
    if ($EnableGui) { $report.cadence_gui = Invoke-SequentialGui $cadenceExe 'cadence' }
    $report.cadence_profile_observed = [ordered]@{ ini = (Test-Path -LiteralPath $profiles.cadence.ini); local = (Test-Path -LiteralPath $profiles.cadence.local); documents = (Test-Path -LiteralPath $profiles.cadence.documents) }
    $report.runtime_profile_isolation_observed = $EnableGui -and $report.official_profile_observed_before_sentinels.ini -and $report.cadence_profile_observed.ini -and $report.official_profile_observed_before_sentinels.local -and $report.cadence_profile_observed.local
    if ($EnableGui -and -not $report.runtime_profile_isolation_observed) { throw 'The requested GUI run did not expose both expected independent INI/local-data profiles; runtime profile isolation remains unvalidated.' }
    $after = Association-Snapshot; $profileAfter = Profile-Snapshot
    Write-Json $after 'associations-with-cadence.json'; Write-Json $profileAfter 'official-profile-with-cadence.json'
    Assert-Same $baselineAssociations $after 'Official association/default snapshot'
    Assert-Same $baselineProfile $profileAfter 'Official settings and owned files'
    $openWith = [ordered]@{}
    foreach ($extension in @('.mscz', '.mscx')) {
        # The pinned release channel is "stable"; the actual WiX template uses
        # major.channel for nonempty channels, including a stable release.
        $valueName = "CadenceStudio$extension.4.stable"
        $values = Read-RegistryValues ClassesRoot "${extension}\OpenWithProgids"
        if (-not $values.values.Contains($valueName)) { throw "Cadence OpenWith ProgID missing: $valueName" }
        $command = Read-RegistryValues ClassesRoot "${valueName}\shell\open\command"
        if (-not $command.values[''].value.Contains($cadenceExe.Replace('/', '\'))) { throw 'Cadence ProgID does not point to its own installed executable.' }
        $openWith[$extension] = [ordered]@{ progid = $valueName; registration = $values; command = $command }
    }
    Write-Json $openWith 'cadence-openwith.json'
    $report.after_cadence_install_preserved = $true
} catch { $errors.Add($_.Exception.Message) }
finally {
    if ($cadenceAttempted -and $null -ne $cadence) {
        try {
            if ((Get-CoexistenceProductState $installer $cadence.product_code) -ne -1) { $report.cadence_uninstall_exit = Invoke-CoexistMsi '/x' $cadence.product_code 'cadence-uninstall.log' }
            $report.cadence_removed = (Get-CoexistenceProductState $installer $cadence.product_code) -eq -1
            if (-not $report.cadence_removed) { throw 'The new Cadence test product remains registered.' }
        } catch { $errors.Add($_.Exception.Message) }
    }
    # Check preservation while the official product is STILL installed.
    if ($null -ne $baselineAssociations -and $null -ne $baselineProfile) {
        try {
            $after = Association-Snapshot; $profileAfter = Profile-Snapshot
            Write-Json $after 'associations-after-cadence-uninstall.json'; Write-Json $profileAfter 'official-profile-after-cadence-uninstall.json'
            Assert-Same $baselineAssociations $after 'Official defaults after Cadence removal'
            Assert-Same $baselineProfile $profileAfter 'Official profile after Cadence removal'
            $report.after_cadence_uninstall_preserved = $true
        } catch { $errors.Add($_.Exception.Message) }
    }
    if ($officialAttempted -and $null -ne $official) {
        try {
            if ((Get-CoexistenceProductState $installer $official.product_code) -ne -1) { $report.official_uninstall_exit = Invoke-CoexistMsi '/x' $official.product_code 'official-uninstall.log' }
            $report.official_removed = (Get-CoexistenceProductState $installer $official.product_code) -eq -1
            if (-not $report.official_removed) { throw 'The new official test product remains registered.' }
        } catch { $errors.Add($_.Exception.Message) }
    }
    $report.errors = @($errors.ToArray())
    $report.status = if ($errors.Count -eq 0 -and $report.after_cadence_install_preserved -and $report.after_cadence_uninstall_preserved -and $report.cadence_removed -and $report.official_removed) { 'passed' } else { 'failed' }
    if (Test-Path -LiteralPath $OutputDirectory -PathType Container) { Write-Json $report 'coexistence-report.json' }
    Release-Com $installer
}
if ($report.status -ne 'passed') { throw ('Coexistence failed: ' + ($errors -join '; ')) }
Write-Host 'PASS: new official and Cadence installations coexist sequentially; official defaults/settings/files preserved before and after Cadence uninstall; both exact new ProductCodes removed.'
