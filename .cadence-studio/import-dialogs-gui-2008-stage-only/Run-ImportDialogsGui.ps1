# SPDX-License-Identifier: GPL-3.0-only
#Requires -Version 7.2
[CmdletBinding()]
param(
 [Parameter(Mandatory)][string]$TargetPath,
 [Parameter(Mandatory)][string]$SourceSelectionDirectory,
 [Parameter(Mandatory)][string]$StagePath,
 [Parameter(Mandatory)][string]$RestorationPath,
 [Parameter(Mandatory)][string]$ProbePath,
 [Parameter(Mandatory)][string]$OutputDirectory,
 [switch]$AnalyzeFixture
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
. "$PSScriptRoot/Read-ActualImportTarget.ps1"
$target=Read-ActualImportTarget $TargetPath $SourceSelectionDirectory
if(-not[OperatingSystem]::IsWindows()-or-not[Environment]::Is64BitProcess-or
 $env:GITHUB_ACTIONS-ne'true'-or$env:CI-ne'true'-or$env:RUNNER_ENVIRONMENT-ne'github-hosted'-or
 -not[Environment]::UserInteractive-or[Diagnostics.Process]::GetCurrentProcess().SessionId-eq0){throw 'An interactive disposable hosted Windows x64 runner is required.'}
function Hash([string]$Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
function Plain([string]$Path){while($Path){if((Test-Path -LiteralPath $Path)-and((Get-Item -LiteralPath $Path -Force).Attributes-band[IO.FileAttributes]::ReparsePoint)){throw 'Reparse ancestor refused.'};$next=[IO.Path]::GetDirectoryName($Path.TrimEnd('\','/'));if(-not$next-or$next-eq$Path){break};$Path=$next}}
$temporary=[IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\','/')+[IO.Path]::DirectorySeparatorChar
$StagePath=[IO.Path]::GetFullPath($StagePath);$ProbePath=[IO.Path]::GetFullPath($ProbePath);$OutputDirectory=[IO.Path]::GetFullPath($OutputDirectory)
foreach($p in @($StagePath,$ProbePath,$OutputDirectory)){if(-not$p.StartsWith($temporary,[StringComparison]::OrdinalIgnoreCase)){throw 'Stage, client and new evidence must be strictly below RUNNER_TEMP.'};Plain $p}
if(Test-Path -LiteralPath $OutputDirectory){throw 'Use a fresh evidence directory.'}
$exe=Join-Path $StagePath 'bin/CadenceStudio4.exe'
if((Hash $exe)-cne$target.stage.executable_sha256-or(Get-Item $exe).Length-ne$target.stage.executable_bytes-or-not(Test-Path -LiteralPath $ProbePath -PathType Leaf)){throw 'Actually produced stage2008 EXE/client required.'}
$restored=Get-Content -LiteralPath $RestorationPath -Raw -Encoding UTF8|ConvertFrom-Json
if((Hash $RestorationPath)-cne$target.authentication_receipt_sha256-or$restored.status-cne'authenticated-original2008-stage-for-GUI-only-known-failed31'-or$restored.source.original_commit-cne$target.source.original_commit-or$restored.source.ci_commit-cne$target.source.ci_commit-or$restored.source.tree-cne$target.source.tree-or$restored.stage.executable_sha256-cne$target.stage.executable_sha256-or$restored.stage.archive_sha256-cne$target.stage.archive_sha256-or$restored.runtime_files_rehashed-ne2712-or$restored.GUI_validated-isnot[bool]-or$restored.GUI_validated-or$restored.full_qualification_complete-isnot[bool]-or$restored.full_qualification_complete-or$null-ne$restored.MSI){throw 'Fresh byte-authenticated StageOnly receipt and exact source/EXE required.'}
$known=@('CadenceStudio4','CadenceStudio4Development','MuseScore4','MuseScore4Development','MuseScoreStudio4')
if(@(Get-Process|Where-Object{$_.ProcessName-in$known}).Count){throw 'Existing score process refused; no existing process/profile touched.'}
$manifest=Get-Content -LiteralPath "$PSScriptRoot/gui-manifest.json" -Raw -Encoding UTF8|ConvertFrom-Json
foreach($e in $manifest.files){
 if($e.path-cnotmatch'^[A-Za-z0-9_.\-/]+$'-or$e.path.Contains('..')){throw 'Unsafe GUI helper manifest path.'}
 $p=Join-Path $PSScriptRoot $e.path;Plain $p
 if((Hash $p)-cne$e.sha256-or(Get-Item $p).Length-ne$e.bytes){throw "GUI helper bytes differ: $($e.path)"}
}
[void][IO.Directory]::CreateDirectory($OutputDirectory)
. "$PSScriptRoot/Owned-WindowEvidence.ps1"
$profile=Join-Path $OutputDirectory 'profile-scope.json'
$report=[ordered]@{schema_version=1;status='running';producer_overall_conclusion='failure';producer_failed_step=31;full_qualification_complete=$false;MSI=$null;scope='GUI-only from actual known-failed31 stage2008: OMR/WAV dialog loading from File menu, owned chooser cancellation, close; optional original WAV analysis draft';target_sha256=Hash $TargetPath;restoration_sha256=Hash $RestorationPath;source_json_sha256=$target.source.source_json_sha256;executable_sha256=Hash $exe;probe_sha256=Hash $ProbePath;phases=@();captures=@();commands=@();drains=@();forced_descendants=0;profile_cleanup_verified=$false;job_closed_cleanly=$false;app_exit_code=$null;app_close_forced=$false;probe_forced=$false;fixture_analysis_requested=[bool]$AnalyzeFixture;fixture=$null;qml_error_matches=@();log_scope='Redirected process stdout/stderr and bounded tails of fresh Cadence profile logs';errors=@();first_launch_tested=$false;real_Audiveris_executed=$false;MIDI_saved_or_opened=$false;listening_tested=$false}
$python=(Get-Command python -CommandType Application -ErrorAction Stop|Select-Object -First 1).Source
$job=$null;$app=$null;$client=$null;$stdout=$null;$stderr=$null;$localData=$null
function Invoke-OwnedPython([string]$Name,[string[]]$Arguments) {
 $i=[Diagnostics.ProcessStartInfo]::new();$i.FileName=$python;$i.UseShellExecute=$false;$i.RedirectStandardOutput=$true;$i.RedirectStandardError=$true
 foreach($arg in $Arguments){$i.ArgumentList.Add($arg)}
 $p=[Diagnostics.Process]::new();$p.StartInfo=$i;$started=$false
 try{
  if(-not$p.Start()){throw 'Owned Python child failed to start.'};$started=$true
  $o=$p.StandardOutput.ReadToEndAsync();$e=$p.StandardError.ReadToEndAsync()
  if(-not$p.WaitForExit(30000)){$p.Kill($true);[void]$p.WaitForExit(5000);throw 'Owned profile/fixture child timed out.'}
  $out=$o.GetAwaiter().GetResult();$err=$e.GetAwaiter().GetResult()
  [IO.File]::WriteAllText((Join-Path $OutputDirectory "$Name.stdout.log"),$out);[IO.File]::WriteAllText((Join-Path $OutputDirectory "$Name.stderr.log"),$err)
  $report.commands+=,@{name=$Name;exit_code=$p.ExitCode;pid=$p.Id}
  if($p.ExitCode-ne0){throw "Owned Python command failed: $Name"}
 }finally{if($started-and-not$p.HasExited){$p.Kill($true);[void]$p.WaitForExit(5000)};$p.Dispose()}
}
function Save-PassiveBlockedForeground([string]$PhaseName) {
 # Read only the already-foreground owned window. Never bring a window forward,
 # set focus, send input, or infer a passed UI phase from this diagnostic PNG.
 try {
  $app.Refresh();if($app.HasExited){throw 'Owned app exited before passive diagnostic capture.'}
  $window=[CadenceLibraryWindowNative]::GetForegroundWindow()
  if(-not[CadenceLibraryWindowNative]::Owned($window,$app.Id)-or-not[CadenceLibraryWindowNative]::IsWindowVisible($window)){throw 'Foreground window is not a visible owned window; passive capture skipped.'}
  $rect=[CadenceLibraryWindowNative+Rect]::new()
  if(-not[CadenceLibraryWindowNative]::GetWindowRect($window,[ref]$rect)){throw 'Owned foreground rectangle unavailable.'}
  $width=$rect.Right-$rect.Left;$height=$rect.Bottom-$rect.Top
  if($width-lt100-or$height-lt100-or([long]$width*$height)-gt12000000){throw 'Owned foreground capture bounds refused.'}
  $title=[CadenceLibraryWindowNative]::Title($window)
  Add-Type -AssemblyName System.Drawing
  $bitmap=[Drawing.Bitmap]::new($width,$height)
  try {
   $graphics=[Drawing.Graphics]::FromImage($bitmap)
   try{$graphics.CopyFromScreen($rect.Left,$rect.Top,0,0,$bitmap.Size)}finally{$graphics.Dispose()}
   if(-not[CadenceLibraryWindowNative]::Owned($window,$app.Id)-or[CadenceLibraryWindowNative]::GetForegroundWindow()-ne$window-or[CadenceLibraryWindowNative]::Title($window)-cne$title){throw 'Owned foreground changed during passive capture.'}
   $path=Join-Path $OutputDirectory "$PhaseName-blocked-passive.png";$bitmap.Save($path,[Drawing.Imaging.ImageFormat]::Png)
   $report.captures+=,@{path=$path;pid=$app.Id;title=$title;bytes=(Get-Item $path).Length;sha256=Hash $path;status='blocked_diagnostic_requires_visual_review';method='passive_desktop_crop_of_already_foreground_owned_window';UI_phase_pass_inferred=$false}
  }finally{$bitmap.Dispose()}
 }catch{$report['blocked_capture_diagnostic']=$_.Exception.Message}
}
function Invoke-Phase([string]$Phase) {
 $app.Refresh();if($app.HasExited){throw 'Owned app exited before native UIA phase.'}
 if((Hash $exe)-cne$target.stage.executable_sha256){throw 'EXE changed between UIA phases.'}
 $sequence=$report.phases.Count+1;$phaseName='{0:D2}-{1}' -f $sequence,$Phase
 $directory=Join-Path $OutputDirectory $phaseName;if(Test-Path $directory){throw 'Phase evidence directory must be new.'};[void][IO.Directory]::CreateDirectory($directory)
 $i=[Diagnostics.ProcessStartInfo]::new();$i.FileName=$ProbePath;$i.UseShellExecute=$false;$i.RedirectStandardOutput=$true;$i.RedirectStandardError=$true
 foreach($arg in @('--pid',[string]$app.Id,'--output',$directory,'--phase',$Phase)){$i.ArgumentList.Add($arg)}
 if($Phase-eq'analyze-wav'){foreach($arg in @('--fixture-root',(Join-Path $OutputDirectory 'controlled-inputs'),'--fixture-wav',$report.fixture.copy_path)){$i.ArgumentList.Add($arg)}}
 $p=[Diagnostics.Process]::new();$p.StartInfo=$i;$started=$false
 try{
  if(-not$p.Start()){throw 'Native UIA client did not start.'};$started=$true
  $o=$p.StandardOutput.ReadToEndAsync();$e=$p.StandardError.ReadToEndAsync()
  if(-not$p.WaitForExit(75000)){$report.probe_forced=$true;$p.Kill($true);[void]$p.WaitForExit(5000);throw 'Owned native UIA phase timed out.'}
  [IO.File]::WriteAllText((Join-Path $directory 'probe.stdout.log'),$o.GetAwaiter().GetResult());[IO.File]::WriteAllText((Join-Path $directory 'probe.stderr.log'),$e.GetAwaiter().GetResult())
  $path=Join-Path $directory 'import-dialog-phase.json';if(-not(Test-Path $path)-or(Get-Item $path).Length-gt1048576){throw 'Missing or oversized native phase report.'}
  $n=Get-Content -LiteralPath $path -Raw -Encoding UTF8|ConvertFrom-Json
  $report.phases+=,@{phase=$Phase;directory=$directory;pid=$app.Id;client_exit_code=$p.ExitCode;report=$n;sha256=Hash $path}
  if($p.ExitCode-ne0-or$n.schema_version-ne1-or$n.pid-ne$app.Id-or$n.phase-cne$Phase-or$n.status-cne'passed_owned_import_dialog_phase'-or$n.keyboard_failure-isnot[bool]-or$n.keyboard_failure-or$n.alt_taps-gt1-or$n.home_taps-gt1-or$n.next_row_taps-gt2-or$n.keys-gt70){Save-PassiveBlockedForeground $phaseName;throw 'Native dialog phase failed or did not prove its exact owned UI claims.'}
  if($Phase-in@('open-omr','open-wav','analyze-wav')){
   $title=if($Phase-eq'open-omr'){'Reconnaître une partition — PDF ou image'}else{'Transcrire une mélodie WAV locale'}
   Capture-OwnedImportDialog $n $title $app "$phaseName.png" $OutputDirectory $report
  }
 }finally{if($started-and-not$p.HasExited){$report.probe_forced=$true;$p.Kill($true);[void]$p.WaitForExit(5000)};$p.Dispose()}
}
try{
 Import-Module "$PSScriptRoot/OwnProcessJob.psm1" -Force;$job=New-OwnedProcessJob
 Invoke-OwnedPython 'prepare-profile' @('-I',"$PSScriptRoot/CadenceProfileScope.py",'prepare','--record',$profile)
 $record=Get-Content -LiteralPath $profile -Raw -Encoding UTF8|ConvertFrom-Json
 if($record.status-cne'prepared'){throw 'Prepared owned profile required.'}
 $localData=$record.local_org_root
 # Only this new owned profile is changed. The seed is provenance, not an ASIO
 # validation claim. No audio output or listening is part of this GUI test.
 [IO.File]::WriteAllText($record.settings_file,"[application]`nhasCompletedFirstLaunchSetup=true`n`n[languages]`nlanguage=fr`n`n[io]`naudioApi=WASAPI`noutputDevice=`nbufferSize=256`nsampleRate=48000`n",[Text.UTF8Encoding]::new($false))
 if($AnalyzeFixture){
  $inputs=Join-Path $OutputDirectory 'controlled-inputs';[void][IO.Directory]::CreateDirectory($inputs);$wave=Join-Path $inputs 'Cadence-QA-three-notes.wav'
  Invoke-OwnedPython 'prepare-original-WAV' @('-I',"$PSScriptRoot/Prepare-OriginalWave.py",'--output',$wave)
  $m=Get-Content -LiteralPath "$PSScriptRoot/fixtures/manifest.json" -Raw -Encoding UTF8|ConvertFrom-Json
  if((Hash $wave)-cne$m.expected_sha256-or(Get-Item $wave).Length-ne$m.expected_bytes){throw 'Original CC0 fixture bytes differ.'}
  $report.fixture=@{copy_path=$wave;sha256=$m.expected_sha256;bytes=$m.expected_bytes;license=$m.license;expected_notes=$m.notes_MIDI}
 }
 $i=[Diagnostics.ProcessStartInfo]::new();$i.FileName=$exe;$i.WorkingDirectory=Split-Path -Parent $exe;$i.UseShellExecute=$false;$i.RedirectStandardOutput=$true;$i.RedirectStandardError=$true
 foreach($arg in @('--test-mode','--session-type','start-empty')){$i.ArgumentList.Add($arg)}
 foreach($key in @($i.Environment.Keys)){if($key-match'^(?i:QT|QML|CMAKE_|VCPKG_|VSCMD_|VSINSTALLDIR$|VCINSTALLDIR$|VCTools|INCLUDE$|LIB$|LIBPATH$|WindowsSdk|WindowsSDK|UniversalCRTSdkDir$|UCRTVersion$|DevEnvDir$|ExtensionSdkDir$|FrameworkDir|FrameworkVersion|GH_TOKEN$|GITHUB_TOKEN$)'){[void]$i.Environment.Remove($key)}}
 $i.Environment['PATH']=(Split-Path -Parent $exe)+';'+(Join-Path $env:SystemRoot 'System32');$i.Environment['QT_ACCESSIBILITY']='1'
 $app=[Diagnostics.Process]::new();$app.StartInfo=$i;if(-not$app.Start()){throw 'Actual staged application did not start.'}
 $stdout=$app.StandardOutput.ReadToEndAsync();$stderr=$app.StandardError.ReadToEndAsync();$report['app_pid']=$app.Id
 foreach($phase in @('open-omr','close-omr','open-wav','close-wav')){Invoke-Phase $phase}
 if($AnalyzeFixture){foreach($phase in @('open-wav','analyze-wav','close-ready-wav')){Invoke-Phase $phase}}
 $report.status='UI-phases-passed-cleanup-and-log-review-pending'
}catch{$report.errors+=,$_.Exception.Message}
finally{
 if($app){
  try{
   $watch=[Diagnostics.Stopwatch]::StartNew()
   while($watch.Elapsed.TotalSeconds-lt12){$app.Refresh();if($app.HasExited){break};foreach($w in @([CadenceLibraryWindowNative]::Windows($app.Id))){$app.Refresh();if($app.HasExited){break};[void][CadenceLibraryWindowNative]::CloseOwned($w,$app.Id)};if($app.WaitForExit(250)){break}}
   $app.Refresh();if(-not$app.HasExited){$report.app_close_forced=$true;$app.Kill($true);[void]$app.WaitForExit(5000)}
   $report.app_exit_code=$app.ExitCode
   $out=$stdout.GetAwaiter().GetResult();$err=$stderr.GetAwaiter().GetResult();[IO.File]::WriteAllText((Join-Path $OutputDirectory 'application.stdout.log'),$out);[IO.File]::WriteAllText((Join-Path $OutputDirectory 'application.stderr.log'),$err)
   if($localData){Save-CadenceApplicationLogEvidence $localData $OutputDirectory $app.Id}
   $text=$out+"`n"+$err
   $logs=Get-Content -LiteralPath (Join-Path $OutputDirectory 'application-log-tails.json') -Raw -Encoding UTF8|ConvertFrom-Json
   foreach($f in $logs.files){$text+="`n"+$f.text}
   $report.qml_error_matches=@([regex]::Matches($text,'(?im)^.*(?:Cannot assign to|Unable to assign|ReferenceError|TypeError|is not a type|failed to load component).*$')|ForEach-Object{$_.Value}|Select-Object -First 30)
   if(@($logs.files).Count-eq0){$report.errors+=,'No fresh application log tail is available; absence of QML failures cannot be inferred.'}
  }catch{$report.errors+=,$_.Exception.Message}finally{$app.Dispose()}
 }
 $drained=$false
 if($job){try{$d=Stop-OwnedJobChildren -Job $job;$report.drains+=,$d;$report.forced_descendants+=@($d.TerminatedPids).Count;$drained=$d.ChildrenDrained-and$d.ActiveProcesses-eq1}catch{$report.errors+=,$_.Exception.Message}}
 if((Test-Path $profile)-and$drained){
  try{Invoke-OwnedPython 'cleanup-profile' @('-I',"$PSScriptRoot/CadenceProfileScope.py",'cleanup','--record',$profile);$r=Get-Content -LiteralPath $profile -Raw -Encoding UTF8|ConvertFrom-Json;$report.profile_cleanup_verified=$r.status-ceq'cleaned'}catch{$report.errors+=,$_.Exception.Message}
 }
 if($report.fixture){try{if((Hash $report.fixture.copy_path)-cne$report.fixture.sha256){throw 'Original WAV copy changed.'}}catch{$report.errors+=,$_.Exception.Message}}
 try{if((Hash $exe)-cne$target.stage.executable_sha256){throw 'Staged EXE changed.'}}catch{$report.errors+=,$_.Exception.Message}
 if($job){try{$d=Stop-OwnedJobChildren -Job $job;$report.drains+=,$d;$report.forced_descendants+=@($d.TerminatedPids).Count;$report['final_job_close']=Close-OwnedProcessJob -Job $job;$report.job_closed_cleanly=$true}catch{$report.errors+=,$_.Exception.Message}}
 # No native process, keyboard, capture, or profile operation after Job close.
 if($report.status-ceq'UI-phases-passed-cleanup-and-log-review-pending'-and$report.app_exit_code-eq0-and-not$report.app_close_forced-and-not$report.probe_forced-and$report.forced_descendants-eq0-and$report.profile_cleanup_verified-and$report.job_closed_cleanly-and@($report.errors).Count-eq0-and@($report.qml_error_matches).Count-eq0){$report.status='passed_actual_import_dialogs_and_clean_owned_exit'}else{$report.status='failed-or-blocked'}
 $report|ConvertTo-Json -Depth 20|Set-Content -LiteralPath (Join-Path $OutputDirectory 'import-dialogs-gui-report.json') -Encoding UTF8
 Write-Host 'CADENCE_IMPORT_DIALOGS_GUI_REPORT_BEGIN';$report|ConvertTo-Json -Depth 20 -Compress|Write-Host;Write-Host 'CADENCE_IMPORT_DIALOGS_GUI_REPORT_END'
}
if($report.status-cne'passed_actual_import_dialogs_and_clean_owned_exit'){throw 'Actual GUI loading or cleanup remains blocked; inspect the real receipts.'}
