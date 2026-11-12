# SPDX-License-Identifier: GPL-3.0-only
#Requires -Version 7.2
[CmdletBinding()]
param([Parameter(Mandatory)][string]$OutputDirectory)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if(-not [OperatingSystem]::IsWindows() -or -not [Environment]::Is64BitProcess -or
   [Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture -ne 'X64' -or
   $env:CI -ne 'true' -or $env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted'){
 throw 'Only disposable native Windows x64 hosted CI; no native call made.'
}
function Hash([string]$Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
$source=$PSScriptRoot
$qaFile=Join-Path $source 'qa-manifest.json'
if((Hash $qaFile) -cne '5fcb4211d2794db9cd7fb7cee0f81cf5a60822d0144766e84f3ab192f169e13f'){throw 'Reviewed OMR QA manifest differs.'}
$qa=Get-Content -LiteralPath $qaFile -Raw -Encoding utf8|ConvertFrom-Json
if($qa.schema_version -ne 1 -or @($qa.files).Count -ne 6){throw 'Exact OMR helper identities required.'}
foreach($entry in $qa.files){
 if($entry.path -cnotmatch '^[A-Za-z0-9_.-]+$' -or $entry.path.Contains('..') -or $entry.sha256 -cnotmatch '^[a-f0-9]{64}$'){throw 'Unsafe QA manifest entry.'}
 $item=Get-Item -LiteralPath (Join-Path $source $entry.path) -Force
 if($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $item.Length -ne $entry.bytes -or (Hash $item.FullName) -cne $entry.sha256){throw ('Reviewed OMR helper bytes differ: '+$entry.path)}
}
$root=[IO.Path]::GetFullPath($OutputDirectory)
$temp=[IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\','/')+[IO.Path]::DirectorySeparatorChar
if(-not $root.StartsWith($temp,[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $root)){throw 'New output strictly below RUNNER_TEMP required.'}
[void][IO.Directory]::CreateDirectory($root)
$profile=Join-Path $root 'profile-scope.json'
$python=(Get-Command python -CommandType Application -ErrorAction Stop|Select-Object -First 1).Source
$report=[ordered]@{schema_version=1;status='running';scope='Real Audiveris PNG/PDF recognition and native Cadence2007 import';commands=@();drains=@();profile_cleanup_verified=$false;job_closed_cleanly=$false;errors=@();forced_descendants=0;GUI_tested=$false;human_listening=$false;application_recompiled=$false;MSI_modified=$false}
$job=$null
function Invoke-Owned([string]$Name,[string[]]$Arguments,[int]$Seconds){
 $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$python;$info.UseShellExecute=$false
 $info.WorkingDirectory=$root;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
 foreach($argument in $Arguments){$info.ArgumentList.Add($argument)}
 $process=[Diagnostics.Process]::new();$process.StartInfo=$info;$started=$false
 $row=[ordered]@{name=$Name;arguments=$Arguments;pid=$null;exit_code=$null;timed_out=$false};$report.commands+=,$row
 try{
  if(-not $process.Start()){throw 'Owned Python process did not start.'};$started=$true;$row.pid=$process.Id
  $stdout=$process.StandardOutput.ReadToEndAsync();$stderr=$process.StandardError.ReadToEndAsync()
  if(-not $process.WaitForExit($Seconds*1000)){$row.timed_out=$true;$process.Kill($true);[void]$process.WaitForExit(5000);throw ('Owned timeout: '+$Name)}
  $proof=Stop-OwnedJobChildren -Job $job;$report.drains+=,$proof;$report.forced_descendants+=@($proof.TerminatedPids).Count
  $out=$stdout.GetAwaiter().GetResult();$err=$stderr.GetAwaiter().GetResult()
  if($out.Length -gt 2097152 -or $err.Length -gt 2097152){throw 'Own transcript exceeds 2 MiB.'}
  [IO.File]::WriteAllText((Join-Path $root ($Name+'.stdout.log')),$out,[Text.UTF8Encoding]::new($false))
  [IO.File]::WriteAllText((Join-Path $root ($Name+'.stderr.log')),$err,[Text.UTF8Encoding]::new($false))
  Write-Host $out;$row.exit_code=$process.ExitCode
  if($row.exit_code -ne 0 -or $row.timed_out -or @($proof.TerminatedPids).Count){throw ('Owned command failed or left descendants: '+$Name)}
 }finally{
  if($started){
   if(-not $process.HasExited){$process.Kill($true);[void]$process.WaitForExit(5000)}
   $proof=Stop-OwnedJobChildren -Job $job;$report.drains+=,$proof;$report.forced_descendants+=@($proof.TerminatedPids).Count
  }
  $process.Dispose()
 }
}
try{
 Import-Module (Join-Path $source 'OwnProcessJob.psm1') -Force;$job=New-OwnedProcessJob
 Invoke-Owned 'python-version' @('--version') 30
 if(([IO.File]::ReadAllText((Join-Path $root 'python-version.stdout.log'))).Trim() -cnotmatch '^Python 3\.12\.'){throw 'Actual Python 3.12 required.'}
 Invoke-Owned 'prepare-profile' @('-I',(Join-Path $source 'CadenceProfileScope.py'),'prepare','--record',$profile) 30
 Invoke-Owned 'real-local-omr' @('-I','-X','utf8',(Join-Path $source 'Run-OmrChain.py'),'--profile-record',$profile,'--output',(Join-Path $root 'native-evidence')) 1800
 $native=Get-Content -LiteralPath (Join-Path $root 'native-evidence/omr-chain-report.json') -Raw -Encoding utf8|ConvertFrom-Json
 if($native.status -cne 'passed-real-PNG-and-PDF-OMR-then-native-import-with-canonical-notes-and-rhythms' -or @($native.cases).Count -ne 2 -or
    -not $native.fixture_unchanged -or -not $native.pinned_downloads_unchanged -or -not $native.native_executable_unchanged){throw 'The two real OMR cases, musical comparisons and source integrity must pass.'}
 $report.status='native-checks-passed-cleanup-pending'
}catch{$report.status='failed-or-blocked';$report.errors+=,$_.Exception.Message}
finally{
 $drained=$false
 if($job){try{$proof=Stop-OwnedJobChildren -Job $job;$report.drains+=,$proof;$report.forced_descendants+=@($proof.TerminatedPids).Count;$drained=$true}catch{$report.errors+=,$_.Exception.Message}}
 if((Test-Path -LiteralPath $profile) -and $drained){
  try{Invoke-Owned 'cleanup-profile' @('-I',(Join-Path $source 'CadenceProfileScope.py'),'cleanup','--record',$profile) 60
   $state=Get-Content -LiteralPath $profile -Raw|ConvertFrom-Json;$report.profile_cleanup_verified=$state.status -ceq 'cleaned'
  }catch{$report.errors+=,$_.Exception.Message}
 }elseif(Test-Path -LiteralPath $profile){$report.errors+=,'Profile cleanup refused without proven Job drainage.'}
 foreach($entry in $qa.files){if((Hash (Join-Path $source $entry.path)) -cne $entry.sha256){$report.errors+=,('QA input changed: '+$entry.path)}}
 if($job){try{$report.final_job_close=Close-OwnedProcessJob -Job $job;$report.job_closed_cleanly=$true}catch{$report.errors+=,$_.Exception.Message}}
 # No process, cleanup or native operation may occur after final Job close.
 if($report.forced_descendants){$report.errors+=,'An owned descendant required forced termination; no qualification PASS.'}
 if($report.status -ceq 'native-checks-passed-cleanup-pending' -and $report.profile_cleanup_verified -and $report.job_closed_cleanly -and -not $report.errors.Count){$report.status='passed-real-local-OMR-with-owned-cleanup'}
 elseif($report.status -cne 'failed-or-blocked'){$report.status='cleanup-failed'}
 $report|ConvertTo-Json -Depth 20|Set-Content -LiteralPath (Join-Path $root 'result.json') -Encoding utf8NoBOM
 Write-Host 'CADENCE_OMR_RESULT_BEGIN';Write-Host ($report|ConvertTo-Json -Depth 20 -Compress);Write-Host 'CADENCE_OMR_RESULT_END'
}
if($report.status -cne 'passed-real-local-OMR-with-owned-cleanup'){throw 'Native local OMR QA failed or blocked; inspect exact reports.'}
