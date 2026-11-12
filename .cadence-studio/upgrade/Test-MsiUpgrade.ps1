# SPDX-License-Identifier: GPL-3.0-only
#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $OldMsiPath,
    [Parameter(Mandatory)][string] $CandidateMsiPath,
    [Parameter(Mandatory)][string] $CandidateMsiSha256,
    [Parameter(Mandatory)][string] $CandidateExecutableSha256,
    [Parameter(Mandatory)][string] $CandidateMsiVersion,
    [Parameter(Mandatory)][string] $InputVerificationRecordPath,
    [Parameter(Mandatory)][string] $OutputDirectory
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (-not [OperatingSystem]::IsWindows() -or $env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitProcess -or
    [Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne 'X64' -or $env:GITHUB_ACTIONS -ne 'true' -or $env:CI -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted') {
    throw 'Upgrade qualification requires a disposable GitHub-hosted Windows x64 runner.'
}
if (-not $env:RUNNER_TEMP) { throw 'RUNNER_TEMP is required.' }
if ($CandidateMsiSha256 -cne '2d0d4b82ced312b22fea36470aec4c2677060135dd6cf8fb43bb25777953673e' -or
    $CandidateExecutableSha256 -cne '35d8b076cacddb8b37a4f23aeea9899e6ab4ac9214e9a5b1125bbeccf26cf39e' -or
    $CandidateMsiVersion -cne '4.7.6.2002') { throw 'Only the real retained MSI2002 and its measured executable are selected.' }
if ($CandidateMsiSha256 -notmatch '^[a-f0-9]{64}$' -or $CandidateExecutableSha256 -notmatch '^[a-f0-9]{64}$') { throw 'The actual candidate MSI and executable SHA-256 values are required.' }
if ($CandidateMsiVersion -notmatch '^4\.7\.6\.\d+$' -or ([version]$CandidateMsiVersion).Revision -lt 2000) { throw 'CandidateMsiVersion must be the actual 4.7.6 build numbered 2000 or higher.' }
. "$PSScriptRoot/MsiReadOnly.ps1"
$oldMsiHash = '9314306b8520d7480bdb57a270152c6329a8c39bb72e1070c9c14c1b8767a6aa'
$oldExeHash = '62987537161d89d9d0f2da6b9915b7f421a9718e288d7aa84a6b3f7dacfc0a34'
$family = '{319B992F-470A-465B-9A79-6B0CBFC7D6C7}'
if ($CandidateMsiSha256 -eq $oldMsiHash -or $CandidateExecutableSha256 -eq $oldExeHash) { throw 'The future candidate must identify its own MSI and executable, not the old build.' }
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
$tempRoot = [IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
if (-not $OutputDirectory.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $OutputDirectory)) { throw 'OutputDirectory must be new and strictly below RUNNER_TEMP.' }
function Hash([string] $Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Write-Json($Value, [string] $Name) { $Value | ConvertTo-Json -Depth 15 | Set-Content -LiteralPath (Join-Path $OutputDirectory $Name) -Encoding utf8 }
foreach($path in @($OldMsiPath,$CandidateMsiPath,$InputVerificationRecordPath,$OutputDirectory)) {
    $full=[IO.Path]::GetFullPath($path)
    if(-not $full.StartsWith($tempRoot,[StringComparison]::OrdinalIgnoreCase)){throw 'All authenticated input paths must be below RUNNER_TEMP.'}
    $current=$full
    while($current) {
        if((Test-Path -LiteralPath $current) -and ((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'Input reparse points are forbidden.'}
        $parent=[IO.Path]::GetDirectoryName($current.TrimEnd('\','/'));if(-not $parent -or $parent -eq $current){break};$current=$parent
    }
}
foreach($inputFile in @($OldMsiPath,$CandidateMsiPath,$InputVerificationRecordPath)) {
    $inputRoot=[IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($inputFile)).TrimEnd('\','/')+[IO.Path]::DirectorySeparatorChar
    if($OutputDirectory.StartsWith($inputRoot,[StringComparison]::OrdinalIgnoreCase) -or
       [IO.Path]::GetFullPath($inputFile).StartsWith($OutputDirectory.TrimEnd('\','/')+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw 'Output and immutable artifact/verification inputs must be separate.'}
}
$verified=Get-Content -LiteralPath $InputVerificationRecordPath -Raw -Encoding utf8 | ConvertFrom-Json
if($verified.status -ne 'passed' -or $verified.application_executed -ne $false -or $verified.installer_executed -ne $false -or
    $verified.old.artifact_id -ne 13720861986 -or $verified.old.run_id -ne 42721049351 -or
    $verified.candidate.artifact_id -ne 13902536112 -or $verified.candidate.run_id -ne 43123411562 -or
    [IO.Path]::GetFullPath($verified.old.msi_path) -ne [IO.Path]::GetFullPath($OldMsiPath) -or
    [IO.Path]::GetFullPath($verified.candidate.msi_path) -ne [IO.Path]::GetFullPath($CandidateMsiPath) -or
    $verified.old.msi_sha256 -ne $oldMsiHash -or $verified.candidate.msi_sha256 -ne $CandidateMsiSha256 -or
    $verified.old.executable_sha256 -ne $oldExeHash -or $verified.candidate.executable_sha256 -ne $CandidateExecutableSha256 -or
    $verified.candidate.source_commit -ne '0e05d04acbeee32f1b561f24493d7ef41c322081' -or
    $verified.candidate.source_tree -ne 'f95b7097a55dddf9c7f697fc826b95721071231a'){throw 'Complete authenticated input verification is required before MSI access.'}
if((Hash "$PSScriptRoot/fixtures/piano.musicxml") -ne '1b38cc5953cc56426976345411394c24d39e0ff22dbf6c350addcb68c770a3fb'){throw 'Original CC0 fixture digest differs.'}
foreach ($entry in @(@{path=$OldMsiPath;sha=$oldMsiHash}, @{path=$CandidateMsiPath;sha=$CandidateMsiSha256})) {
    if (-not (Test-Path -LiteralPath $entry.path -PathType Leaf) -or [IO.Path]::GetExtension($entry.path) -ine '.msi' -or (Hash $entry.path) -ne $entry.sha) { throw 'MSI bytes do not match the explicit qualified input SHA-256.' }
}
$documents = [Environment]::GetFolderPath([Environment+SpecialFolder]::MyDocuments)
if (-not $documents) { throw 'Documents known folder is unavailable.' }
$profileLocations = [ordered]@{
    ini = (Join-Path $env:APPDATA 'CadenceStudio/CadenceStudio4.ini')
    local = (Join-Path $env:LOCALAPPDATA 'CadenceStudio/CadenceStudio4')
    documents = (Join-Path $documents 'CadenceStudio4')
}
$protectedPaths = @($profileLocations.Values) + @((Join-Path $env:APPDATA 'MuseScore/MuseScore4.ini'), (Join-Path $env:LOCALAPPDATA 'MuseScore/MuseScore4'), (Join-Path $documents 'MuseScore4'))
foreach ($path in $protectedPaths) { if (Test-Path -LiteralPath $path) { throw "A score profile already exists: $path. Nothing will be installed or replaced." } }

function Get-ThreePartVersion([string] $Value) {
    if ($Value -notmatch '^\d+\.\d+\.\d+(?:\.\d+)?$') { throw 'Invalid MSI version bound.' }
    $version = [version]$Value
    [version]("{0}.{1}.{2}" -f $version.Major, $version.Minor, $version.Build)
}
function Read-UpgradeRules($Installer, [string] $Path) {
    $database = $null; $view = $null; $record = $null
    try {
        $database = Invoke-ComMethod $Installer 'OpenDatabase' @([IO.Path]::GetFullPath($Path), 0)
        $language = Get-MsiProperty $database 'ProductLanguage'
        $secure = Get-MsiProperty $database 'SecureCustomProperties'
        $rows = @()
        $view = Invoke-ComMethod $database 'OpenView' @('SELECT `UpgradeCode`,`VersionMin`,`VersionMax`,`Language`,`Attributes`,`Remove`,`ActionProperty` FROM `Upgrade`')
        [void](Invoke-ComMethod $view 'Execute')
        while ($null -ne ($record = Invoke-ComMethod $view 'Fetch')) {
            try {
                $rows += [pscustomobject][ordered]@{
                    upgrade_code = Normalize-Guid ([string](Get-ComValue $record 'StringData' @(1)))
                    version_min = [string](Get-ComValue $record 'StringData' @(2)); version_max = [string](Get-ComValue $record 'StringData' @(3))
                    language = [string](Get-ComValue $record 'StringData' @(4)); attributes = [int](Get-ComValue $record 'IntegerData' @(5))
                    remove_is_null = [bool](Get-ComValue $record 'IsNull' @(6)); remove = [string](Get-ComValue $record 'StringData' @(6))
                    action_property = [string](Get-ComValue $record 'StringData' @(7))
                }
            } finally { Release-Com $record; $record = $null }
        }
        [void](Invoke-ComMethod $view 'Close'); Release-Com $view; $view = $null
        $sequence = @()
        $view = Invoke-ComMethod $database 'OpenView' @('SELECT `Action`,`Condition`,`Sequence` FROM `InstallExecuteSequence`')
        [void](Invoke-ComMethod $view 'Execute')
        while ($null -ne ($record = Invoke-ComMethod $view 'Fetch')) {
            try {
                $action = [string](Get-ComValue $record 'StringData' @(1))
                if ($action -in @('FindRelatedProducts', 'RemoveExistingProducts')) {
                    $sequence += [pscustomobject]@{ action=$action; condition=[string](Get-ComValue $record 'StringData' @(2)); sequence=[int](Get-ComValue $record 'IntegerData' @(3)) }
                }
            } finally { Release-Com $record; $record = $null }
        }
        [pscustomobject]@{ product_language=$language; secure_custom_properties=$secure; upgrade_rows=$rows; execute_sequence=$sequence }
    } finally {
        if ($null -ne $view) { [void](Invoke-ComMethod $view 'Close') }
        Release-Com $record; Release-Com $view; Release-Com $database
    }
}
function Find-SameVersionRemovalRule($Rules, [string] $UpgradeCode, [string] $OldVersion, [string] $OldLanguage) {
    $oldThree = Get-ThreePartVersion $OldVersion
    foreach ($row in $Rules.upgrade_rows) {
        if ($row.upgrade_code -ne $UpgradeCode -or ($row.attributes -band 2) -or -not $row.action_property -or $row.action_property -notin ($Rules.secure_custom_properties -split ';')) { continue }
        if (-not $row.remove_is_null -and $row.remove -ne 'ALL') { continue }
        if ($row.language) {
            $listed = $OldLanguage -in @($row.language.Split(',') | ForEach-Object { $_.Trim() })
            if ((($row.attributes -band 1024) -ne 0 -and $listed) -or (($row.attributes -band 1024) -eq 0 -and -not $listed)) { continue }
        }
        if ($row.version_min) {
            $minimum = Get-ThreePartVersion $row.version_min
            if ($oldThree -lt $minimum -or ($oldThree -eq $minimum -and -not ($row.attributes -band 256))) { continue }
        }
        # This specifically proves AllowSameVersionUpgrades behavior for the
        # real MSI: an equal three-part upper bound must include equality.
        if (-not $row.version_max -or (Get-ThreePartVersion $row.version_max) -ne $oldThree -or -not ($row.attributes -band 512)) { continue }
        return $row
    }
    throw 'No actual Upgrade row allows removal of this same-three-part-version old product; a fourth-component increase alone does not qualify.'
}
function Invoke-OwnedMsi([string] $Operation, [string] $Target, [string] $LogName, [string] $Destination = '') {
    foreach ($value in @($Target, $Destination)) { if ($value.Contains('"')) { throw 'A native argument contains an unsupported quote.' } }
    $arguments = "$Operation `"$Target`" /qn /norestart REBOOT=ReallySuppress /L*V `"$(Join-Path $OutputDirectory $LogName)`""
    if ($Destination) { $arguments += " INSTALL_ROOT=`"$Destination`" WIXUI_EXITDIALOGOPTIONALCHECKBOX=0" }
    $entry=[ordered]@{operation=$Operation;target=$Target;log=$LogName;pid=$null;timeout_seconds=180;timed_out=$false;exit_code=$null;elapsed_seconds=$null}
    $report.operations+=$entry;$clock=[Diagnostics.Stopwatch]::StartNew()
    $start=[Diagnostics.ProcessStartInfo]::new();$start.FileName=Join-Path $env:SystemRoot 'System32/msiexec.exe';$start.Arguments=$arguments
    $start.UseShellExecute=$false;$start.CreateNoWindow=$true;$start.WorkingDirectory=$OutputDirectory
    $process=[Diagnostics.Process]::new();$process.StartInfo=$start
    try {
        if(-not $process.Start()){throw 'Owned msiexec client did not start.'}
        $entry.pid=$process.Id
        if(-not $process.WaitForExit(180000)) {$entry.timed_out=$true;$process.Kill();[void]$process.WaitForExit(10000);throw 'Owned msiexec client timed out; installer-service completion is not inferred.'}
        $exitCode=[int]$process.ExitCode;$entry.exit_code=$exitCode
    } finally {$entry.elapsed_seconds=$clock.Elapsed.TotalSeconds;$process.Dispose()}
    if ($exitCode -notin @(0, 3010)) { throw "msiexec $Operation failed with exit code $exitCode; see $LogName" }
    $exitCode
}
function Profile-Snapshot {
    $files = [ordered]@{}
    foreach ($kind in $profileLocations.Keys) {
        $root = $profileLocations[$kind]
        $items = if ($kind -eq 'ini') { @(Get-Item -LiteralPath $root) } else { @(Get-ChildItem -LiteralPath $root -Recurse -File -Force | Sort-Object FullName) }
        foreach ($file in $items) {
            if ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Owned profile snapshot must not include reparse points.' }
            $key = if ($kind -eq 'ini') { 'ini' } else { $kind + '/' + [IO.Path]::GetRelativePath($root, $file.FullName).Replace('\', '/') }
            $files[$key] = [ordered]@{ bytes=$file.Length; sha256=Hash $file.FullName }
        }
    }
    $files
}
function Assert-SameProfile($Before, $After) {
    if (($Before | ConvertTo-Json -Depth 5 -Compress) -cne ($After | ConvertTo-Json -Depth 5 -Compress)) { throw 'Owned INI, app-data or score copy changed during the MSI installation phase.' }
}
function Check-Version([string] $Executable, [string] $ExpectedHash, [string] $Name, [string] $ExpectedRevision) {
    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf) -or (Hash $Executable) -ne $ExpectedHash) { throw 'Installed executable does not match its actual build SHA-256.' }
    $start = [Diagnostics.ProcessStartInfo]::new(); $start.FileName=$Executable; $start.WorkingDirectory=Split-Path $Executable
    $start.UseShellExecute=$false; $start.CreateNoWindow=$true; $start.RedirectStandardOutput=$true; $start.RedirectStandardError=$true
    $start.ArgumentList.Add('--long-version'); $start.Environment['PATH']=(Split-Path $Executable)+';'+(Join-Path $env:SystemRoot 'System32')
    foreach ($key in @($start.Environment.Keys)) { if ($key -match '^(?i:QT|QML|CMAKE_|VCPKG_|VSCMD_|VSINSTALLDIR$|VCINSTALLDIR$|VCTools|INCLUDE$|LIB$|LIBPATH$|WindowsSdk|UniversalCRTSdkDir$|UCRTVersion$|DevEnvDir$|Framework)') { [void]$start.Environment.Remove($key) } }
    $process=[Diagnostics.Process]::new(); $process.StartInfo=$start
    try {
        if (-not $process.Start()) { throw 'Installed version process did not start.' }
        $stdout=$process.StandardOutput.ReadToEndAsync(); $stderr=$process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(30000)) { $process.Kill(); [void]$process.WaitForExit(10000); throw 'Installed version process timed out.' }
        $text=$stdout.GetAwaiter().GetResult()+"`n"+$stderr.GetAwaiter().GetResult()
        [IO.File]::WriteAllText((Join-Path $OutputDirectory "$Name-version.log"),$text)
        if ($process.ExitCode -ne 0 -or $text -notmatch '(?i)Version\s+4\.7\.6(?:\D|$)' -or
            $text -notmatch ('(?i)Build\s+'+[regex]::Escape($ExpectedRevision)+'(?:[a-f0-9]*)(?:\D|$)')) { throw 'Installed version/revision/exit code does not match the pinned application.' }
        [pscustomobject]@{ exit_code=$process.ExitCode; text=$text; executable_sha256=$ExpectedHash; path=$start.Environment['PATH'] }
    } finally { $process.Dispose() }
}

$installer=$null; $old=$null; $candidate=$null; $oldAttempted=$false; $newAttempted=$false
$ownedDestination=Join-Path $OutputDirectory 'installed'; $errors=[Collections.Generic.List[string]]::new()
$report=[ordered]@{
    schema_version=1; status='pending'; scope='Actual MSI upgrade and install-phase preservation of owned profile/score files; no GUI or historical profile migration'
    started_utc=[DateTime]::UtcNow.ToString('o');finished_utc=$null;operations=@();input_verification_sha256=Hash $InputVerificationRecordPath
    source_run_id=43123411562;source_artifact_id=13902536112;application_recompiled=$false
    old_msi_sha256=$oldMsiHash; candidate_msi_sha256=$CandidateMsiSha256; candidate_expected_executable_sha256=$CandidateExecutableSha256
    old_metadata=$null; candidate_metadata=$null; candidate_upgrade_rules=$null; accepted_removal_row=$null
    old_install_exit=$null; candidate_install_exit=$null; old_state_after_upgrade=$null; candidate_state_after_upgrade=$null; family_after_upgrade=@()
    one_candidate_only=$false; install_phase_profile_preserved=$false; input_files_unchanged=$false; old_version=$null; candidate_version=$null
    profile_locations=$profileLocations; profile_kind='Fresh test-owned INI/local sentinel and copy of CC0 score, not a historical GUI profile'
    candidate_uninstall_exit=$null; old_cleanup_exit=$null; candidate_removed=$false; old_removed=$false
    GUI_tested=$false; runtime_profile_migration_tested=$false; Windows10_or_11_consumer_tested=$false; errors=@()
}
try {
    $installer=New-Object -ComObject WindowsInstaller.Installer
    $old=Get-CoexistenceMsiMetadata $installer $OldMsiPath; $candidate=Get-CoexistenceMsiMetadata $installer $CandidateMsiPath
    $report.old_metadata=$old; $report.candidate_metadata=$candidate
    if ($old.product_name -ne 'Cadence Studio 4' -or $old.product_code -ne '{842A564D-92B8-5F7F-9626-0A29746ED9F2}' -or $old.product_version -ne '4.7.6.7' -or $old.upgrade_code -ne $family -or $old.summary_template -cne 'x64;1033' -or $old.product_language -ne '1033') { throw 'Old MSI identity differs from the qualified build7.' }
    if ($candidate.product_name -ne 'Cadence Studio 4' -or $candidate.product_code -ne '{6BF4BBA1-C7AA-5FCD-B5F2-14B7CF0D240C}' -or $candidate.product_version -ne $CandidateMsiVersion -or $candidate.upgrade_code -ne $family -or $candidate.product_code -eq $old.product_code -or $candidate.summary_template -cne 'x64;1033' -or $candidate.product_language -ne '1033') { throw 'Candidate must have the exact produced identity, same Cadence family and x64 platform.' }
    foreach ($metadata in @($old,$candidate)) { if ((Get-CoexistenceProductState $installer $metadata.product_code) -ne -1) { throw 'A target ProductCode is already registered; test must not touch it.' } }
    if (@(Get-CoexistenceRelated $installer $family).Count -or @(Get-CoexistenceProducts $installer | Where-Object {$_.product_name -match '(?i)Cadence|MuseScore'}).Count) { throw 'An existing score product or Cadence family blocks this fresh-runner ownership test.' }
    foreach ($hive in @([Microsoft.Win32.RegistryHive]::LocalMachine,[Microsoft.Win32.RegistryHive]::CurrentUser)) {
        foreach ($view in @([Microsoft.Win32.RegistryView]::Registry64,[Microsoft.Win32.RegistryView]::Registry32)) {
            $base=[Microsoft.Win32.RegistryKey]::OpenBaseKey($hive,$view);$key=$null
            try {$key=$base.OpenSubKey('SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',$false);if($null -ne $key){foreach($subName in $key.GetSubKeyNames()){$entry=$key.OpenSubKey($subName,$false);try{if([string]$entry.GetValue('DisplayName','') -match '(?i)Cadence|MuseScore'){throw 'Existing score uninstall entry blocks ownership of the test installations.'}}finally{$entry.Dispose()}}}}
            finally {if($null -ne $key){$key.Dispose()};$base.Dispose()}
        }
    }
    if (@(Get-Process -ErrorAction SilentlyContinue | Where-Object {$_.ProcessName -match '^(CadenceStudio4|MuseScore4)(Development)?$'}).Count) { throw 'An existing score process blocks this test; it will not be stopped.' }
    $rules=Read-UpgradeRules $installer $CandidateMsiPath
    $report.candidate_upgrade_rules=$rules
    $oldLanguage=$old.product_language
    $report.accepted_removal_row=Find-SameVersionRemovalRule $rules $family $old.product_version $oldLanguage
    $find=@($rules.execute_sequence | Where-Object {$_.action -eq 'FindRelatedProducts'})
    $remove=@($rules.execute_sequence | Where-Object {$_.action -eq 'RemoveExistingProducts'})
    if ($find.Count -ne 1 -or $remove.Count -ne 1 -or $find[0].sequence -le 0 -or $remove[0].sequence -le $find[0].sequence) { throw 'Candidate lacks the expected real related-product detection/removal execution sequence.' }
    New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
    Write-Json $rules 'candidate-upgrade-tables.json'
    $oldAttempted=$true
    $report.old_install_exit=Invoke-OwnedMsi '/i' $OldMsiPath 'old-install.log' $ownedDestination
    if ((Get-CoexistenceProductState $installer $old.product_code) -notin @(3,4,5)) { throw 'Old installation did not register its exact product.' }
    $exe=Join-Path $ownedDestination 'bin/CadenceStudio4.exe'
    $report.old_version=Check-Version $exe $oldExeHash 'old' 'a8f2b24'
    New-Item -ItemType Directory -Path (Split-Path $profileLocations.ini),$profileLocations.local,$profileLocations.documents -Force | Out-Null
    ("[CadenceUpgradeTest]`nOwnedNonce="+[guid]::NewGuid()) | Set-Content -LiteralPath $profileLocations.ini -Encoding utf8
    'Owned data preserved through MSI upgrade' | Set-Content -LiteralPath (Join-Path $profileLocations.local 'upgrade-owned.txt') -Encoding utf8
    Copy-Item -LiteralPath "$PSScriptRoot/fixtures/piano.musicxml" -Destination (Join-Path $profileLocations.documents 'upgrade-owned-piano.musicxml')
    $before=Profile-Snapshot;Write-Json $before 'profile-before-upgrade.json'
    $newAttempted=$true
    $report.candidate_install_exit=Invoke-OwnedMsi '/i' $CandidateMsiPath 'candidate-upgrade.log' $ownedDestination
    # Compare immediately after msiexec, before invoking the new executable.
    $after=Profile-Snapshot;Write-Json $after 'profile-after-install-before-launch.json';Assert-SameProfile $before $after
    $report.install_phase_profile_preserved=$true
    $report.old_state_after_upgrade=Get-CoexistenceProductState $installer $old.product_code
    $report.candidate_state_after_upgrade=Get-CoexistenceProductState $installer $candidate.product_code
    $report.family_after_upgrade=@(Get-CoexistenceRelated $installer $family)
    $remaining=@(Get-CoexistenceProducts $installer | Where-Object {$_.product_name -match '(?i)Cadence'})
    if ($report.old_state_after_upgrade -ne -1 -or $report.candidate_state_after_upgrade -notin @(3,4,5) -or $report.family_after_upgrade.Count -ne 1 -or $report.family_after_upgrade[0] -ne $candidate.product_code -or $remaining.Count -ne 1 -or $remaining[0].product_code -ne $candidate.product_code) { throw 'Upgrade did not replace the old product with exactly one registered candidate.' }
    $report.one_candidate_only=$true
    $report.candidate_version=Check-Version $exe $CandidateExecutableSha256 'candidate' 'dbca538'
    $final=Profile-Snapshot;Write-Json $final 'profile-after-version-check.json';Assert-SameProfile $before $final
} catch {$errors.Add($_.Exception.Message)}
finally {
    foreach ($entry in @(@{attempted=$newAttempted;metadata=$candidate;name='candidate'},@{attempted=$oldAttempted;metadata=$old;name='old'})) {
        if (-not $entry.attempted -or $null -eq $entry.metadata) {continue}
        try {
            if ((Get-CoexistenceProductState $installer $entry.metadata.product_code) -ne -1) {
                $code=Invoke-OwnedMsi '/x' $entry.metadata.product_code ($entry.name+'-uninstall.log')
                if ($entry.name -eq 'candidate') {$report.candidate_uninstall_exit=$code}else{$report.old_cleanup_exit=$code}
            }
            $removed=(Get-CoexistenceProductState $installer $entry.metadata.product_code) -eq -1
            if ($entry.name -eq 'candidate') {$report.candidate_removed=$removed}else{$report.old_removed=$removed}
            if (-not $removed) {throw ('New test product remains registered: '+$entry.name)}
        } catch {$errors.Add($_.Exception.Message)}
    }
    try {
        $report.input_files_unchanged=(Hash $OldMsiPath) -eq $oldMsiHash -and (Hash $CandidateMsiPath) -eq $CandidateMsiSha256 -and
            (Hash "$PSScriptRoot/fixtures/piano.musicxml") -eq '1b38cc5953cc56426976345411394c24d39e0ff22dbf6c350addcb68c770a3fb' -and
            (Hash $InputVerificationRecordPath) -eq $report.input_verification_sha256
        if(-not $report.input_files_unchanged){throw 'Immutable MSI/corpus/verification input bytes changed during qualification.'}
    } catch {$errors.Add($_.Exception.Message)}
    $report.errors=@($errors.ToArray())
    $report.finished_utc=[DateTime]::UtcNow.ToString('o')
    $report.status=if($errors.Count -eq 0 -and $report.one_candidate_only -and $report.install_phase_profile_preserved -and $report.candidate_removed -and $report.old_removed){'passed'}else{'failed'}
    if(Test-Path -LiteralPath $OutputDirectory -PathType Container){Write-Json $report 'msi-upgrade-report.json'}
    Release-Com $installer
}
if($report.status -ne 'passed'){throw ('Upgrade qualification failed: '+($errors -join '; '))}
Write-Host 'PASS: old product replaced by exactly one candidate, expected new executable verified, owned profile/score bytes preserved during INSTALL, and only exact new test products removed.'
