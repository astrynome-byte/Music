# SPDX-License-Identifier: GPL-3.0-only
# Opens only the authenticated retained application on a disposable hosted runner.
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $StagePath,
    [Parameter(Mandatory)][string] $ProbePath,
    [Parameter(Mandatory)][string] $OutputDirectory,
    [Parameter(Mandatory)][ValidatePattern('^[a-f0-9]{64}$')][string] $ExpectedExecutableSha256,
    [ValidatePattern('^Cadence-QA-[A-Za-z0-9-]{1,50}$')][string] $CollectionName = 'Cadence-QA-2005',
    [switch] $ExerciseAdd,
    [switch] $VerifyRestartOpen
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if (-not $ExerciseAdd -or -not $VerifyRestartOpen) { throw 'This candidate probe requires the complete Add/favorite/collections/restart/Open exercise.' }
if ($VerifyRestartOpen -and -not $ExerciseAdd) { throw 'Restart verification requires the same invocation to create and validate its controlled fixture first.' }
if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitProcess -or
    $env:GITHUB_ACTIONS -ne 'true' -or $env:CI -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted') {
    throw 'Library UI inspection is restricted to disposable hosted Windows x64 CI.'
}
if (-not $env:RUNNER_TEMP -or -not [Environment]::UserInteractive -or [Diagnostics.Process]::GetCurrentProcess().SessionId -eq 0) {
    throw 'An interactive disposable runner desktop is required; no application was started.'
}
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
$temporaryRoot = [IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
if (-not $OutputDirectory.StartsWith($temporaryRoot, [StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $OutputDirectory)) {
    throw 'OutputDirectory must be a new directory strictly below RUNNER_TEMP.'
}
$executable = [IO.Path]::GetFullPath((Join-Path $StagePath 'bin/CadenceStudio4.exe'))
$ProbePath = [IO.Path]::GetFullPath($ProbePath)
if (-not (Test-Path -LiteralPath $executable -PathType Leaf) -or -not (Test-Path -LiteralPath $ProbePath -PathType Leaf)) { throw 'Real retained executable and native probe are required.' }
if ((Get-FileHash -LiteralPath $executable -Algorithm SHA256).Hash.ToLowerInvariant() -cne $ExpectedExecutableSha256) { throw 'Actual retained2005 executable differs from the reviewed target SHA; nothing was started.' }
$known = @('CadenceStudio4','CadenceStudio4Development','MuseScore4','MuseScore4Development','MuseScoreStudio4')
if (@(Get-Process | Where-Object { $_.ProcessName -in $known }).Count) { throw 'A score application already exists. Nothing was started or closed.' }
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
$treeDirectory = Join-Path $OutputDirectory 'uia'
New-Item -ItemType Directory -Path $treeDirectory | Out-Null
$report = [ordered]@{
    schema_version = 1; status = 'pending'; scope = 'Owned PID UIA inspection and semantic navigation, real collection UI with auxiliary read-only catalogue verification, never score editing'
    executable = $executable; executable_sha256 = (Get-FileHash $executable -Algorithm SHA256).Hash.ToLowerInvariant()
    probe = $ProbePath; probe_sha256 = (Get-FileHash $ProbePath -Algorithm SHA256).Hash.ToLowerInvariant()
    started_utc = [DateTime]::UtcNow.ToString('o'); pid = $null; probe_exit_code = $null; native_probe_status = $null
    profile_isolated_by_script = $false; hosted_disposable_profile = $true
    profile_seeded_by_script = $false; onboarding_tested = $false
    qa_precondition = 'A new Cadence-only profile with introduction already completed; this does not validate onboarding'
    action_policy = 'Owned source-backed section/panel navigation; Return only on an exact UIA-focused Library/Add/favorite/Open control; optional native file dialogue selects only the controlled copy; foreground and Win32 focus PID verified for every key'
    captures = @(); cleanup = [ordered]@{ forced = $false; exit_code = $null; events = @(); error = $null }
    library_content_observed = $false; score_editing_tested = $false; favorites_tested = $false
    exercise_add_requested = $ExerciseAdd.IsPresent; fixture = $null; catalog_validation = $null; catalog_actual_snapshot_path = $null
    score_added_control_observed = $false; favorite_action_delivered = $false; favorite_remove_label_observed = $false
    probe_cleanup_forced = $false
    collection_name = $CollectionName; collections_tested = $false
    collections_enabled_observed = $false; collection_created_control_observed = $false
    collection_member_control_observed = $false; collection_filter_observed = $false
    error = $null
}
Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class CadenceLibraryWindowNative {
 public delegate bool Callback(IntPtr window,IntPtr state);
 [StructLayout(LayoutKind.Sequential)] public struct Rect { public int Left,Top,Right,Bottom; }
 [DllImport("user32.dll")] static extern bool EnumWindows(Callback cb,IntPtr state);
 [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr window,out uint pid);
 [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr window);
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr window,out Rect rect);
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr window);
 [DllImport("user32.dll",SetLastError=true)] static extern bool PostMessage(IntPtr window,uint msg,IntPtr w,IntPtr l);
 public static bool Owned(IntPtr window,int expectedPid) { uint pid;return window!=IntPtr.Zero&&GetWindowThreadProcessId(window,out pid)!=0&&pid==(uint)expectedPid; }
 public static IntPtr[] Windows(int expectedPid) {
  var list=new List<IntPtr>();EnumWindows((w,s)=>{if(Owned(w,expectedPid)&&IsWindowVisible(w))list.Add(w);return true;},IntPtr.Zero);return list.ToArray();
 }
 public static bool CloseOwned(IntPtr window,int expectedPid) {
  return Owned(window,expectedPid)&&PostMessage(window,0x0010,IntPtr.Zero,IntPtr.Zero);
 }
}
'@
function Capture-OwnedWindow([string] $Name, $Process, [string] $CaptureDirectory = $OutputDirectory, $CaptureReport = $report) {
    try {
        $Process.Refresh()
        if ($Process.HasExited) { throw 'Owned process has exited.' }
        $best = [IntPtr]::Zero; [long]$area = 0
        foreach ($window in @([CadenceLibraryWindowNative]::Windows($Process.Id))) {
            $rect = [CadenceLibraryWindowNative+Rect]::new()
            if ([CadenceLibraryWindowNative]::GetWindowRect($window,[ref]$rect)) {
                [long]$candidate = ([long]$rect.Right-$rect.Left)*([long]$rect.Bottom-$rect.Top)
                if ($candidate -gt $area) { $area=$candidate;$best=$window }
            }
        }
        if ($best -eq [IntPtr]::Zero -or $area -gt 12000000 -or -not [CadenceLibraryWindowNative]::Owned($best,$Process.Id)) { throw 'No bounded owned capture window.' }
        [void][CadenceLibraryWindowNative]::SetForegroundWindow($best)
        $rect = [CadenceLibraryWindowNative+Rect]::new()
        if (-not [CadenceLibraryWindowNative]::Owned($best,$Process.Id) -or -not [CadenceLibraryWindowNative]::GetWindowRect($best,[ref]$rect)) { throw 'Owned rectangle unavailable.' }
        Add-Type -AssemblyName System.Drawing
        $bitmap = [Drawing.Bitmap]::new(($rect.Right-$rect.Left),($rect.Bottom-$rect.Top))
        try {
            $graphics=[Drawing.Graphics]::FromImage($bitmap)
            try { $graphics.CopyFromScreen($rect.Left,$rect.Top,0,0,$bitmap.Size) } finally { $graphics.Dispose() }
            $path=Join-Path $CaptureDirectory $Name
            $bitmap.Save($path,[Drawing.Imaging.ImageFormat]::Png)
            $CaptureReport.captures += [ordered]@{ status='saved_requires_visual_review';path=$path;sha256=(Get-FileHash $path -Algorithm SHA256).Hash.ToLowerInvariant();pid=$Process.Id;method='desktop_pixels_cropped_to_owned_window' }
        } finally { $bitmap.Dispose() }
    } catch { $CaptureReport.captures += [ordered]@{ status='unavailable';error=$_.Exception.Message } }
}
function Save-CadenceApplicationLogEvidence([string] $CadenceDataRoot, [string] $EvidenceDirectory, [int] $OwnedPid) {
    # This exact profile was absent before this invocation. Never search another
    # profile or a score folder to obtain a missing diagnostic.
    $document=[ordered]@{schema_version=1;status='unavailable';owned_pid_context=$OwnedPid;source='fresh Cadence-only profile logs after owned process cleanup';file_pid_attribution_inferred=$false;files=@();notes=@();application_validation_inferred=$false}
    try {
        if(-not [IO.Path]::IsPathFullyQualified($CadenceDataRoot) -or [IO.Path]::GetFileName($CadenceDataRoot.TrimEnd('\','/')) -cne 'CadenceStudio') { throw 'Only the exact fresh Cadence data root is permitted.' }
        $applicationRoot=Join-Path $CadenceDataRoot 'CadenceStudio4'
        $logRoot=Join-Path $applicationRoot 'logs'
        foreach($directory in @($CadenceDataRoot,$applicationRoot,$logRoot)) {
            $item=Get-Item -LiteralPath $directory
            if(-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'The fresh Cadence log directory must be a plain directory.' }
        }
        $files=@(Get-ChildItem -LiteralPath $logRoot -File -Filter '*.log' |
            Where-Object { -not ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) } |
            Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 4)
        foreach($file in $files) {
            $stream=[IO.File]::Open($file.FullName,[IO.FileMode]::Open,[IO.FileAccess]::Read,([IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete))
            try {
                $length=$stream.Length
                [void]$stream.Seek([Math]::Max(0L,$length-16384L),[IO.SeekOrigin]::Begin)
                $bytes=[byte[]]::new([int][Math]::Min(16384L,$length))
                $count=0
                while($count -lt $bytes.Length) { $part=$stream.Read($bytes,$count,$bytes.Length-$count);if($part -eq 0){break};$count+=$part }
                if($count -eq 0){$tail=[byte[]]::new(0)}else{$tail=[byte[]]$bytes[0..($count-1)]}
            } finally { $stream.Dispose() }
            $document.files += [ordered]@{name=$file.Name;file_bytes=$length;tail_bytes=$count;tail_only=$length -gt $count;tail_sha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([byte[]]$tail)).ToLowerInvariant();text=[Text.Encoding]::UTF8.GetString([byte[]]$tail);last_write_utc=$file.LastWriteTimeUtc.ToString('o')}
        }
        $document.status=if($files.Count){'bounded_log_tails_collected'}else{'no_log_files_observed'}
    } catch { $document.notes += $_.Exception.Message }
    $document|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $EvidenceDirectory 'application-log-tails.json') -Encoding utf8
}
function Test-OwnedRestartAndOpen($StartInformation, $FirstReport, [string] $CataloguePath) {
    $restartDirectory=Join-Path $OutputDirectory 'restart-check'
    $restartTree=Join-Path $restartDirectory 'uia'
    if (Test-Path -LiteralPath $restartDirectory) { throw 'Restart evidence directory must be new.' }
    New-Item -ItemType Directory -Path $restartTree | Out-Null
    $result=[ordered]@{ collection_restored_control_observed=$false; schema_version=1;status='pending';scope='Restart the same owned disposable Cadence profile and open only its controlled copy';pid=$null;probe_exit_code=$null;native_probe_status=$null;captures=@();cleanup=[ordered]@{forced=$false;exit_code=$null;error=$null;events=@()};probe_cleanup_forced=$false;favorite_restored_control_observed=$false;score_open_requested=$false;score_editor_title_observed=$false;score_editor_title=$null;catalogue_unchanged=$false;fixture_unchanged=$false;source_unchanged=$false;score_editing_tested=$false;musical_content_visual_review_required=$true;error=$null }
    $ownedApp=$null;$ownedProbe=$null;$appOut=$null;$appErr=$null
    try {
        if (@(Get-Process | Where-Object { $_.ProcessName -in $known }).Count) { throw 'A score process exists before the owned restart; nothing else was closed.' }
        if ((Get-FileHash -LiteralPath $executable -Algorithm SHA256).Hash.ToLowerInvariant() -cne $ExpectedExecutableSha256) { throw 'The retained executable changed before the owned restart.' }
        if (-not $FirstReport.favorites_tested -or $FirstReport.catalog_validation.status -ne 'passed' -or
            (Get-FileHash $CataloguePath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $FirstReport.catalog_validation.sha256 -or
            (Get-FileHash $FirstReport.fixture.copy_path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $FirstReport.fixture.sha256_before) { throw 'First-phase catalogue/copy preconditions changed before restart.' }
        $ownedApp=[Diagnostics.Process]::new();$ownedApp.StartInfo=$StartInformation
        if (-not $ownedApp.Start()) { throw 'Owned restart process did not start.' }
        $result.pid=$ownedApp.Id;$appOut=$ownedApp.StandardOutput.ReadToEndAsync();$appErr=$ownedApp.StandardError.ReadToEndAsync()
        $clock=[Diagnostics.Stopwatch]::StartNew()
        while ($clock.Elapsed.TotalSeconds -lt 35) {
            $ownedApp.Refresh();if($ownedApp.HasExited){throw 'Restarted application exited before inspection.'}
            if(@([CadenceLibraryWindowNative]::Windows($ownedApp.Id)).Count){break}
            Start-Sleep -Milliseconds 200
        }
        $probeInfo=[Diagnostics.ProcessStartInfo]::new();$probeInfo.FileName=$ProbePath;$probeInfo.UseShellExecute=$false
        $probeInfo.RedirectStandardOutput=$true;$probeInfo.RedirectStandardError=$true
        foreach($argument in @('--pid',[string]$ownedApp.Id,'--output',$restartTree,'--fixture-root',[string]$FirstReport.fixture.copy_root,'--verify-fixture',[string]$FirstReport.fixture.copy_path,'--expected-title',[string]$FirstReport.fixture.title,'--collection-name',$CollectionName)){$probeInfo.ArgumentList.Add($argument)}
        $ownedProbe=[Diagnostics.Process]::new();$ownedProbe.StartInfo=$probeInfo
        if(-not $ownedProbe.Start()){throw 'Restart UIA client did not start.'}
        $probeOut=$ownedProbe.StandardOutput.ReadToEndAsync();$probeErr=$ownedProbe.StandardError.ReadToEndAsync()
        if(-not $ownedProbe.WaitForExit(180000)){$ownedProbe.Kill($true);$ownedProbe.WaitForExit();throw 'Restart UIA client timed out.'}
        $result.probe_exit_code=$ownedProbe.ExitCode
        [IO.File]::WriteAllText((Join-Path $restartDirectory 'probe.stdout.log'),$probeOut.GetAwaiter().GetResult())
        [IO.File]::WriteAllText((Join-Path $restartDirectory 'probe.stderr.log'),$probeErr.GetAwaiter().GetResult())
        $native=Get-Content -LiteralPath (Join-Path $restartTree 'uia-report.json') -Raw|ConvertFrom-Json
        if($native.pid -ne $ownedApp.Id){throw 'Restart client inspected a different PID.'}
        $result.native_probe_status=$native.status
        $result.collection_restored_control_observed=$native.collection_restored_control_observed
        $result.favorite_restored_control_observed=$native.favorite_restored_control_observed
        $result.score_open_requested=$native.score_open_requested
        $result.score_editor_title_observed=$native.score_editor_title_observed
        $result.score_editor_title=$native.score_editor_title
        $ownedApp.Refresh();if($ownedApp.HasExited){throw 'Restarted app exited before its score capture.'}
        Start-Sleep -Milliseconds 500
        Capture-OwnedWindow 'after-restart-open.png' $ownedApp $restartDirectory $result
        if($ownedProbe.ExitCode -ne 0 -or -not $result.collection_restored_control_observed -or -not $result.favorite_restored_control_observed -or -not $result.score_open_requested -or -not $result.score_editor_title_observed){throw 'Restart/favorite/Open did not satisfy the actual UI criteria.'}
    } catch { $result.error=$_.Exception.Message }
    finally {
        if($null -ne $ownedProbe){
            try{$ownedProbe.Refresh();if(-not $ownedProbe.HasExited){$result.probe_cleanup_forced=$true;$ownedProbe.Kill($true);[void]$ownedProbe.WaitForExit(5000)}}catch{if(-not $result.error){$result.error=$_.Exception.Message}}
            finally{$ownedProbe.Dispose()}
        }
        if($null -ne $ownedApp){
            try{
                $closing=[Diagnostics.Stopwatch]::StartNew()
                while($closing.Elapsed.TotalSeconds -lt 12){
                    $ownedApp.Refresh();if($ownedApp.HasExited){break}
                    foreach($window in @([CadenceLibraryWindowNative]::Windows($ownedApp.Id))){
                        $ownedApp.Refresh();if($ownedApp.HasExited){break}
                        $posted=[CadenceLibraryWindowNative]::CloseOwned($window,$ownedApp.Id)
                        $result.cleanup.events += [ordered]@{pid=$ownedApp.Id;handle=$window.ToInt64();posted=$posted}
                    }
                    if($ownedApp.WaitForExit(250)){break}
                }
                $ownedApp.Refresh()
                if(-not $ownedApp.HasExited){$result.cleanup.forced=$true;$ownedApp.Kill($true);[void]$ownedApp.WaitForExit(5000)}
                $result.cleanup.exit_code=$ownedApp.ExitCode
                [IO.File]::WriteAllText((Join-Path $restartDirectory 'application.stdout.log'),$appOut.GetAwaiter().GetResult())
                [IO.File]::WriteAllText((Join-Path $restartDirectory 'application.stderr.log'),$appErr.GetAwaiter().GetResult())
            }catch{$result.cleanup.error=$_.Exception.Message}
            finally{$ownedApp.Dispose()}
        }
        if($FirstReport.profile_seeded_by_script){Save-CadenceApplicationLogEvidence $localDataDirectory $restartDirectory $result.pid}
        try{
            $result.fixture_unchanged=(Get-FileHash $FirstReport.fixture.copy_path -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $FirstReport.fixture.sha256_before
            $result.source_unchanged=(Get-FileHash $FirstReport.fixture.source_path -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $FirstReport.fixture.source_sha256_before
            $result.catalogue_unchanged=(Get-FileHash $CataloguePath -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $FirstReport.catalog_validation.sha256
            [IO.File]::Copy($CataloguePath,(Join-Path $restartDirectory 'catalog-after-ui.json'),$false)
            if(-not $result.fixture_unchanged -or -not $result.source_unchanged -or -not $result.catalogue_unchanged){throw 'Source, musical copy or favourite catalogue changed across restart/Open.'}
        }catch{if(-not $result.error){$result.error=$_.Exception.Message}}
        $clean= -not $result.error -and -not $result.cleanup.error -and -not $result.cleanup.forced -and -not $result.probe_cleanup_forced -and $result.cleanup.exit_code -eq 0
        $result.status=if($clean -and $result.collection_restored_control_observed -and $result.favorite_restored_control_observed -and $result.score_open_requested -and $result.score_editor_title_observed){'favorite_restored_and_editor_title_observed_after_open'}else{'failed_restart_or_open_validation'}
        $result|ConvertTo-Json -Depth 12|Set-Content -LiteralPath (Join-Path $restartDirectory 'library-restart-report.json') -Encoding utf8
    }
    return $result
}
$app = $null; $probe = $null; $stdout = $null; $stderr = $null; $fixtureCopyPath = $null
try {
    # QSettings uses IniFormat and the CadenceStudio/CadenceStudio4 identity.
    # This is a test precondition on a disposable hosted profile, never a change
    # to MuseScore settings or a claim that the first-launch wizard was tested.
    $roamingBase = [Environment]::GetFolderPath([Environment+SpecialFolder]::ApplicationData)
    $localBase = [Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
    $userRoot = [IO.Path]::GetFullPath([Environment]::GetFolderPath([Environment+SpecialFolder]::UserProfile)).TrimEnd('\','/') + [IO.Path]::DirectorySeparatorChar
    foreach ($base in @($roamingBase, $localBase)) {
        if (-not [IO.Path]::IsPathFullyQualified($base) -or -not ([IO.Path]::GetFullPath($base) + [IO.Path]::DirectorySeparatorChar).StartsWith($userRoot,[StringComparison]::OrdinalIgnoreCase)) {
            throw 'Standard profile folders must belong to the disposable runner user.'
        }
    }
    $configurationDirectory = Join-Path $roamingBase 'CadenceStudio'
    $localDataDirectory = Join-Path $localBase 'CadenceStudio'
    $settingsPath = Join-Path $configurationDirectory 'CadenceStudio4.ini'
    if ((Test-Path -LiteralPath $configurationDirectory) -or (Test-Path -LiteralPath $localDataDirectory) -or (Test-Path -LiteralPath $settingsPath)) {
        throw 'A Cadence profile or settings file already exists; it was left unchanged and no application was started.'
    }
    New-Item -ItemType Directory -Path $configurationDirectory | Out-Null
    $settingsBytes = [Text.UTF8Encoding]::new($false).GetBytes("[application]`r`nhasCompletedFirstLaunchSetup=true`r`n")
    $settingsStream = [IO.File]::Open($settingsPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    try { $settingsStream.Write($settingsBytes,0,$settingsBytes.Length) } finally { $settingsStream.Dispose() }
    $report.profile_seeded_by_script = $true
    $report.profile_precondition = [ordered]@{ settings_path=$settingsPath;settings_sha256=(Get-FileHash $settingsPath -Algorithm SHA256).Hash.ToLowerInvariant();settings_bytes=$settingsBytes.Length;cadence_roaming_directory_was_absent=$true;cadence_local_directory_was_absent=$true;hasCompletedFirstLaunchSetup=$true;musescore_profile_touched=$false;scope='Fresh Cadence-only settings in a disposable hosted runner user profile, not an isolated Windows user and not a first-launch test' }
    if ($ExerciseAdd) {
        $fixtureSourceDirectory = Join-Path $PSScriptRoot 'fixtures'
        $manifest = Get-Content -LiteralPath (Join-Path $fixtureSourceDirectory 'manifest.json') -Raw | ConvertFrom-Json
        $pianoEntries = @($manifest.fixtures | Where-Object { $_.id -eq 'piano' })
        $expectedFixtureHash = '10ae5eb1fae2679d9ad32aa0b721fef06119ef24b78b4f8b9bd6b770582c289f'
        if ($manifest.license -ne 'CC0-1.0' -or $pianoEntries.Count -ne 1) { throw 'Exactly one CC0 piano fixture is required.' }
        $piano = $pianoEntries[0]
        if ($piano.path -cne 'piano-uia-copy.mscx' -or $piano.sha256 -cne $expectedFixtureHash -or $piano.bytes -ne 10586 -or
            $piano.title -cne 'Piano : voix, accords et triolets' -or $piano.composer -cne 'Cadence regression corpus') { throw 'Unexpected controlled fixture identity.' }
        $fixtureSourcePath = Join-Path $fixtureSourceDirectory 'piano-uia-copy.mscx'
        $sourceHash = (Get-FileHash $fixtureSourcePath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($sourceHash -cne $expectedFixtureHash -or (Get-Item -LiteralPath $fixtureSourcePath).Length -ne 10586) { throw 'Source fixture bytes do not match the immutable reference copy.' }
        $fixtureCopyRoot = Join-Path $OutputDirectory 'controlled-score-copies'
        New-Item -ItemType Directory -Path $fixtureCopyRoot | Out-Null
        $fixtureCopyPath = Join-Path $fixtureCopyRoot 'piano-uia-copy.mscx'
        Copy-Item -LiteralPath $fixtureSourcePath -Destination $fixtureCopyPath
        $copyHash = (Get-FileHash $fixtureCopyPath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($copyHash -cne $expectedFixtureHash -or (Get-FileHash $fixtureSourcePath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $sourceHash) { throw 'Fixture copy or unchanged-source check failed.' }
        $report.fixture = [ordered]@{ source_path=$fixtureSourcePath;copy_root=$fixtureCopyRoot;copy_path=$fixtureCopyPath;sha256_before=$copyHash;source_sha256_before=$sourceHash;title=$piano.title;composer=$piano.composer;license='CC0-1.0';only_copy_passed_to_UI=$true;source_unchanged_after_copy=$true }
    }
    $start=[Diagnostics.ProcessStartInfo]::new()
    $start.FileName=$executable;$start.WorkingDirectory=Split-Path -Parent $executable
    $start.UseShellExecute=$false;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
    foreach ($arg in @('--test-mode','--session-type','start-empty')) { $start.ArgumentList.Add($arg) }
    $start.Environment['PATH']=(Split-Path -Parent $executable)+';'+(Join-Path $env:SystemRoot 'System32')
    foreach ($key in @($start.Environment.Keys)) {
        if ($key -match '^(?i:QT|QML|CMAKE_|VCPKG_|VSCMD_|VSINSTALLDIR$|VCINSTALLDIR$|VCTools|INCLUDE$|LIB$|LIBPATH$|WindowsSdk|WindowsSDK|UniversalCRTSdkDir$|UCRTVersion$|DevEnvDir$|ExtensionSdkDir$|FrameworkDir|FrameworkVersion)') { [void]$start.Environment.Remove($key) }
    }
    $start.Environment['QT_ACCESSIBILITY']='1'
    $app=[Diagnostics.Process]::new();$app.StartInfo=$start
    if (-not $app.Start()) { throw 'Application process did not start.' }
    $report.pid=$app.Id;$stdout=$app.StandardOutput.ReadToEndAsync();$stderr=$app.StandardError.ReadToEndAsync()
    $clock=[Diagnostics.Stopwatch]::StartNew()
    while ($clock.Elapsed.TotalSeconds -lt 35) {
        $app.Refresh();if ($app.HasExited) { throw 'Application exited before inspection.' }
        if (@([CadenceLibraryWindowNative]::Windows($app.Id)).Count) { break }
        Start-Sleep -Milliseconds 200
    }
    Capture-OwnedWindow 'before-navigation.png' $app
    $probeStart=[Diagnostics.ProcessStartInfo]::new();$probeStart.FileName=$ProbePath;$probeStart.UseShellExecute=$false
    $probeStart.RedirectStandardOutput=$true;$probeStart.RedirectStandardError=$true
    foreach ($arg in @('--pid',[string]$app.Id,'--output',$treeDirectory)) { $probeStart.ArgumentList.Add($arg) }
    if ($ExerciseAdd) {
        foreach ($arg in @('--fixture-root',$fixtureCopyRoot,'--add-fixture',$fixtureCopyPath,'--expected-title',[string]$report.fixture.title,'--collection-name',$CollectionName)) { $probeStart.ArgumentList.Add($arg) }
    }
    $probe=[Diagnostics.Process]::new();$probe.StartInfo=$probeStart
    if (-not $probe.Start()) { throw 'Native UIA inspector did not start.' }
    $probeOut=$probe.StandardOutput.ReadToEndAsync();$probeErr=$probe.StandardError.ReadToEndAsync()
    if (-not $probe.WaitForExit(180000)) { $probe.Kill($true);$probe.WaitForExit();throw 'UIA inspector timed out; only its owned process tree was stopped.' }
    $report.probe_exit_code=$probe.ExitCode
    [IO.File]::WriteAllText((Join-Path $OutputDirectory 'probe.stdout.log'),$probeOut.GetAwaiter().GetResult())
    [IO.File]::WriteAllText((Join-Path $OutputDirectory 'probe.stderr.log'),$probeErr.GetAwaiter().GetResult())
    $uiaPath=Join-Path $treeDirectory 'uia-report.json'
    if (-not (Test-Path -LiteralPath $uiaPath)) { throw 'Native inspector returned no UIA report; no UI validation inferred.' }
    $uia=Get-Content -LiteralPath $uiaPath -Raw | ConvertFrom-Json
    if ($uia.pid -ne $app.Id) { throw 'Inspector reported a different process.' }
    $report.library_content_observed=$uia.library_content_observed
    if ($ExerciseAdd) {
        $report.score_added_control_observed=$uia.score_added_control_observed
        $report.favorite_action_delivered=$uia.favorite_action_delivered
        $report.favorite_remove_label_observed=$uia.favorite_remove_label_observed
        $report.collections_enabled_observed=$uia.collections_enabled_observed
        $report.collection_created_control_observed=$uia.collection_created_control_observed
        $report.collection_member_control_observed=$uia.collection_member_control_observed
        $report.collection_filter_observed=$uia.collection_filter_observed
    }
    $report.status=$uia.status
    $report.native_probe_status=$uia.status
    $app.Refresh()
    if ($app.HasExited) { throw 'Application exited before the end-of-test capture and owned cleanup.' }
    Capture-OwnedWindow 'after-navigation.png' $app
    if ($probe.ExitCode -notin @(0,2)) { throw "UIA inspector failed: $($probe.ExitCode)" }
} catch { $report.status='probe_failed';$report.error=$_.Exception.Message }
finally {
    if ($null -ne $probe) {
        try {
            $probe.Refresh()
            if (-not $probe.HasExited) { $report.probe_cleanup_forced=$true;$probe.Kill($true);[void]$probe.WaitForExit(5000) }
        } catch { if (-not $report.error) { $report.error=$_.Exception.Message } }
        finally { $probe.Dispose() }
    }
    if ($null -ne $app) {
        try {
            $closeClock=[Diagnostics.Stopwatch]::StartNew()
            while ($closeClock.Elapsed.TotalSeconds -lt 12) {
                $app.Refresh();if ($app.HasExited) { break }
                foreach ($window in @([CadenceLibraryWindowNative]::Windows($app.Id))) {
                    $app.Refresh();if ($app.HasExited) { break }
                    $posted=[CadenceLibraryWindowNative]::CloseOwned($window,$app.Id)
                    $report.cleanup.events += [ordered]@{ action='cleanup_wm_close_owned_window';pid=$app.Id;handle=$window.ToInt64();posted=$posted }
                }
                if ($app.WaitForExit(250)) { break }
            }
            $app.Refresh()
            if (-not $app.HasExited) { $report.cleanup.forced=$true;$app.Kill($true);if (-not $app.WaitForExit(5000)) { throw 'Owned application could not be stopped.' } }
            $report.cleanup.exit_code=$app.ExitCode
            [IO.File]::WriteAllText((Join-Path $OutputDirectory 'application.stdout.log'),$stdout.GetAwaiter().GetResult())
            [IO.File]::WriteAllText((Join-Path $OutputDirectory 'application.stderr.log'),$stderr.GetAwaiter().GetResult())
        } catch { $report.cleanup.error=$_.Exception.Message }
        finally { $app.Dispose() }
    }
    if($report.profile_seeded_by_script){Save-CadenceApplicationLogEvidence $localDataDirectory $OutputDirectory $report.pid}
    if ($ExerciseAdd -and $report.fixture) {
        try {
            $report.fixture.source_sha256_after_UI=(Get-FileHash $report.fixture.source_path -Algorithm SHA256).Hash.ToLowerInvariant()
            $report.fixture.copy_sha256_after_UI=(Get-FileHash $report.fixture.copy_path -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($report.fixture.source_sha256_after_UI -cne $report.fixture.source_sha256_before -or $report.fixture.copy_sha256_after_UI -cne $report.fixture.sha256_before) { throw 'A musical fixture changed during the UI test.' }
            $catalogPath = Join-Path $localDataDirectory 'CadenceStudio4/local_library.json'
            $catalogFile = Get-Item -LiteralPath $catalogPath
            if ($catalogFile.Length -gt 262144 -or ($catalogFile.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Unexpected catalogue size or reparse point.' }
            $catalogSnapshot = Join-Path $OutputDirectory 'catalog-after-ui.json'
            [IO.File]::Copy($catalogPath,$catalogSnapshot,$false)
            $report.catalog_actual_snapshot_path=$catalogSnapshot
            $catalog = [IO.File]::ReadAllText($catalogPath) | ConvertFrom-Json
            $entries = @($catalog.entries)
            if ($catalog.schema_version -ne 2 -or $entries.Count -ne 1 -or @($catalog.collections).Count -ne 1) { throw 'Expected the schema2 catalogue created through UI with exactly one score and one collection.' }
            $entry = $entries[0]
            if ($entry.title -cne $report.fixture.title -or $entry.composer -cne $report.fixture.composer -or
                -not [string]::Equals([IO.Path]::GetFullPath([string]$entry.path),[IO.Path]::GetFullPath($report.fixture.copy_path),[StringComparison]::OrdinalIgnoreCase) -or
                $entry.favorite -isnot [bool] -or -not $entry.favorite) { throw 'Catalogue title/composer/path/favorite did not match the actual UI actions.' }
            $collection = @($catalog.collections)[0]
            if ($collection.name -cne $CollectionName -or [string]::IsNullOrWhiteSpace([string]$collection.id) -or
                @($collection.entry_ids).Count -ne 1 -or @($collection.entry_ids)[0] -cne $entry.id) {
                throw 'The actual catalogue does not retain the UI-created collection and its exact score membership.'
            }
            $report.catalog_validation = [ordered]@{ status='passed';source_path=$catalogPath;snapshot_path=$catalogSnapshot;sha256=(Get-FileHash $catalogPath -Algorithm SHA256).Hash.ToLowerInvariant();schema_version=2;collection_count=1;collection_id=$collection.id;collection_name=$collection.name;collection_entry_ids=@($collection.entry_ids);entry_count=1;title=$entry.title;composer=$entry.composer;path=$entry.path;favorite=$entry.favorite;id=$entry.id;fixture_bytes_unchanged=$true }
            $cleanFlow = -not $report.error -and -not $report.cleanup.error -and -not $report.cleanup.forced -and -not $report.probe_cleanup_forced -and $report.cleanup.exit_code -eq 0
            $report.favorites_tested = $cleanFlow -and $report.score_added_control_observed -and $report.favorite_action_delivered -and $report.favorite_remove_label_observed
            $report.collections_tested = $cleanFlow -and $report.collections_enabled_observed -and $report.collection_created_control_observed -and $report.collection_member_control_observed -and $report.collection_filter_observed
            if ($report.favorites_tested -and $report.collections_tested) { $report.status='actual_add_favorite_and_collection_ui_observed_and_metadata_persisted' }
        } catch {
            $report.catalog_validation=[ordered]@{ status='failed';error=$_.Exception.Message }
            if (-not $report.error) { $report.error=$_.Exception.Message }
        }
    }
    if ($report.error -or $report.cleanup.error -or $report.cleanup.forced -or $report.probe_cleanup_forced -or $report.cleanup.exit_code -ne 0) { $report.status='failed_owned_UI_or_cleanup' }
    $report | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $OutputDirectory 'library-ui-report.json') -Encoding utf8
}
if ($report.error -or $report.cleanup.error -or $report.cleanup.forced -or $report.probe_cleanup_forced -or $report.cleanup.exit_code -ne 0) { throw 'Owned library inspection or clean exit0 failed; inspect retained reports.' }
if (-not $report.library_content_observed) { Write-Warning "Library UI remains blocked/unvalidated: $($report.status). Tree and screenshots are evidence, not a pass."; exit 2 }
if ($ExerciseAdd -and (-not $report.score_added_control_observed -or -not $report.favorite_action_delivered -or -not $report.favorites_tested -or -not $report.collections_tested)) { throw 'The actual score Add/favorite UI workflow did not pass its independent catalogue and fixture checks.' }
if ($VerifyRestartOpen) {
    $report.restart=Test-OwnedRestartAndOpen $start $report $report.catalog_validation.source_path
    if($report.restart.status -eq 'favorite_restored_and_editor_title_observed_after_open'){$report.status='add_favorite_collection_restart_and_editor_title_observed'}else{$report.status='failed_restart_or_open_validation'}
    $report|ConvertTo-Json -Depth 16|Set-Content -LiteralPath (Join-Path $OutputDirectory 'library-ui-report.json') -Encoding utf8
    if($report.restart.status -ne 'favorite_restored_and_editor_title_observed_after_open'){throw 'Owned restart/favorite/Open did not pass; original scores were not used.'}
}
if ($ExerciseAdd) { Write-Host 'Observed native Add/favorite/collection controls and actions, persistence and restart/Open on the controlled copy; musical source/copy bytes unchanged. Visual score review and listening remain separate.' }
else { Write-Host 'Observed active library tab and its Add control through UIA. No files were added or changed.' }
