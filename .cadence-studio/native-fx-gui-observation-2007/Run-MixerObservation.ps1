# SPDX-License-Identifier: GPL-3.0-only
# Private source preparation. ready=false refuses before native or profile work.
# This wrapper only opens one copied native file, observes UIA/F10 and closes.
#Requires -Version 7.2
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$StageArtifactDirectory,
    [Parameter(Mandatory)][string]$ActivationPath,
    [Parameter(Mandatory)][string]$ProbePath,
    [Parameter(Mandatory)][ValidatePattern('^[a-f0-9]{64}$')][string]$ExpectedProbeSha256,
    [Parameter(Mandatory)][string]$WorkPath
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$plan=Get-Content -LiteralPath "$PSScriptRoot/observation-plan.json" -Raw|ConvertFrom-Json
$activation=Get-Content -LiteralPath $ActivationPath -Raw|ConvertFrom-Json
if($activation.ready -cne $true -or $activation.scope -cne 'private-original2007-mixer-observation'){throw 'Explicit reviewed mixer observation activation is required.'}
if(-not [OperatingSystem]::IsWindows() -or -not [Environment]::Is64BitProcess -or
   -not [Environment]::UserInteractive -or [Diagnostics.Process]::GetCurrentProcess().SessionId -eq 0 -or
   $env:GITHUB_ACTIONS -cne 'true' -or $env:CI -cne 'true' -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted'){
    throw 'Only a disposable interactive hosted Windows x64 runner is permitted.'
}
function Plain([string]$Path){
    if(-not [IO.Path]::IsPathFullyQualified($Path) -or $Path.StartsWith('\\') -or $Path -match '[\x00\r\n]'){throw 'Absolute local runtime path required.'}
    $path=[IO.Path]::GetFullPath($Path)
    for($current=$path;$current;$current=[IO.Path]::GetDirectoryName($current.TrimEnd('\','/'))){
        if((Test-Path -LiteralPath $current) -and ((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'Reparse runtime path refused.'}
        if([IO.Path]::GetDirectoryName($current.TrimEnd('\','/')) -eq $current){break}
    }
    return $path
}
function Sha([string]$Path){return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
function Under([string]$Child,[string]$Parent){return $Child.StartsWith($Parent.TrimEnd('\','/')+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)}
$temporary=Plain $env:RUNNER_TEMP;$WorkPath=Plain $WorkPath;$StageArtifactDirectory=Plain $StageArtifactDirectory;$ProbePath=Plain $ProbePath
foreach($path in @($WorkPath,$StageArtifactDirectory,$ProbePath)){if(-not (Under $path $temporary)){throw 'All runtime artifacts, client and output must remain below RUNNER_TEMP.'}}
if((Test-Path -LiteralPath $WorkPath) -or (Under $WorkPath $StageArtifactDirectory) -or (Under $StageArtifactDirectory $WorkPath) -or
   (Under $ProbePath $WorkPath) -or (Sha $ProbePath) -cne $ExpectedProbeSha256){throw 'Distinct new runtime output and exact compiled client are required.'}
foreach($row in $plan.files){
    if($row.path -cnotmatch '^[A-Za-z0-9_./-]+$' -or $row.path.Contains('..')){throw 'Unsafe observation source manifest path.'}
    $file=Plain (Join-Path $PSScriptRoot $row.path)
    if((Get-Item -LiteralPath $file).Length -ne $row.bytes -or (Sha $file) -cne $row.sha256){throw ('Observation source differs: '+$row.path)}
}
$known=@('CadenceStudio4','CadenceStudio4Development','MuseScore4','MuseScore4Development','MuseScoreStudio4')
if(@(Get-Process|Where-Object{$_.ProcessName -in $known}).Count){throw 'A score process already exists; it is left untouched.'}
# The existing profile helper selects this real endpoint. The caller must own
# its established registry scope and retain it until this child Job is drained.
if($env:CADENCE_QA_CLOCK_REGISTRY_SCOPE -cnotmatch '^[a-f0-9-]{36}$'){throw 'The real qualified QA Clock registry scope must be active before observation.'}
$machine=[Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::LocalMachine,[Microsoft.Win32.RegistryView]::Registry64)
$class=$null;$endpoint=$null
try{
    $userBase=[Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::CurrentUser,[Microsoft.Win32.RegistryView]::Registry64)
    try{$shadow=$userBase.OpenSubKey('SOFTWARE\Classes\CLSID\{8176CDA0-8AF9-4483-A03D-45EE2F9E864E}',$false)
        if($shadow){$shadow.Dispose();throw 'A per-user COM shadow appeared; no existing key is modified.'}
    }finally{$userBase.Dispose()}
    $class=$machine.OpenSubKey('SOFTWARE\Classes\CLSID\{8176CDA0-8AF9-4483-A03D-45EE2F9E864E}\InprocServer32',$false)
    $endpoint=$machine.OpenSubKey('SOFTWARE\ASIO\Cadence QA Clock (silent sink)',$false)
    if(-not $class -or -not $endpoint -or $class.GetValue('CadenceQaScopeOwner') -cne $env:CADENCE_QA_CLOCK_REGISTRY_SCOPE -or
       $endpoint.GetValue('CadenceQaScopeOwner') -cne $env:CADENCE_QA_CLOCK_REGISTRY_SCOPE -or
       $endpoint.GetValue('CLSID') -cne '{8176CDA0-8AF9-4483-A03D-45EE2F9E864E}') {throw 'Owned real endpoint registry identity differs.'}
    $dll=Plain ([string]$class.GetValue(''))
    if(-not (Under $dll $temporary) -or (Sha $dll) -cne '08f570d7df0dfb5f2cafe899c6b6679e48d4e1fa132656e58f4b0113a8709fd2'){throw 'The actual qualified silent endpoint DLL differs.'}
}finally{if($class){$class.Dispose()};if($endpoint){$endpoint.Dispose()};$machine.Dispose()}
[void][IO.Directory]::CreateDirectory($WorkPath)
$report=[ordered]@{schema_version=1;status='pending-observation';source_commit='5058d29dad67e6131ee46ee617258ccfed8ba4b0';executable_sha256='dcfbf9155c6c972c37966a4b2b0dcd212133c8e31fb397c644dda800ac7122be';probe_sha256=$ExpectedProbeSha256;application_pid=$null;application_exit_code=$null;probe_exit_code=$null;fixture=$null;application_started=$false;score_edited=$false;FI15_qualified=$false;FI16_qualified=$false;captures=@();commands=@();forced_owned_processes=@();drains=@();profile_cleanup_verified=$false;app_clock_verified=$false;job_closed=$false;error=$null;cleanup_errors=@()}
$job=$null;$app=$null;$probe=$null;$exeLock=$null;$appOut=$null;$appErr=$null;$profileData=$null;$profile=Join-Path $WorkPath 'profile-scope.json'
$python=(Get-Command python -CommandType Application -ErrorAction Stop|Select-Object -First 1).Source
function Invoke-Preparation([string]$Name,[string[]]$Arguments){
    $start=[Diagnostics.ProcessStartInfo]::new();$start.FileName=$python;$start.UseShellExecute=$false;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true;$start.WorkingDirectory=$WorkPath
    foreach($argument in $Arguments){$start.ArgumentList.Add($argument)}
    $process=[Diagnostics.Process]::new();$process.StartInfo=$start;$started=$false
    try{
        if(-not $process.Start()){throw 'Owned preparation process failed to start.'}
        $started=$true
        $out=$process.StandardOutput.ReadToEndAsync();$err=$process.StandardError.ReadToEndAsync()
        if(-not $process.WaitForExit(60000)){$report.forced_owned_processes+=,$process.Id;$process.Kill();[void]$process.WaitForExit(5000);throw 'Owned preparation timeout.'}
        $proof=Stop-OwnedJobChildren -Job $job;$report.drains+=,$proof
        if(@($proof.TerminatedPids).Count){$report.forced_owned_processes+=@($proof.TerminatedPids);throw 'A preparation descendant required termination.'}
        $stdout=$out.GetAwaiter().GetResult();$stderr=$err.GetAwaiter().GetResult()
        if($stdout.Length -gt 2097152 -or $stderr.Length -gt 2097152){throw 'Bounded preparation transcript exceeded.'}
        [IO.File]::WriteAllText((Join-Path $WorkPath ($Name+'.stdout.log')),$stdout)
        [IO.File]::WriteAllText((Join-Path $WorkPath ($Name+'.stderr.log')),$stderr)
        $report.commands+=,[ordered]@{name=$Name;pid=$process.Id;exit_code=$process.ExitCode}
        if($process.ExitCode -ne 0){throw ('Owned preparation failed: '+$Name)}
    }finally{if($started -and -not $process.HasExited){$report.forced_owned_processes+=,$process.Id;$process.Kill();[void]$process.WaitForExit(5000)};$process.Dispose()}
}
function Assert-AppIdentity {
    $app.Refresh()
    if($app.HasExited -or $app.Id -ne $report.application_pid -or $app.StartTime.ToUniversalTime().Ticks -ne $startedTicks -or
       [IO.Path]::GetFullPath($app.MainModule.FileName) -cne $exe -or (Sha $exe) -cne $report.executable_sha256){throw 'Owned application PID/time/image/bytes differ.'}
}
try{
    Import-Module "$PSScriptRoot/runtime/OwnProcessJob.psm1" -Force;$job=New-OwnedProcessJob
    . "$PSScriptRoot/runtime/Owned-WindowEvidence.ps1"
    $stage=Join-Path $WorkPath 'stage'
    Invoke-Preparation 'restore-actual2007' @('-I',"$PSScriptRoot/restore_for_observation.py",'--artifact',$StageArtifactDirectory,'--stage',$stage,'--result',(Join-Path $WorkPath 'restoration.json'))
    Invoke-Preparation 'prepare-profile' @('-I',"$PSScriptRoot/runtime/CadenceProfileScope.py",'prepare','--record',$profile)
    Invoke-Preparation 'verify-profile' @('-I',"$PSScriptRoot/runtime/CadenceProfileScope.py",'verify','--record',$profile)
    $profileData=Get-Content -LiteralPath $profile -Raw|ConvertFrom-Json
    $fixtureSource=Plain "$PSScriptRoot/fixture.musicxml"
    if((Sha $fixtureSource) -cne 'ced8cabf84b4c3d7b446e8c3c3832a98667886d83e789e320faa9ea4b96d29d6'){throw 'Original CC0 cello MusicXML fixture changed.'}
    $musicxmlCopy=Join-Path $WorkPath 'cello-input-copy.musicxml';Copy-Item -LiteralPath $fixtureSource -Destination $musicxmlCopy
    $copy=Join-Path $WorkPath 'cello-observation-copy.mscz'
    # Conversion creates our own native copy with the actual2007 CLI. This is
    # preparation, not a File/Open GUI claim; source MusicXML stays unchanged.
    Invoke-Preparation 'convert-own-fixture-to-native' @('-I',"$PSScriptRoot/convert_fixture.py",'--stage',$stage,'--input',$musicxmlCopy,'--output',$copy,'--record',(Join-Path $WorkPath 'fixture-conversion.json'))
    $report.fixture=[ordered]@{source_path=$fixtureSource;source_sha256=Sha $fixtureSource;copy_path=$copy;copy_sha256_before=Sha $copy}
    $exe=Plain (Join-Path $stage 'bin/CadenceStudio4.exe')
    $exeLock=[IO.File]::Open($exe,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
    if((Sha $exe) -cne $report.executable_sha256){throw 'Actual2007 executable differs.'}
    $start=[Diagnostics.ProcessStartInfo]::new();$start.FileName=$exe;$start.UseShellExecute=$false;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true;$start.WorkingDirectory=Split-Path -Parent $exe
    $start.ArgumentList.Add($copy)
    $start.Environment['PATH']=(Split-Path -Parent $exe)+';'+(Join-Path $env:SystemRoot 'System32');$start.Environment['QT_ACCESSIBILITY']='1'
    foreach($key in @($start.Environment.Keys)){if($key -match '^(?i:QT(?!_ACCESSIBILITY$)|QML|CMAKE_|VCPKG_|VSCMD_|VSINSTALLDIR$|VCINSTALLDIR$|VCTools|INCLUDE$|LIB$|LIBPATH$|WindowsSdk|WindowsSDK|UniversalCRTSdkDir$|UCRTVersion$|DevEnvDir$|ExtensionSdkDir$|FrameworkDir|FrameworkVersion|GH_TOKEN$|GITHUB_TOKEN$)'){[void]$start.Environment.Remove($key)}}
    $stats=Join-Path $WorkPath 'clock-stats';[void][IO.Directory]::CreateDirectory($stats);$start.Environment['CADENCE_QA_CLOCK_STATS_DIR']=$stats
    $report.clock_stats_directory=$stats
    $app=[Diagnostics.Process]::new();$app.StartInfo=$start;if(-not $app.Start()){throw 'Owned GUI did not start.'}
    $report.application_started=$true;$report.application_pid=$app.Id;$startedTicks=$app.StartTime.ToUniversalTime().Ticks
    $report.application_start_time_utc=$app.StartTime.ToUniversalTime().ToString('o')
    $report.source_manifest_sha256=Sha "$PSScriptRoot/observation-plan.json"
    $appOut=$app.StandardOutput.ReadToEndAsync();$appErr=$app.StandardError.ReadToEndAsync()
    $clock=[Diagnostics.Stopwatch]::StartNew()
    do{Assert-AppIdentity;$windows=@([CadenceLibraryWindowNative]::Windows($app.Id));if($windows.Count){break};Start-Sleep -Milliseconds 200}while($clock.Elapsed.TotalSeconds -lt 35)
    if(-not $windows.Count){throw 'No owned GUI window appeared.'}
    Start-Sleep -Seconds 5
    Assert-AppIdentity
    Capture-OwnedWindow 'before-observation.png' $app $WorkPath $report
    $probeStart=[Diagnostics.ProcessStartInfo]::new();$probeStart.FileName=$ProbePath;$probeStart.UseShellExecute=$false;$probeStart.RedirectStandardOutput=$true;$probeStart.RedirectStandardError=$true
    foreach($argument in @('--pid',[string]$app.Id,'--exe',$exe,'--output',(Join-Path $WorkPath 'uia'))){$probeStart.ArgumentList.Add($argument)}
    $probe=[Diagnostics.Process]::new();$probe.StartInfo=$probeStart;Assert-AppIdentity
    if(-not $probe.Start()){throw 'Owned observation client did not start.'}
    $probeOut=$probe.StandardOutput.ReadToEndAsync();$probeErr=$probe.StandardError.ReadToEndAsync()
    if(-not $probe.WaitForExit(95000)){$report.forced_owned_processes+=,$probe.Id;$probe.Kill();[void]$probe.WaitForExit(5000);throw 'Owned observation client timed out.'}
    $report.probe_exit_code=$probe.ExitCode
    [IO.File]::WriteAllText((Join-Path $WorkPath 'probe.stdout.log'),$probeOut.GetAwaiter().GetResult())
    [IO.File]::WriteAllText((Join-Path $WorkPath 'probe.stderr.log'),$probeErr.GetAwaiter().GetResult())
    Assert-AppIdentity;Capture-OwnedWindow 'after-observation.png' $app $WorkPath $report
    $nativeFile=Get-Item -LiteralPath (Join-Path $WorkPath 'uia/observation-report.json')
    if($nativeFile.Length -gt 65536 -or ($nativeFile.Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'Native observation report is not a bounded regular file.'}
    $native=Get-Content -LiteralPath $nativeFile.FullName -Raw|ConvertFrom-Json
    $report.native_status=$native.status
    if($report.probe_exit_code -ne 0 -or $native.status -cne 'mixer_observation_collected_no_parameter_qualification' -or
       $native.pid -ne $app.Id -or $native.expected_executable_sha256 -cne $report.executable_sha256 -or
       $native.score_edited -cne $false -or $native.recovery_tested -cne $false -or $native.backup_tested -cne $false -or
       $native.tree_incomplete -cne $false -or $native.foreign_node_refused -cne $false -or
       $native.gestures_attempted -lt 1 -or $native.gestures_attempted -gt 1 -or $native.gesture_limit -ne 1){throw 'Native observation was blocked or its owned no-edit contract differs.'}
    $report.status='observation-recorded-close-pending'
}catch{$report.status='blocked-or-failed-observation';$report.error=$_.Exception.Message}
finally{
    if($probe){try{if(-not $probe.HasExited){$report.forced_owned_processes+=,$probe.Id;$probe.Kill();[void]$probe.WaitForExit(5000)}}catch{$report.cleanup_errors+=,$_.Exception.Message};$probe.Dispose()}
    if($app){
        try{
            if(-not $app.HasExited){Assert-AppIdentity;$app.Refresh();$main=$app.MainWindowHandle
                if(-not [CadenceLibraryWindowNative]::Owned($main,$app.Id)){throw 'Owned main HWND missing before the sole close request.'}
                [void][CadenceLibraryWindowNative]::CloseOwned($main,$app.Id)
                if(-not $app.WaitForExit(12000)){$report.forced_owned_processes+=,$app.Id;$app.Kill();[void]$app.WaitForExit(5000)}}
            $report.application_exit_code=$app.ExitCode
        }catch{$report.cleanup_errors+=,$_.Exception.Message};$app.Dispose()
    }
    if($exeLock){$exeLock.Dispose()}
    $drained=$false
    if($job){try{$proof=Stop-OwnedJobChildren -Job $job;$report.drains+=,$proof;$report.forced_owned_processes+=@($proof.TerminatedPids);$drained=$true}catch{$report.cleanup_errors+=,$_.Exception.Message}}
    # Descendants may retain inherited transcript pipes. Drain the exact owned
    # Job first, then wait a bounded time for EOF before reading either task.
    if($drained -and $appOut -and $appErr){try{
        if(-not $appOut.Wait(5000) -or -not $appErr.Wait(5000)){throw 'Owned application transcript EOF was not observed after Job drainage.'}
        $stdout=$appOut.GetAwaiter().GetResult();$stderr=$appErr.GetAwaiter().GetResult()
        if($stdout.Length -gt 2097152 -or $stderr.Length -gt 2097152){throw 'Application transcript exceeds two MiB.'}
        [IO.File]::WriteAllText((Join-Path $WorkPath 'application.stdout.log'),$stdout)
        [IO.File]::WriteAllText((Join-Path $WorkPath 'application.stderr.log'),$stderr)
    }catch{$report.cleanup_errors+=,$_.Exception.Message}}
    if($drained -and $profileData -and $report.application_pid){Save-CadenceApplicationLogEvidence $profileData.local_org_root $WorkPath $report.application_pid}
    if((Test-Path -LiteralPath $profile) -and $drained){try{Invoke-Preparation 'cleanup-profile' @('-I',"$PSScriptRoot/runtime/CadenceProfileScope.py",'cleanup','--record',$profile);$clean=Get-Content -LiteralPath $profile -Raw|ConvertFrom-Json;$report.profile_cleanup_verified=$clean.status -ceq 'cleaned'}catch{$report.cleanup_errors+=,$_.Exception.Message}}
    if($drained -and $report.application_started){try{
        Invoke-Preparation 'validate-app-stopped-clock' @('-I',"$PSScriptRoot/validate_clock.py",'--directory',$stats,'--output',(Join-Path $WorkPath 'app-clock-validation.json'))
        $report.app_clock_verified=$true
    }catch{$report.cleanup_errors+=,$_.Exception.Message}}
    if($report.fixture){try{$report.fixture.source_sha256_after=Sha $fixtureSource;$report.fixture.copy_sha256_after=Sha $copy
        if($report.fixture.source_sha256_after -cne $report.fixture.source_sha256 -or $report.fixture.copy_sha256_after -cne $report.fixture.copy_sha256_before){throw 'Original/copy score changed during observation.'}}catch{$report.cleanup_errors+=,$_.Exception.Message}}
    if($job){try{$report.final_job_close=Close-OwnedProcessJob -Job $job;$report.job_closed=$true}catch{$report.cleanup_errors+=,$_.Exception.Message}}
    if($report.status -ceq 'observation-recorded-close-pending' -and $report.application_exit_code -eq 0 -and
       $report.profile_cleanup_verified -and $report.app_clock_verified -and $report.job_closed -and -not $report.forced_owned_processes.Count -and -not $report.cleanup_errors.Count){$report.status='mixer-observation-collected-no-FX-FI15-FI16-qualification'}else{$report.status='blocked-or-failed-observation'}
    $report|ConvertTo-Json -Depth 24|Set-Content -LiteralPath (Join-Path $WorkPath 'observation-result.json') -Encoding utf8NoBOM
}
if($report.status -cne 'mixer-observation-collected-no-FX-FI15-FI16-qualification'){throw 'Observation was blocked or cleanup was not clean; inspect actual reports.'}
