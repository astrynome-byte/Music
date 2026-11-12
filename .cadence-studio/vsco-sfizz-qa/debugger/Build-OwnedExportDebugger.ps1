# SPDX-License-Identifier: GPL-3.0-only
#Requires -Version 7.0
[CmdletBinding()]
param([Parameter(Mandatory)][string]$SourcePath,[Parameter(Mandatory)][string]$OutputDirectory)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if(-not[OperatingSystem]::IsWindows() -or -not[Environment]::Is64BitProcess -or
   [Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne 'X64' -or $env:GITHUB_ACTIONS -ne 'true' -or
   $env:CI -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted'){throw 'Only disposable native Windows x64 hosted CI is allowed.'}
$SourcePath=[IO.Path]::GetFullPath($SourcePath);$OutputDirectory=[IO.Path]::GetFullPath($OutputDirectory)
$temporary=[IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\','/')+'\'
if(-not$OutputDirectory.StartsWith($temporary,[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $OutputDirectory)){throw 'A new output strictly below RUNNER_TEMP is required.'}
foreach($path in @($SourcePath,$OutputDirectory)){
 $current=$path
 while($current){
  if((Test-Path -LiteralPath $current) -and ((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'No linked/reparse input/output ancestors.'}
  $parent=[IO.Path]::GetDirectoryName($current.TrimEnd('\','/'));if(-not$parent -or $parent -eq $current){break};$current=$parent
 }
}
function Hash([string]$Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
$manifest=Get-Content -LiteralPath (Join-Path ([IO.Path]::GetDirectoryName($SourcePath)) 'source-pin.json') -Raw|ConvertFrom-Json
if($manifest.file -cne 'OwnedExportDebugEvents.cpp' -or (Split-Path -Leaf $SourcePath) -cne $manifest.file -or (Hash $SourcePath) -cne $manifest.sha256){throw 'Exact reviewed debugger source required.'}
if($env:VSCMD_ARG_TGT_ARCH -ne 'x64' -or $env:VSCMD_VER -notmatch '^17\.'){throw 'Native MSVC2022 x64 tools are required.'}
$cl=(Get-Command cl -CommandType Application|Select-Object -First 1).Source
[void][IO.Directory]::CreateDirectory($OutputDirectory)
$target=Join-Path $OutputDirectory 'OwnedExportDebugEvents.exe'
$start=[Diagnostics.ProcessStartInfo]::new();$start.FileName=$cl;$start.WorkingDirectory=$OutputDirectory
$start.UseShellExecute=$false;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
foreach($argument in @('/nologo','/std:c++17','/EHsc','/O2','/W4','/utf-8','/MT','/D_WIN32_WINNT=0x0A00',$SourcePath,('/Fe'+$target),('/Fo'+(Join-Path $OutputDirectory 'OwnedExportDebugEvents.obj')),'/link','/incremental:no','kernel32.lib')){$start.ArgumentList.Add($argument)}
$process=[Diagnostics.Process]::new();$process.StartInfo=$start
$report=[ordered]@{schema_version=1;status='running';source=$manifest;compiler=$cl;MSVC=$env:VSCMD_VER;application_rebuilt=$false;debugger_executed=$false;error=$null}
try{
 if(-not$process.Start()){throw 'Cannot start the owned compiler command.'}
 $stdout=$process.StandardOutput.ReadToEndAsync();$stderr=$process.StandardError.ReadToEndAsync()
 if(-not$process.WaitForExit(120000)){$process.Kill($true);[void]$process.WaitForExit(5000);throw 'Owned small debugger compilation timed out.'}
 [IO.File]::WriteAllText((Join-Path $OutputDirectory 'compiler.stdout.log'),$stdout.GetAwaiter().GetResult())
 [IO.File]::WriteAllText((Join-Path $OutputDirectory 'compiler.stderr.log'),$stderr.GetAwaiter().GetResult())
 $report.exit_code=$process.ExitCode
 if($process.ExitCode -ne 0 -or -not(Test-Path -LiteralPath $target -PathType Leaf)){throw 'Owned debugger compilation failed.'}
 if((Hash $SourcePath) -cne $manifest.sha256){throw 'Reviewed source changed during compilation.'}
 $report.executable_sha256=Hash $target;$report.executable_bytes=(Get-Item -LiteralPath $target).Length;$report.status='compiled_native_debugger_only'
}catch{$report.status='failed';$report.error=$_.Exception.Message}
finally{
 try{if($process.Id -and -not$process.HasExited){$process.Kill($true);[void]$process.WaitForExit(5000)}}catch{}
 $process.Dispose();$report|ConvertTo-Json -Depth 10|Set-Content -LiteralPath (Join-Path $OutputDirectory 'debugger-build-report.json') -Encoding utf8
 Write-Host 'CADENCE_OWNED_DEBUGGER_BUILD_BEGIN';Write-Host ($report|ConvertTo-Json -Depth 10 -Compress);Write-Host 'CADENCE_OWNED_DEBUGGER_BUILD_END'
}
if($report.status -ne 'compiled_native_debugger_only'){throw 'Native debugger tool build failed.'}
