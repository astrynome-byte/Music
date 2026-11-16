# SPDX-License-Identifier: GPL-3.0-only
#Requires -Version 7.2
[CmdletBinding()]
param(
 [Parameter(Mandatory)][string]$TargetPath,
 [Parameter(Mandatory)][string]$SourceSelectionDirectory,
 [Parameter(Mandatory)][string]$StagePath,
 [Parameter(Mandatory)][string]$RestorationPath,
 [Parameter(Mandatory)][string]$InventoryPath,
 [Parameter(Mandatory)][string]$ProbePath,
 [Parameter(Mandatory)][string]$OutputDirectory
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
. "$PSScriptRoot/Read-ActualImportTarget.ps1"
$target=Read-ActualImportTarget $TargetPath $SourceSelectionDirectory
if(-not[OperatingSystem]::IsWindows()-or-not[Environment]::Is64BitProcess-or$env:GITHUB_ACTIONS-ne'true'-or$env:CI-ne'true'-or$env:RUNNER_ENVIRONMENT-ne'github-hosted'-or-not[Environment]::UserInteractive-or[Diagnostics.Process]::GetCurrentProcess().SessionId-eq0){throw 'Interactive disposable hosted Windows x64 required.'}
function Hash([string]$Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
function Plain([string]$Path){while($Path){if((Test-Path -LiteralPath $Path)-and((Get-Item -LiteralPath $Path -Force).Attributes-band[IO.FileAttributes]::ReparsePoint)){throw 'Reparse ancestor refused.'};$next=[IO.Path]::GetDirectoryName($Path.TrimEnd('\','/'));if(-not$next-or$next-eq$Path){break};$Path=$next}}
$temporary=[IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\','/')+[IO.Path]::DirectorySeparatorChar
$StagePath=[IO.Path]::GetFullPath($StagePath);$ProbePath=[IO.Path]::GetFullPath($ProbePath);$OutputDirectory=[IO.Path]::GetFullPath($OutputDirectory)
foreach($path in @($StagePath,$ProbePath,$OutputDirectory,$RestorationPath,$InventoryPath)){$path=[IO.Path]::GetFullPath($path);if(-not$path.StartsWith($temporary,[StringComparison]::OrdinalIgnoreCase)){throw 'Runtime, probe, receipts and evidence must be below RUNNER_TEMP.'};Plain $path}
if(Test-Path -LiteralPath $OutputDirectory){throw 'Fresh evidence directory required.'}
$exe=Join-Path $StagePath 'bin/CadenceStudio4.exe'
if((Hash $exe)-cne$target.stage.executable_sha256-or(Get-Item $exe).Length-ne$target.stage.executable_bytes-or-not(Test-Path -LiteralPath $ProbePath -PathType Leaf)){throw 'Exact authenticated original2008 EXE and independent probe required.'}
if((Hash $RestorationPath)-cne$target.authentication_receipt_sha256){throw 'Exact fresh StageOnly authentication receipt required.'}
$restored=Get-Content -LiteralPath $RestorationPath -Raw -Encoding UTF8|ConvertFrom-Json
if($restored.status-cne'authenticated-original2008-stage-for-GUI-only-known-failed31'-or$restored.stage.executable_sha256-cne$target.stage.executable_sha256-or$restored.runtime_files_rehashed-ne2712){throw 'Fresh stage receipt identity differs.'}
if($target.score_edit.schema_version-ne1-or$target.score_edit.working_basename-cne'Cadence-QA-edit'-or($target.score_edit.expected_midi-join',')-cne'72,74,76,77'-or$target.score_edit.single_undo-isnot[bool]-or-not$target.score_edit.single_undo-or$target.score_edit.single_redo-isnot[bool]-or-not$target.score_edit.single_redo){throw 'Reviewed fixed four-quarter exercise required.'}
$known=@('CadenceStudio4','CadenceStudio4Development','MuseScore4','MuseScore4Development','MuseScoreStudio4')
if(@(Get-Process|Where-Object{$_.ProcessName-in$known}).Count){throw 'Existing score process refused.'}
if((Hash "$PSScriptRoot/gui-manifest.json")-cne$target.gui_manifest_sha256){throw 'Reviewed score-edit helper manifest differs.'}
$manifest=Get-Content -LiteralPath "$PSScriptRoot/gui-manifest.json" -Raw -Encoding UTF8|ConvertFrom-Json
foreach($entry in $manifest.files){if($entry.path-cnotmatch'^[A-Za-z0-9_.\-/]+$'-or$entry.path.Contains('..')){throw 'Unsafe helper path.'};$path=Join-Path $PSScriptRoot $entry.path;Plain $path;if((Hash $path)-cne$entry.sha256-or(Get-Item $path).Length-ne$entry.bytes){throw "Helper bytes differ: $($entry.path)"}}
[void][IO.Directory]::CreateDirectory($OutputDirectory)
. "$PSScriptRoot/Owned-WindowEvidence.ps1"
$python=(Get-Command python -CommandType Application -ErrorAction Stop|Select-Object -First 1).Source
$profile=Join-Path $OutputDirectory 'profile-scope.json'
$scoreDirectory=Join-Path $OutputDirectory 'controlled-scores';[void][IO.Directory]::CreateDirectory($scoreDirectory)
$fixture=Join-Path $PSScriptRoot 'fixtures/empty-piano.musicxml';$fixtureSha=Hash $fixture
$native=Join-Path $scoreDirectory 'Cadence-QA-edit.mscz'
$report=[ordered]@{schema_version=1;status='running';scope='Actual original2008 GUI: four ordinary-key quarter notes, existing native-file save, single undo/save, single redo/save; independent native CLI exports';source=$target.source;executable_sha256=Hash $exe;probe_sha256=Hash $ProbePath;original_producer=@{run=43408309742;job=131828068954;overall='failure';failed_step=31;compilation_steps_25_to_30='success'};separate_existing_qualification=@{run=43421094979;conclusion='success'};separate_existing_MSI=@{run=43425150320;conclusion='success';publicly_published=$true};fixture=@{sha256=$fixtureSha;license='CC0-1.0';original_preserved=$false};phases=@();snapshots=@();commands=@();captures=@();drains=@();forced_owned_processes=0;forced_descendants=0;app_pid=$null;app_exit_code=$null;app_close_forced=$false;probe_forced=$false;profile_cleanup_verified=$false;job_closed_cleanly=$false;stage_unchanged=$false;musical_comparison=$null;errors=@();qml_error_matches=@();human_visual_review_performed=$false;listening_tested=$false;Windows10_11_client_tested=$false;application_rebuilt=$false;MSI_modified=$false}
$job=$null;$app=$null;$stdout=$null;$stderr=$null;$localData=$null
function New-AppInfo([string[]]$Arguments){
 $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$exe;$info.WorkingDirectory=Split-Path -Parent $exe;$info.UseShellExecute=$false;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
 foreach($arg in $Arguments){$info.ArgumentList.Add($arg)}
 foreach($key in @($info.Environment.Keys)){if($key-match'^(?i:QT|QML|CMAKE_|VCPKG_|VSCMD_|VSINSTALLDIR$|VCINSTALLDIR$|VCTools|INCLUDE$|LIB$|LIBPATH$|WindowsSdk|WindowsSDK|UniversalCRTSdkDir$|UCRTVersion$|DevEnvDir$|ExtensionSdkDir$|FrameworkDir|FrameworkVersion|GH_TOKEN$|GITHUB_TOKEN$)'){[void]$info.Environment.Remove($key)}}
 $info.Environment['PATH']=(Split-Path -Parent $exe)+';'+(Join-Path $env:SystemRoot 'System32');$info.Environment['QT_ACCESSIBILITY']='1';return $info
}
function Invoke-Owned([string]$Name,[Diagnostics.ProcessStartInfo]$Info,[int]$Timeout=30000){
 $p=[Diagnostics.Process]::new();$p.StartInfo=$Info;$started=$false
 try{if(-not$p.Start()){throw "Owned process failed: $Name"};$started=$true;$o=$p.StandardOutput.ReadToEndAsync();$e=$p.StandardError.ReadToEndAsync();if(-not$p.WaitForExit($Timeout)){$report.forced_owned_processes++;$p.Kill($true);[void]$p.WaitForExit(5000);throw "Owned process timed out: $Name"};[IO.File]::WriteAllText((Join-Path $OutputDirectory "$Name.stdout.log"),$o.GetAwaiter().GetResult());[IO.File]::WriteAllText((Join-Path $OutputDirectory "$Name.stderr.log"),$e.GetAwaiter().GetResult());$report.commands+=,@{name=$Name;pid=$p.Id;exit_code=$p.ExitCode};if($p.ExitCode-ne0){throw "Owned process failed: $Name"}}
 finally{if($started-and-not$p.HasExited){$report.forced_owned_processes++;$p.Kill($true);[void]$p.WaitForExit(5000)};$p.Dispose()}
}
function Invoke-Python([string]$Name,[string[]]$Arguments){$i=[Diagnostics.ProcessStartInfo]::new();$i.FileName=$python;$i.UseShellExecute=$false;$i.RedirectStandardOutput=$true;$i.RedirectStandardError=$true;foreach($arg in $Arguments){$i.ArgumentList.Add($arg)};Invoke-Owned $Name $i}
function Snapshot-Score([string]$Name,[string]$PreviousSha){
 $destination=Join-Path $scoreDirectory "$Name.mscz";if(Test-Path -LiteralPath $destination){throw 'Snapshot destination exists.'}
 $watch=[Diagnostics.Stopwatch]::StartNew();$last='';$stable=0
 while($watch.Elapsed.TotalSeconds-lt10){
  $app.Refresh();if($app.HasExited){throw 'Application exited before save snapshot.'}
  try{$item=Get-Item -LiteralPath $native -Force;Plain $native;$sha=Hash $native;if($item.Length-gt0-and$item.Length-lt10485760-and$sha-cne$PreviousSha){if($sha-ceq$last){$stable++}else{$last=$sha;$stable=1};if($stable-ge3){
    $stream=[IO.File]::Open($native,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
    try{$copy=[IO.File]::Open($destination,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None);try{$stream.CopyTo($copy)}finally{$copy.Dispose()}}finally{$stream.Dispose()}
    if((Hash $native)-cne$sha-or(Hash $destination)-cne$sha){throw 'Native file changed during the stable snapshot.'}
    $report.snapshots+=,@{name=$Name;path=$destination;sha256=$sha;bytes=(Get-Item $destination).Length;stable_observations=$stable};return $sha
  }}}catch [IO.IOException]{$stable=0}
  Start-Sleep -Milliseconds 250
 };throw 'CtrlS did not yield a changed stable native score within10seconds.'
}
function Invoke-Phase([string]$Phase){
 $app.Refresh();if($app.HasExited-or(Hash $exe)-cne$target.stage.executable_sha256){throw 'Owned actual application missing or changed.'}
 $directory=Join-Path $OutputDirectory $Phase;[void][IO.Directory]::CreateDirectory($directory)
 $i=[Diagnostics.ProcessStartInfo]::new();$i.FileName=$ProbePath;$i.UseShellExecute=$false;$i.RedirectStandardOutput=$true;$i.RedirectStandardError=$true
 foreach($arg in @('--pid',[string]$app.Id,'--output',$directory,'--phase',$Phase)){$i.ArgumentList.Add($arg)}
 try{Invoke-Owned "probe-$Phase" $i 75000}catch{if($report.forced_owned_processes){$report.probe_forced=$true};throw}
 $path=Join-Path $directory 'score-edit-phase.json';$n=Get-Content -LiteralPath $path -Raw -Encoding UTF8|ConvertFrom-Json
 $report.phases+=,@{phase=$Phase;sha256=Hash $path;report=$n}
 if($n.schema_version-ne1-or$n.pid-ne$app.Id-or$n.phase-cne$Phase-or$n.status-cne'passed_owned_score_keyboard_phase'-or$n.keyboard_failure-isnot[bool]-or$n.keyboard_failure-or$n.local_score_focus_verified-isnot[bool]-or-not$n.local_score_focus_verified-or$n.local_focus_scope-cne'focused-element-and-ancestors-only'-or$n.gestures-gt60){throw 'Exact owned ordinary-key phase was not proved.'}
 Capture-OwnedWindow "$Phase.png" $app $OutputDirectory $report
}
function Close-App {
 if(-not$app){return}
 try{$watch=[Diagnostics.Stopwatch]::StartNew();while($watch.Elapsed.TotalSeconds-lt12){$app.Refresh();if($app.HasExited){break};foreach($window in @([CadenceLibraryWindowNative]::Windows($app.Id))){$app.Refresh();if($app.HasExited){break};[void][CadenceLibraryWindowNative]::CloseOwned($window,$app.Id)};if($app.WaitForExit(250)){break}}
  $app.Refresh();if(-not$app.HasExited){$report.app_close_forced=$true;$report.forced_owned_processes++;$app.Kill($true);[void]$app.WaitForExit(5000)};$report.app_exit_code=$app.ExitCode
  [IO.File]::WriteAllText((Join-Path $OutputDirectory 'application.stdout.log'),$stdout.GetAwaiter().GetResult());[IO.File]::WriteAllText((Join-Path $OutputDirectory 'application.stderr.log'),$stderr.GetAwaiter().GetResult())
  if($localData){Save-CadenceApplicationLogEvidence $localData $OutputDirectory $app.Id}
 }finally{$app.Dispose();$script:app=$null}
}
try{
 Import-Module "$PSScriptRoot/OwnProcessJob.psm1" -Force;$job=New-OwnedProcessJob
 Invoke-Python 'prepare-profile' @('-I',"$PSScriptRoot/CadenceProfileScope.py",'prepare','--record',$profile)
 $record=Get-Content -LiteralPath $profile -Raw -Encoding UTF8|ConvertFrom-Json;if($record.status-cne'prepared'){throw 'Fresh owned profile required.'};$localData=$record.local_org_root
 $seed="[General]`nlanguage=en`n`n[application]`nhasCompletedFirstLaunchSetup=true`n`n[io]`naudioApi=WASAPI`noutputDevice=`nbufferSize=256`nsampleRate=48000`n"
 [IO.File]::WriteAllText($record.settings_file,$seed,[Text.UTF8Encoding]::new($false))
 $inputCopy=Join-Path $scoreDirectory 'empty-piano.original-copy.musicxml';Copy-Item -LiteralPath $fixture -Destination $inputCopy
 # The original data and a native immutable baseline are retained. GUI opens a
 # separate existing MSCZ copy so CtrlS never requires SaveAs or file chooser.
 Invoke-Owned 'CLI-create-native' (New-AppInfo @('--test-mode','-o',(Join-Path $scoreDirectory 'baseline.mscz'),$inputCopy)) 60000
 Copy-Item -LiteralPath (Join-Path $scoreDirectory 'baseline.mscz') -Destination $native
 $baselineSha=Hash (Join-Path $scoreDirectory 'baseline.mscz');$report['native_baseline_sha256']=$baselineSha
 [IO.File]::WriteAllText($record.settings_file,$seed,[Text.UTF8Encoding]::new($false))
 $app=[Diagnostics.Process]::new();$app.StartInfo=New-AppInfo @('--test-mode',$native);if(-not$app.Start()){throw 'Actual staged GUI did not start.'};$stdout=$app.StandardOutput.ReadToEndAsync();$stderr=$app.StandardError.ReadToEndAsync();$report.app_pid=$app.Id
 Invoke-Phase 'edit-save';$editedSha=Snapshot-Score 'edited' $baselineSha
 Invoke-Phase 'undo-save';$undoSha=Snapshot-Score 'undo' $editedSha
 Invoke-Phase 'redo-save';$redoSha=Snapshot-Score 'redo' $undoSha
 Close-App
 if($report.app_close_forced-or$report.app_exit_code-ne0){throw 'Clean GUI close0 required before independent exports.'}
 foreach($name in @('baseline','edited','undo','redo')){Invoke-Owned "CLI-export-$name" (New-AppInfo @('--test-mode','-o',(Join-Path $scoreDirectory "$name.musicxml"),(Join-Path $scoreDirectory "$name.mscz"))) 60000}
 $comparison=Join-Path $OutputDirectory 'native-musical-comparison.json';Invoke-Python 'verify-independent-exports' @('-I',"$PSScriptRoot/verify_score_edits.py",'--directory',$scoreDirectory,'--output',$comparison)
 $report.musical_comparison=Get-Content -LiteralPath $comparison -Raw -Encoding UTF8|ConvertFrom-Json
 if((Hash (Join-Path $scoreDirectory 'baseline.mscz'))-cne$baselineSha-or(Hash $inputCopy)-cne$fixtureSha){throw 'Original baseline or fixture copy changed.'}
 foreach($snapshot in $report.snapshots){if((Hash $snapshot.path)-cne$snapshot.sha256){throw 'An immutable save snapshot changed during native export.'}}
 $report.status='keyboard-and-native-comparison-passed-cleanup-pending'
}catch{$report.errors+=,$_.Exception.Message}
finally{
 if($app){try{Capture-OwnedWindow 'failed-before-close.png' $app $OutputDirectory $report;Close-App}catch{$report.errors+=,$_.Exception.Message}}
 if($localData-and(Test-Path -LiteralPath (Join-Path $OutputDirectory 'application-log-tails.json'))){
  $logs=Get-Content -LiteralPath (Join-Path $OutputDirectory 'application-log-tails.json') -Raw -Encoding UTF8|ConvertFrom-Json
  if(@($logs.files).Count-eq0){$report.errors+=,'No fresh application log available.'}
  $allText=(@($logs.files|ForEach-Object{$_.text})-join"`n")+[IO.File]::ReadAllText((Join-Path $OutputDirectory 'application.stderr.log'))
  $report.qml_error_matches=@([regex]::Matches($allText,'(?im)^.*(?:Cannot assign to|Unable to assign|ReferenceError|TypeError|is not a type|failed to load component).*$')|ForEach-Object{$_.Value}|Select-Object -First 30)
 }
 $drained=$false
 if($job){try{$d=Stop-OwnedJobChildren -Job $job;$report.drains+=,$d;$report.forced_descendants+=@($d.TerminatedPids).Count;$drained=$d.ChildrenDrained-and$d.ActiveProcesses-eq1}catch{$report.errors+=,$_.Exception.Message}}
 if((Test-Path -LiteralPath $profile)-and$drained){try{Invoke-Python 'cleanup-profile' @('-I',"$PSScriptRoot/CadenceProfileScope.py",'cleanup','--record',$profile);$record=Get-Content -LiteralPath $profile -Raw -Encoding UTF8|ConvertFrom-Json;$report.profile_cleanup_verified=$record.status-ceq'cleaned'}catch{$report.errors+=,$_.Exception.Message}}
 try{Invoke-Python 'verify-unchanged-runtime' @('-I',"$PSScriptRoot/Check-StageInventory.py",'--stage',$StagePath,'--inventory',$InventoryPath,'--output',(Join-Path $OutputDirectory 'stage-final.json'));$report.stage_unchanged=$true}catch{$report.errors+=,$_.Exception.Message}
 try{$report.fixture.original_preserved=(Hash $fixture)-ceq$fixtureSha;if(-not$report.fixture.original_preserved){throw 'Original CC0 fixture changed.'}}catch{$report.errors+=,$_.Exception.Message}
 if($job){try{$d=Stop-OwnedJobChildren -Job $job;$report.drains+=,$d;$report.forced_descendants+=@($d.TerminatedPids).Count;$report['final_job_close']=Close-OwnedProcessJob -Job $job;$report.job_closed_cleanly=$true}catch{$report.errors+=,$_.Exception.Message}}
 if($report.status-ceq'keyboard-and-native-comparison-passed-cleanup-pending'-and$report.app_exit_code-eq0-and-not$report.app_close_forced-and-not$report.probe_forced-and$report.forced_owned_processes-eq0-and$report.forced_descendants-eq0-and$report.profile_cleanup_verified-and$report.job_closed_cleanly-and$report.stage_unchanged-and$report.fixture.original_preserved-and@($report.errors).Count-eq0-and@($report.qml_error_matches).Count-eq0){$report.status='passed_actual_GUI_edit_save_single_undo_redo_and_native_comparison'}else{$report.status='failed-or-blocked'}
 $report|ConvertTo-Json -Depth 30|Set-Content -LiteralPath (Join-Path $OutputDirectory 'score-edit-gui-report.json') -Encoding UTF8
}
if($report.status-cne'passed_actual_GUI_edit_save_single_undo_redo_and_native_comparison'){throw 'Actual GUI score editing or cleanup remains blocked; inspect real receipts.'}
