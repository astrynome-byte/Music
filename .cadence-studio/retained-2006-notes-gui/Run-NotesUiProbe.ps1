# SPDX-License-Identifier: GPL-3.0-only
[CmdletBinding()]
param(
 [Parameter(Mandatory)][string] $StagePath,
 [Parameter(Mandatory)][string] $ProbePath,
 [Parameter(Mandatory)][string] $OutputDirectory,
 [Parameter(Mandatory)][ValidatePattern('^[a-f0-9]{64}$')][string] $ExpectedExecutableSha256
)
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
. "$PSScriptRoot/NotesEvidence.ps1"
if($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitProcess -or $env:GITHUB_ACTIONS -ne 'true' -or
 $env:CI -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted' -or -not [Environment]::UserInteractive -or
 [Diagnostics.Process]::GetCurrentProcess().SessionId -eq 0){throw 'Only an interactive disposable hosted Windows x64 runner is permitted.'}
$OutputDirectory=[IO.Path]::GetFullPath($OutputDirectory)
$tempPrefix=[IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\','/')+[IO.Path]::DirectorySeparatorChar
if(-not $OutputDirectory.StartsWith($tempPrefix,[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $OutputDirectory)){throw 'Use a new evidence directory strictly below RUNNER_TEMP.'}
$executable=[IO.Path]::GetFullPath((Join-Path $StagePath 'bin/CadenceStudio4.exe'));$ProbePath=[IO.Path]::GetFullPath($ProbePath)
if($ExpectedExecutableSha256 -cne 'c29d7c8c76b213b79d7390acd65cbabc6fb940f06e3e7f86c0ce60be7e9b9520' -or
 (Get-FileHash -LiteralPath $executable -Algorithm SHA256).Hash.ToLowerInvariant() -cne $ExpectedExecutableSha256 -or
 -not (Test-Path -LiteralPath $ProbePath -PathType Leaf)){throw 'The retained2006 executable/native client identity is not valid.'}
$known=@('CadenceStudio4','CadenceStudio4Development','MuseScore4','MuseScore4Development','MuseScoreStudio4')
if(@(Get-Process|Where-Object{$_.ProcessName -in $known}).Count){throw 'A score process exists; no existing process/profile is touched.'}
New-Item -ItemType Directory -Path $OutputDirectory|Out-Null
$report=[ordered]@{schema_version=1;status='pending';scope='One actual private-note create/save/restart/read flow on one copied score; no score editing or audio';executable_sha256=$ExpectedExecutableSha256;probe_sha256=(Get-FileHash $ProbePath -Algorithm SHA256).Hash.ToLowerInvariant();profile_seeded_by_script=$false;onboarding_tested=$false;fixture=$null;first=$null;restart=$null;captures=@();error=$null;listening_tested=$false;score_editing_tested=$false}
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

function Invoke-OwnedNotesPhase([bool] $Restart, [string] $PhaseDirectory, $StartInformation) {
 New-Item -ItemType Directory -Path $PhaseDirectory|Out-Null
 $tree=Join-Path $PhaseDirectory 'uia';New-Item -ItemType Directory -Path $tree|Out-Null
 $result=[ordered]@{schema_version=1;status='pending';restart=$Restart;pid=$null;probe_exit_code=$null;native_status=$null;native_ui_claims_passed=$false;captures=@();catalogue_validation=$null;cleanup=[ordered]@{forced=$false;exit_code=$null;error=$null;events=@()};probe_cleanup_forced=$false;error=$null}
 $app=$null;$probe=$null;$stdout=$null;$stderr=$null
 try{
  if(@(Get-Process|Where-Object{$_.ProcessName -in $known}).Count){throw 'A score process exists before this phase.'}
  if((Get-FileHash $executable -Algorithm SHA256).Hash.ToLowerInvariant() -cne $ExpectedExecutableSha256){throw 'The retained executable changed.'}
  # Restart preconditions are read before starting the owned application.
  if($Restart -and ((Get-FileHash $catalogPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $report.first.catalogue_validation.sha256)){throw 'The persisted catalogue changed between phases.'}
  $app=[Diagnostics.Process]::new();$app.StartInfo=$StartInformation
  if(-not $app.Start()){throw 'The owned application did not start.'}
  $result.pid=$app.Id;$stdout=$app.StandardOutput.ReadToEndAsync();$stderr=$app.StandardError.ReadToEndAsync()
  $clock=[Diagnostics.Stopwatch]::StartNew()
  while($clock.Elapsed.TotalSeconds -lt 35){$app.Refresh();if($app.HasExited){throw 'Application exited before UIA.'};if(@([CadenceLibraryWindowNative]::Windows($app.Id)).Count){break};Start-Sleep -Milliseconds 200}
  $pi=[Diagnostics.ProcessStartInfo]::new();$pi.FileName=$ProbePath;$pi.UseShellExecute=$false;$pi.RedirectStandardOutput=$true;$pi.RedirectStandardError=$true
  $fixtureSwitch=if($Restart){'--verify-fixture'}else{'--add-fixture'}
  foreach($arg in @('--pid',[string]$app.Id,'--output',$tree,'--fixture-root',$report.fixture.copy_root,$fixtureSwitch,$report.fixture.copy_path,'--expected-title',$report.fixture.title,'--note-text','Cadence-QA-PrivateNote-2006')){$pi.ArgumentList.Add($arg)}
  $probe=[Diagnostics.Process]::new();$probe.StartInfo=$pi;if(-not $probe.Start()){throw 'The native UIA client did not start.'}
  $po=$probe.StandardOutput.ReadToEndAsync();$pe=$probe.StandardError.ReadToEndAsync()
  if(-not $probe.WaitForExit(180000)){$result.probe_cleanup_forced=$true;$probe.Kill($true);[void]$probe.WaitForExit(5000);throw 'Owned UIA client timed out.'}
  $result.probe_exit_code=$probe.ExitCode
  [IO.File]::WriteAllText((Join-Path $PhaseDirectory 'probe.stdout.log'),$po.GetAwaiter().GetResult())
  [IO.File]::WriteAllText((Join-Path $PhaseDirectory 'probe.stderr.log'),$pe.GetAwaiter().GetResult())
  $native=Get-Content -LiteralPath (Join-Path $tree 'uia-report.json') -Raw|ConvertFrom-Json
  $result.native_status=$native.status
  $app.Refresh();if($app.HasExited){throw 'Owned app exited before capture.'}
  Capture-OwnedWindow 'after-notes-flow.png' $app $PhaseDirectory $result
  if($result.probe_exit_code -ne 0){throw 'Native private-note UI flow was blocked; inspect its actual report.'}
  Assert-NotesUiClaims $native $app.Id $Restart
  $result.native_ui_claims_passed=$true
 }catch{$result.error=$_.Exception.Message}
 finally{
  if($null -ne $probe){try{$probe.Refresh();if(-not $probe.HasExited){$result.probe_cleanup_forced=$true;$probe.Kill($true);[void]$probe.WaitForExit(5000)}}catch{if(-not $result.error){$result.error=$_.Exception.Message}}finally{$probe.Dispose()}}
  if($null -ne $app){
   try{
    $clock=[Diagnostics.Stopwatch]::StartNew()
    while($clock.Elapsed.TotalSeconds -lt 12){
     $app.Refresh();if($app.HasExited){break}
     foreach($window in @([CadenceLibraryWindowNative]::Windows($app.Id))){$app.Refresh();if($app.HasExited){break};$posted=[CadenceLibraryWindowNative]::CloseOwned($window,$app.Id);$result.cleanup.events += [ordered]@{pid=$app.Id;handle=$window.ToInt64();posted=$posted}}
     if($app.WaitForExit(250)){break}
    }
    $app.Refresh();if(-not $app.HasExited){$result.cleanup.forced=$true;$app.Kill($true);if(-not $app.WaitForExit(5000)){throw 'Owned application could not be stopped.'}}
    $result.cleanup.exit_code=$app.ExitCode
    [IO.File]::WriteAllText((Join-Path $PhaseDirectory 'application.stdout.log'),$stdout.GetAwaiter().GetResult())
    [IO.File]::WriteAllText((Join-Path $PhaseDirectory 'application.stderr.log'),$stderr.GetAwaiter().GetResult())
   }catch{$result.cleanup.error=$_.Exception.Message}finally{$app.Dispose()}
  }
  if($report.profile_seeded_by_script){Save-CadenceApplicationLogEvidence $localDataDirectory $PhaseDirectory $result.pid}
  try{
   $result.catalogue_validation=Read-ClosedNotesCatalogue $result.cleanup.exit_code $result.cleanup.forced $catalogPath $report.fixture $PhaseDirectory
   if($Restart -and ($result.catalogue_validation.sha256 -cne $report.first.catalogue_validation.sha256 -or
      $result.catalogue_validation.note_id -cne $report.first.catalogue_validation.note_id -or
      $result.catalogue_validation.migration_backup_sha256 -cne $report.first.catalogue_validation.migration_backup_sha256)){throw 'The saved note/catalogue/backup changed during read-only restart.'}
  }catch{if(-not $result.error){$result.error=$_.Exception.Message}}
  if(-not $result.error -and -not $result.cleanup.error -and -not $result.cleanup.forced -and -not $result.probe_cleanup_forced -and
    $result.native_ui_claims_passed -and $result.cleanup.exit_code -eq 0){$result.status='passed_actual_UI_and_post_exit_corroboration'}else{$result.status='failed_or_blocked'}
  $result|ConvertTo-Json -Depth 14|Set-Content -LiteralPath (Join-Path $PhaseDirectory 'notes-phase-report.json') -Encoding utf8
 }
 return $result
}
try{
 $userRoot=[IO.Path]::GetFullPath([Environment]::GetFolderPath('UserProfile')).TrimEnd('\','/')+[IO.Path]::DirectorySeparatorChar
 $roamingBase=[Environment]::GetFolderPath('ApplicationData');$localBase=[Environment]::GetFolderPath('LocalApplicationData')
 foreach($folder in @($roamingBase,$localBase)){if(-not [IO.Path]::IsPathFullyQualified($folder) -or -not ([IO.Path]::GetFullPath($folder)+[IO.Path]::DirectorySeparatorChar).StartsWith($userRoot,[StringComparison]::OrdinalIgnoreCase)){throw 'Standard profile folders must belong to this disposable runner.'}}
 $configurationDirectory=Join-Path $roamingBase 'CadenceStudio';$localDataDirectory=Join-Path $localBase 'CadenceStudio'
 if((Test-Path -LiteralPath $configurationDirectory) -or (Test-Path -LiteralPath $localDataDirectory)){throw 'Existing Cadence profile left unchanged.'}
 New-Item -ItemType Directory -Path $configurationDirectory|Out-Null
 $settingsPath=Join-Path $configurationDirectory 'CadenceStudio4.ini'
 [IO.File]::WriteAllBytes($settingsPath,[Text.UTF8Encoding]::new($false).GetBytes("[application]`r`nhasCompletedFirstLaunchSetup=true`r`n"));$report.profile_seeded_by_script=$true
 $sourcePath=Join-Path $PSScriptRoot 'fixtures/piano-uia-copy.mscx';$expectedFixture='10ae5eb1fae2679d9ad32aa0b721fef06119ef24b78b4f8b9bd6b770582c289f'
 if((Get-FileHash $sourcePath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $expectedFixture -or (Get-Item $sourcePath).Length -ne 10586){throw 'Controlled native piano differs.'}
 $copyRoot=Join-Path $OutputDirectory 'controlled-score-copies';New-Item -ItemType Directory -Path $copyRoot|Out-Null
 $copyPath=Join-Path $copyRoot 'piano-uia-copy.mscx';Copy-Item -LiteralPath $sourcePath -Destination $copyPath
 if((Get-FileHash $copyPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $expectedFixture){throw 'Controlled score copy differs.'}
 $report.fixture=[ordered]@{source_path=$sourcePath;source_sha256_before=$expectedFixture;copy_root=$copyRoot;copy_path=$copyPath;sha256_before=$expectedFixture;title='Piano : voix, accords et triolets';composer='Cadence regression corpus';license='CC0-1.0';only_copy_passed_to_UI=$true}
 $catalogPath=Join-Path $localDataDirectory 'CadenceStudio4/local_library.json'
 $start=[Diagnostics.ProcessStartInfo]::new();$start.FileName=$executable;$start.WorkingDirectory=Split-Path -Parent $executable;$start.UseShellExecute=$false;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
 foreach($arg in @('--test-mode','--session-type','start-empty')){$start.ArgumentList.Add($arg)}
 $start.Environment['PATH']=(Split-Path -Parent $executable)+';'+(Join-Path $env:SystemRoot 'System32')
 foreach($key in @($start.Environment.Keys)){if($key -match '^(?i:QT|QML|CMAKE_|VCPKG_|VSCMD_|VSINSTALLDIR$|VCINSTALLDIR$|VCTools|INCLUDE$|LIB$|LIBPATH$|WindowsSdk|WindowsSDK|UniversalCRTSdkDir$|UCRTVersion$|DevEnvDir$|ExtensionSdkDir$|FrameworkDir|FrameworkVersion|GH_TOKEN$|GITHUB_TOKEN$)'){[void]$start.Environment.Remove($key)}}
 $start.Environment['QT_ACCESSIBILITY']='1'
 $report.first=Invoke-OwnedNotesPhase $false (Join-Path $OutputDirectory 'create-save') $start
 if($report.first.status -cne 'passed_actual_UI_and_post_exit_corroboration'){throw 'The only create/save phase did not pass; no restart variation was attempted.'}
 $report.restart=Invoke-OwnedNotesPhase $true (Join-Path $OutputDirectory 'restart-read') $start
 if($report.restart.status -cne 'passed_actual_UI_and_post_exit_corroboration'){throw 'The only read-only restart did not pass.'}
 $report.status='private_note_UI_create_save_restart_read_and_unchanged_score_observed'
}catch{$report.error=$_.Exception.Message;$report.status='failed_or_blocked'}
finally{$report|ConvertTo-Json -Depth 20|Set-Content -LiteralPath (Join-Path $OutputDirectory 'notes-ui-report.json') -Encoding utf8}
if($report.status -cne 'private_note_UI_create_save_restart_read_and_unchanged_score_observed'){throw 'Actual private notes UI flow remains blocked/failed; see retained reports.'}
Write-Host 'PASS: actual private-note UI create/save/restart/read, clean owned exits0, unchanged catalogue during replay and unchanged musical source/copy.'
