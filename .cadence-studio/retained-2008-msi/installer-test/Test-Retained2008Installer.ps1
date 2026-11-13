# SPDX-License-Identifier: GPL-3.0-only
# Uses the byte-exact source helper on a disposable hosted runner. No developer tools are installed for the recipient.
#Requires -Version 7.2
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$MsiPath,
    [Parameter(Mandatory)][string]$StageBuildResultPath,
    [Parameter(Mandatory)][string]$RetainedStageExecutablePath,
    [Parameter(Mandatory)][string]$StageNoticeReportPath,
    [Parameter(Mandatory)][string]$OutputDirectory,
    [string]$GuiWrapperPath,
    [string]$GuiProbePath,
    [switch]$RequireGui
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
# These checks precede output creation, COM and any install/uninstall operation.
if(-not[OperatingSystem]::IsWindows()-or-not[Environment]::Is64BitProcess-or
   $env:OS-cne'Windows_NT'-or$env:GITHUB_ACTIONS-cne'true'-or$env:CI-cne'true'-or
   $env:RUNNER_ENVIRONMENT-cne'github-hosted'-or-not$env:RUNNER_TEMP){throw 'Disposable native hosted Windows x64 CI only.'}
$expectedExe='13cd4e6d2f408d2e64b187d4c3bff1188ff4192ac7b670d3a12373bbeb37f6cd'
$expectedSource='95cebb22fe6cbde22919c94f2b480bd14c3eb8de'
$sourceTree='c5452043983a048ef0aeef085615af903de3f5b0'
$sourceOriginal='a2b7abaf045a8f3cb84ec2953d9e0e51b9e78903'
$expectedProduct='{CA4AC56B-9ED9-568F-9F5A-0D9475D4CC26}'
$expectedUpgrade='{319B992F-470A-465B-9A79-6B0CBFC7D6C7}'
$expectedHelper='77c25db2996ddf85f302ef59f78ca842580c695abe5a75692b4d94d85c7f6a4c'
$expectedGuiWrapper='8a5f7d237c4ebf452ca347fab7c5dfc612bc7b457036e541cbd5df635902c68d'
$expectedGuiProbe='c3c3223e9dcb676db7da2df5502232d919ebeecc1f53dc43c7607b1d9a8e737f'

function Get-RetainedHash([string]$Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
function Resolve-RetainedPlainPath([string]$Path,[switch]$MustExist,[long]$MaximumBytes=536870912){
    if(-not[IO.Path]::IsPathFullyQualified($Path)-or$Path.StartsWith('\\')-or$Path-match'[;"\x00-\x1f]'){throw 'Explicit local absolute data path required.'}
    $full=[IO.Path]::GetFullPath($Path)
    for($current=$full;$current;){
        try{
            $item=Get-Item -LiteralPath $current -Force -ErrorAction Stop
            if($item.Attributes-band[IO.FileAttributes]::ReparsePoint){throw 'Reparse data path refused.'}
        }catch [System.Management.Automation.ItemNotFoundException]{}
        $parent=[IO.Path]::GetDirectoryName($current.TrimEnd('\','/'))
        if(-not$parent-or$parent-eq$current){break};$current=$parent
    }
    if($MustExist){
        $item=Get-Item -LiteralPath $full -Force
        if($item.PSIsContainer-or$item.Length-le0-or$item.Length-gt$MaximumBytes){throw 'Bounded existing regular file required.'}
    }
    return $full
}
function Assert-RetainedBelow([string]$Path,[string]$Parent){
    if(-not$Path.StartsWith($Parent.TrimEnd('\','/')+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw 'Runtime input/output must stay strictly below RUNNER_TEMP.'}
}
function Invoke-RetainedCom($Object,[string]$Name,[Reflection.BindingFlags]$Flags,[object[]]$Arguments=@()){
    return ,($Object.GetType().InvokeMember($Name,$Flags,$null,$Object,$Arguments))
}
function Release-RetainedCom($Object){if($null-ne$Object-and[Runtime.InteropServices.Marshal]::IsComObject($Object)){[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($Object)}}
function Read-RetainedMsiIdentity([string]$Path){
    $installer=$null;$database=$null;$summary=$null;$result=[ordered]@{}
    try{
        $installer=New-Object -ComObject WindowsInstaller.Installer
        $database=Invoke-RetainedCom $installer 'OpenDatabase' ([Reflection.BindingFlags]::InvokeMethod) @($Path,0)
        foreach($name in @('ProductName','ProductVersion','ProductCode','UpgradeCode')){
            $view=$null;$record=$null
            try{
                $view=Invoke-RetainedCom $database 'OpenView' ([Reflection.BindingFlags]::InvokeMethod) @("SELECT ``Value`` FROM ``Property`` WHERE ``Property``='$name'")
                [void](Invoke-RetainedCom $view 'Execute' ([Reflection.BindingFlags]::InvokeMethod))
                $record=Invoke-RetainedCom $view 'Fetch' ([Reflection.BindingFlags]::InvokeMethod)
                if($null-eq$record){throw 'Required MSI identity property missing.'}
                $result[$name]=[string](Invoke-RetainedCom $record 'StringData' ([Reflection.BindingFlags]::GetProperty) @(1))
            }finally{
                if($null-ne$view){[void](Invoke-RetainedCom $view 'Close' ([Reflection.BindingFlags]::InvokeMethod))}
                Release-RetainedCom $record;Release-RetainedCom $view
            }
        }
        $summary=Invoke-RetainedCom $database 'SummaryInformation' ([Reflection.BindingFlags]::GetProperty) @(0)
        $result['summary_template']=[string](Invoke-RetainedCom $summary 'Property' ([Reflection.BindingFlags]::GetProperty) @(7))
        return [pscustomobject]$result
    }finally{Release-RetainedCom $summary;Release-RetainedCom $database;Release-RetainedCom $installer}
}

$temp=Resolve-RetainedPlainPath $env:RUNNER_TEMP
$MsiPath=Resolve-RetainedPlainPath $MsiPath -MustExist
$StageBuildResultPath=Resolve-RetainedPlainPath $StageBuildResultPath -MustExist -MaximumBytes 65536
$StageNoticeReportPath=Resolve-RetainedPlainPath $StageNoticeReportPath -MustExist -MaximumBytes 16777216
$RetainedStageExecutablePath=Resolve-RetainedPlainPath $RetainedStageExecutablePath -MustExist
$OutputDirectory=Resolve-RetainedPlainPath $OutputDirectory
foreach($path in @($MsiPath,$StageBuildResultPath,$StageNoticeReportPath,$RetainedStageExecutablePath,$OutputDirectory)){Assert-RetainedBelow $path $temp}
if((Test-Path -LiteralPath $OutputDirectory)-or[IO.Path]::GetExtension($MsiPath)-ine'.msi'-or
   [IO.Path]::GetFileName($RetainedStageExecutablePath)-cne'CadenceStudio4.exe'){throw 'Fresh test output, actual MSI and exact retained executable required.'}
$helper=Resolve-RetainedPlainPath (Join-Path $PSScriptRoot 'upstream/Test-MsiInstall.ps1') -MustExist -MaximumBytes 1048576
if((Get-RetainedHash $helper)-cne$expectedHelper){throw 'The original Test-MsiInstall.ps1 bytes changed.'}
$guiRequested=-not[string]::IsNullOrWhiteSpace($GuiWrapperPath)
if($guiRequested-ne(-not[string]::IsNullOrWhiteSpace($GuiProbePath))){throw 'GUI wrapper and probe must both be supplied or both omitted.'}
if($RequireGui-and-not$guiRequested){throw 'This qualification requires installed GUI observation.'}
if($guiRequested){
    if(-not[Environment]::UserInteractive-or[Diagnostics.Process]::GetCurrentProcess().SessionId-eq0){throw 'Interactive hosted desktop required for installed GUI observation.'}
    $GuiWrapperPath=Resolve-RetainedPlainPath $GuiWrapperPath -MustExist -MaximumBytes 1048576
    $GuiProbePath=Resolve-RetainedPlainPath $GuiProbePath -MustExist -MaximumBytes 1048576
    if((Get-RetainedHash $GuiWrapperPath)-cne$expectedGuiWrapper-or(Get-RetainedHash $GuiProbePath)-cne$expectedGuiProbe){throw 'Reviewed clean GUI wrapper/readiness probe source changed.'}
    $nativeProbe=Resolve-RetainedPlainPath (Join-Path $env:RUNNER_TEMP 'combined-ui-probe/UiReadyProbe.exe') -MustExist
    Assert-RetainedBelow $nativeProbe $temp
}
$build=Get-Content -LiteralPath $StageBuildResultPath -Raw -Encoding utf8|ConvertFrom-Json
if($build.schema_version-ne1-or$build.source_commit-cne$expectedSource-or
   $build.source_dirty_at_build-isnot[bool]-or$build.source_dirty_at_build-or
   $build.executable_sha256-cne$expectedExe-or[IO.Path]::GetFileName([string]$build.executable)-ine'CadenceStudio4.exe'){
    throw 'The unchanged original clean Build.ps1 result from CI95 and its exact executable are required.'
}
if((Get-RetainedHash $RetainedStageExecutablePath)-cne$expectedExe){throw 'Relocated retained stage executable differs from original CI95.'}
$notice=Get-Content -LiteralPath $StageNoticeReportPath -Raw -Encoding utf8|ConvertFrom-Json
if($notice.schema_version-ne1-or$notice.passed-isnot[bool]-or-not$notice.passed-or
   $notice.application_executed-isnot[bool]-or$notice.application_executed-or
   $notice.executable_sha256-cne$expectedExe-or@($notice.notices).Count-eq0-or
   @($notice.notices).Count-ne$notice.notice_files_verified){throw 'Actual completed read-only notice verification for the exact2008 executable required.'}
$identity=Read-RetainedMsiIdentity $MsiPath
if($identity.ProductName-cnotmatch'^Cadence Studio(?:\s+4)?$'-or$identity.ProductVersion-cne'4.7.6.2008'-or
   ('{'+([guid]$identity.ProductCode).ToString().ToUpperInvariant()+'}')-cne$expectedProduct-or
   ('{'+([guid]$identity.UpgradeCode).ToString().ToUpperInvariant()+'}')-cne$expectedUpgrade-or
   $identity.summary_template-cnotmatch'^x64(?:;|$)'){throw 'MSI identity/version/platform differs before installation.'}

$before=[ordered]@{msi=Get-RetainedHash $MsiPath;build_result=Get-RetainedHash $StageBuildResultPath;notice_report=Get-RetainedHash $StageNoticeReportPath;retained_executable=Get-RetainedHash $RetainedStageExecutablePath}
[void][IO.Directory]::CreateDirectory($OutputDirectory)
$evidence=Join-Path $OutputDirectory 'original-inputs';[void][IO.Directory]::CreateDirectory($evidence)
[IO.File]::WriteAllBytes((Join-Path $evidence 'cadence-build-result.original.json'),[IO.File]::ReadAllBytes($StageBuildResultPath))
[IO.File]::WriteAllBytes((Join-Path $evidence 'stage-notices-report.original.json'),[IO.File]::ReadAllBytes($StageNoticeReportPath))
$inner=Join-Path $OutputDirectory 'actual-msi-test'
$report=[ordered]@{schema_version=1;status='running';scope='Real retained2008 MSI install/installed CLI/optional GUI/exact-product uninstall';source_original_commit=$sourceOriginal;source_CI_commit=$expectedSource;source_tree=$sourceTree;executable_sha256=$expectedExe;expected_product_code=$expectedProduct;expected_upgrade_code=$expectedUpgrade;product_version='4.7.6.2008';MSI_readonly_identity=$identity;input_sha256_before=$before;input_sha256_after=$null;original_inputs_preserved=$false;source_helper_sha256=$expectedHelper;gui_requested=$guiRequested;require_gui=[bool]$RequireGui;installer_cli_verified=$false;installed_gui_verified=$false;installer_qualified_for_experimental_release=$false;final_gift_qualified=$false;inner_report=$null;error=$null;editing_tested=$false;human_listening=$false;consumer_Windows_tested=$false}
$oldExpected=[Environment]::GetEnvironmentVariable('CADENCE_QA_EXPECTED_EXECUTABLE_SHA256','Process')
try{
    $env:CADENCE_QA_EXPECTED_EXECUTABLE_SHA256=$expectedExe
    $parameters=@{MsiPath=$MsiPath;StageBuildResultPath=$StageBuildResultPath;RetainedStageExecutablePath=$RetainedStageExecutablePath;StageNoticeReportPath=$StageNoticeReportPath;OutputDirectory=$inner;ExpectedVersion='4.7.6';ExpectedProductVersion='4.7.6.2008';RequireSystemIcu=$true}
    if($guiRequested){$parameters['GuiWrapperPath']=$GuiWrapperPath;$parameters['GuiProbePath']=$GuiProbePath;$report['native_readiness_probe_sha256']=Get-RetainedHash $nativeProbe}
    $innerFailure=$null
    try{& $helper @parameters}catch{$innerFailure=$_.Exception.Message}
    $innerPath=Join-Path $inner 'msi-install-report.json'
    if(-not(Test-Path -LiteralPath $innerPath -PathType Leaf)){
        if($innerFailure){throw ('Original source helper failed before report: '+$innerFailure)}
        throw 'Original source helper did not produce its real MSI report.'
    }
    $actual=Get-Content -LiteralPath $innerPath -Raw -Encoding utf8|ConvertFrom-Json
    $report.inner_report=$actual
    if($innerFailure){throw ('Original source helper failed: '+$innerFailure)}
    if($actual.status-cne'passed'-or$actual.source_commit-cne$expectedSource-or$actual.msi_sha256-cne$before.msi-or
       $actual.product_code-cne$expectedProduct-or$actual.product_version-cne'4.7.6.2008'-or$actual.upgrade_code-cne$expectedUpgrade-or
       $actual.install_exit_code-ne0-or$actual.cli_exit_code-ne0-or$actual.uninstall_exit_code-ne0-or
       $actual.install_reboot_required-or$actual.uninstall_reboot_required-or-not$actual.product_removed-or
       $actual.installed_executable_sha256-cne$expectedExe-or-not$actual.cli_version_matched-or
       -not$actual.retained_stage_relocation_requested-or$actual.retained_stage_executable_sha256-cne$expectedExe-or
       $actual.stage_build_result_sha256-cne$before.build_result-or-not$actual.require_system_icu-or
       -not$actual.installed_local_icuuc_absent-or-not$actual.notice_verification_requested-or
       $actual.installed_notices_verified-ne$notice.notice_files_verified){throw 'Exact original install0/CLI0/uninstall0/notice/system-ICU/retained-stage evidence did not pass.'}
    $report.installer_cli_verified=$true
    if($guiRequested){
        if(-not$actual.gui_tested-or$actual.gui_status-cne'startup_observed_closed_cleanly'-or$actual.gui_exit_status-ne0-or
           -not$actual.gui_startup_observed-or-not$actual.clean_exit_observed){throw 'Installed GUI startup and clean close0 remain unqualified.'}
        $guiPath=Join-Path $inner 'installed-gui/gui-report.json';$gui=Get-Content -LiteralPath $guiPath -Raw -Encoding utf8|ConvertFrom-Json
        if($gui.executable_sha256-cne$expectedExe-or$gui.shutdown.exit_code-ne0-or$gui.shutdown.forced-or$gui.probe_forced){throw 'Installed GUI executable/clean-close evidence differs.'}
        $report.installed_gui_verified=$true
    }
    $report.installer_qualified_for_experimental_release=$report.installer_cli_verified-and$report.installed_gui_verified
    $report.status=if($report.installed_gui_verified){'passed-retained2008-msi-and-installed-gui'}else{'passed-retained2008-msi-CLI-only-GUI-unqualified'}
}catch{$report.status='failed-or-blocked';$report.error=$_.Exception.Message}
finally{
    [Environment]::SetEnvironmentVariable('CADENCE_QA_EXPECTED_EXECUTABLE_SHA256',$oldExpected,'Process')
    try{
        $after=[ordered]@{msi=Get-RetainedHash $MsiPath;build_result=Get-RetainedHash $StageBuildResultPath;notice_report=Get-RetainedHash $StageNoticeReportPath;retained_executable=Get-RetainedHash $RetainedStageExecutablePath}
        $report.input_sha256_after=$after
        $report.original_inputs_preserved=$before.msi-ceq$after.msi-and$before.build_result-ceq$after.build_result-and$before.notice_report-ceq$after.notice_report-and$before.retained_executable-ceq$after.retained_executable
        if(-not$report.original_inputs_preserved){throw 'An original retained input changed during installer qualification.'}
    }catch{$report.status='failed-or-blocked';$report.error=$_.Exception.Message}
    $report|ConvertTo-Json -Depth 30|Set-Content -LiteralPath (Join-Path $OutputDirectory 'retained2008-installer-qualification.json') -Encoding utf8NoBOM
    Write-Host 'CADENCE_RETAINED2008_INSTALLER_QUALIFICATION_BEGIN';$report|ConvertTo-Json -Depth 30 -Compress|Write-Host;Write-Host 'CADENCE_RETAINED2008_INSTALLER_QUALIFICATION_END'
}
if($report.status-ceq'failed-or-blocked'){throw ('Retained2008 installer remains failed or blocked: '+$report.error)}
