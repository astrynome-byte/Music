# SPDX-License-Identifier: GPL-3.0-only
# Synthetic native Windows test only: never reads an application token/profile.
[CmdletBinding()]
param(
 [Parameter(Mandatory)][string]$HarnessPath,
 [Parameter(Mandatory)][string]$JobModulePath,
 [Parameter(Mandatory)][string]$OutputDirectory
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if(-not[OperatingSystem]::IsWindows()-or-not[Environment]::Is64BitProcess-or
 $env:GITHUB_ACTIONS-ne'true'-or$env:CI-ne'true'-or$env:RUNNER_ENVIRONMENT-ne'github-hosted'-or
 -not[Environment]::UserInteractive-or[Diagnostics.Process]::GetCurrentProcess().SessionId-eq0){throw 'Interactive disposable hosted Windows x64 runner required.'}
$root=[IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\','/')+[IO.Path]::DirectorySeparatorChar
$HarnessPath=[IO.Path]::GetFullPath($HarnessPath);$OutputDirectory=[IO.Path]::GetFullPath($OutputDirectory)
foreach($path in @($HarnessPath,$OutputDirectory)){
 if(-not$path.StartsWith($root,[StringComparison]::OrdinalIgnoreCase)){throw 'Native helper/evidence must be beneath RUNNER_TEMP.'}
 $ancestor=$path
 while($ancestor){if((Test-Path -LiteralPath $ancestor)-and((Get-Item -LiteralPath $ancestor -Force).Attributes-band[IO.FileAttributes]::ReparsePoint)){throw 'Reparse ancestor refused.'};$next=[IO.Path]::GetDirectoryName($ancestor.TrimEnd('\','/'));if(-not$next-or$next-eq$ancestor){break};$ancestor=$next}
}
if((Test-Path -LiteralPath $OutputDirectory)-or-not(Test-Path -LiteralPath $HarnessPath -PathType Leaf)){throw 'Fresh evidence path and compiled native helper required.'}
[void][IO.Directory]::CreateDirectory($OutputDirectory)
$report=[ordered]@{schema_version=1;status='running';scope='Synthetic native password Edit and file/focus guards only';real_token_used=$false;Cadence_application_executed=$false;server_started=$false;helper_sha256=(Get-FileHash -LiteralPath $HarnessPath -Algorithm SHA256).Hash.ToLowerInvariant();client_exit_code=$null;forced_client=$false;forced_descendants=0;job_closed=$false;drains=@();native_report=$null;errors=@()}
$job=$null;$process=$null;$started=$false
try{
 Import-Module $JobModulePath -Force;$job=New-OwnedProcessJob
 $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$HarnessPath;$info.WorkingDirectory=[IO.Path]::GetDirectoryName($HarnessPath);$info.UseShellExecute=$false;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
 foreach($key in @($info.Environment.Keys)){if($key-match'^(?i:GH_TOKEN$|GITHUB_TOKEN$|QT|QML)'){[void]$info.Environment.Remove($key)}}
 $info.Environment['PATH']=[IO.Path]::GetDirectoryName($HarnessPath)+';'+(Join-Path $env:SystemRoot 'System32')
 $process=[Diagnostics.Process]::new();$process.StartInfo=$info
 if(-not$process.Start()){throw 'Synthetic native helper did not start.'};$started=$true
 $out=$process.StandardOutput.ReadToEndAsync();$err=$process.StandardError.ReadToEndAsync()
 if(-not$process.WaitForExit(45000)){$report.forced_client=$true;$process.Kill($true);[void]$process.WaitForExit(5000);throw 'Owned synthetic helper exceeded45seconds.'}
 $capture=[Threading.Tasks.Task]::WhenAll([Threading.Tasks.Task[]]@($out,$err))
 if(-not$capture.Wait(5000)){throw 'Owned synthetic helper output pipes did not close within5seconds.'}
 $stdout=$out.GetAwaiter().GetResult();$stderr=$err.GetAwaiter().GetResult()
 [IO.File]::WriteAllText((Join-Path $OutputDirectory 'native.original.stdout.json'),$stdout,[Text.UTF8Encoding]::new($false))
 [IO.File]::WriteAllText((Join-Path $OutputDirectory 'native.original.stderr.log'),$stderr,[Text.UTF8Encoding]::new($false))
 $report.client_exit_code=$process.ExitCode
 if($stdout.Length-gt65536-or$stderr.Length-gt65536){throw 'Unexpectedly large synthetic native output.'}
 $native=$stdout|ConvertFrom-Json
 $report.native_report=$native
 $expected=@('synthetic-43-base64url-password-entry','wrong-process-id-refused','plain-text-field-refused','nonempty-password-field-refused','wrong-accessible-label-refused','short-token-file-refused','oversized-token-file-refused','invalid-base64url-alphabet-refused','synthetic-CRLF-token-accepted','outside-runner-temp-path-refused-before-open','directory-token-refused','multiply-linked-token-file-refused')
 if($native.observation_attempt-ne2-or$native.worker_started-isnot[bool]-or-not$native.worker_started-or$native.worker_completed-isnot[bool]-or-not$native.worker_completed-or
    $native.worker_exit_code-ne0-or$native.process_exit_without_cpp_cleanup-isnot[bool]-or$native.process_exit_without_cpp_cleanup-or
    $native.worker_phase-ne10-or$native.worker_failure_phase-ne0-or$native.case_index-ne12-or
    $native.pump.foreign_timer_injected-isnot[bool]-or-not$native.pump.foreign_timer_injected-or
    $native.pump.foreign_quit_injected-isnot[bool]-or-not$native.pump.foreign_quit_injected-or
    $native.pump.injected_timer_observed-isnot[bool]-or-not$native.pump.injected_timer_observed-or
    $native.pump.injected_quit_observed-isnot[bool]-or-not$native.pump.injected_quit_observed-or
    $native.pump.foreign_timer_observed-lt1-or$native.pump.foreign_quit_observed-lt1-or
    $native.pump.timed_out-isnot[bool]-or$native.pump.timed_out-or
    $native.pump.wait_failed-isnot[bool]-or$native.pump.wait_failed-or
    $native.pump.setup_failed-isnot[bool]-or$native.pump.setup_failed){throw 'Actual worker completion and both ignored synthetic message regressions required.'}
 if($process.ExitCode-ne0-or$native.schema_version-ne1-or$native.passed-isnot[bool]-or-not$native.passed-or
    $native.owned_temporary_files_removed-isnot[bool]-or-not$native.owned_temporary_files_removed-or@($native.cases).Count-ne12){throw 'Native synthetic helper did not pass its12actual cases and cleanup.'}
 for($i=0;$i-lt12;$i++){
  $case=$native.cases[$i]
  if($case.case-cne$expected[$i]-or$case.passed-isnot[bool]-or-not$case.passed){throw 'Actual synthetic case differs from the reviewed inventory.'}
  if($i-eq0-or$i-eq8){if($case.input_count-ne86-or$case.masked_length-ne43){throw 'Synthetic entry counts differ.'}}
  elseif($case.input_count-ne0){throw 'A rejection attempted text input.'}
 }
 if($stderr.Length-ne0){throw 'Unexpected native helper stderr.'}
 $report.status='native-cases-passed-cleanup-pending'
}catch{$report.errors+=,$_.Exception.Message}
finally{
 if($process){try{if($started-and-not$process.HasExited){$report.forced_client=$true;$process.Kill($true);[void]$process.WaitForExit(5000)}}catch{$report.errors+=,$_.Exception.Message}finally{$process.Dispose()}}
 if($job){try{
  $drain=Stop-OwnedJobChildren -Job $job;$report.drains+=,$drain;$report.forced_descendants+=@($drain.TerminatedPids).Count
  if(-not$drain.ChildrenDrained-or$drain.ActiveProcesses-ne1){throw 'Owned child tree did not drain.'}
  [void](Close-OwnedProcessJob -Job $job);$report.job_closed=$true
 }catch{$report.errors+=,$_.Exception.Message}}
 if($report.status-ceq'native-cases-passed-cleanup-pending'-and-not$report.forced_client-and$report.forced_descendants-eq0-and$report.job_closed-and@($report.errors).Count-eq0){$report.status='passed-synthetic-native-password-entry-only'}else{$report.status='failed-or-blocked'}
 $report|ConvertTo-Json -Depth 15|Set-Content -LiteralPath (Join-Path $OutputDirectory 'qualification-report.json') -Encoding utf8NoBOM
 Write-Host 'CADENCE_SYNTHETIC_SECRET_QUALIFICATION_BEGIN';$report|ConvertTo-Json -Depth 15 -Compress|Write-Host;Write-Host 'CADENCE_SYNTHETIC_SECRET_QUALIFICATION_END'
}
if($report.status-cne'passed-synthetic-native-password-entry-only'){throw 'Synthetic primitive remains failed or blocked; inspect exact native output.'}
