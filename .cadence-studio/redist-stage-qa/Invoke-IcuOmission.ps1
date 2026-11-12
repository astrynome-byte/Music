# SPDX-License-Identifier: GPL-3.0-only
# Exactly one local-forwarder omission on a private copy of retained2005.
#Requires -Version 7.2
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ArtifactDirectory,
    [Parameter(Mandatory)][string]$BaselineStage,
    [Parameter(Mandatory)][string]$CandidateStage,
    [Parameter(Mandatory)][string]$OutputDirectory
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if(-not [OperatingSystem]::IsWindows() -or -not [Environment]::Is64BitProcess -or
   [Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture -ne 'X64' -or
   [Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne 'X64' -or
   $env:CI -ne 'true' -or $env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted'){
    throw 'Only disposable native Windows x64 hosted CI is permitted; no paths accessed.'
}
function Plain([string]$Value){
    if([string]::IsNullOrWhiteSpace($Value) -or $Value -notmatch '^[A-Za-z]:[\\/]' -or $Value -match '[\x00\r\n]'){
        throw 'An absolute local Windows path is required.'
    }
    $result=[IO.Path]::GetFullPath($Value)
    for($current=$result;$current;$current=[IO.Path]::GetDirectoryName($current.TrimEnd('\','/'))){
        if((Test-Path -LiteralPath $current) -and ((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)){
            throw 'Reparse QA path or ancestor refused.'
        }
    };$result
}
function Below([string]$Child,[string]$Parent){$Child.StartsWith($Parent.TrimEnd('\','/')+'\',[StringComparison]::OrdinalIgnoreCase)}
function Sha([string]$Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
$temporary=Plain $env:RUNNER_TEMP
$ArtifactDirectory=Plain $ArtifactDirectory;$BaselineStage=Plain $BaselineStage
$CandidateStage=Plain $CandidateStage;$OutputDirectory=Plain $OutputDirectory
$roots=@($ArtifactDirectory,$BaselineStage,$CandidateStage,$OutputDirectory)
foreach($path in $roots){
    if(-not (Below $path $temporary)){throw 'Every stage/input/output must stay strictly below RUNNER_TEMP.'}
    foreach($other in $roots){if($path -cne $other -and ((Below $path $other) -or (Below $other $path))){throw 'Runtime roots must be separate.'}}
}
if(@($roots|Sort-Object -Unique).Count -ne 4 -or -not (Test-Path -LiteralPath $ArtifactDirectory -PathType Container)){
    throw 'Four distinct roots and the original artifact directory are required.'
}
foreach($path in @($BaselineStage,$CandidateStage,$OutputDirectory)){if(Test-Path -LiteralPath $path){throw 'All stage/output directories must be new.'}}
$source=Plain $PSScriptRoot
$manifest=Get-Content -LiteralPath (Join-Path $source 'source-manifest.json') -Raw|ConvertFrom-Json
if($manifest.schema_version -ne 1 -or $manifest.status -cne 'source-prepared-ICU-omission-not-executed'){throw 'Reviewed source manifest is missing.'}
$seen=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach($row in $manifest.files){
    if($row.path -match '(^|/)\.\.?(/|$)|[\\:\x00-\x1f]|^/|//' -or -not $seen.Add($row.path)){throw 'Unsafe source-manifest path.'}
    $path=Plain (Join-Path $source $row.path)
    if(-not (Below $path $source) -or (Get-Item -LiteralPath $path).Length -ne $row.bytes -or (Sha $path) -cne $row.sha256){throw 'Reviewed QA source bytes differ.'}
}
$python=(Get-Command python -ErrorAction Stop).Source
[void][IO.Directory]::CreateDirectory($OutputDirectory)
$record=[ordered]@{schema_version=1;status='running';producer_build=2005;producer_run_id=43207550870
    only_requested_stage_change='omit bin/icuuc.dll from the private candidate copy after complete SystemDirectory proof'
    original_stage_modified=$null;system_files_modified=$null;DXC_DXIL_D3DCompiler47_or_Mesa_changed=$null
    all_graphics_backends_preserved=$true;application_rebuilt=$false;registry_or_driver_install_performed=$false
    system_icu_export_gate_passed=$false;candidate_exact_omission_verified=$false;own_process_System32_ICU_observed=$false
    existing_corpus_comparison_passed=$false;profile_cleanup_verified=$false;owned_job_closed_cleanly=$false
    forced_descendants=0;commands=@();error=$null;cleanup_errors=@();last_job_drain=$null}
$jobScope=$null;$profileRecord=Join-Path $OutputDirectory 'profile-scope.json'
function Drain-Owned {
    if($jobScope){
        $record.last_job_drain=Stop-OwnedJobChildren -Job $jobScope
        $record.forced_descendants+=@($record.last_job_drain.TerminatedPids).Count
    }
}
function Run-Owned([string]$Name,[string]$Program,[string[]]$Arguments,[int]$Seconds,[hashtable]$Environment=@{}){
    $start=[Diagnostics.ProcessStartInfo]::new();$start.FileName=$Program;$start.UseShellExecute=$false
    $start.CreateNoWindow=$true;$start.WorkingDirectory=$OutputDirectory
    $start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
    foreach($arg in $Arguments){$start.ArgumentList.Add($arg)}
    foreach($key in $Environment.Keys){$start.Environment[$key]=[string]$Environment[$key]}
    $process=[Diagnostics.Process]::new();$process.StartInfo=$start;$started=$false
    $row=[ordered]@{name=$Name;pid=$null;exit_code=$null;timed_out=$false;arguments=@($Program)+$Arguments};$record.commands+=,$row
    try{
        if(-not $process.Start()){throw 'Owned QA process did not start.'};$started=$true;$row.pid=$process.Id
        $out=$process.StandardOutput.ReadToEndAsync();$err=$process.StandardError.ReadToEndAsync()
        if(-not $process.WaitForExit($Seconds*1000)){$row.timed_out=$true;$process.Kill($true);if(-not $process.WaitForExit(5000)){throw 'Owned process did not stop at timeout.'}}
        # No descendant may retain an output pipe after the parent exits.
        Drain-Owned
        $text=$out.GetAwaiter().GetResult();$errors=$err.GetAwaiter().GetResult()
        if($text.Length -gt 1048576 -or $errors.Length -gt 1048576){throw 'Owned transcript exceeds its bound.'}
        [IO.File]::WriteAllText((Join-Path $OutputDirectory ($Name+'.stdout.log')),$text,[Text.UTF8Encoding]::new($false))
        [IO.File]::WriteAllText((Join-Path $OutputDirectory ($Name+'.stderr.log')),$errors,[Text.UTF8Encoding]::new($false))
        $row.exit_code=$process.ExitCode;Write-Host $text
        if($row.timed_out -or $row.exit_code -ne 0){throw "Owned QA command failed: $Name"}
    }finally{
        if($started -and -not $process.HasExited){$process.Kill($true);[void]$process.WaitForExit(5000)}
        if($started){Drain-Owned};$process.Dispose()
    }
}
function Stage-Hashes([string]$Root){
    $table=[Collections.Generic.Dictionary[string,string]]::new([StringComparer]::Ordinal)
    $items=@(Get-ChildItem -LiteralPath $Root -Recurse -Force)
    if($items.Count -gt 10000){throw 'Stage entry count exceeds bound.'}
    foreach($item in $items){
        [void](Plain $item.FullName)
        if($item.PSIsContainer){continue}
        if($item.Length -gt 524288000){throw 'Stage file exceeds its known extraction bound.'}
        $relative=[IO.Path]::GetRelativePath($Root,$item.FullName).Replace('\','/')
        $table.Add($relative,(Sha $item.FullName))
    };return $table
}
function Assert-HashMap($Expected,$Actual,[string]$Except=''){
    $missing=if($Except){1}else{0}
    if($Actual.Count -ne $Expected.Count-$missing){throw 'Stage member count differs from exact omission policy.'}
    foreach($key in $Expected.Keys){
        if($key -ceq $Except){if($Actual.ContainsKey($key)){throw 'The candidate still contains its local ICU forwarder.'};continue}
        if(-not $Actual.ContainsKey($key) -or $Actual[$key] -cne $Expected[$key]){throw "Unexpected stage-byte change: $key"}
    }
}
function Observe-SystemIcu([string]$Executable,[string]$SystemDirectory){
    $start=[Diagnostics.ProcessStartInfo]::new();$start.FileName=$Executable;$start.UseShellExecute=$false
    $start.CreateNoWindow=$true;$start.WorkingDirectory=$OutputDirectory
    $start.ArgumentList.Add('--long-version');$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
    $start.Environment['PATH']=(Split-Path -Parent $Executable)+';'+$SystemDirectory
    $start.Environment['QT_QPA_PLATFORM']='windows'
    $process=[Diagnostics.Process]::new();$process.StartInfo=$start;$started=$false
    $found=@{};$timer=[Diagnostics.Stopwatch]::StartNew()
    try{
        if(-not $process.Start()){throw 'The exact candidate executable did not start.'};$started=$true
        $out=$process.StandardOutput.ReadToEndAsync();$err=$process.StandardError.ReadToEndAsync()
        while(-not $process.HasExited -and $timer.Elapsed.TotalSeconds -lt 20){
            try{
                $process.Refresh()
                foreach($module in $process.Modules){
                    if($module.ModuleName -iin @('icuuc.dll','icu.dll','Qt6Core.dll')){
                        $path=[IO.Path]::GetFullPath($module.FileName)
                        $expected=if($module.ModuleName -ieq 'Qt6Core.dll'){Join-Path (Split-Path -Parent $Executable) 'Qt6Core.dll'}else{Join-Path $SystemDirectory $module.ModuleName}
                        if($path -ine [IO.Path]::GetFullPath($expected)){throw 'Owned process resolved a dependency outside its exact expected location.'}
                        $found[$module.ModuleName.ToLowerInvariant()]=@{path=$path;sha256=Sha $path}
                    }
                }
            }catch [ComponentModel.Win32Exception] { }
            catch [InvalidOperationException] {if(-not $process.HasExited){throw}}
            [void]$process.WaitForExit(10)
        }
        if(-not $process.HasExited){$process.Kill($true);[void]$process.WaitForExit(5000);throw 'Owned version/module probe timed out.'}
        Drain-Owned
        $text=$out.GetAwaiter().GetResult();$errors=$err.GetAwaiter().GetResult()
        if($text.Length -gt 65536 -or $errors.Length -gt 65536){throw 'Version-probe transcript exceeds bound.'}
        [IO.File]::WriteAllText((Join-Path $OutputDirectory 'candidate-loader.stdout.log'),$text)
        [IO.File]::WriteAllText((Join-Path $OutputDirectory 'candidate-loader.stderr.log'),$errors)
        if($process.ExitCode -ne 0 -or $found.Count -ne 3){throw 'Candidate did not prove both System32 ICU modules and its unchanged QtCore.'}
        return @{pid=$process.Id;exit_code=$process.ExitCode;modules=$found;scope='Only modules of the explicitly started candidate PID were read; no DLL injection or target-code invocation'}
    }finally{
        if($started -and -not $process.HasExited){$process.Kill($true);[void]$process.WaitForExit(5000)}
        if($started){Drain-Owned};$process.Dispose()
    }
}
try{
    Import-Module (Join-Path $source 'OwnProcessJob.psm1') -Force
    $jobScope=New-OwnedProcessJob
    & (Join-Path $source 'Restore-NextStage.ps1') -TargetPath (Join-Path $source 'target.json') `
        -ArtifactDirectory $ArtifactDirectory -StagePath $BaselineStage -ResultPath (Join-Path $OutputDirectory 'restoration.json')
    $baselineHashes=Stage-Hashes $BaselineStage
    if($baselineHashes['bin/icuuc.dll'] -cne '6febd789ff616dd6398ae2453adc1e7ccd7bbb6aee8c623a2638c1c00d51e003' -or
       $baselineHashes['bin/Qt6Core.dll'] -cne 'b98eea394a95563879b614dbd4432ce074b0fceeb154c3bae252f4e7a9376a40'){
        throw 'Retained ICU/QtCore bytes differ from the authenticated PE evidence.'
    }
    $systemDirectory=[Environment]::SystemDirectory
    Run-Owned 'system-icu-proof' $python @('-I',(Join-Path $source 'verify_system_icu.py'),'--system-directory',$systemDirectory,
        '--required-names-json',(Join-Path $source 'required-system-icu.json')) 40
    $proof=Get-Content -LiteralPath (Join-Path $OutputDirectory 'system-icu-proof.stdout.log') -Raw|ConvertFrom-Json
    if($proof.local_forwarder_omission_export_gate_passed -cne $true -or $proof.complete -cne $true -or $proof.resolutions.Count -ne 20 -or $proof.errors.Count){
        throw 'All20 exact Windows SystemDirectory ICU functions must resolve before any omission.'
    }
    $record.system_icu_export_gate_passed=$true;$record.system_icu_proof=$proof
    Copy-Item -LiteralPath $BaselineStage -Destination $CandidateStage -Recurse
    Assert-HashMap $baselineHashes (Stage-Hashes $CandidateStage)
    $localForwarder=Plain (Join-Path $CandidateStage 'bin/icuuc.dll')
    if((Sha $localForwarder) -cne $baselineHashes['bin/icuuc.dll']){throw 'The only omission candidate changed.'}
    [IO.File]::Delete($localForwarder)
    Assert-HashMap $baselineHashes (Stage-Hashes $CandidateStage) 'bin/icuuc.dll'
    $record.candidate_exact_omission_verified=$true;$record.baseline_stage_files=$baselineHashes.Count
    $record.DXC_DXIL_D3DCompiler47_or_Mesa_changed=$false
    Run-Owned 'prepare-profile' $python @('-I',(Join-Path $source 'CadenceProfileScope.py'),'prepare','--record',$profileRecord) 40
    Run-Owned 'verify-profile' $python @('-I',(Join-Path $source 'CadenceProfileScope.py'),'verify','--record',$profileRecord) 40
    # The unchanged scope helper verifies its ASIO seed, but this converter-only
    # experiment has no registered QA endpoint. Replace only our verified INI,
    # as in the already exercised native SF2 converter qualification.
    $profileState=Get-Content -LiteralPath $profileRecord -Raw|ConvertFrom-Json
    $settings=Plain $profileState.settings_file
    $expectedSettings=Join-Path ([Environment]::GetFolderPath('ApplicationData')) 'CadenceStudio/CadenceStudio4.ini'
    if($settings -ine [IO.Path]::GetFullPath($expectedSettings) -or (Sha $settings) -cne $profileState.seed_settings_sha256){
        throw 'Only the exact verified owned profile seed may be adjusted for converter use.'
    }
    $converterSettings=[Text.UTF8Encoding]::new($false).GetBytes("[application]`nhasCompletedFirstLaunchSetup=true`n`n[io]`naudioApi=WASAPI`noutputDevice=`nbufferSize=256`nsampleRate=48000`n")
    $settingsStream=[IO.File]::Open($settings,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
    try{
        if($settingsStream.Length -gt 2097152){throw 'Owned settings file exceeds its bound.'}
        $initialHash=[Security.Cryptography.SHA256]::HashData($settingsStream)
        if([Convert]::ToHexString($initialHash).ToLowerInvariant() -cne $profileState.seed_settings_sha256){throw 'Owned seed changed before converter configuration.'}
        $settingsStream.Position=0;$settingsStream.Write($converterSettings,0,$converterSettings.Length);$settingsStream.SetLength($converterSettings.Length);$settingsStream.Flush($true)
    }finally{$settingsStream.Dispose()}
    $record.owned_converter_settings=@{audio_api='WASAPI';output_device='default';path=$settings;sha256=Sha $settings;seed_verified_before_adjustment=$true}
    $candidateExe=Join-Path $CandidateStage 'bin/CadenceStudio4.exe'
    $record.candidate_loader_proof=Observe-SystemIcu $candidateExe $systemDirectory
    $record.own_process_System32_ICU_observed=$true
    foreach($variant in @(@{name='baseline';root=$BaselineStage},@{name='without-local-icu';root=$CandidateStage})){
        $exe=Join-Path $variant.root 'bin/CadenceStudio4.exe'
        $environment=@{PATH=(Join-Path $variant.root 'bin')+';'+$systemDirectory;QT_QPA_PLATFORM='windows'}
        Run-Owned ($variant.name+'-existing-corpus') $python @('-I',(Join-Path $source 'corpus_run_exports.py'),
            '--executable',$exe,'--output',(Join-Path $OutputDirectory $variant.name),'--timeout','45') 540 $environment
    }
    Run-Owned 'compare-existing-corpus' $python @('-I',(Join-Path $source 'compare_corpus_reports.py'),
        '--baseline',(Join-Path $OutputDirectory 'baseline/report.json'),'--candidate',(Join-Path $OutputDirectory 'without-local-icu/report.json')) 40
    $record.corpus_comparison=Get-Content -LiteralPath (Join-Path $OutputDirectory 'compare-existing-corpus.stdout.log') -Raw|ConvertFrom-Json
    $record.existing_corpus_comparison_passed=$true
    Assert-HashMap $baselineHashes (Stage-Hashes $BaselineStage)
    Assert-HashMap $baselineHashes (Stage-Hashes $CandidateStage) 'bin/icuuc.dll'
    $record.original_stage_modified=$false
    foreach($file in $proof.system_files){if((Sha $file.path) -cne $file.sha256){throw 'A system ICU file changed during the test.'}}
    $record.system_files_modified=$false
    $record.status='checks-passed-pending-owned-profile-cleanup'
}catch{$record.status='failed-or-blocked';$record.error=$_.Exception.Message;throw}
finally{
    $drained=$false
    try{Drain-Owned;$drained=$true}catch{$record.cleanup_errors+=('Owned process drain failed: '+$_.Exception.Message)}
    if(Test-Path -LiteralPath $profileRecord){
        if($drained){
            try{
                Run-Owned 'cleanup-profile' $python @('-I',(Join-Path $source 'CadenceProfileScope.py'),'cleanup','--record',$profileRecord) 60
                $state=Get-Content -LiteralPath $profileRecord -Raw|ConvertFrom-Json
                $record.profile_cleanup_verified=$state.status -ceq 'cleaned'
            }catch{$record.cleanup_errors+=$_.Exception.Message}
        }else{$record.cleanup_errors+='Profile cleanup refused because child-process drainage was not proven.'}
    }
    if($jobScope){
        try{$record.final_job_close=Close-OwnedProcessJob -Job $jobScope;$record.owned_job_closed_cleanly=$true}
        catch{$record.cleanup_errors+=('Owned Job close failed: '+$_.Exception.Message)}
    }
    if($record.forced_descendants){$record.cleanup_errors+='A descendant required forced termination; no clean qualification permitted.'}
    if($record.status -ne 'failed-or-blocked'){
        $record.status=if($record.profile_cleanup_verified -and $record.owned_job_closed_cleanly -and -not $record.cleanup_errors.Count){
            'passed-ICU-System32-resolution57-corpus-checks35-stable-hashes-and-cleanup'
        }else{'cleanup-failed'}
    }
    $record|ConvertTo-Json -Depth 20|Set-Content -LiteralPath (Join-Path $OutputDirectory 'icu-omission-result.json') -Encoding utf8NoBOM
    Write-Host 'CADENCE_ICU_OMISSION_RESULT_BEGIN';Write-Host ($record|ConvertTo-Json -Depth 20 -Compress);Write-Host 'CADENCE_ICU_OMISSION_RESULT_END'
    if($record.cleanup_errors.Count -or $record.status -eq 'cleanup-failed'){throw 'Owned cleanup failed; inspect the separate result.'}
}
