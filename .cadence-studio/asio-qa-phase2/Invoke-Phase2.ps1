# SPDX-License-Identifier: GPL-3.0-only
# Future disposable native Windows CI only. No application compilation or install.
#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$EndpointArtifactPath,
    [Parameter(Mandatory)][string]$StageArtifactPath,
    [Parameter(Mandatory)][string]$StagePath,
    [Parameter(Mandatory)][string]$WorkPath
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if(-not [OperatingSystem]::IsWindows() -or -not [Environment]::Is64BitProcess -or
   [Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne 'X64' -or
   $env:GITHUB_ACTIONS -ne 'true' -or $env:CI -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted'){
    throw 'Only disposable native Windows x64 GitHub-hosted CI is permitted.'
}
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
try{if(-not ([Security.Principal.WindowsPrincipal]::new($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'The disposable CI token cannot create the explicit QA-only HKLM keys.'}}finally{$identity.Dispose()}
function Plain([string]$Path){
    if([string]::IsNullOrWhiteSpace($Path) -or $Path -match '[\x00\r\n]'){throw 'Invalid QA path.'}
    $path=[IO.Path]::GetFullPath($Path)
    for($current=$path;$current;$current=[IO.Path]::GetDirectoryName($current.TrimEnd('\','/'))){
        if((Test-Path -LiteralPath $current) -and ((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'Reparse runtime path refused.'}
        if([IO.Path]::GetDirectoryName($current.TrimEnd('\','/')) -eq $current){break}
    };$path
}
function Below([string]$Child,[string]$Parent){$Child.StartsWith($Parent.TrimEnd('\','/')+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)}
function Sha([string]$Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
$temporary=Plain $env:RUNNER_TEMP
$EndpointArtifactPath=Plain $EndpointArtifactPath;$StageArtifactPath=Plain $StageArtifactPath;$StagePath=Plain $StagePath;$WorkPath=Plain $WorkPath
foreach($path in @($EndpointArtifactPath,$StageArtifactPath,$StagePath,$WorkPath)){if(-not (Below $path $temporary)){throw 'DLL/stage/artifacts/results must stay strictly below RUNNER_TEMP.'}}
$runtimeRoots=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach($path in @($EndpointArtifactPath,$StageArtifactPath,$StagePath,$WorkPath)){if(-not $runtimeRoots.Add($path)){throw 'Runtime roots must be distinct.'}}
if((Test-Path -LiteralPath $WorkPath) -or (Test-Path -LiteralPath $StagePath)){throw 'Work and extracted stage must be new.'}
foreach($a in @($EndpointArtifactPath,$StageArtifactPath,$StagePath,$WorkPath)){
    foreach($b in @($EndpointArtifactPath,$StageArtifactPath,$StagePath,$WorkPath)){
        if($a -cne $b -and ((Below $a $b) -or (Below $b $a))){throw 'Runtime roots must be separate.'}
    }
}
$source=Plain $PSScriptRoot
$manifest=Get-Content -LiteralPath (Join-Path $source 'phase2-source-manifest.json') -Raw|ConvertFrom-Json
if($manifest.schema_version -ne 1 -or $manifest.status -cne 'source-prepared-phase2-not-executed'){throw 'Reviewed source profile missing.'}
$seen=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach($file in $manifest.files){
    if($file.path -match '(^|/)\.\.?(/|$)|[\\:\x00-\x1f]|^/|//' -or -not $seen.Add($file.path)){throw 'Unsafe source profile member.'}
    $path=Plain (Join-Path $source $file.path)
    if(-not (Below $path $source) -or (Get-Item -LiteralPath $path).Length -ne $file.bytes -or (Sha $path) -cne $file.sha256){throw 'Phase2 source differs from the reviewed profile.'}
}
$python=(Get-Command python -ErrorAction Stop).Source
[void][IO.Directory]::CreateDirectory($WorkPath)
$record=[ordered]@{schema_version=1;status='running';endpoint_original_run_id=43212261044;endpoint_original_artifact_id=13941567509
    retained_application_build=2002;application_recompiled=$false;physical_audio_output=$false;human_listening=$false
    source_manifest_sha256=Sha (Join-Path $source 'phase2-source-manifest.json');commands=@();registered_harness_passed=$false
    same_GUI_render_save_passed=$false;registry_cleanup_verified=$false;profile_cleanup_verified=$false
    owned_process_job_created=$false;last_job_drain=$null;forced_descendants_terminated=0
    owned_job_closed_cleanly=$false;final_job_close=$null;error=$null;cleanup_errors=@()}
$owned=[Collections.Generic.List[Diagnostics.Process]]::new()
$processJob=$null
function Run-Owned([string]$Name,[string]$Program,[string[]]$Arguments,[int]$Seconds,[hashtable]$Environment=@{}){
    $start=[Diagnostics.ProcessStartInfo]::new();$start.FileName=$Program;$start.UseShellExecute=$false;$start.CreateNoWindow=$true
    $start.WorkingDirectory=$WorkPath;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
    foreach($argument in $Arguments){$start.ArgumentList.Add($argument)}
    foreach($key in $Environment.Keys){$start.Environment[$key]=[string]$Environment[$key]}
    $process=[Diagnostics.Process]::new();$process.StartInfo=$start;$started=$false
    $row=[ordered]@{name=$Name;pid=$null;arguments=@($Program)+$Arguments;exit_code=$null;timed_out=$false;forced=$false}
    $record.commands += $row
    try{
        if(-not $process.Start()){throw "Owned process did not start: $Name"}
        $started=$true;$owned.Add($process);$row.pid=$process.Id
        $stdout=$process.StandardOutput.ReadToEndAsync();$stderr=$process.StandardError.ReadToEndAsync()
        if(-not $process.WaitForExit($Seconds*1000)){$row.timed_out=$true;$row.forced=$true;$process.Kill($true);[void]$process.WaitForExit(5000);throw "Owned process timeout: $Name"}
        # A descendant may retain an inherited stdout pipe after its parent
        # exits. Drain the owned native Job before waiting for transcript EOF.
        $record.last_job_drain=Stop-OwnedJobChildren -Job $processJob
        if(@($record.last_job_drain.TerminatedPids).Count){$row.forced=$true;$record.forced_descendants_terminated+=@($record.last_job_drain.TerminatedPids).Count}
        $out=$stdout.GetAwaiter().GetResult();$err=$stderr.GetAwaiter().GetResult()
        if($out.Length -gt 1048576 -or $err.Length -gt 1048576){throw 'Unexpected oversized own-process transcript.'}
        [IO.File]::WriteAllText((Join-Path $WorkPath ($Name+'.stdout.log')),$out,[Text.UTF8Encoding]::new($false))
        [IO.File]::WriteAllText((Join-Path $WorkPath ($Name+'.stderr.log')),$err,[Text.UTF8Encoding]::new($false))
        $row.exit_code=$process.ExitCode
        Write-Host $out
        if($process.ExitCode -ne 0){throw "Owned process failed: $Name (exit $($process.ExitCode)); inspect retained report/logs."}
        if($row.forced){throw "Owned process left a descendant requiring termination: $Name"}
    }finally{
        if($started){
            if(-not $process.HasExited){$row.forced=$true;$process.Kill($true);if(-not $process.WaitForExit(5000)){throw 'Owned process tree did not drain.'}}
            $record.last_job_drain=Stop-OwnedJobChildren -Job $processJob
            $record.forced_descendants_terminated+=@($record.last_job_drain.TerminatedPids).Count
            [void]$owned.Remove($process)
        }
        $process.Dispose()
    }
}
function Drain-Owned {
    foreach($process in @($owned.ToArray())){
        if(-not $process.HasExited){$process.Kill($true);if(-not $process.WaitForExit(5000)){throw 'Owned process remained active before registry cleanup.'}}
        $process.Dispose();[void]$owned.Remove($process)
    }
    if($processJob){$record.last_job_drain=Stop-OwnedJobChildren -Job $processJob;$record.forced_descendants_terminated+=@($record.last_job_drain.TerminatedPids).Count}
    elseif($record.owned_process_job_created){throw 'Owned process Job is unexpectedly unavailable.'}
}
$profileRecord=Join-Path $WorkPath 'profile-scope.json';$registryRecord=Join-Path $WorkPath 'registry-scope.json'
$oldStats=$env:CADENCE_QA_CLOCK_STATS_DIR
try{
    Import-Module (Join-Path $source 'OwnProcessJob.psm1') -Force
    # Joining the controller first makes every future descendant inherit the
    # owned nested Job; there is no Start/Assign race for a fast child.
    $processJob=New-OwnedProcessJob
    $record.owned_process_job_created=$true
    Run-Owned 'read-original-endpoint' $python @('-I',(Join-Path $source 'Read-EndpointEvidence.py'),'--root',$EndpointArtifactPath,'--output',(Join-Path $WorkPath 'original-endpoint-evidence.json')) 30
    & (Join-Path $source 'Restore-CombinedStage.ps1') -ArtifactDirectory $StageArtifactPath -StagePath $StagePath -ResultPath (Join-Path $WorkPath 'stage-restoration.json')
    $dll=Plain (Join-Path $EndpointArtifactPath 'CadenceQaClock.dll');$harness=Plain (Join-Path $EndpointArtifactPath 'CadenceQaClockHarness.exe')
    if((Sha $dll) -cne '08f570d7df0dfb5f2cafe899c6b6679e48d4e1fa132656e58f4b0113a8709fd2' -or
       (Sha $harness) -cne 'adeea91ef5207b7425dfa90b8c412c23ca0d0e4ad9e99138b6dfe4778bcc9665'){throw 'Reviewed endpoint binaries changed before activation.'}
    $registeredStats=Join-Path $WorkPath 'registered-harness-stats';[void][IO.Directory]::CreateDirectory($registeredStats)
    $env:CADENCE_QA_CLOCK_STATS_DIR=$registeredStats
    Import-Module (Join-Path $source 'QaRegistryScope.psm1') -Force
    Invoke-QaClockRegistryScope -DllPath $dll -ExpectedDllSha256 '08f570d7df0dfb5f2cafe899c6b6679e48d4e1fa132656e58f4b0113a8709fd2' -ResultPath $registryRecord -AssertBeforeCleanup {Drain-Owned} -Action {
        try{
            Run-Owned 'registered-harness' $harness @($dll,'--registered') 45
            $text=[IO.File]::ReadAllText((Join-Path $WorkPath 'registered-harness.stdout.log'))
            if($text -notmatch 'PASS 4 native ASIO ABI scenarios through CoCreateInstance inside explicit owned registry scope; no physical output or listening\.'){
                throw 'Four real registered harness scenarios were not witnessed.'
            }
            $reports=@(Get-ChildItem -LiteralPath $registeredStats -File -Filter 'clock-*.json')
            if($reports.Count -ne 4){throw 'Four original reports from the registered harness are required.'}
            $record.registered_clock_reports=@()
            foreach($file in $reports){
                if($file.Length -gt 4096){throw 'Oversized registered clock report.'}
                $data=Get-Content -LiteralPath $file.FullName -Raw|ConvertFrom-Json
                if($data.schema_version -ne 1 -or $data.callbacks -lt 1 -or $data.frames -ne $data.callbacks*256 -or
                   $data.finite_samples -ne $data.frames*2 -or $data.callback_errors -ne 0 -or $data.nonfinite_samples -ne 0 -or
                   $data.physical_audio_output -cne $false -or $data.qualified_hardware -cne $false){throw 'Registered callback metrics differ.'}
                $record.registered_clock_reports += @{file=$file.Name;sha256=Sha $file.FullName;report=$data}
            }
            $record.registered_harness_passed=$true
            Run-Owned 'prepare-profile' $python @('-I',(Join-Path $source 'CadenceProfileScope.py'),'prepare','--record',$profileRecord) 30
            Copy-Item -LiteralPath $profileRecord -Destination (Join-Path $WorkPath 'profile-scope-prepared.snapshot.json')
            Run-Owned 'GUI-render-native-save' $python @('-I','-X','utf8',(Join-Path $source 'Run-Retention-WithClock.py'),'--stage',$StagePath,
                '--restoration-record',(Join-Path $WorkPath 'stage-restoration.json'),'--profile-record',$profileRecord,'--output',(Join-Path $WorkPath 'GUI-retention')) 420
            $gui=Get-Content -LiteralPath (Join-Path $WorkPath 'GUI-retention/retention-report.json') -Raw|ConvertFrom-Json
            if($gui.status -cne 'passed_same_GUI_project_resource_preservation' -or $gui.cases.Count -ne 2 -or
               @($gui.cases|Where-Object {-not $_.gui_audio_render_then_native_save_confirmed -or -not $_.audio.passed}).Count){throw 'Same real GUI project did not prove nonmute WAV, native save witness and resource preservation.'}
            $record.same_GUI_render_save_passed=$true
        }finally{Drain-Owned}
    }
    $scope=Get-Content -LiteralPath $registryRecord -Raw|ConvertFrom-Json
    $record.registry_cleanup_verified=$scope.cleanup_verified -eq $true -and $scope.status -ceq 'action-returned-owned-keys-removed'
    if(-not $record.registry_cleanup_verified){throw 'Owned registry cleanup did not verify.'}
    $record.status='registered-endpoint-and-retained2002-GUI-passed-pending-profile-cleanup'
}catch{$record.status='failed-or-blocked';$record.error=$_.Exception.Message;throw}
finally{
    $drained=$false
    try{Drain-Owned;$drained=$true}catch{$record.cleanup_errors += $_.Exception.Message}
    $env:CADENCE_QA_CLOCK_STATS_DIR=$oldStats
    if(Test-Path -LiteralPath $registryRecord){
        try{$scope=Get-Content -LiteralPath $registryRecord -Raw|ConvertFrom-Json;$record.registry_cleanup_verified=$scope.cleanup_verified -eq $true}catch{$record.cleanup_errors += $_.Exception.Message}
    }
    if((Test-Path -LiteralPath $profileRecord) -and $drained){
        try{
            Run-Owned 'cleanup-profile' $python @('-I',(Join-Path $source 'CadenceProfileScope.py'),'cleanup','--record',$profileRecord) 60
            $profile=Get-Content -LiteralPath $profileRecord -Raw|ConvertFrom-Json
            $record.profile_cleanup_verified=$profile.status -ceq 'cleaned'
        }catch{$record.cleanup_errors += $_.Exception.Message}
    }
    elseif(Test-Path -LiteralPath $profileRecord){$record.cleanup_errors += 'Profile deletion refused: owned process Job drain did not verify.'}
    if($processJob){
        try{$record.final_job_close=Close-OwnedProcessJob -Job $processJob;$record.owned_job_closed_cleanly=$true}
        catch{$record.cleanup_errors += ('Owned Job could not close cleanly: '+$_.Exception.Message)}
    }
    if($record.forced_descendants_terminated -gt 0){$record.cleanup_errors += 'A descendant required forced termination; this execution cannot qualify a clean GUI close.'}
    if($record.status -cne 'failed-or-blocked' -and $record.registry_cleanup_verified -and $record.profile_cleanup_verified -and -not $record.cleanup_errors.Count){
        $record.status='passed-registered-endpoint-and-retained2002-GUI-with-cleanup'
    }elseif($record.status -cne 'failed-or-blocked'){$record.status='cleanup-failed'}
    $record|ConvertTo-Json -Depth 18|Set-Content -LiteralPath (Join-Path $WorkPath 'phase2-result.json') -Encoding utf8NoBOM
    Write-Host 'CADENCE_ASIO_PHASE2_RESULT_BEGIN';Write-Host ($record|ConvertTo-Json -Depth 18 -Compress);Write-Host 'CADENCE_ASIO_PHASE2_RESULT_END'
    if($record.cleanup_errors.Count -or $record.status -ceq 'cleanup-failed'){throw 'Owned profile/registry cleanup failed; inspect the separate result.'}
}
