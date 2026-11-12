# SPDX-License-Identifier: GPL-3.0-only
#Requires -Version 7.2
[CmdletBinding()]
param([Parameter(Mandatory)][string]$StagePath,[Parameter(Mandatory)][string]$RestorationRecord,
      [Parameter(Mandatory)][string]$OutputDirectory)
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
if((Hash $qaFile) -cne 'ef73d1b128741b88b59a4d5bff5a6920fce33233978acb2a14af9ba3334f0395'){throw 'Reviewed QA manifest differs.'}
$qa=Get-Content -LiteralPath $qaFile -Raw -Encoding utf8|ConvertFrom-Json
if($qa.schema_version -ne 1 -or $qa.content_pack_sha256 -cne '00906d5d4bc85eabb931e9afebb4c2b9c5a452ef2a6a6b28916dbaa867016d03' -or
   $qa.stage_executable_sha256 -cne 'c29d7c8c76b213b79d7390acd65cbabc6fb940f06e3e7f86c0ce60be7e9b9520' -or @($qa.files).Count -ne 11){throw 'Exact content/stage/helper identities required.'}
foreach($entry in $qa.files){
 if($entry.path -cnotmatch '^[A-Za-z0-9_.-]+$' -or $entry.path.Contains('..') -or $entry.sha256 -cnotmatch '^[a-f0-9]{64}$'){throw 'Unsafe QA manifest entry.'}
 $item=Get-Item -LiteralPath (Join-Path $source $entry.path) -Force
 if($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $item.Length -ne $entry.bytes -or (Hash $item.FullName) -cne $entry.sha256){throw ('Reviewed helper/content bytes differ: '+$entry.path)}
}
$root=[IO.Path]::GetFullPath($OutputDirectory)
$temp=[IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\','/')+[IO.Path]::DirectorySeparatorChar
if(-not $root.StartsWith($temp,[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $root)){throw 'New output strictly below RUNNER_TEMP required.'}
[void][IO.Directory]::CreateDirectory($root)
$profile=Join-Path $root 'profile-scope.json'
$python=(Get-Command python -CommandType Application -ErrorAction Stop|Select-Object -First 1).Source
$report=[ordered]@{schema_version=1;status='running';stage_build_number=2006;content_pack_sha256=$qa.content_pack_sha256;executable_sha256=$qa.stage_executable_sha256;commands=@();drains=@();profile_cleanup_verified=$false;job_closed_cleanly=$false;errors=@();forced_descendants=0;GUI_tested=$false;human_listening=$false;ASIO_endpoint_used=$false;application_recompiled=$false;MSI_modified=$false}
$job=$null
function Write-BoundedPythonStderr([string]$Name,[int]$ExitCode,[string]$Text){
 if($ExitCode -eq 0){return}
 $maximum=8192
 $tail=if($Text.Length -gt $maximum){$Text.Substring($Text.Length-$maximum)}else{$Text}
 $diagnostic=[ordered]@{name=$Name;exit_code=$ExitCode;original_characters=$Text.Length;printed_characters=$tail.Length;maximum_characters=$maximum;tail_only=($Text.Length -gt $maximum);text=$tail}
 Write-Host 'CADENCE_OPENSCORE_PYTHON_STDERR_BEGIN'
 Write-Host ($diagnostic|ConvertTo-Json -Depth 4 -Compress)
 Write-Host 'CADENCE_OPENSCORE_PYTHON_STDERR_END'
}
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
  Write-BoundedPythonStderr -Name $Name -ExitCode $row.exit_code -Text $err
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
 Invoke-Owned 'ten-native-scores' @('-I','-X','utf8',(Join-Path $source 'Run-OpenScoreCorpus.py'),'--stage',$StagePath,'--restoration-record',$RestorationRecord,'--profile-record',$profile,'--output',(Join-Path $root 'native-evidence')) 1500
 $native=Get-Content -LiteralPath (Join-Path $root 'native-evidence/openscore-native-report.json') -Raw -Encoding utf8|ConvertFrom-Json
 if($native.status -cne 'passed-ten-native-score-cases' -or $native.cases.Count -ne 10 -or $native.cases_passed -ne 10 -or
    -not $native.originals_unchanged -or -not $native.stage_unchanged -or @($native.commands).Count -ne 40){throw 'All ten real cases and forty commands must pass; sources and stage must remain unchanged.'}
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
 if($report.status -ceq 'native-checks-passed-cleanup-pending' -and $report.profile_cleanup_verified -and $report.job_closed_cleanly -and -not $report.errors.Count){$report.status='passed-ten-native-scores-with-owned-cleanup'}
 elseif($report.status -cne 'failed-or-blocked'){$report.status='cleanup-failed'}
 $report|ConvertTo-Json -Depth 20|Set-Content -LiteralPath (Join-Path $root 'result.json') -Encoding utf8NoBOM
 Write-Host 'CADENCE_OPENSCORE_RESULT_BEGIN';Write-Host ($report|ConvertTo-Json -Depth 20 -Compress);Write-Host 'CADENCE_OPENSCORE_RESULT_END'
}
if($report.status -cne 'passed-ten-native-scores-with-owned-cleanup'){throw 'Native OpenScore QA failed or blocked; inspect exact reports.'}
