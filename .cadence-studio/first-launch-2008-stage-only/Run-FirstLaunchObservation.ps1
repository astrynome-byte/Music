# SPDX-License-Identifier: GPL-3.0-only
# Known failed31 StageOnly source preparation; this never asserts overall PASS or MSI validation.
#Requires -Version 7.2
[CmdletBinding()]
param([Parameter(Mandatory)][string]$StagePath,
      [Parameter(Mandatory)][string]$StageAuthenticationReceipt,
      [Parameter(Mandatory)][string]$NativeProbePath,
      [Parameter(Mandatory)][string]$WorkPath)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$target=Get-Content -LiteralPath "$PSScriptRoot/target.json" -Raw|ConvertFrom-Json
foreach($name in @('ready','full_qualification_complete','MSI_produced_or_tested')){if($target.$name-isnot[bool]){throw 'StageOnly truth flags must be JSON booleans, not inferred overall qualification.'}}
if($target.ready-cne$true-or$target.scope-cne'known-failed31-stage-only-first-launch'-or
 $target.source_commit-cne'a2b7abaf045a8f3cb84ec2953d9e0e51b9e78903'-or$target.source_tree-cne'c5452043983a048ef0aeef085615af903de3f5b0'-or
 $target.producer_run_id-ne43408309742-or$target.producer_job_id-ne131828068954-or
 $target.producer_driver_commit-cne'a8470ae087841875fd39284188d0e9d11d95e32b'-or$target.producer_overall_conclusion-cne'failure'-or
 $target.expected_failed_step-ne31-or$target.producer_run_number-ne12-or$target.producer_run_attempt-ne1-or
 ($target.required_passed_steps-join',')-cne'25,26,27,28,29,30'-or$target.stage_artifact_id-ne14031621703-or
 $target.full_qualification_complete-cne$false-or$target.MSI_produced_or_tested-cne$false){throw 'Exact known-failed31 compiled stage only; no overall PASS or installer qualification allowed.'}
if($target.stage_archive_sha256-cne'360ee31bcd6599af40b8d395aad16db732ec32ebabe76b777aed465c274ae830'-or
 $target.stage_manifest_sha256-cne'266defaed6a0fe9033ef1ea3c50148bfd833ce84e01131508fea1ceedee8da53'-or
 $target.executable_sha256-cne'13cd4e6d2f408d2e64b187d4c3bff1188ff4192ac7b670d3a12373bbeb37f6cd'){throw 'Actual DATAONLY stage pins differ.'}
foreach($name in @('executable_sha256','stage_authentication_receipt_sha256','source_manifest_sha256')){if($target.$name-cnotmatch'^[a-f0-9]{64}$'){throw 'Actual stage, executable and source identities remain unknown.'}}
if(-not[OperatingSystem]::IsWindows()-or-not[Environment]::Is64BitProcess-or-not[Environment]::UserInteractive-or[Diagnostics.Process]::GetCurrentProcess().SessionId-eq0-or$env:CI-cne'true'-or$env:GITHUB_ACTIONS-cne'true'-or$env:RUNNER_ENVIRONMENT-cne'github-hosted'){throw 'Disposable interactive hosted Windows x64 only.'}
function Plain([string]$p){
 if(-not[IO.Path]::IsPathFullyQualified($p)-or$p.StartsWith('\\')){throw 'Absolute local path required.'};$p=[IO.Path]::GetFullPath($p)
 for($a=$p;$a;$a=[IO.Path]::GetDirectoryName($a.TrimEnd('\','/'))){if((Test-Path -LiteralPath $a)-and((Get-Item -LiteralPath $a -Force).Attributes-band[IO.FileAttributes]::ReparsePoint)){throw 'Reparse runtime path refused.'};if([IO.Path]::GetDirectoryName($a.TrimEnd('\','/'))-eq$a){break}};return $p
}
function Sha([string]$p){return(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant()}
$temporary=(Plain $env:RUNNER_TEMP).TrimEnd('\','/')+'\'
$StagePath=Plain $StagePath;$StageAuthenticationReceipt=Plain $StageAuthenticationReceipt;$NativeProbePath=Plain $NativeProbePath;$WorkPath=Plain $WorkPath
foreach($p in @($StagePath,$StageAuthenticationReceipt,$NativeProbePath,$WorkPath)){if(-not$p.StartsWith($temporary,[StringComparison]::OrdinalIgnoreCase)){throw 'Runtime paths must be below RUNNER_TEMP.'}}
if(Test-Path -LiteralPath $WorkPath){throw 'New observation output required.'}
if($WorkPath.StartsWith($StagePath.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)-or$StagePath.StartsWith($WorkPath.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Observation and stage must be separate.'}
if((Sha $StageAuthenticationReceipt)-cne$target.stage_authentication_receipt_sha256){throw 'Caller must authenticate and restore the exact actual stage first.'}
$manifestPath="$PSScriptRoot/source-manifest.json";if((Sha $manifestPath)-cne$target.source_manifest_sha256){throw 'Reviewed source manifest changed.'}
$manifest=Get-Content -LiteralPath $manifestPath -Raw|ConvertFrom-Json
foreach($row in $manifest.files){if($row.path-cnotmatch'^[A-Za-z0-9_./-]+$'-or$row.path.Contains('..')){throw 'Unsafe source path.'};$p=Plain(Join-Path $PSScriptRoot $row.path);if((Get-Item -LiteralPath $p).Length-ne$row.bytes-or(Sha $p)-cne$row.sha256){throw 'Original helper or observation source changed.'}}
$exe=Plain(Join-Path $StagePath 'bin/CadenceStudio4.exe');if((Sha $exe)-cne$target.executable_sha256){throw 'Actual executable differs.'}
if(@(Get-Process|Where-Object{$_.ProcessName-in@('CadenceStudio4','CadenceStudio4Development','MuseScore4','MuseScore4Development','MuseScoreStudio4')}).Count){throw 'An existing score application is left untouched.'}
[void][IO.Directory]::CreateDirectory($WorkPath)
$profile=Join-Path $WorkPath 'profile.json';$unseeded=Join-Path $WorkPath 'seed-removal.json';$readiness=Join-Path $WorkPath 'readiness';[void][IO.Directory]::CreateDirectory($readiness)
$report=[ordered]@{schema_version=1;status='failed-or-blocked';scope='StageOnly known-failed31 producer; first actual startup without INI, observation only';producer_overall_conclusion='failure';expected_failed_step=31;full_qualification_complete=$false;MSI_produced_or_tested=$false;source_commit=$target.source_commit;producer_run_id=$target.producer_run_id;application_arguments=@();pid=$null;app_exit_code=$null;probe_exit_code=$null;ini_absent_before_start=$false;setup_user_choices_exercised=$false;setup_completion_qualified=$false;first_launch_wizard_observed=$null;French_runtime_verified=$false;visual_review_required=$true;zero_network_claimed=$false;playback_qualified=$false;captures=@();forced_owned=@();profile_cleaned=$false;job_closed=$false;error=$null;cleanup_errors=@()}
$python=(Get-Command python -CommandType Application|Select-Object -First 1).Source
$job=$null;$app=$null;$appStarted=$false;$probe=$null;$probeStarted=$false;$lock=$null;$appOut=$null;$appErr=$null;$profileData=$null
function Python-Owned([string]$name,[string[]]$arguments){
 $i=[Diagnostics.ProcessStartInfo]::new();$i.FileName=$python;$i.UseShellExecute=$false;$i.RedirectStandardOutput=$true;$i.RedirectStandardError=$true
 foreach($a in $arguments){$i.ArgumentList.Add($a)};$p=[Diagnostics.Process]::new();$p.StartInfo=$i;$pStarted=$false
 try{if(-not$p.Start()){throw 'Owned preparation failed to start.'};$pStarted=$true;$o=$p.StandardOutput.ReadToEndAsync();$e=$p.StandardError.ReadToEndAsync();if(-not$p.WaitForExit(30000)){$report.forced_owned+=,$p.Id;$p.Kill($true);[void]$p.WaitForExit(5000);throw 'Owned profile operation timed out.'};if(-not[Threading.Tasks.Task]::WhenAll([Threading.Tasks.Task[]]@($o,$e)).Wait(5000)){throw 'Owned profile pipes did not close.'};[IO.File]::WriteAllText((Join-Path $WorkPath ($name+'.stdout.log')),$o.GetAwaiter().GetResult());[IO.File]::WriteAllText((Join-Path $WorkPath ($name+'.stderr.log')),$e.GetAwaiter().GetResult());if($p.ExitCode-ne0){throw ('Profile operation failed: '+$name)}}finally{if($pStarted-and-not$p.HasExited){$report.forced_owned+=,$p.Id;$p.Kill($true);[void]$p.WaitForExit(5000)};$p.Dispose()}
}
function Assert-App { $app.Refresh();if($app.HasExited-or$app.StartTime.ToUniversalTime().Ticks-ne$started-or[IO.Path]::GetFullPath($app.MainModule.FileName)-cne$exe-or(Sha $exe)-cne$target.executable_sha256){throw 'Owned app PID/time/image/bytes differ.'} }
try{
 Import-Module "$PSScriptRoot/runtime/OwnProcessJob.psm1" -Force;$job=New-OwnedProcessJob
 . "$PSScriptRoot/runtime/Owned-WindowEvidence.ps1"
 Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;
public static class CadenceFirstLaunchWindow {
 [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern int GetWindowText(IntPtr h,StringBuilder b,int n);
 [DllImport("user32.dll")] public static extern bool IsWindowEnabled(IntPtr h);
 [DllImport("user32.dll")] public static extern IntPtr GetWindow(IntPtr h,uint cmd);
 public static string Title(IntPtr h){var b=new StringBuilder(513);GetWindowText(h,b,513);return b.ToString();}
}
'@
 Python-Owned 'prepare-verify-remove-only-seed' @('-I',"$PSScriptRoot/Prepare-UnseededProfile.py",'prepare-and-remove','--record',$profile,'--receipt',$unseeded)
 Python-Owned 'verify-no-INI-before-start' @('-I',"$PSScriptRoot/Prepare-UnseededProfile.py",'verify-before-start','--record',$profile,'--receipt',$unseeded)
 $profileData=Get-Content -LiteralPath $profile -Raw|ConvertFrom-Json;$report.ini_absent_before_start=$true
 $lock=[IO.File]::Open($exe,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
 $i=[Diagnostics.ProcessStartInfo]::new();$i.FileName=$exe;$i.WorkingDirectory=Split-Path -Parent $exe;$i.UseShellExecute=$false;$i.RedirectStandardOutput=$true;$i.RedirectStandardError=$true
 foreach($k in @($i.Environment.Keys)){if($k-match'^(?i:GH_TOKEN$|GITHUB_TOKEN$|QT|QML|CMAKE_|VCPKG_|VSCMD_|VSINSTALLDIR$|VCINSTALLDIR$|VCTools|INCLUDE$|LIB$|LIBPATH$|WindowsSdk|WindowsSDK|UniversalCRTSdkDir$|UCRTVersion$|DevEnvDir$|ExtensionSdkDir$)'){[void]$i.Environment.Remove($k)}}
 $i.Environment['PATH']=(Split-Path -Parent $exe)+';'+(Join-Path $env:SystemRoot 'System32');$i.Environment['QT_ACCESSIBILITY']='1'
 $app=[Diagnostics.Process]::new();$app.StartInfo=$i;if(-not$app.Start()){throw 'Actual unseeded app did not start.'};$appStarted=$true;$report.pid=$app.Id;$started=$app.StartTime.ToUniversalTime().Ticks;$appOut=$app.StandardOutput.ReadToEndAsync();$appErr=$app.StandardError.ReadToEndAsync()
 Start-Sleep -Seconds 5;Assert-App
 $i=[Diagnostics.ProcessStartInfo]::new();$i.FileName=$NativeProbePath;$i.UseShellExecute=$false;$i.RedirectStandardOutput=$true;$i.RedirectStandardError=$true
 foreach($a in @('--pid',[string]$app.Id,'--output',$readiness)){$i.ArgumentList.Add($a)}
 $probe=[Diagnostics.Process]::new();$probe.StartInfo=$i;if(-not$probe.Start()){throw 'Original SDK readiness probe did not start.'};$probeStarted=$true;$report.native_probe_sha256=Sha $NativeProbePath;$out=$probe.StandardOutput.ReadToEndAsync();$err=$probe.StandardError.ReadToEndAsync()
 if(-not$probe.WaitForExit(45000)){$report.forced_owned+=,$probe.Id;$probe.Kill($true);[void]$probe.WaitForExit(5000);throw 'SDK observation timed out.'}
 $report.probe_exit_code=$probe.ExitCode;if(-not[Threading.Tasks.Task]::WhenAll([Threading.Tasks.Task[]]@($out,$err)).Wait(5000)){throw 'Probe output EOF not observed.'}
 [IO.File]::WriteAllText((Join-Path $WorkPath 'probe.stdout.log'),$out.GetAwaiter().GetResult());[IO.File]::WriteAllText((Join-Path $WorkPath 'probe.stderr.log'),$err.GetAwaiter().GetResult())
 $native=Get-Content -LiteralPath (Join-Path $readiness 'native-readiness.json') -Raw|ConvertFrom-Json;$report.native_readiness=$native
 Assert-App;Capture-OwnedWindow 'first-start-without-INI.png' $app $WorkPath $report
 if($probe.ExitCode-ne0-or$native.pid-ne$app.Id-or$native.ready-cne$true-or$native.status-notin@('ready_owned_semantic_control','ready_owned_introduction_dialog')){throw 'Original Home/Intro readiness was not established.'}
 if(@($report.captures|Where-Object{$_.status-ceq'saved_requires_visual_review'}).Count-ne1){throw 'An owned screenshot is required.'}
 $report.status='observation-collected-close-pending'
}catch{$report.error=$_.Exception.Message;if($appStarted-and-not$app.HasExited){Capture-OwnedWindow 'blocked-first-start.png' $app $WorkPath $report}}
finally{
 if($probe){try{if($probeStarted-and-not$probe.HasExited){$report.forced_owned+=,$probe.Id;$probe.Kill($true);[void]$probe.WaitForExit(5000)}}catch{$report.cleanup_errors+=,$_.Exception.Message};$probe.Dispose()}
 if($app){try{
  if($appStarted-and-not$app.HasExited){Assert-App
   $allowed=@('Introduction','Introduction - Cadence Studio','Getting started','Getting started - Cadence Studio')
   $intro=@([CadenceLibraryWindowNative]::Windows($app.Id)|Where-Object{[CadenceFirstLaunchWindow]::Title($_)-cin$allowed-and[CadenceFirstLaunchWindow]::IsWindowEnabled($_)-and[CadenceLibraryWindowNative]::Owned([CadenceFirstLaunchWindow]::GetWindow($_,4),$app.Id)-and-not[CadenceFirstLaunchWindow]::IsWindowEnabled([CadenceFirstLaunchWindow]::GetWindow($_,4))})
   if($intro.Count-gt1){throw 'Ambiguous owned Introduction windows; none chosen.'}
   if($intro.Count-eq1){[void][CadenceLibraryWindowNative]::CloseOwned($intro[0],$app.Id);$report.owned_introduction_close_requested=$true;[void]$app.WaitForExit(1500)}
   if(-not$app.HasExited){$app.Refresh();$main=$app.MainWindowHandle;if(-not[CadenceLibraryWindowNative]::Owned($main,$app.Id)-or-not[CadenceFirstLaunchWindow]::IsWindowEnabled($main)-or[CadenceFirstLaunchWindow]::GetWindow($main,4)-ne[IntPtr]::Zero){throw 'Owned enabled main window not proven after Intro close; unknown modal left untouched.'};[void][CadenceLibraryWindowNative]::CloseOwned($main,$app.Id);[void]$app.WaitForExit(12000)}
  }
  if($appStarted-and-not$app.HasExited){$report.forced_owned+=,$app.Id;$app.Kill($true);[void]$app.WaitForExit(5000)};if($appStarted){$report.app_exit_code=$app.ExitCode}
 }catch{$report.cleanup_errors+=,$_.Exception.Message;if($appStarted-and-not$app.HasExited){$report.forced_owned+=,$app.Id;$app.Kill($true);[void]$app.WaitForExit(5000)}}finally{if($appStarted-and$app.HasExited){$report.app_exit_code=$app.ExitCode};$app.Dispose()}}
 if($lock){$lock.Dispose()}
 $drained=$false;if($job){try{$report.drain=Stop-OwnedJobChildren -Job $job;$report.forced_owned+=@($report.drain.TerminatedPids);$drained=$report.drain.ChildrenDrained}catch{$report.cleanup_errors+=,$_.Exception.Message}}
 if($drained-and$appOut-and$appErr){try{if(-not[Threading.Tasks.Task]::WhenAll([Threading.Tasks.Task[]]@($appOut,$appErr)).Wait(5000)){throw 'Application EOF not observed after Job drain.'};[IO.File]::WriteAllText((Join-Path $WorkPath 'application.stdout.log'),$appOut.GetAwaiter().GetResult());[IO.File]::WriteAllText((Join-Path $WorkPath 'application.stderr.log'),$appErr.GetAwaiter().GetResult())}catch{$report.cleanup_errors+=,$_.Exception.Message}}
 if($drained-and$profileData-and$appStarted){try{Save-CadenceApplicationLogEvidence $profileData.local_org_root $WorkPath $report.pid}catch{$report.cleanup_errors+=,$_.Exception.Message}}
 if($drained-and(Test-Path -LiteralPath $profile)){try{Python-Owned 'cleanup-owned-unseeded-profile' @('-I',"$PSScriptRoot/runtime/CadenceProfileScope.py",'cleanup','--record',$profile);$clean=Get-Content -LiteralPath $profile -Raw|ConvertFrom-Json;$report.profile_cleaned=$clean.status-ceq'cleaned'}catch{$report.cleanup_errors+=,$_.Exception.Message}}
 if($job){try{$report.final_job=Close-OwnedProcessJob -Job $job;$report.job_closed=$true}catch{$report.cleanup_errors+=,$_.Exception.Message}}
 if($report.status-ceq'observation-collected-close-pending'-and$report.app_exit_code-eq0-and$report.profile_cleaned-and$report.job_closed-and-not$report.forced_owned.Count-and-not$report.cleanup_errors.Count){$report.status='stage-only-unseeded-startup-observed-clean-close-pending-visual-review'}else{$report.status='failed-or-blocked'}
 $report|ConvertTo-Json -Depth 24|Set-Content -LiteralPath (Join-Path $WorkPath 'first-launch-observation.json') -Encoding utf8NoBOM
 Write-Host 'CADENCE_FIRST_LAUNCH_OBSERVATION_BEGIN';$report|ConvertTo-Json -Depth 24 -Compress|Write-Host;Write-Host 'CADENCE_FIRST_LAUNCH_OBSERVATION_END'
}
if($report.status-cne'stage-only-unseeded-startup-observed-clean-close-pending-visual-review'){throw 'First unseeded observation failed or was blocked; no wizard/playback qualification inferred.'}
