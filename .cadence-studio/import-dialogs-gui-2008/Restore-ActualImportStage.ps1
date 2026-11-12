# SPDX-License-Identifier: GPL-3.0-only
# Restore only an actually produced and explicitly reviewed build2008 stage.
#Requires -Version 7.2
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $TargetPath,
    [Parameter(Mandatory)][string] $SourceSelectionDirectory,
    [Parameter(Mandatory)][string] $ArtifactDirectory,
    [Parameter(Mandatory)][string] $StagePath,
    [Parameter(Mandatory)][string] $ResultPath
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (-not [OperatingSystem]::IsWindows() -or $env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitProcess -or
    [Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne 'X64' -or
    [Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture -ne 'X64' -or
    $env:GITHUB_ACTIONS -ne 'true' -or $env:CI -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted') {
    throw 'Restoration is restricted to disposable native Windows x64 GitHub-hosted runners.'
}
if (-not $env:RUNNER_TEMP) { throw 'RUNNER_TEMP is required.' }
function FullPath([string] $Value) {
    if ([string]::IsNullOrWhiteSpace($Value) -or $Value -match '[;\r\n"\x00]') { throw 'An input path is empty or contains an unsupported character.' }
    [IO.Path]::GetFullPath($Value)
}
function Is-Below([string] $Child, [string] $Parent) {
    $Child.StartsWith($Parent.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)
}
function Assert-NoReparseAncestor([string] $Path) {
    $current = $Path
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            if ((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'A path contains a reparse point.' }
        }
        $parent = [IO.Path]::GetDirectoryName($current.TrimEnd('\', '/'))
        if (-not $parent -or $parent -eq $current) { break }
        $current = $parent
    }
}
function Hash([string] $Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Read-Json([string] $Path) { Get-Content -LiteralPath $Path -Raw -Encoding utf8 | ConvertFrom-Json }
. "$PSScriptRoot/Read-ActualImportTarget.ps1"
$target = Read-ActualImportTarget $TargetPath $SourceSelectionDirectory
$ArtifactDirectory = FullPath $ArtifactDirectory
$StagePath = FullPath $StagePath
$ResultPath = FullPath $ResultPath
$temporaryRoot = FullPath $env:RUNNER_TEMP
foreach ($path in @($ArtifactDirectory,$StagePath,$ResultPath)) {
    if (-not (Is-Below $path $temporaryRoot)) { throw 'All restoration paths must be strictly below RUNNER_TEMP.' }
    Assert-NoReparseAncestor $path
}
if (-not (Test-Path -LiteralPath $ArtifactDirectory -PathType Container) -or
    (Test-Path -LiteralPath $StagePath) -or (Test-Path -LiteralPath $ResultPath)) { throw 'Original artifact is required; extracted stage/result must be new.' }
if ((Is-Below $StagePath $ArtifactDirectory) -or (Is-Below $ArtifactDirectory $StagePath) -or
    (Is-Below $ResultPath $ArtifactDirectory) -or (Is-Below $ResultPath $StagePath)) { throw 'Original artifact, extracted stage and result must be separate.' }
# The artifact container metadata and these original companion digests must have
# been reviewed independently of this extracted artifact. Its own checksum file
# cannot authenticate itself. The reader requires the actual produced target.
$externalFiles = @($target.artifact_files.PSObject.Properties)
$requiredExternal = @('SHA256SUMS.txt','stage-manifest.json','cadence-build.json','cadence-build-result.json')
if ($externalFiles.Count -lt 4 -or $externalFiles.Count -gt 10000) { throw 'Independently pinned original companions are required.' }
$externalNames = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($pin in $externalFiles) {
    $name = $pin.Name; $expected = $pin.Value
    if ($name -notmatch '^[A-Za-z0-9][A-Za-z0-9_.-]*$' -or $name.Contains('..') -or -not $externalNames.Add($name) -or
        $expected.sha256 -isnot [string] -or $expected.sha256 -cnotmatch '^[a-f0-9]{64}$' -or
        ($expected.bytes -isnot [int] -and $expected.bytes -isnot [long]) -or $expected.bytes -lt 1) { throw 'Malformed independently pinned original companion.' }
    $path = Join-Path $ArtifactDirectory $name
    Assert-NoReparseAncestor $path
    if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or (Get-Item -LiteralPath $path).Length -ne $expected.bytes -or
        (Hash $path) -cne $expected.sha256) { throw "Original companion differs from its independently reviewed bytes: $name" }
}
foreach ($name in $requiredExternal) { if (-not $externalNames.Contains($name)) { throw "Missing independently pinned original companion: $name" } }
# Verify every original companion/source record as well as the independently pinned stage ZIP.
$checksums = @{}
foreach ($line in Get-Content -LiteralPath (Join-Path $ArtifactDirectory 'SHA256SUMS.txt')) {
    if ($line -cnotmatch '^([a-f0-9]{64})  (.+)$') { throw 'Malformed original checksum record.' }
    $digest=$Matches[1];$name=$Matches[2]
    if ($checksums.Count -ge 10000 -or $name -match '(^|/)\.\.?(/|$)|[\\:\x00-\x1f]|^/|//' -or
        $name -ceq 'SHA256SUMS.txt' -or $checksums.ContainsKey($name)) { throw 'Unsafe or duplicate original checksum member.' }
    foreach ($segment in $name.Split('/')) {
        if ($segment -in @('', '.', '..') -or $segment.EndsWith('.') -or $segment.EndsWith(' ') -or
            $segment -match '[<>:"|?*]' -or $segment -match '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)') { throw 'Unsafe original checksum path component.' }
    }
    $path=FullPath (Join-Path $ArtifactDirectory $name)
    if (-not (Is-Below $path $ArtifactDirectory)) { throw 'A checksum path escapes the original artifact.' }
    Assert-NoReparseAncestor $path
    if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or (Hash $path) -cne $digest) { throw "Original artifact changed: $name" }
    $checksums[$name]=$digest
}
$artifactItems = @(Get-ChildItem -LiteralPath $ArtifactDirectory -Recurse -Force)
if ($artifactItems.Count -gt 20000) { throw 'Original artifact exceeds member bounds.' }
foreach ($item in $artifactItems) { if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Original artifact contains a reparse member.' } }
$actualFiles=@($artifactItems | Where-Object { -not $_.PSIsContainer })
if ($checksums.Count -lt 7 -or $actualFiles.Count -ne $checksums.Count+1) { throw 'Original artifact has incomplete/unhashed members.' }
foreach ($file in $actualFiles) {
    Assert-NoReparseAncestor $file.FullName
    $name=[IO.Path]::GetRelativePath($ArtifactDirectory,$file.FullName).Replace('\','/')
    if ($name -cne 'SHA256SUMS.txt' -and -not $checksums.ContainsKey($name)) { throw 'An original file lacks a checksum.' }
}
$manifest=Read-Json (Join-Path $ArtifactDirectory 'stage-manifest.json')
$state=Read-Json (Join-Path $ArtifactDirectory 'cadence-build.json')
$result=Read-Json (Join-Path $ArtifactDirectory 'cadence-build-result.json')
$expectedArchive=[string]$target.stage.archive
if ($expectedArchive -cne ('CadenceStudio-v4.7.6-combined-system-aac-stage-build-2008-attempt-{0}-x64.zip' -f $target.run_attempt)) { throw 'Actual archive name differs from the reviewed producer convention.' }
if ($manifest.schema_version -ne 1 -or $state.schema_version -ne 1 -or $result.schema_version -ne 1 -or $manifest.variant -cne 'Cadence' -or $state.variant -cne 'Cadence' -or
    $manifest.status -cne 'experimental-stage-before-qa' -or $manifest.original_source_commit -cne $target.source.original_commit -or
    $manifest.source_tree -cne $target.source.tree -or $manifest.source_commit -cne $target.source.ci_commit -or
    $state.source_commit -cne $target.source.ci_commit -or $result.source_commit -cne $target.source.ci_commit -or
    $state.source_dirty_at_configure -isnot [bool] -or $state.source_dirty_at_configure -ne $false -or
    $result.source_dirty_at_build -isnot [bool] -or $result.source_dirty_at_build -ne $false -or
    $manifest.build_number -ne 2008 -or $state.build_number -ne 2008 -or $manifest.run_number -ne $target.run_number -or $manifest.run_attempt -ne $target.run_attempt -or
    $manifest.upstream_commit -cne '96480d58445e3b24b230a3fe7d4725d639aa2eb3' -or $manifest.upstream_tag -cne 'v4.7.6' -or $manifest.qt_version -cne '6.10.2' -or $state.qt_version -cne '6.10.2' -or
    $manifest.windows_system_aac -isnot [bool] -or $manifest.windows_system_aac -ne $true -or
    $state.windows_system_aac -isnot [bool] -or $state.windows_system_aac -ne $true -or
    $state.open_source_zlib.pinned_ci_verified -isnot [bool] -or $state.open_source_zlib.pinned_ci_verified -ne $true -or
    $manifest.configuration -cne 'Release' -or $state.configuration -cne 'Release' -or
    $manifest.stage_archive -cne $expectedArchive -or $manifest.stage_archive_sha256 -cne $target.stage.archive_sha256 -or
    $checksums[$expectedArchive] -cne $target.stage.archive_sha256 -or
    $manifest.executable_sha256 -cne $target.stage.executable_sha256 -or $result.executable_sha256 -cne $target.stage.executable_sha256) {
    throw 'Original records do not match the independently reviewed actual2008 stage target.'
}
$archivePath = Join-Path $ArtifactDirectory $expectedArchive
Assert-NoReparseAncestor $archivePath
if ((Get-Item -LiteralPath $archivePath).Length -ne $target.stage.archive_bytes -or (Hash $archivePath) -cne $target.stage.archive_sha256) { throw 'Actual stage archive bytes/SHA-256 differ; extraction did not start.' }
$zip = [IO.Compression.ZipFile]::OpenRead($archivePath)
$members = [Collections.Generic.List[object]]::new()
try {
    if ($zip.Entries.Count -gt 100000) { throw 'Stage ZIP has too many members.' }
    $names = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    [long]$expandedBytes = 0; $hasExecutable = $false
    foreach ($entry in $zip.Entries) {
        $name = $entry.FullName.Replace('\', '/')
        while ($name.StartsWith('./')) { $name = $name.Substring(2) }
        if ($name -in @('', '.', '/')) { continue }
        $isDirectory = $name.EndsWith('/')
        $name = $name.TrimEnd('/')
        if ($name.StartsWith('/') -or $name -match '[<>:"|?*\x00-\x1f]' -or
            -not $names.Add($name) -or (($entry.ExternalAttributes -shr 16) -band 61440) -eq 40960 -or
            ($entry.ExternalAttributes -band 1024)) { throw 'Unsafe, linked or duplicate ZIP member.' }
        foreach ($segment in $name.Split('/')) {
            if ($segment -in @('', '.', '..') -or $segment.EndsWith('.') -or $segment.EndsWith(' ') -or
                $segment -match '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)') { throw 'Unsafe ZIP path component.' }
        }
        $destination = FullPath (Join-Path $StagePath $name)
        if (-not (Is-Below $destination $StagePath)) { throw 'ZIP path escapes the new stage.' }
        if ($entry.Length -lt 0 -or $entry.Length -gt 5368709120) { throw 'Stage ZIP entry exceeds extraction bounds.' }
        $expandedBytes += $entry.Length
        if ($expandedBytes -gt 5368709120 -or ($isDirectory -and $entry.Length -ne 0)) { throw 'Stage ZIP exceeds extraction bounds or has an invalid directory.' }
        if ($name -ceq 'bin/CadenceStudio4.exe' -and -not $isDirectory -and $entry.Length -gt 0) {
            if ($entry.Length -ne $target.stage.executable_bytes) { throw 'Actual executable length differs before extraction.' }
            $hasExecutable = $true
        }
        $members.Add([pscustomobject]@{ Entry = $entry; Destination = $destination; Directory = $isDirectory })
    }
    if (-not $hasExecutable) { throw 'Stage ZIP does not contain the actual Cadence executable.' }

    # All provenance and archive preflight checks precede these first writes.
    Assert-NoReparseAncestor $StagePath
    New-Item -ItemType Directory -Path $StagePath | Out-Null
    foreach ($member in $members) {
        Assert-NoReparseAncestor $member.Destination
        if ($member.Directory) { [void][IO.Directory]::CreateDirectory($member.Destination); continue }
        [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($member.Destination))
        $inputStream = $member.Entry.Open()
        try {
            $outputStream = [IO.File]::Open($member.Destination, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
            try {
                # Do not let a malformed compression stream exceed its reviewed
                # preflight length, even if ZIP metadata understates its bytes.
                [long]$written = 0
                $buffer = [byte[]]::new(65536)
                while ($written -lt $member.Entry.Length) {
                    $wanted = [int][Math]::Min([long]$buffer.Length, $member.Entry.Length - $written)
                    $count = $inputStream.Read($buffer, 0, $wanted)
                    if ($count -le 0) { throw 'Stage ZIP stream ended before its declared length.' }
                    $outputStream.Write($buffer, 0, $count); $written += $count
                }
                if ($inputStream.ReadByte() -ne -1) { throw 'Stage ZIP stream exceeds its declared length.' }
            } finally { $outputStream.Dispose() }
        } finally { $inputStream.Dispose() }
        if ((Get-Item -LiteralPath $member.Destination).Length -ne $member.Entry.Length) { throw 'Extracted member length differs from ZIP metadata.' }
    }
} finally { $zip.Dispose() }

$executable = Join-Path $StagePath 'bin/CadenceStudio4.exe'
if ((Get-Item -LiteralPath $executable).Length -ne $target.stage.executable_bytes -or (Hash $executable) -cne $target.stage.executable_sha256 -or (Hash $executable) -cne $manifest.executable_sha256) { throw 'Extracted executable SHA-256 mismatch; no stage program was executed.' }
foreach ($file in Get-ChildItem -LiteralPath $StagePath -Recurse -Force) {
    if ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Restored stage contains a reparse point.' }
}
$record = [ordered]@{
    schema_version=1;status='retained-actual2008-stage-restored-and-sha256-verified'
    producer_run_id=$target.producer_run_id;artifact_id=$target.artifact_id
    original_source_commit=$target.source.original_commit;source_commit=$target.source.ci_commit;source_tree=$target.source.tree
    build_number=2008;original_run_number=$target.run_number;original_run_attempt=$target.run_attempt
    stage_path=$StagePath;executable_path=$executable;executable_sha256=Hash $executable;executable_bytes=(Get-Item -LiteralPath $executable).Length
    stage_archive=$expectedArchive;stage_archive_sha256=Hash $archivePath;stage_archive_bytes=(Get-Item -LiteralPath $archivePath).Length
    target_sha256=Hash $TargetPath;source_json_sha256=$target.source.source_json_sha256;source_patch_sha256=$target.source.patch_sha256
    independently_pinned_companions_verified=$externalFiles.Count;original_artifact_files_verified=$checksums.Count;original_companion_sources_left_in_artifact=$true
    outer_artifact_digest_from_github_metadata=$target.artifact_digest_from_github_metadata
    raw_outer_archive_digest_verified_by_this_script=$false
    artifact_expires_utc=$target.artifact_expires_utc
    application_recompiled=$false;application_executed_by_restore=$false;gui_validated_by_restore=$false
    zip_members_preflighted=$members.Count;expanded_bytes=$expandedBytes;maximum_zip_members=100000;maximum_expanded_bytes=5368709120
    restored_utc=[DateTime]::UtcNow.ToString('o')
}
Assert-NoReparseAncestor $ResultPath
[void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($ResultPath))
$record|ConvertTo-Json -Depth 8|Set-Content -LiteralPath $ResultPath -Encoding utf8
Write-Host 'CADENCE_NEXT_GUI_STAGE_BEGIN'
Write-Host ($record|ConvertTo-Json -Depth 8 -Compress)
Write-Host 'CADENCE_NEXT_GUI_STAGE_END'
