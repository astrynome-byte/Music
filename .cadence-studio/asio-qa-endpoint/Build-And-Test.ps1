# SPDX-License-Identifier: GPL-3.0-only
# Source preparation is not a Windows qualification. This script may run only
# on a disposable native Windows x64 GitHub-hosted runner, never an end-user PC.
#Requires -Version 7.0
[CmdletBinding()]
param([string]$SourcePath=$PSScriptRoot,[Parameter(Mandatory)][string]$WorkPath)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if(-not [OperatingSystem]::IsWindows() -or -not [Environment]::Is64BitProcess -or
   [Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne 'X64' -or
   $env:GITHUB_ACTIONS -ne 'true' -or $env:CI -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted'){
    throw 'Only disposable native Windows x64 GitHub-hosted CI is permitted.'
}
function Plain([string]$Path){
    if([string]::IsNullOrWhiteSpace($Path) -or $Path -match '[\x00\r\n]'){throw 'Invalid path.'}
    $path=[IO.Path]::GetFullPath($Path)
    for($current=$path;$current;$current=[IO.Path]::GetDirectoryName($current.TrimEnd('\','/'))){
        if((Test-Path -LiteralPath $current) -and ((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'Reparse paths are refused.'}
        if([IO.Path]::GetDirectoryName($current.TrimEnd('\','/')) -eq $current){break}
    };$path
}
$SourcePath=Plain $SourcePath;$WorkPath=Plain $WorkPath;$temporary=Plain $env:RUNNER_TEMP
if(-not $WorkPath.StartsWith($temporary.TrimEnd('\','/')+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase) -or
   (Test-Path -LiteralPath $WorkPath)){throw 'WorkPath must be a new directory strictly below RUNNER_TEMP.'}
$sourceManifestPath=Join-Path $SourcePath 'source-manifest.json'
$sourceManifest=Get-Content -LiteralPath $sourceManifestPath -Raw|ConvertFrom-Json
if($sourceManifest.schema_version -ne 1 -or $sourceManifest.status -cne 'source-prepared-not-Windows-qualified' -or $sourceManifest.files.Count -lt 15){throw 'Reviewed QA source manifest is missing.'}
foreach($file in $sourceManifest.files){
    if($file.path -match '(^|/)\.\.?(/|$)|[\\:\x00-\x1f]|^/|//' -or $file.path -ceq 'source-manifest.json'){throw 'Unsafe source manifest path.'}
    $path=Plain (Join-Path $SourcePath $file.path)
    if((Get-Item -LiteralPath $path).Length -ne $file.bytes -or (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $file.sha256){throw 'Prepared QA source bytes differ from the reviewed manifest.'}
}
$sdkLock=Get-Content -LiteralPath (Join-Path $SourcePath 'asio-interfaces.lock.json') -Raw|ConvertFrom-Json
if($sdkLock.schema_version -ne 1 -or $sdkLock.archive_sha256 -cne 'd5ebf0c20dd2c5f43771fd0c1418f4b361bf52434ee670097cfa6b3a335e2eca' -or
   $sdkLock.license_selected -cne 'GPL-3.0-only' -or $sdkLock.files.Count -ne 4){throw 'Pinned ASIO interface profile differs.'}
foreach($file in $sdkLock.files){
    if($file.path -cnotmatch '^third_party/asio/(?:asio\.h|asiosys\.h|iasiodrv\.h|LICENSE\.txt)$'){throw 'Unexpected SDK file.'}
    $path=Plain (Join-Path $SourcePath $file.path)
    if((Get-Item -LiteralPath $path).Length -ne $file.bytes -or (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $file.sha256){throw 'ASIO interface bytes changed.'}
}
[void](Get-Command cmake.exe -ErrorAction Stop);[void](Get-Command cl.exe -ErrorAction Stop)
$build=Join-Path $WorkPath 'build';$evidence=Join-Path $WorkPath 'evidence';$stats=Join-Path $evidence 'stats'
[void][IO.Directory]::CreateDirectory($stats)
$sourceCopy=Join-Path $evidence 'corresponding-source'
[void][IO.Directory]::CreateDirectory($sourceCopy)
foreach($file in $sourceManifest.files){
    $destination=Join-Path $sourceCopy $file.path
    [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination))
    Copy-Item -LiteralPath (Join-Path $SourcePath $file.path) -Destination $destination
}
Copy-Item -LiteralPath $sourceManifestPath -Destination $sourceCopy
Compress-Archive -LiteralPath $sourceCopy -DestinationPath (Join-Path $evidence 'Cadence-QA-Clock-corresponding-source.zip') -CompressionLevel Optimal
function Native([string[]]$Arguments,[string]$Log){
    & cmake.exe @Arguments 2>&1|Tee-Object -FilePath (Join-Path $evidence $Log)|ForEach-Object {Write-Host $_}
    if($LASTEXITCODE -ne 0){throw "CMake failed; inspect $Log."}
}
Native @('-S',$SourcePath,'-B',$build,'-G','Ninja','-DCMAKE_BUILD_TYPE=Release') 'configure.log'
Native @('--build',$build,'--parallel','2') 'build.log'
$metrics=Join-Path $build 'cadence_qa_metrics_test.exe'
& $metrics 2>&1|Tee-Object -FilePath (Join-Path $evidence 'metrics.log')|ForEach-Object {Write-Host $_}
if($LASTEXITCODE -ne 0){throw 'Portable metrics failed in the native build.'}
$harness=Join-Path $build 'CadenceQaClockHarness.exe';$dll=Join-Path $build 'CadenceQaClock.dll'
$previousStats=$env:CADENCE_QA_CLOCK_STATS_DIR
$process=$null
try{
    $env:CADENCE_QA_CLOCK_STATS_DIR=$stats
    # WorkPath and SDK paths are local controlled values; Start-Process quoting
    # is limited to one explicit fully qualified DLL argument, never a shell.
    if($dll.Contains('"')){throw 'Unsupported DLL path.'}
    $process=Start-Process -FilePath $harness -ArgumentList ('"'+$dll+'"') -PassThru -NoNewWindow `
        -RedirectStandardOutput (Join-Path $evidence 'harness.stdout.log') -RedirectStandardError (Join-Path $evidence 'harness.stderr.log')
    if(-not $process.WaitForExit(45000)){
        $process.Kill($true);[void]$process.WaitForExit(5000);throw 'Owned QA harness exceeded45s; its process tree was stopped.'
    }
    $process.WaitForExit();$process.Refresh()
    if($process.ExitCode -ne 0){throw 'Native COM/ASIO harness failed; original logs retained.'}
}finally{
    if($process){if(-not $process.HasExited){$process.Kill($true);[void]$process.WaitForExit(5000)};$process.Dispose()}
    $env:CADENCE_QA_CLOCK_STATS_DIR=$previousStats
}
$reports=@(Get-ChildItem -LiteralPath $stats -File -Filter 'clock-*.json')
if($reports.Count -ne 4){throw 'Expected four bounded stopped-run reports.'}
foreach($file in $reports){
    if($file.Length -gt 4096){throw 'Oversized metric report.'}
    $report=Get-Content -LiteralPath $file.FullName -Raw|ConvertFrom-Json
    if($report.schema_version -ne 1 -or $report.physical_audio_output -cne $false -or $report.qualified_hardware -cne $false -or
       $report.callbacks -lt 1 -or $report.frames -ne $report.callbacks*256 -or $report.finite_samples -ne $report.frames*2 -or
       $report.nonfinite_samples -ne 0 -or $report.clipped_samples -ne 0 -or $report.callback_errors -ne 0){throw 'Stopped-run report has inconsistent output metrics.'}
}
Copy-Item -LiteralPath $dll,$harness -Destination $evidence
$record=[ordered]@{schema_version=1;status='native-qa-endpoint-direct-factory-harness-passed';physical_audio_output=$false;listening_validated=$false
    application_Cadence_executed=$false;registry_modified=$false;kernel_driver_installed=$false;native_scenarios=4
    run_id=$env:GITHUB_RUN_ID;commit=$env:GITHUB_SHA;dll_sha256=(Get-FileHash -LiteralPath $dll -Algorithm SHA256).Hash.ToLowerInvariant()
    harness_sha256=(Get-FileHash -LiteralPath $harness -Algorithm SHA256).Hash.ToLowerInvariant();sdk_archive_sha256=$sdkLock.archive_sha256}
$record.source_manifest_sha256=(Get-FileHash -LiteralPath $sourceManifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
$record.corresponding_source_zip_sha256=(Get-FileHash -LiteralPath (Join-Path $evidence 'Cadence-QA-Clock-corresponding-source.zip') -Algorithm SHA256).Hash.ToLowerInvariant()
$record|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $evidence 'result.json') -Encoding utf8NoBOM
Copy-Item -LiteralPath (Join-Path $SourcePath 'LICENSE.txt'),(Join-Path $SourcePath 'asio-interfaces.lock.json'),(Join-Path $SourcePath 'README-FR.md') -Destination $evidence
Write-Host 'CADENCE_QA_CLOCK_RESULT_BEGIN';Write-Host ($record|ConvertTo-Json -Compress);Write-Host 'CADENCE_QA_CLOCK_RESULT_END'
Write-Host "Evidence: $evidence"
