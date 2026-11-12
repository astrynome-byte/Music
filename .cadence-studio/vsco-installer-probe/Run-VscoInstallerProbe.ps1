# SPDX-License-Identifier: GPL-3.0-only
#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $SourcePath,
    [Parameter(Mandatory)][string] $QtPath,
    [Parameter(Mandatory)][string] $OutputDirectory
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if (-not [OperatingSystem]::IsWindows() -or $env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitProcess -or
    [Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne [Runtime.InteropServices.Architecture]::X64 -or
    $env:GITHUB_ACTIONS -ne 'true' -or $env:CI -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted') {
    throw 'Only disposable native Windows x64 hosted runners may execute this qualification.'
}
if(-not $env:RUNNER_TEMP){throw 'RUNNER_TEMP is required.'}
$SourcePath=[IO.Path]::GetFullPath($SourcePath)
$QtPath=[IO.Path]::GetFullPath($QtPath)
$OutputDirectory=[IO.Path]::GetFullPath($OutputDirectory)
$temporary=[IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\','/')+[IO.Path]::DirectorySeparatorChar
if(-not $OutputDirectory.StartsWith($temporary,[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $OutputDirectory)){
    throw 'OutputDirectory must be new and strictly below RUNNER_TEMP.'
}
function Hash([string] $Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
function Assert-PlainFile([string] $Path){
    $item=Get-Item -LiteralPath $Path
    if($item.PSIsContainer){throw "File required: $Path"}
    for($current=$item;$null -ne $current;$current=$current.Parent){
        if($current.Attributes -band [IO.FileAttributes]::ReparsePoint){throw "Reparse path refused: $Path"}
        if($current -is [IO.FileInfo]){$current=$current.Directory;if($null -eq $current){break}}
        if($current.Attributes -band [IO.FileAttributes]::ReparsePoint){throw "Reparse ancestor refused: $Path"}
    }
}
function Get-VerifiedSourceSnapshot([string] $SourceRoot){
    $expected=@(
        'source/src/musesounds/internal/freecollectioninstaller.h',
        'source/src/musesounds/internal/freecollectioninstaller.cpp',
        'source/src/musesounds/qml/MuseScore/MuseSounds/resources/free-sound-collections.json',
        'source/src/musesounds/qml/MuseScore/MuseSounds/resources/VSCO-CC0-LICENSE.txt',
        'source/src/musesounds/qml/MuseScore/MuseSounds/resources/GeneralUser-GS-LICENSE.txt',
        'source/test/cadence/free_sound_collections/CMakeLists.txt',
        'source/test/cadence/free_sound_collections/installer_tests.cpp',
        'source/test/cadence/free_sound_collections/local_only_tests.cpp',
        'converter/build_vsco_sf2.py','converter/asset-source-manifest.json','converter/VSCO-CC0-LICENSE.txt',
        'converter/mappings/FluteSusVib.sfz','converter/mappings/SViolinVib.sfz','converter/CODE-GPL-3.0.txt'
    )
    $path=Join-Path $SourceRoot 'probe-source-manifest.json'
    Assert-PlainFile $path
    if((Get-Item -LiteralPath $path).Length -gt 65536 -or
       (Hash $path) -cne 'a4e9812807b825d1c4e7023619b807ec090ae8d23e789589de007bacad6ffed6'){
        throw 'Reviewed source manifest hash/size differs.'
    }
    $manifest=Get-Content -LiteralPath $path -Raw|ConvertFrom-Json -AsHashtable
    if($manifest.schema_version -ne 1 -or $manifest.source_commit -cne '13c68381fe81f57e09f892db00b014d9c1a09133' -or
       $manifest.source_tree -cne 'dda148ef004e17d038a443315eb4e975b1d9ef5e' -or
       $manifest.required_qt_version -cne '6.10.2' -or $manifest.required_python_version -cne '3.12' -or
       $manifest.expected_local_only_scenarios -ne 8 -or $manifest.expected_existing_scenarios -ne 13 -or
       $manifest.qualified_converter_run -ne 43231480145 -or
       $manifest.qualified_converter_driver_commit -cne '1fbc211789c7698c4c191fa204ddbb00216209ec' -or
       @($manifest.files).Count -ne $expected.Count){throw 'Unexpected source identity, tools or scenario counts.'}
    $seen=[Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    $verified=@()
    foreach($entry in $manifest.files){
        if($entry.path -isnot [string] -or $entry.path -cnotin $expected -or -not $seen.Add($entry.path) -or
           $entry.sha256 -isnot [string] -or $entry.sha256 -cnotmatch '^[a-f0-9]{64}$' -or
           ($entry.bytes -isnot [int] -and $entry.bytes -isnot [long]) -or $entry.bytes -le 0 -or $entry.bytes -gt 1048576){
            throw 'Invalid, duplicate or unexpected source manifest entry.'
        }
        $file=Join-Path $SourceRoot $entry.path
        Assert-PlainFile $file
        $item=Get-Item -LiteralPath $file
        $digest=Hash $file
        if($item.Length -ne $entry.bytes -or $digest -cne $entry.sha256){throw "Pinned source changed: $($entry.path)"}
        $verified+=,[ordered]@{path=$entry.path;bytes=$item.Length;sha256=$digest}
    }
    return [ordered]@{schema_version=1;verified=$true;source_commit=$manifest.source_commit;source_tree=$manifest.source_tree
        manifest_sha256=(Hash $path);files=$verified}
}
function Get-VerifiedAssets([string] $Root){
    $expected=@(
        @{file='banks/Cadence-VSCO-Flute.sf2';bytes=16778410L;sha256='2bc48929d1996687b99e27b532043c4cb34b89480471faaea446ffc021ab3768'},
        @{file='banks/Cadence-VSCO-Violin.sf2';bytes=74366558L;sha256='801896ef3be53c4b60d9dc87078787add7fdc44b1a3bfe9fff30fcc519d93e0d'},
        @{file='banks/Cadence-VSCO-Flute-minus18.sf2';bytes=16778410L;sha256='b1a53205814bcf3068f0278f2940f6d8b953215f2adf4659a238448a9a70a17f'},
        @{file='banks/VSCO-CC0-LICENSE.txt';bytes=6555L;sha256='36ffd9dc085d529a7e60e1276d73ae5a030b020313e6c5408593a6ae2af39673'},
        @{file='GeneralUser-GS.sf2';bytes=32319396L;sha256='9575028c7a1f589f5770fccc8cff2734566af40cd26ed836944e9a5152688cfe'}
    )
    $verified=@()
    foreach($entry in $expected){
        $path=Join-Path $Root $entry.file
        Assert-PlainFile $path
        $size=(Get-Item -LiteralPath $path).Length
        $digest=Hash $path
        if($size -ne $entry.bytes -or $digest -cne $entry.sha256){throw "Asset bytes/size differ: $($entry.file)"}
        $verified+=,[ordered]@{file=$entry.file;bytes=$size;sha256=$digest}
    }
    return [ordered]@{schema_version=1;verified=$true;files=$verified}
}
function Assert-ScenarioOutput([string] $Text,[int] $Expected,[string] $Summary){
    if([regex]::Matches($Text,'(?m)^PASS:').Count -ne $Expected -or
       [regex]::Matches($Text,'(?m)^'+[regex]::Escape($Summary)+'\s*$').Count -ne 1 -or
       $Text -match '(?m)^FAIL:'){throw 'Native runtime summary/PASS accounting differs; no qualification.'}
}
[void][IO.Directory]::CreateDirectory($OutputDirectory)
$report=[ordered]@{
    schema_version=1;status='running';passed=$false;source_commit='13c68381fe81f57e09f892db00b014d9c1a09133'
    source_tree='dda148ef004e17d038a443315eb4e975b1d9ef5e';driver_commit=$env:GITHUB_SHA;run_id=$env:GITHUB_RUN_ID
    scope='Standalone real Qt production installer: 8 local-only VSCO and 13 existing scenarios; no complete application'
    source_verified_before=$false;source_verified_after=$false;assets_verified_before=$false;assets_verified_after=$false
    local_only_scenarios=0;existing_scenarios=0;total_scenarios=0;production_network_download_executed=$false
    source_asset_preparation_downloads=$true;application_built=$false;application_executed=$false
    gui_tested=$false;human_listening=$false;commands=@();error=$null;started_utc=[DateTime]::UtcNow.ToString('o')
}
function Invoke-ProbeCommand([string] $Name,[string] $Executable,[string[]] $Arguments,[int] $Timeout){
    $row=[ordered]@{name=$Name;executable=$Executable;arguments=$Arguments;pid=$null;exit_code=$null
        timed_out=$false;elapsed_seconds=$null;started_utc=[DateTime]::UtcNow.ToString('o')}
    $report.commands+=,$row
    $start=[Diagnostics.ProcessStartInfo]::new();$start.FileName=$Executable;$start.WorkingDirectory=$OutputDirectory
    $start.UseShellExecute=$false;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
    foreach($argument in $Arguments){$start.ArgumentList.Add($argument)}
    $process=[Diagnostics.Process]::new();$process.StartInfo=$start
    $timer=[Diagnostics.Stopwatch]::StartNew();$started=$false
    try{
        if(-not $process.Start()){throw "Cannot start owned command: $Name"};$started=$true;$row.pid=$process.Id
        $stdout=$process.StandardOutput.ReadToEndAsync();$stderr=$process.StandardError.ReadToEndAsync()
        if(-not $process.WaitForExit($Timeout)){
            $row.timed_out=$true;$process.Kill($true)
            if(-not $process.WaitForExit(5000)){throw "Owned timeout did not terminate: $Name"}
        }
        $out=$stdout.GetAwaiter().GetResult();$err=$stderr.GetAwaiter().GetResult()
        if($out.Length -gt 2097152 -or $err.Length -gt 2097152){throw 'Command transcript exceeds 2 MiB.'}
        [IO.File]::WriteAllText((Join-Path $OutputDirectory ($Name+'.stdout.log')),$out,[Text.UTF8Encoding]::new($false))
        [IO.File]::WriteAllText((Join-Path $OutputDirectory ($Name+'.stderr.log')),$err,[Text.UTF8Encoding]::new($false))
        $row.exit_code=$process.ExitCode
        Write-Host ("{0}: exit {1}, timeout={2}" -f $Name,$row.exit_code,$row.timed_out)
        if($row.timed_out -or $row.exit_code -ne 0){throw "Owned command failed: $Name"}
    }finally{
        if($started -and -not $process.HasExited){$process.Kill($true);[void]$process.WaitForExit(5000)}
        $timer.Stop();$row.elapsed_seconds=$timer.Elapsed.TotalSeconds;$process.Dispose()
    }
}
$originalPath=$env:PATH
try{
    $report.kernel=[ordered]@{os_description=[Runtime.InteropServices.RuntimeInformation]::OSDescription
        os_version=[Environment]::OSVersion.VersionString;process_architecture=[Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture.ToString()
        powershell=$PSVersionTable.PSVersion.ToString();dotnet=[Runtime.InteropServices.RuntimeInformation]::FrameworkDescription
        image_os=$env:ImageOS;image_version=$env:ImageVersion;runner_os=$env:RUNNER_OS;runner_arch=$env:RUNNER_ARCH}
    $before=Get-VerifiedSourceSnapshot $SourcePath
    $before|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $OutputDirectory 'source-verification-before.json') -Encoding utf8NoBOM
    [IO.File]::Copy((Join-Path $SourcePath 'probe-source-manifest.json'),(Join-Path $OutputDirectory 'probe-source-manifest.json'),$false)
    $report.source_verified_before=$true
    if($env:VSCMD_ARG_TGT_ARCH -ne 'x64' -or $env:VSCMD_VER -notmatch '^17\.14(?:\.|$)' -or
       ([string]$env:WindowsSDKVersion).TrimEnd('\') -cne '10.0.26100.0'){
        throw 'MSVC 17.14 x64 and Windows SDK 10.0.26100.0 are required.'
    }
    $cmake=(Get-Command cmake -CommandType Application -ErrorAction Stop|Select-Object -First 1).Source
    $ninja=(Get-Command ninja -CommandType Application -ErrorAction Stop|Select-Object -First 1).Source
    $cl=(Get-Command cl -CommandType Application -ErrorAction Stop|Select-Object -First 1).Source
    $python=(Get-Command python -CommandType Application -ErrorAction Stop|Select-Object -First 1).Source
    $report.toolchain=[ordered]@{cmake=$cmake;ninja=$ninja;cl=$cl;python=$python;visual_studio=$env:VSCMD_VER
        vc_tools_version=$env:VCToolsVersion;windows_sdk=$env:WindowsSDKVersion
        compiler_file_version=(Get-Item -LiteralPath $cl).VersionInfo.FileVersion;compiler_sha256=(Hash $cl)}
    $qmake=Join-Path $QtPath 'bin/qmake.exe'
    $dlls=@()
    foreach($name in @('Qt6Core.dll','Qt6Network.dll')){
        $file=Join-Path $QtPath ('bin/'+$name);Assert-PlainFile $file
        $dlls+=,[ordered]@{name=$name;sha256=(Hash $file);file_version=(Get-Item -LiteralPath $file).VersionInfo.FileVersion}
    }
    $report.qt_libraries=$dlls
    $env:PATH=(Join-Path $QtPath 'bin')+';'+$env:PATH
    Invoke-ProbeCommand 'qt-version' $qmake @('-query','QT_VERSION') 30000
    if(([IO.File]::ReadAllText((Join-Path $OutputDirectory 'qt-version.stdout.log'))).Trim() -cne '6.10.2'){throw 'Actual Qt 6.10.2 required.'}
    Invoke-ProbeCommand 'python-version' $python @('--version') 30000
    if(([IO.File]::ReadAllText((Join-Path $OutputDirectory 'python-version.stdout.log'))).Trim() -notmatch '^Python 3\.12\.\d+$'){throw 'Actual Python 3.12 required.'}
    Invoke-ProbeCommand 'cmake-version' $cmake @('--version') 30000
    Invoke-ProbeCommand 'ninja-version' $ninja @('--version') 30000
    $banks=Join-Path $OutputDirectory 'banks'
    Invoke-ProbeCommand 'build-CC0-banks' $python @('-I','-X','utf8',(Join-Path $SourcePath 'converter/build_vsco_sf2.py'),'--output',$banks,'--download') 240000
    $bankManifest=Join-Path $banks 'banks-manifest.json'
    $generated=Get-Content -LiteralPath $bankManifest -Raw|ConvertFrom-Json -AsHashtable
    if($generated.status -cne 'built-pinned-vsco-sf2' -or
       $generated.source_commit -cne '28092772094b2d9f1148d84cea97f4545b8c687d' -or @($generated.banks).Count -ne 3){
        throw 'The existing converter did not produce its exact three-bank set.'
    }
    [IO.File]::Copy($bankManifest,(Join-Path $OutputDirectory 'generated-banks-manifest.json'),$false)
    $general=Join-Path $OutputDirectory 'GeneralUser-GS.sf2'
    $generalUrl='https://raw.githubusercontent.com/mrbumpy409/GeneralUser-GS/684543d5e5efaef08d02be50dcda8d552478fa60/GeneralUser-GS.sf2'
    $report.regression_asset=[ordered]@{url=$generalUrl;expected_bytes=32319396;sha256='9575028c7a1f589f5770fccc8cff2734566af40cd26ed836944e9a5152688cfe'}
    Invoke-WebRequest -Uri $generalUrl -OutFile $general -MaximumRedirection 0 -TimeoutSec 180
    $assetsBefore=Get-VerifiedAssets $OutputDirectory
    $assetsBefore|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $OutputDirectory 'assets-verification-before.json') -Encoding utf8NoBOM
    $report.assets_verified_before=$true
    $testSource=Join-Path $SourcePath 'source/test/cadence/free_sound_collections'
    $build=Join-Path $OutputDirectory 'build'
    Invoke-ProbeCommand 'configure' $cmake @('-S',$testSource,'-B',$build,'-G','Ninja','-DCMAKE_BUILD_TYPE=Release',
        "-DCMAKE_PREFIX_PATH=$QtPath","-DCMAKE_CXX_COMPILER=$cl","-DCMAKE_MAKE_PROGRAM=$ninja",'-DCMAKE_CXX_FLAGS=/utf-8') 120000
    Invoke-ProbeCommand 'build' $cmake @('--build',$build,'--target','local_only_collection_tests','free_collection_installer_tests','--parallel','2') 180000
    $binaries=@()
    foreach($name in @('local_only_collection_tests.exe','free_collection_installer_tests.exe')){
        $file=Join-Path $build $name;Assert-PlainFile $file
        $binaries+=,[ordered]@{name=$name;sha256=(Hash $file);bytes=(Get-Item -LiteralPath $file).Length}
    }
    $report.test_binaries=$binaries
    $resources=Join-Path $SourcePath 'source/src/musesounds/qml/MuseScore/MuseSounds/resources'
    Invoke-ProbeCommand 'local-only-scenarios' (Join-Path $build 'local_only_collection_tests.exe') @((Join-Path $resources 'free-sound-collections.json'),$banks) 120000
    Assert-ScenarioOutput ([IO.File]::ReadAllText((Join-Path $OutputDirectory 'local-only-scenarios.stdout.log'))) 8 '8/8 local-only production installer scenarios passed (Qt 6.10.2).'
    $report.local_only_scenarios=8
    # No --download-real flag: the 13 local regressions include cancellation,
    # reentrancy/destruction, unknown files, corrupt bytes and the live lock.
    Invoke-ProbeCommand 'existing-scenarios' (Join-Path $build 'free_collection_installer_tests.exe') @($general,(Join-Path $resources 'GeneralUser-GS-LICENSE.txt')) 120000
    Assert-ScenarioOutput ([IO.File]::ReadAllText((Join-Path $OutputDirectory 'existing-scenarios.stdout.log'))) 13 '13/13 real installer scenarios passed (Qt 6.10.2).'
    $report.existing_scenarios=13
    $after=Get-VerifiedSourceSnapshot $SourcePath
    $after|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $OutputDirectory 'source-verification-after.json') -Encoding utf8NoBOM
    $report.source_verified_after=$true
    $assetsAfter=Get-VerifiedAssets $OutputDirectory
    $assetsAfter|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $OutputDirectory 'assets-verification-after.json') -Encoding utf8NoBOM
    $report.assets_verified_after=$true
    if((Hash $bankManifest) -cne (Hash (Join-Path $OutputDirectory 'generated-banks-manifest.json'))){throw 'Generated bank manifest changed during installer tests.'}
    $report.total_scenarios=21;$report.status='passed_native_VSCO_local_only_and_existing_installer';$report.passed=$true
}catch{$report.status='failed_or_blocked';$report.error=$_.Exception.Message}
finally{
    $env:PATH=$originalPath;$report.finished_utc=[DateTime]::UtcNow.ToString('o')
    $report|ConvertTo-Json -Depth 20|Set-Content -LiteralPath (Join-Path $OutputDirectory 'vsco-installer-report.json') -Encoding utf8NoBOM
    Write-Host 'CADENCE_FREE_INSTALLER_REPORT_BEGIN'
    Write-Host ($report|ConvertTo-Json -Depth 20 -Compress)
    Write-Host 'CADENCE_FREE_INSTALLER_REPORT_END'
}
if(-not $report.passed){throw 'Native VSCO installer qualification failed or is blocked; inspect exact evidence.'}
