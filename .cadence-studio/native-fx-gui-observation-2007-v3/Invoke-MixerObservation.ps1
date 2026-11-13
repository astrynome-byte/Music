# SPDX-License-Identifier: GPL-3.0-only
# Inactive source recipe. Only exact target activation permits owned observation.
#Requires -Version 7.2
[CmdletBinding()]
param([Parameter(Mandatory)][string]$EndpointArtifactPath,
      [Parameter(Mandatory)][string]$StageArtifactPath,
      [Parameter(Mandatory)][string]$ProbePath,
      [Parameter(Mandatory)][string]$WorkPath)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$activationPath=Join-Path $PSScriptRoot 'target.json'
$target=Get-Content -LiteralPath $activationPath -Raw|ConvertFrom-Json
if($target.ready -cne $true -or $target.scope -cne 'private-original2007-mixer-observation' -or
   $target.source_commit -cne '5058d29dad67e6131ee46ee617258ccfed8ba4b0' -or
   $target.executable_sha256 -cne 'dcfbf9155c6c972c37966a4b2b0dcd212133c8e31fb397c644dda800ac7122be' -or
   $target.stage_artifact_id -ne 13970570430 -or $target.endpoint_artifact_id -ne 13941567509){throw 'Exact explicitly activated original2007 observation required.'}
if(-not [OperatingSystem]::IsWindows() -or -not [Environment]::Is64BitProcess -or
   -not [Environment]::UserInteractive -or $env:CI -cne 'true' -or $env:GITHUB_ACTIONS -cne 'true' -or
   $env:RUNNER_ENVIRONMENT -cne 'github-hosted'){throw 'Disposable interactive hosted Windows x64 only.'}
function Plain([string]$Path){
    if(-not [IO.Path]::IsPathFullyQualified($Path) -or $Path.StartsWith('\\') -or $Path -match '[\x00\r\n]'){throw 'Absolute local path required.'}
    $p=[IO.Path]::GetFullPath($Path)
    for($c=$p;$c;$c=[IO.Path]::GetDirectoryName($c.TrimEnd('\','/'))){
        if((Test-Path -LiteralPath $c) -and ((Get-Item -LiteralPath $c -Force).Attributes-band[IO.FileAttributes]::ReparsePoint)){throw 'Reparse runtime path refused.'}
        if([IO.Path]::GetDirectoryName($c.TrimEnd('\','/')) -eq $c){break}
    };return $p
}
function Sha([string]$Path){return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
function Below([string]$Child,[string]$Parent){return $Child.StartsWith($Parent.TrimEnd('\','/')+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)}
$temp=Plain $env:RUNNER_TEMP
$EndpointArtifactPath=Plain $EndpointArtifactPath;$StageArtifactPath=Plain $StageArtifactPath;$ProbePath=Plain $ProbePath;$WorkPath=Plain $WorkPath
$roots=@($EndpointArtifactPath,$StageArtifactPath,$WorkPath)
foreach($p in @($roots)+$ProbePath){if(-not(Below $p $temp)){throw 'Runtime paths must remain below RUNNER_TEMP.'}}
foreach($a in $roots){foreach($b in $roots){if($a -cne $b -and ((Below $a $b)-or(Below $b $a))){throw 'Runtime roots must be separate.'}}}
if($roots|Group-Object|Where-Object{$_.Count-ne1}){throw 'Distinct runtime roots required.'}
if(Test-Path -LiteralPath $WorkPath){throw 'New outer observation work path required.'}
$manifest=Get-Content -LiteralPath "$PSScriptRoot/observation-plan.json" -Raw|ConvertFrom-Json
foreach($row in $manifest.files){
    if($row.path-cnotmatch'^[A-Za-z0-9_./-]+$'-or$row.path.Contains('..')){throw 'Unsafe source path.'}
    $p=Plain (Join-Path $PSScriptRoot $row.path)
    if((Get-Item -LiteralPath $p).Length-ne$row.bytes-or(Sha $p)-cne$row.sha256){throw ('Reviewed source changed: '+$row.path)}
}
[void][IO.Directory]::CreateDirectory($WorkPath)
$python=(Get-Command python -CommandType Application -ErrorAction Stop|Select-Object -First 1).Source
$pwsh=(Get-Command pwsh -CommandType Application -ErrorAction Stop|Select-Object -First 1).Source
$report=[ordered]@{schema_version=1;status='running';source_commit=$target.source_commit;stage_artifact_id=13970570430;endpoint_artifact_id=13941567509;registered_harness_passed=$false;registry_cleanup_verified=$false;job_closed=$false;commands=@();drains=@();forced_descendants=0;error=$null;cleanup_errors=@();physical_audio_output=$false;human_listening=$false;FX_parameters_qualified=$false;FI15_qualified=$false;FI16_qualified=$false}
$job=$null;$registry=Join-Path $WorkPath 'registry-scope.json';$oldStats=$env:CADENCE_QA_CLOCK_STATS_DIR
function Run-Owned([string]$Name,[string]$Program,[string[]]$Arguments,[int]$Seconds){
    $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$Program;$info.WorkingDirectory=$WorkPath;$info.UseShellExecute=$false;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    foreach($a in $Arguments){$info.ArgumentList.Add($a)}
    foreach($k in @('GH_TOKEN','GITHUB_TOKEN')){[void]$info.Environment.Remove($k)}
    $p=[Diagnostics.Process]::new();$p.StartInfo=$info;$started=$false
    try{
        if(-not$p.Start()){throw 'Owned child failed to start.'};$started=$true
        $stdout=$p.StandardOutput.ReadToEndAsync();$stderr=$p.StandardError.ReadToEndAsync()
        if(-not$p.WaitForExit($Seconds*1000)){$report.forced_descendants++;$p.Kill($true);[void]$p.WaitForExit(5000);throw ('Owned child timeout: '+$Name)}
        $drain=Stop-OwnedJobChildren -Job $job;$report.drains+=,$drain;$report.forced_descendants+=@($drain.TerminatedPids).Count
        if(-not$stdout.Wait(5000)-or-not$stderr.Wait(5000)){throw 'Owned pipes did not reach EOF after drainage.'}
        $out=$stdout.GetAwaiter().GetResult();$err=$stderr.GetAwaiter().GetResult()
        if($out.Length-gt2097152-or$err.Length-gt2097152){throw 'Owned transcript exceeds bound.'}
        [IO.File]::WriteAllText((Join-Path $WorkPath ($Name+'.stdout.log')),$out);[IO.File]::WriteAllText((Join-Path $WorkPath ($Name+'.stderr.log')),$err)
        Write-Host ('CADENCE_OWNED_CHILD '+$Name+' exit='+$p.ExitCode+' stdout_chars='+$out.Length+' stderr_chars='+$err.Length)
        if($out.Length){Write-Host ($out.Substring(0,[Math]::Min(65536,$out.Length)))}
        if($err.Length){Write-Host ($err.Substring(0,[Math]::Min(16384,$err.Length)))}
        $report.commands+=,[ordered]@{name=$Name;pid=$p.Id;exit_code=$p.ExitCode}
        if($p.ExitCode-ne0-or@($drain.TerminatedPids).Count){throw ('Owned command or descendants failed: '+$Name)}
    }finally{if($started-and-not$p.HasExited){$report.forced_descendants++;$p.Kill($true);[void]$p.WaitForExit(5000)};$p.Dispose()}
}
function Drain-Owned {if($job){$d=Stop-OwnedJobChildren -Job $job;$report.drains+=,$d;$report.forced_descendants+=@($d.TerminatedPids).Count}}
try{
    Import-Module "$PSScriptRoot/runtime/OwnProcessJob.psm1" -Force;$job=New-OwnedProcessJob
    Run-Owned 'read-original-endpoint' $python @('-I',"$PSScriptRoot/runtime/Read-EndpointEvidence.py",'--root',$EndpointArtifactPath,'--output',(Join-Path $WorkPath 'original-endpoint-evidence.json')) 30
    $dll=Plain (Join-Path $EndpointArtifactPath 'CadenceQaClock.dll');$harness=Plain (Join-Path $EndpointArtifactPath 'CadenceQaClockHarness.exe')
    $stats=Join-Path $WorkPath 'registered-harness-stats';[void][IO.Directory]::CreateDirectory($stats);$env:CADENCE_QA_CLOCK_STATS_DIR=$stats
    Import-Module "$PSScriptRoot/runtime/QaRegistryScope.psm1" -Force
    Invoke-QaClockRegistryScope -DllPath $dll -ExpectedDllSha256 '08f570d7df0dfb5f2cafe899c6b6679e48d4e1fa132656e58f4b0113a8709fd2' -ResultPath $registry -AssertBeforeCleanup {Drain-Owned} -Action {
        Run-Owned 'registered-harness' $harness @($dll,'--registered') 45
        $text=[IO.File]::ReadAllText((Join-Path $WorkPath 'registered-harness.stdout.log'))
        if($text-notmatch'PASS 4 native ASIO ABI scenarios through CoCreateInstance inside explicit owned registry scope; no physical output or listening\.'-or@(Get-ChildItem -LiteralPath $stats -File -Filter 'clock-*.json').Count-ne4){throw 'Four registered harness scenarios and stopped reports required.'}
        Run-Owned 'check-registered-clock' $python @('-I',"$PSScriptRoot/validate_clock.py",'--directory',$stats,'--output',(Join-Path $WorkPath 'registered-clock-validation.json')) 30
        $report.registered_harness_passed=$true
        Run-Owned 'actual2007-mixer-observation' $pwsh @('-NoProfile','-File',"$PSScriptRoot/Run-MixerObservation.ps1",'-StageArtifactDirectory',$StageArtifactPath,'-ActivationPath',$activationPath,'-ProbePath',$ProbePath,'-ExpectedProbeSha256',(Sha $ProbePath),'-WorkPath',(Join-Path $WorkPath 'app-observation')) 300
        $inner=Get-Content -LiteralPath (Join-Path $WorkPath 'app-observation/observation-result.json') -Raw|ConvertFrom-Json
        if($inner.status-cne'mixer-observation-collected-no-FX-FI15-FI16-qualification'-or$inner.app_clock_verified-cne$true){throw 'Actual owned observation or GUI engine callbacks did not pass.'}
        $report.status='observation-collected-pending-cleanup'
    }
}catch{$report.status='blocked-or-failed';$report.error=$_.Exception.Message}
finally{
    try{Drain-Owned}catch{$report.cleanup_errors+=,$_.Exception.Message}
    $env:CADENCE_QA_CLOCK_STATS_DIR=$oldStats
    if(Test-Path -LiteralPath $registry){try{$r=Get-Content -LiteralPath $registry -Raw|ConvertFrom-Json;$report.registry_cleanup_verified=$r.cleanup_verified-ceq$true}catch{$report.cleanup_errors+=,$_.Exception.Message}}
    if($job){try{$report.final_job_close=Close-OwnedProcessJob -Job $job;$report.job_closed=$true}catch{$report.cleanup_errors+=,$_.Exception.Message}}
    if($report.status-ceq'observation-collected-pending-cleanup'-and$report.registry_cleanup_verified-and$report.job_closed-and-not$report.forced_descendants-and-not$report.cleanup_errors.Count){$report.status='collected-mixer-observation-no-FX-parameter-or-recovery-qualification'}else{$report.status='blocked-or-failed'}
    $report|ConvertTo-Json -Depth 24|Set-Content -LiteralPath (Join-Path $WorkPath 'result.json') -Encoding utf8NoBOM
    Write-Host 'CADENCE_MIXER_OBSERVATION_BEGIN';Write-Host ($report|ConvertTo-Json -Depth 24 -Compress);Write-Host 'CADENCE_MIXER_OBSERVATION_END'
}
if($report.status-cne'collected-mixer-observation-no-FX-parameter-or-recovery-qualification'){throw 'Observation blocked or cleanup failed; retained evidence is not a GUI PASS.'}
