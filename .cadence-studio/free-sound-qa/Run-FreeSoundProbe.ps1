# SPDX-License-Identifier: GPL-3.0-only
#Requires -Version 7.0
[CmdletBinding()]
param([Parameter(Mandatory)][string]$SourcePath,[Parameter(Mandatory)][string]$QtPath,
      [Parameter(Mandatory)][string]$BankPath,[Parameter(Mandatory)][string]$LicensePath,
      [Parameter(Mandatory)][string]$OutputDirectory)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if (-not [OperatingSystem]::IsWindows() -or $env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitProcess -or
    [Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne 'X64' -or $env:GITHUB_ACTIONS -ne 'true' -or
    $env:CI -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted') { throw 'Only disposable native Windows x64 hosted runners.' }
$SourcePath=[IO.Path]::GetFullPath($SourcePath);$QtPath=[IO.Path]::GetFullPath($QtPath)
$OutputDirectory=[IO.Path]::GetFullPath($OutputDirectory);$temporary=[IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\','/')+'\'
if (-not $OutputDirectory.StartsWith($temporary,[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $OutputDirectory)) { throw 'New output strictly below RUNNER_TEMP required.' }
function Hash([string]$Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
if((Hash $BankPath) -ne '9575028c7a1f589f5770fccc8cff2734566af40cd26ed836944e9a5152688cfe' -or
   (Hash $LicensePath) -ne '7b32efefdf95ce38a043799f0659853ddc00fbaa14d8c50f0aca16b9b8b405be'){throw 'Exact upstream bank and licence required.'}
$manifest=Get-Content -LiteralPath (Join-Path $SourcePath 'source-manifest.json') -Raw|ConvertFrom-Json
if($manifest.schema_version -ne 1 -or @($manifest.files).Count -ne 4){throw 'Four exact production/test sources required.'}
$allowed=@('src/musesounds/internal/freecollectioninstaller.h','src/musesounds/internal/freecollectioninstaller.cpp','test/cadence/free_sound_collections/installer_tests.cpp','test/cadence/free_sound_collections/CMakeLists.txt')
$seen=[Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
foreach($entry in $manifest.files){
 if($entry.path -cnotin $allowed -or -not $seen.Add($entry.path) -or $entry.sha256 -cnotmatch '^[a-f0-9]{64}$' -or
    (Hash (Join-Path $SourcePath $entry.path)) -cne $entry.sha256){throw 'Source manifest mismatch before compilation.'}
}
if($env:VSCMD_ARG_TGT_ARCH -ne 'x64' -or $env:VSCMD_VER -notmatch '^17\.' -or $env:WindowsSDKVersion.TrimEnd('\') -ne '10.0.26100.0'){throw 'MSVC2022 x64 / SDK26100 required.'}
[void][IO.Directory]::CreateDirectory($OutputDirectory)
$report=[ordered]@{schema_version=1;status='running';application_built=$false;application_executed=$false;gui_tested=$false;human_listening=$false;commands=@();source_manifest=$manifest;error=$null}
$originalPath=$env:PATH
function Run([string]$Name,[string]$Executable,[string[]]$Arguments,[int]$Timeout){
 $item=[ordered]@{name=$Name;exit_code=$null;timed_out=$false};$report.commands+=,$item
 $start=[Diagnostics.ProcessStartInfo]::new();$start.FileName=$Executable;$start.WorkingDirectory=$OutputDirectory
 $start.UseShellExecute=$false;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
 foreach($argument in $Arguments){$start.ArgumentList.Add($argument)}
 $process=[Diagnostics.Process]::new();$process.StartInfo=$start
 try{
  if(-not $process.Start()){throw 'Cannot start owned probe command.'}
  $stdout=$process.StandardOutput.ReadToEndAsync();$stderr=$process.StandardError.ReadToEndAsync()
  if(-not $process.WaitForExit($Timeout)){$item.timed_out=$true;$process.Kill($true);[void]$process.WaitForExit(5000)}
  [IO.File]::WriteAllText((Join-Path $OutputDirectory ($Name+'.stdout.log')),$stdout.GetAwaiter().GetResult())
  [IO.File]::WriteAllText((Join-Path $OutputDirectory ($Name+'.stderr.log')),$stderr.GetAwaiter().GetResult())
  $item.exit_code=$process.ExitCode
  if($item.timed_out -or $item.exit_code -ne 0){throw "Owned command failed: $Name"}
 }finally{try{if($process.Id -and -not $process.HasExited){$process.Kill($true);[void]$process.WaitForExit(5000)}}catch{};$process.Dispose()}
}
try{
 $env:PATH=(Join-Path $QtPath 'bin')+';'+$env:PATH
 Run 'qt-version' (Join-Path $QtPath 'bin/qmake.exe') @('-query','QT_VERSION') 30000
 if(([IO.File]::ReadAllText((Join-Path $OutputDirectory 'qt-version.stdout.log'))).Trim() -cne '6.10.2'){throw 'Actual Qt6.10.2 required.'}
 $cmake=(Get-Command cmake -CommandType Application | Select-Object -First 1).Source
 $ninja=(Get-Command ninja -CommandType Application | Select-Object -First 1).Source
 $cl=(Get-Command cl -CommandType Application | Select-Object -First 1).Source
 $report.toolchain=[ordered]@{cmake=$cmake;ninja=$ninja;cl=$cl;visual_studio=$env:VSCMD_VER;windows_sdk=$env:WindowsSDKVersion}
 $build=Join-Path $OutputDirectory 'build' 
 Run 'configure' $cmake @('-S',(Join-Path $SourcePath 'test/cadence/free_sound_collections'),'-B',$build,'-G','Ninja','-DCMAKE_BUILD_TYPE=Release',"-DCMAKE_PREFIX_PATH=$QtPath","-DCMAKE_CXX_COMPILER=$cl","-DCMAKE_MAKE_PROGRAM=$ninja",'-DCMAKE_CXX_FLAGS=/utf-8') 120000
 Run 'build' $cmake @('--build',$build,'--target','free_collection_installer_tests','--parallel','2') 180000
 $binary=Join-Path $build 'free_collection_installer_tests.exe'
 $report.test_executable_sha256=Hash $binary
 Run 'actual-installer-scenarios' $binary @($BankPath,$LicensePath,'--download-real') 240000
 $stdout=[IO.File]::ReadAllText((Join-Path $OutputDirectory 'actual-installer-scenarios.stdout.log')).Replace("`r`n","`n")
 if($stdout -notmatch '(?m)^14/14 real installer scenarios passed \(Qt 6\.10\.2\)\.$' -or
    [regex]::Matches($stdout,'(?m)^PASS:').Count -ne 14){throw 'Actual fourteen scenarios did not pass.'}
 foreach($entry in $manifest.files){if((Hash (Join-Path $SourcePath $entry.path)) -cne $entry.sha256){throw 'Production source changed during probe.'}}
 $report.runtime_scenarios=14;$report.explicit_production_network_download_tested=$true;$report.status='passed_real_installer_scenarios'
}catch{$report.status='failed';$report.error=$_.Exception.Message}
finally{
 $env:PATH=$originalPath
 $report|ConvertTo-Json -Depth 20|Set-Content -LiteralPath (Join-Path $OutputDirectory 'free-installer-report.json') -Encoding utf8
 Write-Host 'CADENCE_FREE_INSTALLER_REPORT_BEGIN';Write-Host ($report|ConvertTo-Json -Depth 20 -Compress);Write-Host 'CADENCE_FREE_INSTALLER_REPORT_END'
}
if($report.status -ne 'passed_real_installer_scenarios'){throw 'Real optional sound installer test failed.'}
