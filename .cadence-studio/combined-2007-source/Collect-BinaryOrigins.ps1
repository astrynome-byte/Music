# SPDX-License-Identifier: GPL-3.0-only
# Reads source/build hints and native Windows version/signature metadata only.
# No staged DLL or application is loaded or executed. qmake is a developer tool.
#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $StagePath,
    [Parameter(Mandatory)][string] $ExpectedExecutableSha256,
    [Parameter(Mandatory)][string] $OutputDirectory,
    [string] $QtPath,
    [string] $ExpectedQtVersion = '6.10.2'
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (-not [OperatingSystem]::IsWindows() -or $env:OS -ne 'Windows_NT' -or
    [Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne 'X64' -or
    -not [Environment]::Is64BitProcess -or $env:GITHUB_ACTIONS -ne 'true' -or
    $env:CI -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted') {
    throw 'Only disposable native Windows x64 GitHub-hosted runners are permitted.'
}
if ($ExpectedExecutableSha256 -cnotmatch '^[a-f0-9]{64}$' -or $ExpectedQtVersion -cnotmatch '^6\.10\.2$') {
    throw 'An actual stage executable SHA and the pinned Qt6.10.2 are required.'
}
function Full-PlainPath([string] $Path) {
    if ([string]::IsNullOrWhiteSpace($Path) -or $Path -match '[\x00\r\n]') { throw 'Missing or invalid path.' }
    $path = [IO.Path]::GetFullPath($Path)
    for ($current=$path; $current; $current=[IO.Path]::GetDirectoryName($current.TrimEnd('\','/'))) {
        if ((Test-Path -LiteralPath $current) -and
            ((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw 'Reparse path refused for source/metadata reads.'
        }
        if ([IO.Path]::GetDirectoryName($current.TrimEnd('\','/')) -eq $current) { break }
    }
    return $path
}
function Hash([string] $Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Is-Below([string] $Child, [string] $Parent) {
    $Child.StartsWith($Parent.TrimEnd('\','/')+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)
}
$StagePath=Full-PlainPath $StagePath
$OutputDirectory=Full-PlainPath $OutputDirectory
$temporary=Full-PlainPath $env:RUNNER_TEMP
if (-not (Is-Below $StagePath $temporary) -or -not (Is-Below $OutputDirectory $temporary) -or
    (Is-Below $OutputDirectory $StagePath) -or (Is-Below $StagePath $OutputDirectory) -or
    $StagePath -eq $OutputDirectory -or (Test-Path -LiteralPath $OutputDirectory)) {
    throw 'Stage and new output must be separate children of RUNNER_TEMP.'
}
$executable=Full-PlainPath (Join-Path $StagePath 'bin/CadenceStudio4.exe')
if (-not (Test-Path -LiteralPath $executable -PathType Leaf) -or (Hash $executable) -cne $ExpectedExecutableSha256) {
    throw 'The staged executable differs from its original build result; nothing executed.'
}
if ($QtPath) {
    $QtPath=Full-PlainPath $QtPath
    if (-not (Test-Path -LiteralPath $QtPath -PathType Container)) { throw 'Qt SDK path is missing.' }
}
[void][IO.Directory]::CreateDirectory($OutputDirectory)
$report=[ordered]@{
    schema_version=1;scope='Read-only version/signature/source-build hints; this is evidence, not a license or reproducible-build approval'
    stage=$StagePath;executable_sha256=$ExpectedExecutableSha256
    driver_commit=$env:GITHUB_SHA;run_id=$env:GITHUB_RUN_ID
    application_executed=$false;staged_dll_loaded=$false;staged_bytes_modified=$false
    qmake_developer_tool_executed=$false;qt_sdk_present=[bool]$QtPath
    dll_metadata=@();qt_runtime_identity=@();sdk_metadata=@();sdk_notices=@();qmake=$null;errors=@()
    sdk_sbom=[ordered]@{status='sdk-not-supplied';present=$false;files=@();source_or_application_program_executed=$false}
    acquisition_log_scope='Qt installer/action URLs are in the original GitHub step logs; no guessed filesystem or credential paths are searched'
}
$textBudget=98304L
function Read-SdkRecord([string] $Path, [string] $Category) {
    $path=Full-PlainPath $Path
    $relative=[IO.Path]::GetRelativePath($QtPath,$path).Replace('\','/')
    if (-not (Is-Below $path $QtPath)) { throw 'SDK metadata escapes the supplied SDK.' }
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        return [ordered]@{path=$relative;category=$Category;present=$false}
    }
    $file=Get-Item -LiteralPath $path
    if ($file.Length -gt 4194304) { throw 'Unexpected oversized SDK text candidate.' }
    $limit=[int][Math]::Min([Math]::Min(16384L,$file.Length),$script:textBudget)
    $stream=[IO.File]::OpenRead($path)
    try {
        $bytes=[byte[]]::new($limit);$count=$stream.Read($bytes,0,$limit)
        $text=[Text.Encoding]::UTF8.GetString($bytes,0,$count)
    } finally { $stream.Dispose() }
    $script:textBudget-=$count
    return [ordered]@{path=$relative;category=$Category;present=$true;bytes=$file.Length
        sha256=Hash $path;printed_bytes=$count;head_only=$file.Length -gt $count;text=$text}
}
function Copy-SdkSbom([string] $SdkRoot, [string] $EvidenceRoot) {
    $sbom=Full-PlainPath (Join-Path $SdkRoot 'sbom')
    $document=[ordered]@{status='optional-sdk-sbom-absent';present=$false;files=@();total_bytes=0L
        maximum_files=128;maximum_file_bytes=16777216L;maximum_total_bytes=134217728L
        source_or_application_program_executed=$false;full_original_bytes_retained=$false}
    if (-not (Test-Path -LiteralPath $sbom)) { return $document }
    if (-not (Test-Path -LiteralPath $sbom -PathType Container) -or -not (Is-Below $sbom $SdkRoot)) { throw 'SDK sbom must be a plain directory below the supplied SDK.' }
    $document.present=$true
    $pending=[Collections.Generic.Queue[string]]::new();$pending.Enqueue($sbom)
    $files=[Collections.Generic.List[object]]::new();$names=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    [int]$directories=1;[long]$total=0
    while ($pending.Count) {
        $directory=Full-PlainPath $pending.Dequeue()
        Get-ChildItem -LiteralPath $directory -Force | ForEach-Object {
            $path=Full-PlainPath $_.FullName
            if (-not (Is-Below $path $sbom)) { throw 'SDK SBOM entry escapes its supplied root.' }
            if ($_.PSIsContainer) {
                $directories++
                if ($directories -gt 256) { throw 'SDK SBOM directory listing exceeds the explicit256 bound.' }
                $pending.Enqueue($path)
            } else {
                if ($files.Count -ge 128 -or $_.Length -gt 16777216L) { throw 'SDK SBOM exceeds128 files or16MiB for one original.' }
                $relative=[IO.Path]::GetRelativePath($sbom,$path).Replace('\','/')
                if (-not $names.Add($relative)) { throw 'SDK SBOM contains a duplicate relative path.' }
                $total += $_.Length
                if ($total -gt 134217728L) { throw 'SDK SBOM originals exceed the explicit128MiB total bound.' }
                $files.Add([pscustomobject]@{source=$path;relative=$relative;bytes=$_.Length})
            }
        }
    }
    $destinationRoot=Full-PlainPath (Join-Path $EvidenceRoot 'sdk-sbom')
    if (-not (Is-Below $destinationRoot $EvidenceRoot) -or (Test-Path -LiteralPath $destinationRoot)) { throw 'SDK SBOM evidence must use a new child directory.' }
    [void][IO.Directory]::CreateDirectory($destinationRoot)
    foreach ($file in $files) {
        $source=Full-PlainPath $file.source
        $destination=Full-PlainPath (Join-Path $destinationRoot $file.relative)
        if (-not (Is-Below $destination $destinationRoot) -or (Get-Item -LiteralPath $source).Length -ne $file.bytes) { throw 'SDK SBOM source/destination changed before retention.' }
        $digest=Hash $source
        [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination))
        [IO.File]::Copy($source,$destination,$false)
        if ((Get-Item -LiteralPath $destination).Length -ne $file.bytes -or (Hash $destination) -cne $digest -or (Hash $source) -cne $digest) { throw 'SDK SBOM bytes changed while retaining the original.' }
        $document.files += [ordered]@{sdk_path='sbom/'+$file.relative;retained_path='sdk-sbom/'+$file.relative;bytes=$file.bytes;sha256=$digest}
    }
    $document.status='optional-sdk-sbom-originals-retained';$document.total_bytes=$total
    $document.full_original_bytes_retained=$true
    return $document
}
try {
    $dlls=@('icuuc.dll','opengl32sw.dll','dxcompiler.dll','dxil.dll','d3dcompiler_47.dll',
        'concrt140.dll','msvcp140.dll','msvcp140_1.dll','msvcp140_2.dll',
        'msvcp140_atomic_wait.dll','msvcp140_codecvt_ids.dll','vcruntime140.dll','vcruntime140_1.dll')
    foreach ($name in $dlls) {
        $file=Full-PlainPath (Join-Path $StagePath ('bin/'+$name))
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
            $report.dll_metadata += [ordered]@{file='bin/'+$name;present=$false};continue
        }
        $item=Get-Item -LiteralPath $file
        $version=$item.VersionInfo
        $signature=Get-AuthenticodeSignature -LiteralPath $file
        $certificate=$signature.SignerCertificate
        $sdkMatch=$null
        if ($QtPath -and (Test-Path -LiteralPath (Join-Path $QtPath ('bin/'+$name)) -PathType Leaf)) {
            $sdkFile=Full-PlainPath (Join-Path $QtPath ('bin/'+$name))
            $sdkHash=Hash $sdkFile
            $sdkMatch=[ordered]@{file='bin/'+$name;sha256=$sdkHash;identical_to_stage=$sdkHash -ceq (Hash $file)}
        }
        $report.dll_metadata += [ordered]@{
            file='bin/'+$name;present=$true;bytes=$item.Length;sha256=Hash $file
            company=$version.CompanyName;file_version=$version.FileVersion;product_version=$version.ProductVersion
            original_filename=$version.OriginalFilename;description=$version.FileDescription;product=$version.ProductName
            copyright=$version.LegalCopyright;signature_status=[string]$signature.Status
            signature_status_message=$signature.StatusMessage
            signer=if($certificate){[ordered]@{subject=$certificate.Subject;issuer=$certificate.Issuer
                thumbprint=$certificate.Thumbprint;not_before=$certificate.NotBefore.ToUniversalTime().ToString('o')
                not_after=$certificate.NotAfter.ToUniversalTime().ToString('o')}}else{$null}
            qt_sdk_same_named_file=$sdkMatch
        }
    }
    if ($QtPath) {
        $qtRuntimeFiles=@(Get-ChildItem -LiteralPath (Join-Path $StagePath 'bin') -File -Filter 'Qt6*.dll')
        if ($qtRuntimeFiles.Count -gt 64) { throw 'Qt runtime file count exceeds the reviewed bound.' }
        foreach ($item in $qtRuntimeFiles) {
            $staged=Full-PlainPath $item.FullName
            $sdkFile=Full-PlainPath (Join-Path $QtPath ('bin/'+$item.Name))
            $stagedHash=Hash $staged
            $sdkExists=Test-Path -LiteralPath $sdkFile -PathType Leaf
            $sdkHash=if($sdkExists){Hash $sdkFile}else{$null}
            $report.qt_runtime_identity += [ordered]@{
                file='bin/'+$item.Name;stage_sha256=$stagedHash;stage_bytes=$item.Length
                file_version=$item.VersionInfo.FileVersion;product_version=$item.VersionInfo.ProductVersion
                sdk_same_named_file_present=$sdkExists;sdk_sha256=$sdkHash
                identical_to_sdk=$sdkExists -and $sdkHash -ceq $stagedHash
            }
        }
        $qmake=Full-PlainPath (Join-Path $QtPath 'bin/qmake.exe')
        if (-not (Test-Path -LiteralPath $qmake -PathType Leaf)) { throw 'Pinned SDK qmake is absent.' }
        $start=[Diagnostics.ProcessStartInfo]::new();$start.FileName=$qmake;$start.UseShellExecute=$false
        $start.WorkingDirectory=$OutputDirectory;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
        $start.ArgumentList.Add('-query')
        $process=[Diagnostics.Process]::new();$process.StartInfo=$start
        try {
            if (-not $process.Start()) { throw 'SDK qmake query did not start.' }
            $report.qmake_developer_tool_executed=$true
            $stdout=$process.StandardOutput.ReadToEndAsync();$stderr=$process.StandardError.ReadToEndAsync()
            if (-not $process.WaitForExit(30000)) {
                $process.Kill();[void]$process.WaitForExit(5000);throw 'Owned qmake query timed out.'
            }
            $out=$stdout.GetAwaiter().GetResult();$err=$stderr.GetAwaiter().GetResult()
            if ($out.Length -gt 32768 -or $err.Length -gt 8192) { throw 'Unexpected oversized qmake output.' }
            $report.qmake=[ordered]@{path=$qmake;sha256=Hash $qmake;exit_code=$process.ExitCode;stdout=$out;stderr=$err}
            if ($process.ExitCode -ne 0 -or $out -cnotmatch '(?m)^QT_VERSION:6\.10\.2\s*$') {
                throw 'SDK qmake does not report the pinned Qt6.10.2.'
            }
        } finally {
            try {if($process.Id -and -not $process.HasExited){$process.Kill();[void]$process.WaitForExit(5000)}}catch{}
            $process.Dispose()
        }
        $metadata=@('mkspecs/qconfig.pri','mkspecs/modules/qt_lib_core.pri','mkspecs/modules/qt_lib_gui.pri',
            'mkspecs/modules/qt_lib_network.pri','mkspecs/modules/qt_lib_qml.pri','mkspecs/modules/qt_lib_quick.pri',
            'mkspecs/modules/qt_lib_quickcontrols2.pri','mkspecs/modules/qt_lib_core5compat.pri',
            'mkspecs/modules/qt_lib_networkauth.pri','mkspecs/modules/qt_lib_shadertools.pri','mkspecs/modules/qt_lib_svg.pri',
            'lib/cmake/Qt6Core/Qt6CoreConfig.cmake','lib/cmake/Qt6Core/Qt6CoreConfigExtras.cmake',
            'lib/cmake/Qt6Core/Qt6CoreConfigVersionImpl.cmake','lib/cmake/Qt6Gui/Qt6GuiConfigExtras.cmake',
            'include/QtCore/qtcoreversion.h','include/QtCore/qconfig.h',
            'include/QtCore/6.10.2/QtCore/private/qconfig_p.h')
        foreach ($relative in $metadata) {$report.sdk_metadata += Read-SdkRecord (Join-Path $QtPath $relative) 'build configuration'}
        $licenseCandidates=@(Get-ChildItem -LiteralPath $QtPath -File | Where-Object {$_.Name -match '(?i)licen[cs]e|copying|notice|attribution'})
        foreach ($directory in @('LICENSES','licenses','licences','doc/licenses')) {
            $folder=Join-Path $QtPath $directory
            if (Test-Path -LiteralPath $folder -PathType Container) {
                [void](Full-PlainPath $folder)
                $licenseCandidates += @(Get-ChildItem -LiteralPath $folder -File -Recurse | Select-Object -First 129)
            }
        }
        $licenseCandidates=@($licenseCandidates | Sort-Object FullName -Unique)
        if ($licenseCandidates.Count -gt 128) { throw 'SDK notice listing exceeds the explicit file bound.' }
        foreach($file in $licenseCandidates){$report.sdk_notices += Read-SdkRecord $file.FullName 'original SDK notice'}
        # Keep complete original SPDX/SBOM files as evidence without sending
        # their potentially large content through the bounded text/head reader.
        $report.sdk_sbom=Copy-SdkSbom $QtPath $OutputDirectory
    }
    if ((Hash $executable) -cne $ExpectedExecutableSha256) { throw 'Staged executable changed during metadata reads.' }
} catch {
    $report.errors += $_.Exception.Message
} finally {
    $path=Join-Path $OutputDirectory 'binary-origin-metadata.json'
    $report | ConvertTo-Json -Depth 15 | Set-Content -LiteralPath $path -Encoding utf8NoBOM
    Write-Host 'CADENCE_BINARY_ORIGIN_METADATA_BEGIN'
    Write-Host ($report|ConvertTo-Json -Depth 15 -Compress)
    Write-Host 'CADENCE_BINARY_ORIGIN_METADATA_END'
}
if ($report.errors.Count) { throw 'Binary/SDK origin metadata collection failed; inspect its exact report.' }
