# SPDX-License-Identifier: GPL-3.0-only
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $SourcePath,
    [Parameter(Mandatory)][string] $QtPath,
    [Parameter(Mandatory)][string] $OutputDirectory
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if (-not [OperatingSystem]::IsWindows() -or
    [Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne [Runtime.InteropServices.Architecture]::X64 -or
    $env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitProcess -or
    $env:GITHUB_ACTIONS -ne 'true' -or $env:CI -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted') {
    throw 'This probe requires disposable hosted Windows x64 CI.'
}
$SourcePath = [IO.Path]::GetFullPath($SourcePath)
$QtPath = [IO.Path]::GetFullPath($QtPath)
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
if (-not $env:RUNNER_TEMP) { throw 'RUNNER_TEMP is required.' }
$temporaryRoot = [IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\','/') + [IO.Path]::DirectorySeparatorChar
if (-not $OutputDirectory.StartsWith($temporaryRoot,[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $OutputDirectory)) {
    throw 'OutputDirectory must be new and strictly below RUNNER_TEMP.'
}
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
$report = [ordered]@{
    schema_version=1;status='pending';passed=$false;source_path=$SourcePath;qt_path=$QtPath
    source_run_id=$env:GITHUB_RUN_ID;driver_commit=$env:GITHUB_SHA
    scope='Compile and run only the twenty real QtCore store/journal/collection/XML/native-watch scenarios'
    source_manifest_verified=$false;source_manifest_verified_after=$false;expected_scenarios=20;runtime_scenarios_passed=$null
    source_commit='2e1b0987e633bcec0247d03cde8933408fd95f81';source_tree='df58fc9b447840ab2b4451096f5e12ba18a29455';kernel=$null
    application_built=$false;application_executed=$false;gui_tested=$false;musical_editing_tested=$false
    ctest_started=$false;commands=@();error=$null;started_utc=[DateTime]::UtcNow.ToString('o')
}
function Assert-PlainFile([string] $Path) {
    $item = Get-Item -LiteralPath $Path
    if ($item.PSIsContainer) { throw "A file was required: $Path" }
    for ($current=$item; $null -ne $current; $current=$current.Parent) {
        if ($current.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Reparse path refused: $Path" }
        if ($current -is [IO.FileInfo]) { $current=$current.Directory; if ($null -eq $current) { break } }
        if ($current.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Reparse ancestor refused: $Path" }
    }
}
function Invoke-ProbeCommand([string] $Name, [string] $Executable, [string[]] $Arguments, [int] $TimeoutMilliseconds) {
    $stdoutPath=Join-Path $OutputDirectory ($Name+'.stdout.log')
    $stderrPath=Join-Path $OutputDirectory ($Name+'.stderr.log')
    $record=[ordered]@{started_utc=[DateTime]::UtcNow.ToString('o');elapsed_seconds=$null;name=$Name;executable=$Executable;arguments=$Arguments;exit_code=$null;timed_out=$false;stdout_path=$stdoutPath;stderr_path=$stderrPath}
    $report.commands += $record
    $info=[Diagnostics.ProcessStartInfo]::new()
    $info.FileName=$Executable;$info.WorkingDirectory=$OutputDirectory;$info.UseShellExecute=$false
    $info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    foreach($argument in $Arguments){$info.ArgumentList.Add($argument)}
    $timer=[Diagnostics.Stopwatch]::StartNew()
    $process=[Diagnostics.Process]::new();$process.StartInfo=$info
    try {
        if(-not $process.Start()){throw "Could not start $Name."}
        if($Name -ceq 'ctest'){$report.ctest_started=$true}
        $out=$process.StandardOutput.ReadToEndAsync();$err=$process.StandardError.ReadToEndAsync()
        if(-not $process.WaitForExit($TimeoutMilliseconds)){
            $record.timed_out=$true;$process.Kill($true)
            if(-not $process.WaitForExit(5000)){throw "Owned $Name process did not stop after its timeout."}
        }
        [IO.File]::WriteAllText($stdoutPath,$out.GetAwaiter().GetResult())
        [IO.File]::WriteAllText($stderrPath,$err.GetAwaiter().GetResult())
        $record.exit_code=$process.ExitCode
        Write-Host ("{0}: exit {1}, timeout={2}" -f $Name,$record.exit_code,$record.timed_out)
        if($record.timed_out -or $record.exit_code -ne 0){throw "$Name failed; inspect its retained stdout/stderr."}
    } finally {
        try { if($process.Id -and -not $process.HasExited){$process.Kill($true);[void]$process.WaitForExit(5000)} } catch {}
        $timer.Stop();$record.elapsed_seconds=$timer.Elapsed.TotalSeconds
        $process.Dispose()
    }
}

function Get-VerifiedSourceSnapshot([string] $SourceRoot) {
    $expected=@(
        'src/project/internal/localscorelibrarystore.cpp',
        'src/project/internal/localscorelibrarystore.h',
        'src/project/internal/localannotationdraft.h',
        'src/project/internal/localscorexmlcheck.h',
        'src/project/internal/localcatalogwatch.h',
        'test/cadence/local_library_store/CMakeLists.txt',
        'test/cadence/local_library_store/store_tests.cpp'
    )
    $manifestPath=Join-Path $SourceRoot 'source-manifest.json'
    Assert-PlainFile $manifestPath
    if((Get-Item -LiteralPath $manifestPath).Length -gt 65536){throw 'Source manifest exceeds 64 KiB.'}
    $manifestHash=(Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if($manifestHash -cne 'd972bce4a997238faffa3b5c02d14e2df0f313ee8645dfa5c99a72535c3486bc'){throw 'The source manifest differs from the reviewed pinned manifest.'}
    $manifest=Get-Content -LiteralPath $manifestPath -Raw|ConvertFrom-Json -AsHashtable
    if(($manifest.schema_version -isnot [int] -and $manifest.schema_version -isnot [long]) -or $manifest.schema_version -ne 1 -or
       ($manifest.expected_scenarios -isnot [int] -and $manifest.expected_scenarios -isnot [long]) -or $manifest.expected_scenarios -ne 20 -or
       $manifest.source_commit -cne '2e1b0987e633bcec0247d03cde8933408fd95f81' -or $manifest.source_tree -cne 'df58fc9b447840ab2b4451096f5e12ba18a29455' -or
       $manifest.required_qt_version -cne '6.10.2' -or @($manifest.files).Count -ne $expected.Count){throw 'Expected the reviewed source commit/tree, Qt 6.10.2 and exactly seven sources/twenty scenarios.'}
    $seen=[Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    $verified=@()
    foreach($entry in $manifest.files){
        if($entry.path -isnot [string] -or $entry.path -cnotin $expected -or -not $seen.Add($entry.path) -or
           $entry.sha256 -isnot [string] -or $entry.sha256 -cnotmatch '^[0-9a-f]{64}$' -or
           ($entry.bytes -isnot [long] -and $entry.bytes -isnot [int]) -or $entry.bytes -le 0 -or $entry.bytes -gt 1048576){throw 'Invalid, unexpected or duplicate source manifest entry.'}
        $file=Join-Path $SourceRoot $entry.path
        Assert-PlainFile $file
        $item=Get-Item -LiteralPath $file
        $hash=(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
        if($item.Length -ne $entry.bytes -or $hash -cne $entry.sha256){throw "Source bytes/SHA-256 mismatch: $($entry.path)"}
        $verified += [ordered]@{path=$entry.path;bytes=$item.Length;sha256=$hash}
    }
    return [ordered]@{manifest=$manifest;verification=[ordered]@{schema_version=1;verified=$true;source_commit=$manifest.source_commit;source_tree=$manifest.source_tree;manifest_sha256=$manifestHash;files=$verified}}
}
function Assert-ScenarioTranscript([string] $Runtime) {
    $expectedSummary=[regex]::Escape('20/20 production-store runtime scenarios passed (Qt 6.10.2).')
    if([regex]::Matches($Runtime,'(?m)^(?:\d+:\s*)?'+$expectedSummary+'\s*$').Count -ne 1 -or
       [regex]::Matches($Runtime,'(?m)^(?:\d+:\s*)?PASS:').Count -ne 20 -or
       $Runtime -match '(?m)^(?:\d+:\s*)?FAIL:'){throw 'CTest did not report every reviewed production runtime scenario passing on Qt 6.10.2.'}
}

$originalPath=$env:PATH
try {
    $report.kernel=[ordered]@{
        os_description=[Runtime.InteropServices.RuntimeInformation]::OSDescription
        os_version=[Environment]::OSVersion.VersionString
        process_architecture=[Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture.ToString()
        powershell=$PSVersionTable.PSVersion.ToString();dotnet=[Runtime.InteropServices.RuntimeInformation]::FrameworkDescription
        runner_os=$env:RUNNER_OS;runner_arch=$env:RUNNER_ARCH;image_os=$env:ImageOS;image_version=$env:ImageVersion
    }
    $snapshot=Get-VerifiedSourceSnapshot $SourcePath
    $manifest=$snapshot.manifest
    $manifestPath=Join-Path $SourcePath 'source-manifest.json'
    $snapshot.verification|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $OutputDirectory 'source-verification-before.json') -Encoding utf8
    [IO.File]::Copy($manifestPath,(Join-Path $OutputDirectory 'source-manifest.json'),$false)
    $report.source_manifest_verified=$true
    $scenarioCount=20
    if($env:VSCMD_ARG_TGT_ARCH -ne 'x64' -or $env:VSCMD_VER -notmatch '^17\.14(?:\.|$)' -or ([string]$env:WindowsSDKVersion).TrimEnd('\') -ne '10.0.26100.0'){throw 'MSVC 17.14 x64 and SDK 10.0.26100.0 are required.'}
    # A hosted developer PATH can contain both standalone and Visual Studio
    # installations. Use its first actual application, not an array converted
    # to a space-joined non-existent executable filename.
    $cmake=(Get-Command cmake -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
    $ninja=(Get-Command ninja -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
    $cl=(Get-Command cl -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
    $report.toolchain=[ordered]@{
        cmake=$cmake;ninja=$ninja;cl=$cl;visual_studio=$env:VSCMD_VER;vc_tools_version=$env:VCToolsVersion
        windows_sdk=$env:WindowsSDKVersion;compiler_file_version=(Get-Item -LiteralPath $cl).VersionInfo.FileVersion
        compiler_sha256=(Get-FileHash -LiteralPath $cl -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $qmake=Join-Path $QtPath 'bin/qmake.exe'
    foreach($file in @($qmake,(Join-Path $QtPath 'bin/Qt6Core.dll'),(Join-Path $QtPath 'lib/cmake/Qt6/Qt6Config.cmake'))){if(-not(Test-Path -LiteralPath $file -PathType Leaf)){throw 'The supplied Qt base development kit is incomplete.'}}
    $env:PATH=(Join-Path $QtPath 'bin')+';'+$env:PATH
    Invoke-ProbeCommand 'qt-version' $qmake @('-query','QT_VERSION') 30000
    if(([IO.File]::ReadAllText((Join-Path $OutputDirectory 'qt-version.stdout.log'))).Trim() -cne '6.10.2'){throw 'The actual Qt kit must report exactly 6.10.2.'}
    $report.qt_core=[ordered]@{
        required_version='6.10.2';arch='win64_msvc2022_64';qmake_sha256=(Get-FileHash -LiteralPath $qmake -Algorithm SHA256).Hash.ToLowerInvariant()
        dll_sha256=(Get-FileHash -LiteralPath (Join-Path $QtPath 'bin/Qt6Core.dll') -Algorithm SHA256).Hash.ToLowerInvariant()
        dll_file_version=(Get-Item -LiteralPath (Join-Path $QtPath 'bin/Qt6Core.dll')).VersionInfo.FileVersion
    }
    Invoke-ProbeCommand 'cmake-version'  $cmake @('--version') 30000
    Invoke-ProbeCommand 'ninja-version' $ninja @('--version') 30000
    $build=Join-Path $OutputDirectory 'build'
    Invoke-ProbeCommand 'configure' $cmake @('-S',(Join-Path $SourcePath 'test/cadence/local_library_store'),'-B',$build,'-G','Ninja',"-DCMAKE_CXX_COMPILER=$cl",'-DCMAKE_BUILD_TYPE=Release',"-DCMAKE_PREFIX_PATH=$QtPath","-DQt6_DIR=$QtPath/lib/cmake/Qt6","-DQt6Core_DIR=$QtPath/lib/cmake/Qt6Core",'-DCMAKE_CXX_FLAGS=/utf-8') 120000
    Invoke-ProbeCommand 'build' $cmake @('--build',$build,'--target','local_library_store_tests','--parallel','2') 180000
    $binary=Join-Path $build 'local_library_store_tests.exe'
    if(-not(Test-Path -LiteralPath $binary -PathType Leaf)){throw 'The real standalone test binary was not produced.'}
    $report.test_executable_sha256=(Get-FileHash -LiteralPath $binary -Algorithm SHA256).Hash.ToLowerInvariant()
    $ctest=Join-Path (Split-Path -Parent $cmake) 'ctest.exe'
    Invoke-ProbeCommand 'ctest' $ctest @('--test-dir',$build,'--verbose','--output-on-failure','--no-tests=error','--timeout','60','-R','^local_library_store$') 120000
    $runtime=[IO.File]::ReadAllText((Join-Path $OutputDirectory 'ctest.stdout.log'))
    Assert-ScenarioTranscript $runtime
    # Validate the same pinned manifest, exact byte lengths and all source hashes
    # after compilation/execution; a source mutation cannot become a pass.
    $after=Get-VerifiedSourceSnapshot $SourcePath
    $after.verification|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $OutputDirectory 'source-verification-after.json') -Encoding utf8
    $report.source_manifest_verified_after=$true
    $report.runtime_scenarios_passed=[int]$scenarioCount;$report.passed=$true;$report.status='all_reviewed_production_runtime_scenarios_passed'
} catch {
    $report.status='failed';$report.error=$_.Exception.Message
} finally {
    $env:PATH=$originalPath
    $report.finished_utc=[DateTime]::UtcNow.ToString('o')
    $report|ConvertTo-Json -Depth 12|Set-Content -LiteralPath (Join-Path $OutputDirectory 'annotation-store-probe-report.json') -Encoding utf8
    Write-Host ($report|ConvertTo-Json -Depth 12 -Compress)
}
if(-not $report.passed){throw 'The real Windows QtCore store probe did not pass; inspect retained evidence.'}
