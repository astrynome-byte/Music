# SPDX-License-Identifier: GPL-3.0-only
# Actual retained2005 UI only; no application rebuild, purchase or bank install.
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$StagePath,
    [Parameter(Mandatory)][string]$ProbePath,
    [Parameter(Mandatory)][string]$OutputDirectory,
    [Parameter(Mandatory)][ValidatePattern('^[a-f0-9]{64}$')][string]$ExpectedExecutableSha256
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if(-not[OperatingSystem]::IsWindows()-or$env:OS-ne'Windows_NT'-or-not[Environment]::Is64BitProcess-or[Runtime.InteropServices.RuntimeInformation]::OSArchitecture-ne'X64'-or$env:GITHUB_ACTIONS-ne'true'-or$env:CI-ne'true'-or$env:RUNNER_ENVIRONMENT-ne'github-hosted'){throw 'Disposable native Windows x64 hosted CI required before any write or firewall call.'}
if(-not$env:RUNNER_TEMP-or-not[Environment]::UserInteractive-or[Diagnostics.Process]::GetCurrentProcess().SessionId-eq0){throw 'An interactive owned runner desktop is required.'}
function Full-Path([string]$Path){if([string]::IsNullOrWhiteSpace($Path)-or$Path-match'[;\r\n"\x00*?]'){throw 'Unsupported path.'};[IO.Path]::GetFullPath($Path)}
function Is-Below([string]$Child,[string]$Parent){$Child.StartsWith($Parent.TrimEnd('\','/')+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)}
function Assert-NoReparse([string]$Path){while($Path){if((Test-Path -LiteralPath $Path)-and((Get-Item -LiteralPath $Path -Force).Attributes-band[IO.FileAttributes]::ReparsePoint)){throw 'Reparse path refused.'};$parent=[IO.Path]::GetDirectoryName($Path.TrimEnd('\','/'));if(-not$parent-or$parent-eq$Path){break};$Path=$parent}}
function Hash([string]$Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
$StagePath=Full-Path $StagePath;$ProbePath=Full-Path $ProbePath;$OutputDirectory=Full-Path $OutputDirectory;$temporary=Full-Path $env:RUNNER_TEMP
foreach($path in @($StagePath,$ProbePath,$OutputDirectory)){if(-not(Is-Below $path $temporary)){throw 'Stage, client and new evidence must be below RUNNER_TEMP.'};Assert-NoReparse $path}
if((Test-Path -LiteralPath $OutputDirectory)-or(Is-Below $OutputDirectory $StagePath)-or(Is-Below $StagePath $OutputDirectory)){throw 'Evidence must be new and separate from the stage.'}
$executable=Join-Path $StagePath 'bin/CadenceStudio4.exe'
if(-not(Test-Path -LiteralPath $executable -PathType Leaf)-or-not(Test-Path -LiteralPath $ProbePath -PathType Leaf)-or(Hash $executable)-cne$ExpectedExecutableSha256-or$ExpectedExecutableSha256-cne'd957ffc99497cb01b1f00f82ba1d6e89ef84547708506c6c51423675805e140a'){throw 'Actual retained2005 executable/native client required.'}
$known=@('CadenceStudio4','CadenceStudio4Development','MuseScore4','MuseScore4Development','MuseScoreStudio4')
if(@(Get-Process|Where-Object{$_.ProcessName-in$known}).Count){throw 'Existing score application refused; nothing was started or closed.'}
[void][IO.Directory]::CreateDirectory($OutputDirectory);$treeDirectory=Join-Path $OutputDirectory 'uia';[void][IO.Directory]::CreateDirectory($treeDirectory)
$report=[ordered]@{
 schema_version=1;status='pending';phase='preflight';scope='Actual sound-offer/license UI, eight local lesson controls and UI-created CC0 exercise copy/editor; no editing/listening/bank installation'
 executable=$executable;executable_sha256=Hash $executable;probe=$ProbePath;probe_sha256=Hash $ProbePath;started_utc=[DateTime]::UtcNow.ToString('o');finished_utc=$null
 pid=$null;probe_exit_code=$null;native_probe_status=$null;native_claims_passed=$false;native_claim_error=$null
 profile_isolated_by_script=$false;hosted_disposable_profile=$true;profile_seeded_by_script=$false;onboarding_tested=$false;no_account_credentials_supplied=$true
 captures=@();cleanup=[ordered]@{forced=$false;exit_code=$null;events=@();error=$null};probe_cleanup_forced=$false;close_probe=$null;exercise_evidence=$null;exercise_evidence_error=$null
 coach_tested=$false;score_editing_tested=$false;listening_tested=$false;bank_download_requested=$false;purchase_requested=$false
 physical_network_disconnected=$false;network_scope='Exact staged EXE outbound Block/Any; all firewall profiles/services must already be enabled; runner/GitHub transport remain online';network_probe_performed=$false;child_executable_network_coverage=$false
 firewall=[ordered]@{rule_name=$null;creation_attempted=$false;created=$false;active_store_verified=$false;active_profiles=@();service_states=@();snapshots=@();removed=$false;cleanup_error=$null}
 error=$null
}
. "$PSScriptRoot/Owned-WindowEvidence.ps1"
. "$PSScriptRoot/Scoped-OfflineRule.ps1"
. "$PSScriptRoot/Read-ExerciseEvidence.ps1"
function Invoke-OwnedExerciseClose($OwnedApp,[string]$Client,[string]$Directory) {
    $OwnedApp.Refresh();if($OwnedApp.HasExited){throw 'Exercise app exited before its controlled close observation.'}
    if(Test-Path -LiteralPath $Directory){throw 'Close evidence directory must be new.'}
    [void][IO.Directory]::CreateDirectory($Directory)
    $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$Client;$info.UseShellExecute=$false;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    foreach($argument in @('--pid',[string]$OwnedApp.Id,'--output',$Directory,'--close-exercise','true')){$info.ArgumentList.Add($argument)}
    $close=[Diagnostics.Process]::new();$close.StartInfo=$info
    try{
        if(-not$close.Start()){throw 'Owned close client did not start.'}
        $out=$close.StandardOutput.ReadToEndAsync();$err=$close.StandardError.ReadToEndAsync()
        if(-not$close.WaitForExit(45000)){$close.Kill($true);[void]$close.WaitForExit(5000);throw 'Owned close client timed out.'}
        [IO.File]::WriteAllText((Join-Path $Directory 'close.stdout.log'),$out.GetAwaiter().GetResult());[IO.File]::WriteAllText((Join-Path $Directory 'close.stderr.log'),$err.GetAwaiter().GetResult())
        $path=Join-Path $Directory 'close-report.json'
        if(-not(Test-Path -LiteralPath $path)-or(Get-Item -LiteralPath $path).Length-gt262144){throw 'Owned close report is absent or oversized.'}
        $data=Get-Content -LiteralPath $path -Raw -Encoding utf8|ConvertFrom-Json
        if($close.ExitCode-ne0){throw 'Native owned close client did not report success.'}
        [void](Test-OwnedExerciseCloseClaims $data $OwnedApp.Id)
        return [ordered]@{status='owned_exercise_close_exit0_observed';probe_exit_code=$close.ExitCode;report=$data;report_sha256=Hash $path}
    }finally{try{if($close.Id-and-not$close.HasExited){$close.Kill($true);[void]$close.WaitForExit(5000)}}catch{};$close.Dispose()}
}
$app=$null;$probe=$null;$stdout=$null;$stderr=$null;$native=$null;$ruleName=$null;$ruleCreationAttempted=$false
$ruleDescription='Cadence retained2005 tools UI offline QA; exact owned disposable executable; '+[guid]::NewGuid().ToString('D')
$roamingBase=[Environment]::GetFolderPath([Environment+SpecialFolder]::ApplicationData)
$localBase=[Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
$documentsBase=[Environment]::GetFolderPath([Environment+SpecialFolder]::MyDocuments,[Environment+SpecialFolderOption]::DoNotVerify)
$userRoot=Full-Path([Environment]::GetFolderPath([Environment+SpecialFolder]::UserProfile))
foreach($base in @($roamingBase,$localBase,$documentsBase)){if(-not[IO.Path]::IsPathFullyQualified($base)-or-not(Is-Below (Full-Path $base) $userRoot)){throw 'Known folders must belong to the disposable runner user.'};Assert-NoReparse (Full-Path $base)}
$configurationDirectory=Join-Path $roamingBase 'CadenceStudio';$localDataDirectory=Join-Path $localBase 'CadenceStudio';$settingsPath=Join-Path $configurationDirectory 'CadenceStudio4.ini'
$exerciseRoot=Join-Path $documentsBase 'CadenceStudio4/Exercices'
foreach($path in @($configurationDirectory,$localDataDirectory,$exerciseRoot)){if(Test-Path -LiteralPath $path){throw 'Fresh Cadence settings/data/exercise root required; no existing profile or exercise was changed.'}}
$report['exercise_precondition']=[ordered]@{known_documents=$documentsBase;exercise_root=$exerciseRoot;was_absent_before_start=$true;source_commit='961c80b235d413dc9d123ea8f669ddb7f84ecd09';expected_id='pulsation';scope='Only the application may create its new UUID exercise copy; wrapper never populates its folder'}
try {
    $report.phase='firewall-prerequisites'
    if (-not ([Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Administrator token unavailable; no escalation or security changes attempted.' }
    foreach ($name in @('Get-NetFirewallRule','New-NetFirewallRule','Remove-NetFirewallRule','Get-NetFirewallApplicationFilter','Get-NetFirewallAddressFilter','Get-NetFirewallPortFilter','Get-NetFirewallInterfaceTypeFilter','Get-NetFirewallProfile')) {
        [void](Get-Command $name -ErrorAction Stop)
    }
    foreach ($name in @('MpsSvc','BFE')) {
        $service=Get-Service -Name $name -ErrorAction Stop
        $report.firewall.service_states += [ordered]@{ name=$name; status=[string]$service.Status }
        if ($service.Status -ne 'Running') { throw 'Firewall services must already be running; none will be changed.' }
    }
    $profiles=@(Get-NetFirewallProfile -PolicyStore ActiveStore -ErrorAction Stop)
    $report.firewall.active_profiles=@($profiles | ForEach-Object { [ordered]@{ name=[string]$_.Name; enabled=[string]$_.Enabled; allow_local_rules=[string]$_.AllowLocalFirewallRules } })
    if ($profiles.Count -ne 3 -or @($profiles | Where-Object { [string]$_.Enabled -ne 'True' }).Count) { throw 'All effective firewall profiles must already be enabled.' }
    $ruleName='CadenceToolsOfflineQa-'+[guid]::NewGuid().ToString('D')
    $report.firewall.rule_name=$ruleName
    if (@(Read-ExactRule 'PersistentStore').Count -or @(Read-ExactRule 'ActiveStore').Count) { throw 'New UUID rule name unexpectedly exists; no rule was changed.' }
    $ruleCreationAttempted=$true; $report.firewall.creation_attempted=$true
    New-NetFirewallRule -PolicyStore PersistentStore -Name $ruleName -DisplayName $ruleName -Description $ruleDescription `
        -Program $executable -Direction Outbound -Action Block -Enabled True -Profile Any -Protocol Any `
        -LocalAddress Any -RemoteAddress Any -InterfaceType Any -ErrorAction Stop | Out-Null
    $report.firewall.created=$true
    Assert-EffectiveRule 'initial'
    [void][IO.Directory]::CreateDirectory($configurationDirectory)
    $settingsBytes=[Text.UTF8Encoding]::new($false).GetBytes("[application]`r`nhasCompletedFirstLaunchSetup=true`r`n")
    $stream=[IO.File]::Open($settingsPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    try{$stream.Write($settingsBytes,0,$settingsBytes.Length)}finally{$stream.Dispose()}
    $report.profile_seeded_by_script=$true
    $report['profile_precondition']=[ordered]@{settings_path=$settingsPath;sha256=Hash $settingsPath;bytes=$settingsBytes.Length;hasCompletedFirstLaunchSetup=$true;official_musescore_profile_touched=$false;first_launch_tested=$false}
    if((Hash $executable)-cne$ExpectedExecutableSha256){throw 'Stage executable changed before startup.'}
    $start=[Diagnostics.ProcessStartInfo]::new();$start.FileName=$executable;$start.WorkingDirectory=Split-Path -Parent $executable
    $start.UseShellExecute=$false;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
    foreach($arg in @('--test-mode','--session-type','start-empty')){$start.ArgumentList.Add($arg)}
    $start.Environment['PATH']=(Split-Path -Parent $executable)+';'+(Join-Path $env:SystemRoot 'System32')
    foreach($key in @($start.Environment.Keys)){if($key-match'^(?i:QT|QML|CMAKE_|VCPKG_|VSCMD_|VSINSTALLDIR$|VCINSTALLDIR$|VCTools|INCLUDE$|LIB$|LIBPATH$|WindowsSdk|WindowsSDK|UniversalCRTSdkDir$|UCRTVersion$|DevEnvDir$|ExtensionSdkDir$|FrameworkDir|FrameworkVersion|GH_TOKEN$|GITHUB_TOKEN$)'){[void]$start.Environment.Remove($key)}}
    $start.Environment['QT_ACCESSIBILITY']='1'
    $app=[Diagnostics.Process]::new();$app.StartInfo=$start
    if(-not$app.Start()){throw 'Owned application did not start.'}
    $report.pid=$app.Id;$stdout=$app.StandardOutput.ReadToEndAsync();$stderr=$app.StandardError.ReadToEndAsync();$report.phase='owned-ui'
    $ready=[Diagnostics.Stopwatch]::StartNew()
    while($ready.Elapsed.TotalSeconds-lt35){$app.Refresh();if($app.HasExited){throw 'Application exited before inspection.'};if(@([CadenceLibraryWindowNative]::Windows($app.Id)).Count){break};Start-Sleep -Milliseconds 200}
    Capture-OwnedWindow 'before-tools.png' $app
    $probeStart=[Diagnostics.ProcessStartInfo]::new();$probeStart.FileName=$ProbePath;$probeStart.UseShellExecute=$false;$probeStart.RedirectStandardOutput=$true;$probeStart.RedirectStandardError=$true
    foreach($arg in @('--pid',[string]$app.Id,'--output',$treeDirectory)){$probeStart.ArgumentList.Add($arg)}
    $probe=[Diagnostics.Process]::new();$probe.StartInfo=$probeStart
    if(-not$probe.Start()){throw 'Native UIA tools client did not start.'}
    $probeOut=$probe.StandardOutput.ReadToEndAsync();$probeErr=$probe.StandardError.ReadToEndAsync()
    if(-not$probe.WaitForExit(180000)){$report.probe_cleanup_forced=$true;$probe.Kill($true);[void]$probe.WaitForExit(5000);throw 'Owned tools client timed out.'}
    $report.probe_exit_code=$probe.ExitCode
    [IO.File]::WriteAllText((Join-Path $OutputDirectory 'probe.stdout.log'),$probeOut.GetAwaiter().GetResult());[IO.File]::WriteAllText((Join-Path $OutputDirectory 'probe.stderr.log'),$probeErr.GetAwaiter().GetResult())
    $nativePath=Join-Path $treeDirectory 'uia-report.json'
    if(-not(Test-Path -LiteralPath $nativePath)-or(Get-Item -LiteralPath $nativePath).Length-gt4194304){throw 'Missing or oversized native tools report.'}
    $native=Get-Content -LiteralPath $nativePath -Raw -Encoding utf8|ConvertFrom-Json
    $report.native_probe_status=$native.status
    try{$report.native_claims_passed=Test-ToolsNativeClaims $native $app.Id}catch{$report.native_claim_error=$_.Exception.Message}
    $app.Refresh();if($app.HasExited){throw 'Application exited before its end-of-tools capture.'}
    Capture-OwnedWindow 'after-tools.png' $app
    if($probe.ExitCode-ne0-or-not$report.native_claims_passed){throw 'One or both actual tool pages/exercise opening remain blocked; inspect native report.'}
} catch {$report.error=$_.Exception.Message}
finally {
    if($null-ne$probe){try{$probe.Refresh();if(-not$probe.HasExited){$report.probe_cleanup_forced=$true;$probe.Kill($true);[void]$probe.WaitForExit(5000)}}catch{if(-not$report.error){$report.error=$_.Exception.Message}}finally{$probe.Dispose()}}
    if($null-ne$app-and$null-ne$native){
        $opened=$native.PSObject.Properties['lesson_editor_title_observed'];$requested=$native.PSObject.Properties['lesson_open_requested']
        if($opened-and$requested-and$opened.Value-is[bool]-and$opened.Value-and$requested.Value-is[bool]-and$requested.Value){
            try{$report.close_probe=Invoke-OwnedExerciseClose $app $ProbePath (Join-Path $OutputDirectory 'close-uia')}
            catch{$report.close_probe=[ordered]@{status='blocked_or_failed_owned_exercise_close';error=$_.Exception.Message};if(-not$report.error){$report.error='Controlled exercise close did not complete.'}}
        }
    }
    if($null-ne$app){
        try{
            $closing=[Diagnostics.Stopwatch]::StartNew()
            while($closing.Elapsed.TotalSeconds-lt12){$app.Refresh();if($app.HasExited){break};foreach($window in @([CadenceLibraryWindowNative]::Windows($app.Id))){$app.Refresh();if($app.HasExited){break};$posted=[CadenceLibraryWindowNative]::CloseOwned($window,$app.Id);$report.cleanup.events += [ordered]@{pid=$app.Id;handle=$window.ToInt64();posted=$posted}};if($app.WaitForExit(250)){break}}
            $app.Refresh();if(-not$app.HasExited){$report.cleanup.forced=$true;$app.Kill($true);if(-not$app.WaitForExit(5000)){throw 'Owned application did not stop.'}}
            $report.cleanup.exit_code=$app.ExitCode
            [IO.File]::WriteAllText((Join-Path $OutputDirectory 'application.stdout.log'),$stdout.GetAwaiter().GetResult());[IO.File]::WriteAllText((Join-Path $OutputDirectory 'application.stderr.log'),$stderr.GetAwaiter().GetResult())
        }catch{$report.cleanup.error=$_.Exception.Message}finally{$app.Dispose()}
    }
    if($report.profile_seeded_by_script){Save-CadenceApplicationLogEvidence $localDataDirectory $OutputDirectory $report.pid}
    try{$report.exercise_evidence=Test-CopiedExerciseEvidence $exerciseRoot (Join-Path $PSScriptRoot 'fixtures') $report.cleanup.exit_code}catch{$report.exercise_evidence_error=$_.Exception.Message}
    if($ruleCreationAttempted){
        try{
            Assert-EffectiveRule 'after-owned-cleanup-before-removal'
        }catch{if(-not$report.error){$report.error=$_.Exception.Message}}
        try{
            $owned=@(Read-ExactRule 'PersistentStore');if($owned.Count-gt1){throw 'Exact UUID cleanup is ambiguous.'}
            if($owned.Count-eq1){if($owned[0].Name-cne$ruleName-or$owned[0].Description-cne$ruleDescription){throw 'UUID ownership changed; another rule was not touched.'};Remove-NetFirewallRule -PolicyStore PersistentStore -Name $ruleName -ErrorAction Stop}
            if(@(Read-ExactRule 'PersistentStore').Count-or@(Read-ExactRule 'ActiveStore').Count){throw 'Owned UUID firewall rule remains.'}
            $report.firewall.removed=$true
        }catch{$report.firewall.cleanup_error=$_.Exception.Message}
    }
    $complete= -not$report.error-and-not$report.cleanup.error-and-not$report.cleanup.forced-and$report.cleanup.exit_code-eq0-and-not$report.probe_cleanup_forced-and$report.probe_exit_code-eq0-and$report.native_claims_passed-and$null-ne$report.exercise_evidence-and$report.exercise_evidence.passed-and$report.firewall.active_store_verified-and$report.firewall.removed-and-not$report.firewall.cleanup_error
    if($complete){$report.status='actual_two_tools_pages_and_UI_created_exercise_editor_observed_offline';$report.phase='completed'}else{$report.status='blocked_or_failed_actual_tools_UI';$report.phase='blocked-or-failed'}
    $report.finished_utc=[DateTime]::UtcNow.ToString('o')
    $report|ConvertTo-Json -Depth 24|Set-Content -LiteralPath (Join-Path $OutputDirectory 'tools-ui-report.json') -Encoding utf8NoBOM
    Write-Host 'CADENCE_TOOLS_UI_REPORT_BEGIN';Write-Host($report|ConvertTo-Json -Depth 24 -Compress);Write-Host 'CADENCE_TOOLS_UI_REPORT_END'
}
if($report.status-ne'actual_two_tools_pages_and_UI_created_exercise_editor_observed_offline'){throw 'Actual tools UI remains incomplete; no GUI or listening success inferred from source/data alone.'}
