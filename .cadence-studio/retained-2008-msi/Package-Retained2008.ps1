# SPDX-License-Identifier: GPL-3.0-only
# Package only the authenticated retained stage. Never invoke an application build.
#Requires -Version 7.2
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$StagePath,
    [Parameter(Mandatory)][string]$ApplicationSource,
    [Parameter(Mandatory)][string]$SourceProfilePath,
    [Parameter(Mandatory)][string]$ArtifactDirectory,
    [Parameter(Mandatory)][string]$RuntimeInventoryPath,
    [Parameter(Mandatory)][string]$ReadbackReceiptPath,
    [Parameter(Mandatory)][string]$PackageBindingsPath,
    [Parameter(Mandatory)][string]$QualificationReportPath,
    [string]$QualificationEvidenceRoot,
    [Parameter(Mandatory)][string]$CorrespondingSourceBundle,
    [Parameter(Mandatory)][string]$BuildRecipeDirectory,
    [Parameter(Mandatory)][string]$OutputDirectory,
    [ValidateSet('4.7.6.2008')][string]$ProductVersion='4.7.6.2008'
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if(-not[OperatingSystem]::IsWindows()-or-not[Environment]::Is64BitProcess-or
   [Runtime.InteropServices.RuntimeInformation]::OSArchitecture-ne'X64'-or
   $env:GITHUB_ACTIONS-cne'true'-or$env:CI-cne'true'-or$env:RUNNER_ENVIRONMENT-cne'github-hosted'){
    throw 'Retained packaging requires disposable native Windows x64 GitHub-hosted CI.'
}
function Full([string]$Path){
    if(-not[IO.Path]::IsPathFullyQualified($Path)-or$Path.StartsWith('\\')-or$Path-match'[;"\x00-\x1f]'){throw 'Explicit local absolute path required.'}
    $path=[IO.Path]::GetFullPath($Path)
    for($part=$path;$part;$part=[IO.Path]::GetDirectoryName($part.TrimEnd('\','/'))){
        if((Test-Path -LiteralPath $part)-and((Get-Item -LiteralPath $part -Force).Attributes-band[IO.FileAttributes]::ReparsePoint)){throw 'Reparse package path refused.'}
        $next=[IO.Path]::GetDirectoryName($part.TrimEnd('\','/'));if(-not$next-or$next-eq$part){break}
    };return $path
}
function Hash([string]$Path){return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
function Tool([string]$Name){return (Get-Command $Name -CommandType Application -ErrorAction Stop|Select-Object -First 1).Source}
$StagePath=Full $StagePath;$ApplicationSource=Full $ApplicationSource;$SourceProfilePath=Full $SourceProfilePath
$ArtifactDirectory=Full $ArtifactDirectory;$RuntimeInventoryPath=Full $RuntimeInventoryPath;$ReadbackReceiptPath=Full $ReadbackReceiptPath
$PackageBindingsPath=Full $PackageBindingsPath;$QualificationReportPath=Full $QualificationReportPath
if($QualificationEvidenceRoot){$QualificationEvidenceRoot=Full $QualificationEvidenceRoot}
$CorrespondingSourceBundle=Full $CorrespondingSourceBundle;$BuildRecipeDirectory=Full $BuildRecipeDirectory;$OutputDirectory=Full $OutputDirectory
$temp=(Full $env:RUNNER_TEMP).TrimEnd('\','/')+[IO.Path]::DirectorySeparatorChar
if(-not$OutputDirectory.StartsWith($temp,[StringComparison]::OrdinalIgnoreCase)-or(Test-Path -LiteralPath $OutputDirectory)){throw 'A fresh packaging output beneath RUNNER_TEMP is required.'}
foreach($protected in @($StagePath,$ApplicationSource,$ArtifactDirectory,$CorrespondingSourceBundle,$BuildRecipeDirectory)){
    if($OutputDirectory-eq$protected-or$OutputDirectory.StartsWith($protected.TrimEnd('\','/')+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)-or
       $protected.StartsWith($OutputDirectory.TrimEnd('\','/')+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){
        throw 'Packaging output must not overlap source, original stage, component sources or recipe.'
    }
}
$bindings=Get-Content -LiteralPath $PackageBindingsPath -Raw -Encoding utf8|ConvertFrom-Json
$qualification=Get-Content -LiteralPath $QualificationReportPath -Raw -Encoding utf8|ConvertFrom-Json
if($bindings.ready-isnot[bool]-or-not$bindings.ready-or$qualification.ready-isnot[bool]-or-not$qualification.ready-or
   $qualification.passed-isnot[bool]-or-not$qualification.passed){throw 'Actual measured bindings and completed qualification are required; inactive templates cannot package.'}
$python=Tool python;$cmake=Tool cmake;$cpack=Tool cpack;$git=Tool git
$project=Join-Path $OutputDirectory 'internal/packaging-source';$build=Join-Path $OutputDirectory 'internal/packaging-build'
$delivery=Join-Path $OutputDirectory 'deliverables';$preflight=Join-Path $OutputDirectory 'validated-inputs.json'
$report=[ordered]@{schema_version=1;status='running';application_recompiled=$false;application_executed=$false;
    source_original_commit='a2b7abaf045a8f3cb84ec2953d9e0e51b9e78903';source_ci_commit='95cebb22fe6cbde22919c94f2b480bd14c3eb8de';
    source_tree='c5452043983a048ef0aeef085615af903de3f5b0';executable_sha256='13cd4e6d2f408d2e64b187d4c3bff1188ff4192ac7b670d3a12373bbeb37f6cd';
    product_version=$ProductVersion;product_code='{CA4AC56B-9ED9-568F-9F5A-0D9475D4CC26}';upgrade_code='{319B992F-470A-465B-9A79-6B0CBFC7D6C7}';
    actual_installer_tested=$false;final_gift_qualified=$false;publicly_published=$false;
    stage_preserved=$null;source_preserved=$null;component_sources_preserved=$null;commands=@();drains=@();forced_descendants=0;forced_tools=@();job_closed=$false;error=$null}
$job=$null
function Run([string]$Name,[string]$Program,[string[]]$Arguments,[int]$Seconds){
    $start=[Diagnostics.ProcessStartInfo]::new();$start.FileName=$Program;$start.WorkingDirectory=[IO.Path]::GetDirectoryName($Program)
    $start.UseShellExecute=$false;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
    foreach($arg in $Arguments){$start.ArgumentList.Add($arg)}
    foreach($key in @('GH_TOKEN','GITHUB_TOKEN')){[void]$start.Environment.Remove($key)}
    $child=[Diagnostics.Process]::new();$child.StartInfo=$start;$started=$false
    try{
        if(-not$child.Start()){throw 'Owned packaging tool failed to start.'};$started=$true
        $stdout=$child.StandardOutput.ReadToEndAsync();$stderr=$child.StandardError.ReadToEndAsync()
        if(-not$child.WaitForExit($Seconds*1000)){$report.forced_tools+=,$child.Id;$child.Kill($true);[void]$child.WaitForExit(5000);throw ('Packaging tool timed out: '+$Name)}
        $drain=Stop-OwnedJobChildren -Job $job;$report.drains+=,$drain;$report.forced_descendants+=@($drain.TerminatedPids).Count
        if(-not$stdout.Wait(5000)-or-not$stderr.Wait(5000)){throw 'Packaging tool transcript did not close after owned drainage.'}
        $out=$stdout.GetAwaiter().GetResult();$err=$stderr.GetAwaiter().GetResult()
        if($out.Length-gt8388608-or$err.Length-gt8388608){throw 'Packaging transcript exceeds its bound.'}
        Write-Host $out;if($err){Write-Host $err}
        if(Test-Path -LiteralPath $OutputDirectory -PathType Container){
            [IO.File]::WriteAllText((Join-Path $OutputDirectory ($Name+'.stdout.log')),$out)
            [IO.File]::WriteAllText((Join-Path $OutputDirectory ($Name+'.stderr.log')),$err)
        }
        $report.commands+=,[ordered]@{name=$Name;exit_code=$child.ExitCode}
        if($child.ExitCode-ne0-or@($drain.TerminatedPids).Count){throw ('Packaging tool or owned descendants failed: '+$Name)}
    }finally{if($started-and-not$child.HasExited){$report.forced_tools+=,$child.Id;$child.Kill($true);[void]$child.WaitForExit(5000)};$child.Dispose()}
}
$preflightArgs=@('-I','-B',"$PSScriptRoot/prepare_retained_package.py",'--stage',$StagePath,'--application-source',$ApplicationSource,
    '--source-profile',$SourceProfilePath,'--artifact-directory',$ArtifactDirectory,'--runtime-inventory',$RuntimeInventoryPath,
    '--readback-receipt',$ReadbackReceiptPath,'--bindings',$PackageBindingsPath,'--qualification',$QualificationReportPath,
    '--corresponding-sources',$CorrespondingSourceBundle,'--project-output',$project,'--report',$preflight)
if($QualificationEvidenceRoot){$preflightArgs+=@('--qualification-evidence-root',$QualificationEvidenceRoot)}
try{
    Import-Module "$PSScriptRoot/OwnProcessJob.psm1" -Force;$job=New-OwnedProcessJob
    Run 'validate-original-runtime-source-and-real-qualification' $python $preflightArgs 180
    [void][IO.Directory]::CreateDirectory($delivery)
    Run 'configure-packaging-only-no-languages-no-targets' $cmake @('-S',$project,'-B',$build,'-G','Ninja',
        ('-DCADENCE_STAGE_ROOT='+($StagePath-replace'\\','/')),('-DCADENCE_PRODUCT_VERSION='+$ProductVersion)) 120
    $configuration=Get-Content -LiteralPath (Join-Path $build 'CPackConfig.cmake') -Raw
    if($configuration-notmatch'set\(CPACK_INSTALL_CMAKE_PROJECTS ""\)'-or$configuration-notmatch'set\(CPACK_PACKAGE_VERSION "4\.7\.6\.2008"\)'){
        throw 'Only directory packaging with no application install project is allowed.'
    }
    Run 'CPack-original-WiX-over-unchanged-stage' $cpack @('--config',(Join-Path $build 'CPackConfig.cmake'),'-G','WIX','-C','Release','-B',$delivery,'--verbose') 600
    $msis=@(Get-ChildItem -LiteralPath $delivery -File -Filter '*.msi');if($msis.Count-ne1){throw 'Exactly one real MSI must be produced.'}
    $msi=Join-Path $delivery 'CadenceStudio-4.7.6-cadence.2008-x86_64.msi'
    if($msis[0].FullName-cne$msi){Move-Item -LiteralPath $msis[0].FullName -Destination $msi}
    $tar=Join-Path $delivery 'CadenceStudio-4.7.6-cadence.2008-source.tar.gz'
    Run 'archive-exact-compiled-source-CI95' $git @('-C',$ApplicationSource,'archive','--format=tar.gz',('--output='+$tar),'95cebb22fe6cbde22919c94f2b480bd14c3eb8de') 180
    $delta=Join-Path $OutputDirectory 'internal/CadenceStudio-2008-from-upstream.patch'
    Run 'archive-exact-source-delta' $git @('-C',$ApplicationSource,'diff','--binary','--full-index',('--output='+$delta),
        '96480d58445e3b24b230a3fe7d4725d639aa2eb3','95cebb22fe6cbde22919c94f2b480bd14c3eb8de') 180
    Run 'bundle-required-sources-notices-recipe-and-checksums' $python @('-I','-B',"$PSScriptRoot/bundle_delivery.py",'--validated',$preflight,
        '--stage',$StagePath,'--application-source',$ApplicationSource,'--corresponding-sources',$CorrespondingSourceBundle,
        '--recipe',$BuildRecipeDirectory,'--source-delta',$delta,'--delivery',$delivery,'--qualification',$QualificationReportPath,
        '--bindings',$PackageBindingsPath,'--source-profile',$SourceProfilePath) 600
    $report.installer=@{path=$msi;bytes=(Get-Item -LiteralPath $msi).Length;sha256=Hash $msi}
    $report.status='packaged-immutable2008-stage-awaiting-actual-MSI-installation-test'
}catch{
    $report.status='failed';$report.error=$_.Exception.Message
    if(Test-Path -LiteralPath $delivery){foreach($log in Get-ChildItem -LiteralPath $delivery -Recurse -File -Filter wix.log){Get-Content -LiteralPath $log.FullName|Out-Host}}
}finally{
    if($job-and(Test-Path -LiteralPath $preflight -PathType Leaf)){
        try{
            $after=Join-Path $OutputDirectory 'immutability-after.json'
            Run 'verify-all-original-inputs-even-after-failure' $python @('-I','-B',"$PSScriptRoot/verify_package_immutability.py",'--validated',$preflight,
                '--stage',$StagePath,'--application-source',$ApplicationSource,'--corresponding-sources',$CorrespondingSourceBundle,'--output',$after) 180
            $proof=Get-Content -LiteralPath $after -Raw|ConvertFrom-Json
            $report.stage_preserved=$proof.stage_preserved;$report.source_preserved=$proof.source_preserved;$report.component_sources_preserved=$proof.component_sources_preserved
            if($proof.passed-cne$true){throw 'Original inputs changed during packaging.'}
        }catch{$report.status='failed';$report.error=([string]$report.error+'; immutability: '+$_.Exception.Message)}
    }
    if($job){try{$drain=Stop-OwnedJobChildren -Job $job;$report.drains+=,$drain;$report.forced_descendants+=@($drain.TerminatedPids).Count;
        [void](Close-OwnedProcessJob -Job $job);$report.job_closed=$true}catch{$report.status='failed';$report.error=$_.Exception.Message}}
    if($report.forced_descendants-ne0-or$report.forced_tools.Count-ne0-or-not$report.job_closed){$report.status='failed'}
    if(Test-Path -LiteralPath $OutputDirectory){$report|ConvertTo-Json -Depth 18|Set-Content -LiteralPath (Join-Path $OutputDirectory 'package-manifest.json') -Encoding utf8NoBOM}
    Write-Host 'CADENCE_RETAINED2008_PACKAGE_BEGIN';Write-Host ($report|ConvertTo-Json -Depth 18 -Compress);Write-Host 'CADENCE_RETAINED2008_PACKAGE_END'
}
if($report.status-cne'packaged-immutable2008-stage-awaiting-actual-MSI-installation-test'){throw 'Retained packaging did not pass; inspect original reports. No application was rebuilt.'}
