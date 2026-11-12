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
    scope='Candidate production store21 and watch comparison against frozen2005 helper; no application/GUI fix inferred'
    source_manifest_verified=$false;source_manifest_verified_after=$false;expected_phases=6;runtime_phases_completed=$null;expected_store_scenarios=21;runtime_store_scenarios_passed=$null;selective_file_watch_conflict_observed=$false
    source_commit='391107f9d42518db272420d3f80215ff1e4ba389';source_tree='ef85a87bbf4c5aad0f2add1a379ff5aaf1f3008b';kernel=$null
    application_built=$false;application_executed=$false;gui_tested=$false;musical_editing_tested=$false
    stress_started=$false;commands=@();error=$null;started_utc=[DateTime]::UtcNow.ToString('o')
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
        if($Name -ceq 'stress'){$report.stress_started=$true}
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
        'source/src/project/internal/localscorelibrarystore.cpp',
        'source/src/project/internal/localscorelibrarystore.h',
        'source/src/project/internal/localannotationdraft.h',
        'source/src/project/internal/localscorexmlcheck.h',
        'source/src/project/internal/localcatalogwatch.h',
        'source/test/cadence/local_library_store/CMakeLists.txt',
        'source/test/cadence/local_library_store/store_tests.cpp',
        'control/localcatalogwatch-2005.h',
        'watch_mode_stress.cpp',
        'CMakeLists.txt'
    )
    $manifestPath=Join-Path $SourceRoot 'probe-source-manifest.json'
    Assert-PlainFile $manifestPath
    if((Get-Item -LiteralPath $manifestPath).Length -gt 65536){throw 'Source manifest exceeds 64 KiB.'}
    $manifestHash=(Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if($manifestHash -cne 'b6cb3e36ca19a792651145bd3de8f08111e8c982b44235a826f601d4dd99a403'){throw 'The source manifest differs from the reviewed pinned manifest.'}
    $manifest=Get-Content -LiteralPath $manifestPath -Raw|ConvertFrom-Json -AsHashtable
    if(($manifest.schema_version -isnot [int] -and $manifest.schema_version -isnot [long]) -or $manifest.schema_version -ne 1 -or
       ($manifest.expected_phases -isnot [int] -and $manifest.expected_phases -isnot [long]) -or $manifest.expected_phases -ne 6 -or
       $manifest.source_commit -cne '391107f9d42518db272420d3f80215ff1e4ba389' -or $manifest.source_tree -cne 'ef85a87bbf4c5aad0f2add1a379ff5aaf1f3008b' -or
       $manifest.expected_scenarios -ne 21 -or $manifest.old_control_source_commit -cne '961c80b235d413dc9d123ea8f669ddb7f84ecd09' -or $manifest.required_qt_version -cne '6.10.2' -or @($manifest.files).Count -ne $expected.Count){throw 'Expected the reviewed source commit/tree, Qt 6.10.2 and exactly ten build inputs, twenty-one store scenarios and six baseline diagnostic phases.'}
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
function Assert-StressObservations([hashtable] $Observation) {
    if($Observation.source_commit -cne '391107f9d42518db272420d3f80215ff1e4ba389' -or
       $Observation.old_control_source_commit -cne '961c80b235d413dc9d123ea8f669ddb7f84ecd09' -or $Observation.qt_version -cne '6.10.2' -or $Observation.native_windows -ne $true -or
       @($Observation.phases).Count -notin @(6,12) -or $Observation.data_preserved -ne $true -or
       $Observation.no_watch_failures -ne 0){throw 'Diagnostic runtime controls/source/version were not satisfied.'}
    if($Observation.existing_cadence_profiles_accessed -ne $false -or
       @($Observation.phases).Count -ne $(if($Observation.fresh_local_appdata_experiment_performed){12}else{6})){throw 'Unexpected profile access or location experiment accounting.'}
    $seen=[Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    foreach($phase in $Observation.phases){
        if($phase.mode -cnotin @('none','file-and-directory','directory-only-fileid') -or
           $phase.location_group -cnotin @('default-temp','fresh-local-appdata') -or
           $phase.round -notin @(0,1) -or -not $seen.Add($phase.location_group+'|'+$phase.mode+'|'+$phase.round) -or
           $phase.attempts -lt 1 -or $phase.attempts -gt 2000 -or
           $phase.successes+$phase.failures -ne $phase.attempts -or $phase.data_preserved -ne $true -or
           ($phase.mode -cne 'none' -and $phase.callbacks_overlapping_store_mutation -lt 1)){
            throw 'Missing/duplicate phase, invalid mutation accounting or no callback overlap; inspect the diagnostic.'
        }
    }
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
    $manifestPath=Join-Path $SourcePath 'probe-source-manifest.json'
    $snapshot.verification|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $OutputDirectory 'source-verification-before.json') -Encoding utf8
    [IO.File]::Copy($manifestPath,(Join-Path $OutputDirectory 'probe-source-manifest.json'),$false)
    $report.source_manifest_verified=$true
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
    Invoke-ProbeCommand 'configure' $cmake @('-S',$SourcePath,'-B',$build,'-G','Ninja',"-DCMAKE_CXX_COMPILER=$cl",'-DCMAKE_BUILD_TYPE=Release',"-DCMAKE_PREFIX_PATH=$QtPath","-DQt6_DIR=$QtPath/lib/cmake/Qt6","-DQt6Core_DIR=$QtPath/lib/cmake/Qt6Core",'-DCMAKE_CXX_FLAGS=/utf-8') 120000
    Invoke-ProbeCommand 'build' $cmake @('--build',$build,'--target','cadence_watch_mode_stress','local_library_store_tests','--parallel','2') 180000
    $binary=Join-Path $build 'cadence_watch_mode_stress.exe'
    if(-not(Test-Path -LiteralPath $binary -PathType Leaf)){throw 'The real standalone test binary was not produced.'}
    $report.test_executable_sha256=(Get-FileHash -LiteralPath $binary -Algorithm SHA256).Hash.ToLowerInvariant()
    $ctest=Join-Path (Split-Path -Parent $cmake) 'ctest.exe'
    Invoke-ProbeCommand 'store-ctest' $ctest @('--test-dir',(Join-Path $build 'production-store-tests'),'--verbose','--output-on-failure','--no-tests=error','--timeout','60','-R','^local_library_store$') 120000
    $storeOutput=[IO.File]::ReadAllText((Join-Path $OutputDirectory 'store-ctest.stdout.log'))
    $summary=[regex]::Escape('21/21 production-store runtime scenarios passed (Qt 6.10.2).')
    if([regex]::Matches($storeOutput,'(?m)^(?:\d+:\s*)?'+$summary+'\s*$').Count -ne 1 -or
       [regex]::Matches($storeOutput,'(?m)^(?:\d+:\s*)?PASS:').Count -ne 21 -or $storeOutput -match '(?m)^(?:\d+:\s*)?FAIL:'){
        throw 'The exact candidate did not complete twenty-one real production store scenarios.'
    }
    $report.runtime_store_scenarios_passed=21
    $observationPath=Join-Path $OutputDirectory 'watch-mode-observations.json'
    Invoke-ProbeCommand 'stress' $binary @($observationPath) 480000
    $observation=Get-Content -LiteralPath $observationPath -Raw|ConvertFrom-Json -AsHashtable
    Assert-StressObservations $observation
    $report.selective_file_watch_conflict_observed=$observation.selective_file_watch_conflict_observed
    $report.causal_interpretation=$observation.interpretation
    $report.no_watch_failures=$observation.no_watch_failures
    $report.file_and_directory_failures=$observation.file_and_directory_failures
    $report.directory_only_failures=$observation.directory_only_failures
    if($observation.directory_only_failures -ne 0){throw 'The actual fixed production helper still had concurrent save failures; candidate is not clear.'}
    # Validate the same pinned manifest, exact byte lengths and all source hashes
    # after compilation/execution; a source mutation cannot become a pass.
    $after=Get-VerifiedSourceSnapshot $SourcePath
    $after.verification|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $OutputDirectory 'source-verification-after.json') -Encoding utf8
    $report.source_manifest_verified_after=$true
    $report.runtime_phases_completed=@($observation.phases).Count;$report.passed=$true;$report.status='bounded_diagnostic_experiment_completed'
} catch {
    $report.status='failed';$report.error=$_.Exception.Message
} finally {
    $env:PATH=$originalPath
    $report.finished_utc=[DateTime]::UtcNow.ToString('o')
    $report|ConvertTo-Json -Depth 12|Set-Content -LiteralPath (Join-Path $OutputDirectory 'parent-watch-fix-probe-report.json') -Encoding utf8
    Write-Host ($report|ConvertTo-Json -Depth 12 -Compress)
}
if(-not $report.passed){throw 'The concurrent diagnostic did not complete valid controls; inspect retained evidence. No application fix is inferred.'}
