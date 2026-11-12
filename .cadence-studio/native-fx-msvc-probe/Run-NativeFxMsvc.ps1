# SPDX-License-Identifier: GPL-3.0-only
# Builds only the two existing pure C++17 targets; never installs an application.
[CmdletBinding()]
param([Parameter(Mandatory)][string]$OutputDirectory)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitProcess){throw 'Native Windows x64 is required.'}
$OutputDirectory=[IO.Path]::GetFullPath($OutputDirectory)
if(Test-Path -LiteralPath $OutputDirectory){throw 'The evidence/build directory must be new.'}
[void][IO.Directory]::CreateDirectory($OutputDirectory)
$source=Join-Path $PSScriptRoot 'source'
$manifestPath=Join-Path $PSScriptRoot 'standalone-source-manifest.json'
$manifest=Get-Content -LiteralPath $manifestPath -Raw -Encoding utf8|ConvertFrom-Json
$report=[ordered]@{
    schema_version=1;status='failed';scope='Standalone production DSP and codec only; no Qt, VST SDK, complete app, GUI or audio-device test'
    native_windows_x64=$true;compiler_family='MSVC';generator='Visual Studio 17 2022';configuration='Release'
    github_run_id=$env:GITHUB_RUN_ID;github_run_attempt=$env:GITHUB_RUN_ATTEMPT;driver_commit=$env:GITHUB_SHA
    patch_sha256=$manifest.patch_sha256;manifest_sha256=(Get-FileHash $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
    runner_sha256=(Get-FileHash $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant();source_hashes_verified=$false
    expected_ctest_targets=@('native_fx_dsp_tests','native_fx_config_tests');ctest_passed=$false;test_binaries=@();commands=@();error=$null
}
function Invoke-OwnedCommand([string]$Name,[string]$Program,[string[]]$Arguments,[int]$TimeoutSeconds){
    $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$Program;$info.UseShellExecute=$false
    $info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    $info.StandardOutputEncoding=[Text.Encoding]::UTF8;$info.StandardErrorEncoding=[Text.Encoding]::UTF8
    foreach($argument in $Arguments){$info.ArgumentList.Add($argument)}
    $process=[Diagnostics.Process]::new();$process.StartInfo=$info
    try{
        if(-not $process.Start()){throw ('Could not start '+$Name)}
        $stdout=$process.StandardOutput.ReadToEndAsync();$stderr=$process.StandardError.ReadToEndAsync()
        if(-not $process.WaitForExit($TimeoutSeconds*1000)){$process.Kill($true);[void]$process.WaitForExit(5000);throw ($Name+' timed out.')}
        $out=$stdout.GetAwaiter().GetResult();$err=$stderr.GetAwaiter().GetResult()
        [IO.File]::WriteAllText((Join-Path $OutputDirectory ($Name+'.stdout.txt')),$out,[Text.UTF8Encoding]::new($false))
        [IO.File]::WriteAllText((Join-Path $OutputDirectory ($Name+'.stderr.txt')),$err,[Text.UTF8Encoding]::new($false))
        $report.commands+=@{name=$Name;program=$Program;arguments=$Arguments;exit_code=$process.ExitCode}
        Write-Host $out
        if($err){Write-Host $err}
        if($process.ExitCode -ne 0){throw ($Name+' failed with exit '+$process.ExitCode)}
    }finally{try{if($process.Id -and -not $process.HasExited){$process.Kill($true)}}catch{};$process.Dispose()}
}
try{
    $expected=@('src/framework/audio/common/cadencefxparams.h','src/framework/audio/engine/internal/dsp/nativeeffects.cpp','src/framework/audio/engine/internal/dsp/nativeeffects.h','test/cadence/native_fx/CMakeLists.txt','test/cadence/native_fx/allocationtracker.cpp','test/cadence/native_fx/allocationtracker.h','test/cadence/native_fx/config_codec_tests.cpp','test/cadence/native_fx/native_fx_dsp_tests.cpp')
    if($manifest.schema_version -ne 1 -or @($manifest.source_files).Count -ne 8 -or $manifest.patch_sha256 -cnotmatch '^[0-9a-f]{64}$'){throw 'Invalid standalone source manifest.'}
    [string[]]$actualPaths=@($manifest.source_files.path)
    [Array]::Sort($actualPaths,[StringComparer]::Ordinal)
    [Array]::Sort($expected,[StringComparer]::Ordinal)
    if(($actualPaths -join "`n") -cne ($expected -join "`n")){throw 'The source inventory differs from the exact two-target closure.'}
    foreach($entry in $manifest.source_files){
        $file=Get-Item -LiteralPath (Join-Path $source $entry.path)
        if($file.LinkType -or $file.PSIsContainer -or $file.Length -ne $entry.bytes -or (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entry.sha256){throw ('Source manifest mismatch: '+$entry.path)}
    }
    $report.source_hashes_verified=$true
    $cmake=(Get-Command cmake -CommandType Application -ErrorAction Stop|Select-Object -First 1).Source
    $ctest=(Get-Command ctest -CommandType Application -ErrorAction Stop|Select-Object -First 1).Source
    $build=Join-Path $OutputDirectory 'build'
    Invoke-OwnedCommand 'cmake-version' $cmake @('--version') 30
    Invoke-OwnedCommand 'configure' $cmake @('-S',(Join-Path $source 'test/cadence/native_fx'),'-B',$build,'-G','Visual Studio 17 2022','-A','x64') 120
    Invoke-OwnedCommand 'build' $cmake @('--build',$build,'--config','Release','--target','native_fx_dsp_tests','native_fx_config_tests','--parallel','2') 240
    Invoke-OwnedCommand 'ctest' $ctest @('--test-dir',$build,'-C','Release','--verbose','--no-tests=error','--tests-regex','^(native_fx_dsp_tests|native_fx_config_tests)$','--output-on-failure','--output-junit',(Join-Path $OutputDirectory 'ctest-junit.xml')) 120
    [xml]$junit=Get-Content -LiteralPath (Join-Path $OutputDirectory 'ctest-junit.xml') -Raw
    $cases=@($junit.testsuite.testcase)
    [string[]]$caseNames=@($cases.name)
    [Array]::Sort($caseNames,[StringComparer]::Ordinal)
    if($cases.Count -ne 2 -or ($caseNames -join ',') -cne 'native_fx_config_tests,native_fx_dsp_tests' -or @($cases|Where-Object{$_.status -cne 'run'}).Count){throw 'CTest did not report both exact standalone tests as executed.'}
    foreach($name in $report.expected_ctest_targets){
        $exe=Get-Item -LiteralPath (Join-Path $build ('Release/'+$name+'.exe'))
        $report.test_binaries+=@{name=$exe.Name;bytes=$exe.Length;sha256=(Get-FileHash -LiteralPath $exe.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
    }
    $report.ctest_passed=$true;$report.status='passed-standalone-msvc-x64-release-ctest-2-of-2'
}catch{$report.error=$_.Exception.Message}
finally{
    $report|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $OutputDirectory 'native-fx-msvc-report.json') -Encoding utf8
    Write-Host 'CADENCE_NATIVE_FX_MSVC_REPORT_BEGIN';Write-Host ($report|ConvertTo-Json -Depth 8 -Compress);Write-Host 'CADENCE_NATIVE_FX_MSVC_REPORT_END'
}
if(-not $report.ctest_passed){throw 'Standalone MSVC qualification failed; no application qualification is claimed.'}
