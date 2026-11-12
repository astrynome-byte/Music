# SPDX-License-Identifier: GPL-3.0-only
#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $SourcePath,
    [Parameter(Mandatory)][string] $QtPath,
    [Parameter(Mandatory)][string] $ZlibTransportPath,
    [Parameter(Mandatory)][string] $OutputDirectory
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if(-not [OperatingSystem]::IsWindows() -or $env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitProcess -or
   [Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne [Runtime.InteropServices.Architecture]::X64 -or
   $env:GITHUB_ACTIONS -ne 'true' -or $env:CI -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted'){
    throw 'Only disposable native Windows x64 hosted runners may execute this probe.'
}
if(-not $env:RUNNER_TEMP){throw 'RUNNER_TEMP is required.'}
$SourcePath=[IO.Path]::GetFullPath($SourcePath);$QtPath=[IO.Path]::GetFullPath($QtPath)
$ZlibTransportPath=[IO.Path]::GetFullPath($ZlibTransportPath);$OutputDirectory=[IO.Path]::GetFullPath($OutputDirectory)
$temporary=[IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\','/')+[IO.Path]::DirectorySeparatorChar
if(-not $OutputDirectory.StartsWith($temporary,[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $OutputDirectory)){
    throw 'A new output directory strictly below RUNNER_TEMP is required.'
}
function Hash([string] $Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
function Assert-PlainFile([string] $Path){
    $item=Get-Item -LiteralPath $Path
    if($item.PSIsContainer){throw 'Expected an ordinary file.'}
    for($current=$item;$null -ne $current;$current=$current.Parent){
        if($current.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Linked source path refused.'}
        if($current -is [IO.FileInfo]){$current=$current.Directory;if($null -eq $current){break}}
        if($current.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Linked source ancestor refused.'}
    }
}
function Get-VerifiedQaFiles([string] $Root){
    $manifestFile=Join-Path $Root 'qa-manifest.json';Assert-PlainFile $manifestFile
    if((Get-Item -LiteralPath $manifestFile).Length -gt 65536 -or (Hash $manifestFile) -cne '4a94391a6ced2f2904cbf398d04f73b7ce4695405cc15500bef8605372231839'){
        throw 'Reviewed QA manifest differs.'
    }
    $manifest=Get-Content -LiteralPath $manifestFile -Raw|ConvertFrom-Json -AsHashtable
    $allowed=@('source-snapshot.zip.base64','snapshot-contract.json','RestoreSnapshot.py','CMakeLists.txt',
        'GenerateProbeConfig.cmake','prepare_zlib_package.py','Validate-OpenSourceZlib.ps1','zlib-source-profile.lock.json')
    if($manifest.schema_version -ne 1 -or $manifest.source_commit -cne '0f1b61397d7b00714f135ecc737c48cdc380c930' -or
       $manifest.source_tree -cne '34bd415cc77469c6439e6274c8c8c556391ae7e1' -or
       $manifest.old_engine_commit -cne 'b02b41f4cbb31f43df073d6cdf5249a18d425a7e' -or
       $manifest.expected_ON_groups -ne 10 -or $manifest.expected_OFF_groups -ne 3 -or @($manifest.files).Count -ne $allowed.Count){
        throw 'Unexpected source identity or scenario accounting.'
    }
    $seen=[Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal);$rows=@()
    foreach($row in $manifest.files){
        if($row.path -isnot [string] -or $row.path -cnotin $allowed -or -not $seen.Add($row.path) -or
           $row.sha256 -isnot [string] -or $row.sha256 -cnotmatch '^[a-f0-9]{64}$' -or
           ($row.bytes -isnot [int] -and $row.bytes -isnot [long]) -or $row.bytes -le 0 -or $row.bytes -gt 2097152){
            throw 'Invalid QA input manifest entry.'
        }
        $path=Join-Path $Root $row.path;Assert-PlainFile $path
        $size=(Get-Item -LiteralPath $path).Length;$digest=Hash $path
        if($size -ne $row.bytes -or $digest -cne $row.sha256){throw "Reviewed QA input changed: $($row.path)"}
        $rows+=,[ordered]@{path=$row.path;bytes=$size;sha256=$digest}
    }
    return [ordered]@{verified=$true;source_commit=$manifest.source_commit;source_tree=$manifest.source_tree
        manifest_sha256=(Hash $manifestFile);files=$rows}
}
function Assert-ExactRuntime([string] $Text,[int] $Groups,[string] $Summary){
    if([regex]::Matches($Text,'(?m)^PASS:').Count -ne $Groups -or
       [regex]::Matches($Text,'(?m)^'+[regex]::Escape($Summary)+'\s*$').Count -ne 1 -or $Text -match '(?m)^FAIL:'){
        throw 'Native runtime did not complete the exact expected group count.'
    }
}
function Assert-ExpectedOldFailure([string] $ErrorText,[string] $Expected){
    if([regex]::Matches($ErrorText,'(?m)^'+[regex]::Escape('FAIL: '+$Expected)+'\s*$').Count -ne 1){
        throw 'Old control did not fail for the exact expected behavior.'
    }
}
[void][IO.Directory]::CreateDirectory($OutputDirectory)
$report=[ordered]@{
    schema_version=1;status='running';passed=$false;source_commit='0f1b61397d7b00714f135ecc737c48cdc380c930'
    source_tree='34bd415cc77469c6439e6274c8c8c556391ae7e1';old_engine_commit='b02b41f4cbb31f43df073d6cdf5249a18d425a7e'
    driver_commit=$env:GITHUB_SHA;run_id=$env:GITHUB_RUN_ID;scope='Real engine and same native project-settings writer; external synth/FX doubles only'
    source_verified_before=$false;source_verified_after=$false;qa_verified_before=$false;qa_verified_after=$false
    ON_groups=0;OFF_groups=0;old_getter_failure_observed=$false;old_native_save_failure_observed=$false
    application_built=$false;application_executed=$false;GUI_tested=$false;human_listening=$false
    real_external_plugin_loaded=$false;real_sound_bank_loaded=$false;audio_device_or_ASIO_used=$false
    missing_resource_UI_warning_implemented=$false;commands=@();error=$null;started_utc=[DateTime]::UtcNow.ToString('o')
}
function Invoke-ProbeCommand([string] $Name,[string] $Executable,[string[]] $Arguments,[int] $Timeout,[int] $ExpectedExit=0){
    $row=[ordered]@{name=$Name;executable=$Executable;arguments=$Arguments;expected_exit_code=$ExpectedExit
        pid=$null;exit_code=$null;timed_out=$false;elapsed_seconds=$null;started_utc=[DateTime]::UtcNow.ToString('o')}
    $report.commands+=,$row
    $start=[Diagnostics.ProcessStartInfo]::new();$start.FileName=$Executable;$start.WorkingDirectory=$OutputDirectory
    $start.UseShellExecute=$false;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
    foreach($argument in $Arguments){$start.ArgumentList.Add($argument)}
    $process=[Diagnostics.Process]::new();$process.StartInfo=$start;$started=$false;$timer=[Diagnostics.Stopwatch]::StartNew()
    try{
        if(-not $process.Start()){throw "Cannot start owned command: $Name"};$started=$true;$row.pid=$process.Id
        $stdout=$process.StandardOutput.ReadToEndAsync();$stderr=$process.StandardError.ReadToEndAsync()
        if(-not $process.WaitForExit($Timeout)){
            $row.timed_out=$true;$process.Kill($true)
            if(-not $process.WaitForExit(5000)){throw "Owned process did not stop after timeout: $Name"}
        }
        $out=$stdout.GetAwaiter().GetResult();$err=$stderr.GetAwaiter().GetResult()
        if($out.Length -gt 2097152 -or $err.Length -gt 2097152){throw 'Command transcript exceeds 2 MiB.'}
        [IO.File]::WriteAllText((Join-Path $OutputDirectory ($Name+'.stdout.log')),$out,[Text.UTF8Encoding]::new($false))
        [IO.File]::WriteAllText((Join-Path $OutputDirectory ($Name+'.stderr.log')),$err,[Text.UTF8Encoding]::new($false))
        $row.exit_code=$process.ExitCode
        Write-Host ("{0}: exit {1}, expected={2}, timeout={3}" -f $Name,$row.exit_code,$ExpectedExit,$row.timed_out)
        if($row.timed_out -or $row.exit_code -ne $ExpectedExit){throw "Owned command failed its expected exit: $Name"}
    }finally{
        if($started -and -not $process.HasExited){$process.Kill($true);[void]$process.WaitForExit(5000)}
        $timer.Stop();$row.elapsed_seconds=$timer.Elapsed.TotalSeconds;$process.Dispose()
    }
}
$originalPath=$env:PATH
try{
    $report.kernel=[ordered]@{os_description=[Runtime.InteropServices.RuntimeInformation]::OSDescription
        os_version=[Environment]::OSVersion.VersionString;architecture=[Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture.ToString()
        powershell=$PSVersionTable.PSVersion.ToString();dotnet=[Runtime.InteropServices.RuntimeInformation]::FrameworkDescription
        image_os=$env:ImageOS;image_version=$env:ImageVersion;runner_os=$env:RUNNER_OS;runner_arch=$env:RUNNER_ARCH}
    $qaBefore=Get-VerifiedQaFiles $SourcePath
    $qaBefore|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $OutputDirectory 'qa-verification-before.json') -Encoding utf8NoBOM
    $report.qa_verified_before=$true
    [IO.File]::Copy((Join-Path $SourcePath 'qa-manifest.json'),(Join-Path $OutputDirectory 'qa-manifest.json'),$false)
    if($env:VSCMD_ARG_TGT_ARCH -ne 'x64' -or $env:VSCMD_VER -notmatch '^17\.14(?:\.|$)' -or
       ([string]$env:WindowsSDKVersion).TrimEnd('\') -cne '10.0.26100.0'){throw 'MSVC 17.14 x64 and Windows SDK 26100 required.'}
    $cmake=(Get-Command cmake -CommandType Application -ErrorAction Stop|Select-Object -First 1).Source
    $ninja=(Get-Command ninja -CommandType Application -ErrorAction Stop|Select-Object -First 1).Source
    $cl=(Get-Command cl -CommandType Application -ErrorAction Stop|Select-Object -First 1).Source
    $python=(Get-Command python -CommandType Application -ErrorAction Stop|Select-Object -First 1).Source
    $report.toolchain=[ordered]@{cmake=$cmake;ninja=$ninja;cl=$cl;python=$python;visual_studio=$env:VSCMD_VER
        vc_tools_version=$env:VCToolsVersion;windows_sdk=$env:WindowsSDKVersion
        compiler_file_version=(Get-Item -LiteralPath $cl).VersionInfo.FileVersion;compiler_sha256=(Hash $cl)}
    $env:PATH=(Join-Path $QtPath 'bin')+';'+$env:PATH
    $qmake=Join-Path $QtPath 'bin/qmake.exe';Assert-PlainFile $qmake
    Invoke-ProbeCommand 'qt-version' $qmake @('-query','QT_VERSION') 30000
    if(([IO.File]::ReadAllText((Join-Path $OutputDirectory 'qt-version.stdout.log'))).Trim() -cne '6.10.2'){throw 'Actual Qt 6.10.2 required.'}
    Invoke-ProbeCommand 'python-version' $python @('--version') 30000
    if(([IO.File]::ReadAllText((Join-Path $OutputDirectory 'python-version.stdout.log'))).Trim() -notmatch '^Python 3\.12\.\d+$'){throw 'Actual Python 3.12 required after Qt setup.'}
    $report.qt_libraries=@()
    foreach($name in @('Qt6Core.dll','Qt6Gui.dll')){
        $file=Join-Path $QtPath ('bin/'+$name);Assert-PlainFile $file
        $report.qt_libraries+=,[ordered]@{name=$name;sha256=(Hash $file);file_version=(Get-Item -LiteralPath $file).VersionInfo.FileVersion}
    }
    Invoke-ProbeCommand 'cmake-version' $cmake @('--version') 30000
    Invoke-ProbeCommand 'ninja-version' $ninja @('--version') 30000
    $snapshot=Join-Path $OutputDirectory 'source-snapshot';$oldTree=Join-Path $OutputDirectory 'old-engine-source'
    $restore=Join-Path $SourcePath 'RestoreSnapshot.py'
    Invoke-ProbeCommand 'restore-sources' $python @('-I','-X','utf8',$restore,'restore','--source',(Join-Path $SourcePath 'source-snapshot.zip.base64'),
        '--snapshot',$snapshot,'--old-tree',$oldTree,'--report',(Join-Path $OutputDirectory 'source-verification-before.json')) 60000
    $report.source_verified_before=$true
    [IO.File]::Copy((Join-Path $snapshot 'source-manifest.json'),(Join-Path $OutputDirectory 'source-manifest.json'),$false)
    Invoke-ProbeCommand 'prepare-zlib' $python @('-I','-X','utf8',(Join-Path $SourcePath 'prepare_zlib_package.py'),
        '--input',$ZlibTransportPath,'--output',(Join-Path $OutputDirectory 'zlib-inspection'),
        '--prepared-package',(Join-Path $OutputDirectory 'zlib-prepared')) 120000
    . (Join-Path $SourcePath 'Validate-OpenSourceZlib.ps1')
    $zlibBefore=Get-OpenSourceZlibProfile -PackageRoot (Join-Path $OutputDirectory 'zlib-prepared') -LockPath (Join-Path $SourcePath 'zlib-source-profile.lock.json') -RequirePinnedCi
    $zlibBefore|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $OutputDirectory 'zlib-verification-before.json') -Encoding utf8NoBOM
    $report.zlib_profile=$zlibBefore
    $zlibInclude=Join-Path $zlibBefore.prefix 'include';$zlibLibrary=Join-Path $zlibBefore.prefix 'lib/zs.lib'
    $report.test_binaries=@();$report.profiles=@()
    foreach($variant in @('ON','OFF','OLD')){
        $build=Join-Path $OutputDirectory ('build-'+$variant)
        Invoke-ProbeCommand ('configure-'+$variant) $cmake @('-S',$SourcePath,'-B',$build,'-G','Ninja','-DCMAKE_BUILD_TYPE=Release',
            "-DCMAKE_CXX_COMPILER=$cl","-DCMAKE_MAKE_PROGRAM=$ninja",'-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreadedDLL',
            "-DCMAKE_PREFIX_PATH=$QtPath","-DQt6_DIR=$QtPath/lib/cmake/Qt6","-DPROBE_VARIANT=$variant", "-DPROBE_SNAPSHOT_ROOT=$snapshot", "-DPROBE_OLD_TREE=$oldTree",
            "-DZLIB_INCLUDE_DIR=$zlibInclude","-DZLIB_LIBRARY=$zlibLibrary","-DZLIB_LIBRARY_RELEASE=$zlibLibrary") 120000
        Invoke-ProbeCommand ('build-'+$variant) $cmake @('--build',$build,'--target','audio_intent_retention_tests','--parallel','2') 240000
        $binary=Join-Path $build 'production-retention-tests/audio_intent_retention_tests.exe';Assert-PlainFile $binary
        $report.test_binaries+=,[ordered]@{variant=$variant;sha256=(Hash $binary);bytes=(Get-Item -LiteralPath $binary).Length}
        $profileFile=Join-Path $build 'generated/probe-profile.json'
        $profile=Get-Content -LiteralPath $profileFile -Raw|ConvertFrom-Json -AsHashtable
        $header=Join-Path $build 'generated/muse_framework_config.h'
        $text=[IO.File]::ReadAllText($header).Replace("`r`n","`n")
        $normalized=[Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($text))
        $normalizedHash=[Convert]::ToHexString($normalized).ToLowerInvariant()
        if($normalizedHash -cne '0a3698bb1600a10760128ef912f9558b1bf6b4201a2cfee221d461f2b13a3358' -or
           -not $profile.cadence_build_owned_by_test_target -or $profile.asio_compiled -or $profile.vst_host_compiled){throw 'Canonical probe profile differs.'}
        $report.profiles+=,[ordered]@{variant=$variant;header_sha256=(Hash $header);normalized_LF_header_sha256=$normalizedHash;profile=$profile}
        [IO.File]::Copy($profileFile,(Join-Path $OutputDirectory ('profile-'+$variant+'.json')),$false)
        if($variant -ceq 'ON'){
            Invoke-ProbeCommand 'runtime-ON' $binary @() 90000
            Assert-ExactRuntime ([IO.File]::ReadAllText((Join-Path $OutputDirectory 'runtime-ON.stdout.log'))) 10 '10/10 real engine and native writer groups passed.'
            $report.ON_groups=10
        }elseif($variant -ceq 'OFF'){
            Invoke-ProbeCommand 'runtime-OFF' $binary @('--legacy-control') 60000
            Assert-ExactRuntime ([IO.File]::ReadAllText((Join-Path $OutputDirectory 'runtime-OFF.stdout.log'))) 3 '3/3 legacy control groups passed.'
            $report.OFF_groups=3
        }else{
            Invoke-ProbeCommand 'runtime-OLD-getter' $binary @() 90000 1
            Assert-ExpectedOldFailure ([IO.File]::ReadAllText((Join-Path $OutputDirectory 'runtime-OLD-getter.stderr.log'))) 'Fallback replaced full requested metadata/configuration'
            $report.old_getter_failure_observed=$true
            Invoke-ProbeCommand 'runtime-OLD-native-save' $binary @('--persistence-only') 90000 1
            Assert-ExpectedOldFailure ([IO.File]::ReadAllText((Join-Path $OutputDirectory 'runtime-OLD-native-save.stderr.log'))) 'Native writer saved the fallback instead of the original request'
            $report.old_native_save_failure_observed=$true
        }
    }
    Invoke-ProbeCommand 'verify-sources-after' $python @('-I','-X','utf8',$restore,'verify','--snapshot',$snapshot,'--old-tree',$oldTree,
        '--report',(Join-Path $OutputDirectory 'source-verification-after.json')) 60000
    if((Hash (Join-Path $OutputDirectory 'source-verification-before.json')) -cne (Hash (Join-Path $OutputDirectory 'source-verification-after.json'))){throw 'Source snapshots changed across execution.'}
    $report.source_verified_after=$true
    $qaAfter=Get-VerifiedQaFiles $SourcePath
    $qaAfter|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $OutputDirectory 'qa-verification-after.json') -Encoding utf8NoBOM
    $report.qa_verified_after=$true
    $zlibAfter=Get-OpenSourceZlibProfile -PackageRoot (Join-Path $OutputDirectory 'zlib-prepared') -LockPath (Join-Path $SourcePath 'zlib-source-profile.lock.json') -RequirePinnedCi
    $zlibAfter|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $OutputDirectory 'zlib-verification-after.json') -Encoding utf8NoBOM
    if($zlibAfter.fingerprint -cne $zlibBefore.fingerprint){throw 'Retained zlib changed across execution.'}
    $report.status='passed_native_ON10_OFF3_and_expected_old_failures';$report.passed=$true
}catch{$report.status='failed_or_blocked';$report.error=$_.Exception.Message}
finally{
    $env:PATH=$originalPath;$report.finished_utc=[DateTime]::UtcNow.ToString('o')
    $report|ConvertTo-Json -Depth 20|Set-Content -LiteralPath (Join-Path $OutputDirectory 'audio-intent-probe-report.json') -Encoding utf8NoBOM
    Write-Host 'CADENCE_AUDIO_INTENT_REPORT_BEGIN';Write-Host ($report|ConvertTo-Json -Depth 20 -Compress);Write-Host 'CADENCE_AUDIO_INTENT_REPORT_END'
}
if(-not $report.passed){throw 'Native audio intent retention probe failed or is blocked; inspect exact evidence.'}
