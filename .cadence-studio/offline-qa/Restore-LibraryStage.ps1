# SPDX-License-Identifier: GPL-3.0-only
# Restore only the authenticated, already compiled local-library candidate.
#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $ArtifactDirectory,
    [Parameter(Mandatory)][string] $StagePath,
    [Parameter(Mandatory)][string] $ResultPath
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# This script performs no network access. actions/download-artifact retrieves the
# one pinned artifact with the workflow's short-lived GITHUB_TOKEN (actions:read).
if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitProcess -or
    $env:GITHUB_ACTIONS -ne 'true' -or $env:CI -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted') {
    throw 'Stage restoration is restricted to disposable native Windows x64 GitHub-hosted runners.'
}
if (-not $env:RUNNER_TEMP) { throw 'RUNNER_TEMP is required.' }
$expectedOriginalCommit = '76b51af495b721776945717a812e1de2394a689a'
$expectedTree = '59d63e6f93b3bb7e8e5291cf57f57f9c5d61a06b'
$expectedUpstreamCommit = '96480d58445e3b24b230a3fe7d4725d639aa2eb3'
$expectedPatchHash = '2b208e6d9ff98e7375c6518bc2222133b35a5619d80131d1a87b220d144f0e6f'
$expectedArchive = 'CadenceStudio-v4.7.6-library-stage-build-1001-attempt-1-x64.zip'

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
function Read-Json([string] $Path) { Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json }

$ArtifactDirectory = FullPath $ArtifactDirectory
$StagePath = FullPath $StagePath
$ResultPath = FullPath $ResultPath
$temporaryRoot = FullPath $env:RUNNER_TEMP
foreach ($path in @($ArtifactDirectory, $StagePath, $ResultPath)) {
    if (-not (Is-Below $path $temporaryRoot)) { throw 'All restoration paths must be strictly below RUNNER_TEMP.' }
    Assert-NoReparseAncestor $path
}
if (-not (Test-Path -LiteralPath $ArtifactDirectory -PathType Container)) { throw 'The downloaded artifact directory is missing.' }
if ((Test-Path -LiteralPath $StagePath) -or (Test-Path -LiteralPath $ResultPath)) { throw 'StagePath and ResultPath must be new; existing files are never replaced.' }
if ((Is-Below $StagePath $ArtifactDirectory) -or (Is-Below $ArtifactDirectory $StagePath) -or
    (Is-Below $ResultPath $ArtifactDirectory) -or (Is-Below $ResultPath $StagePath) -or
    (Is-Below $StagePath $ResultPath) -or $ResultPath -eq $StagePath) {
    throw 'Original artifact, extracted stage and result record must be separate.'
}

# Authenticate the same immutable source selection as the source Bootstrap. Do
# not reconstruct it, change source.json, or label the retained payload a rebuild.
$sourceRecordPath = FullPath (Join-Path $PSScriptRoot '../library-source/source.json')
$patchPath = FullPath (Join-Path $PSScriptRoot '../library-source/changes.patch.gz')
$sourceRecord = Read-Json $sourceRecordPath
if ($sourceRecord.schema_version -ne 1 -or $sourceRecord.source.commit -ne $expectedOriginalCommit -or
    $sourceRecord.source.tree -ne $expectedTree -or $sourceRecord.upstream.commit -ne $expectedUpstreamCommit -or
    $sourceRecord.upstream.tag -ne 'v4.7.6' -or
    $sourceRecord.upstream.repository -ne 'https://github.com/musescore/MuseScore.git' -or
    $sourceRecord.patch.file -ne 'changes.patch.gz' -or $sourceRecord.patch.sha256 -ne $expectedPatchHash -or
    (Hash $patchPath) -ne $expectedPatchHash) { throw 'Driver source provenance no longer matches the pinned library candidate.' }

$expectedRootNames = @('SHA256SUMS.txt', 'stage-manifest.json', 'cadence-build.json', 'cadence-build-result.json',
    'dependencies.lock.json', 'BUILD-COMMANDS.txt', 'archive.log', $expectedArchive)
$rootItems = @(Get-ChildItem -LiteralPath $ArtifactDirectory -Force)
if ($rootItems.Count -ne $expectedRootNames.Count) { throw 'The original artifact root file set is incomplete or unexpected.' }
foreach ($file in $rootItems) {
    if ($file.PSIsContainer -or ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $file.Name -cnotin $expectedRootNames) {
        throw 'The original artifact must contain only the expected ordinary root files.'
    }
}
$checksums = @{}
foreach ($line in Get-Content -LiteralPath (Join-Path $ArtifactDirectory 'SHA256SUMS.txt')) {
    if ($line -notmatch '^([a-fA-F0-9]{64})  (.+)$') { throw 'Malformed original SHA256SUMS line.' }
    $digest = $Matches[1].ToLowerInvariant(); $name = $Matches[2]
    if ($name -match '[/\\:]' -or $name -ceq 'SHA256SUMS.txt' -or $name -cnotin $expectedRootNames -or $checksums.ContainsKey($name)) {
        throw 'Unexpected or duplicate checksum member.'
    }
    if ((Hash (Join-Path $ArtifactDirectory $name)) -ne $digest) { throw "Original artifact hash mismatch: $name" }
    $checksums[$name] = $digest
}
if ($checksums.Count -ne $expectedRootNames.Count - 1) { throw 'Not every original artifact member has a checksum.' }

$manifest = Read-Json (Join-Path $ArtifactDirectory 'stage-manifest.json')
$state = Read-Json (Join-Path $ArtifactDirectory 'cadence-build.json')
$result = Read-Json (Join-Path $ArtifactDirectory 'cadence-build-result.json')
$lock = Read-Json (Join-Path $ArtifactDirectory 'dependencies.lock.json')
if ($manifest.schema_version -ne 1 -or $state.schema_version -ne 1 -or $result.schema_version -ne 1 -or
    $manifest.variant -ne 'Cadence' -or $state.variant -ne 'Cadence' -or
    $manifest.original_source_commit -ne $expectedOriginalCommit -or $manifest.source_tree -ne $expectedTree -or
    $manifest.source_commit -notmatch '^[a-f0-9]{40}$' -or $manifest.source_commit -ne $state.source_commit -or
    $manifest.source_commit -ne $result.source_commit -or
    $state.source_dirty_at_configure -ne $false -or $result.source_dirty_at_build -ne $false -or
    $manifest.configuration -ne 'Release' -or $state.configuration -ne 'Release' -or
    $manifest.build_number -ne 1001 -or $state.build_number -ne 1001 -or
    $manifest.run_number -ne 1 -or $manifest.run_attempt -ne 1 -or
    $manifest.upstream_tag -ne 'v4.7.6' -or $manifest.upstream_commit -ne $expectedUpstreamCommit -or
    $lock.upstream.commit -ne $expectedUpstreamCommit -or $lock.qt.version -ne '6.10.2' -or
    $manifest.qt_version -ne '6.10.2' -or $state.qt_version -ne '6.10.2' -or
    $manifest.stage_archive -cne $expectedArchive -or $manifest.stage_archive_sha256 -notmatch '^[a-f0-9]{64}$' -or
    $manifest.stage_archive_sha256 -ne $checksums[$expectedArchive] -or
    $manifest.executable_sha256 -notmatch '^[a-f0-9]{64}$' -or $result.executable_sha256 -ne $manifest.executable_sha256 -or
    [IO.Path]::GetFileName(([string]$result.executable -replace '\\', '/')) -cne 'CadenceStudio4.exe') {
    throw 'Original stage records do not describe the pinned clean Cadence library build 1001.'
}

$archivePath = Join-Path $ArtifactDirectory $expectedArchive
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
        $expandedBytes += $entry.Length
        if ($expandedBytes -gt 5368709120 -or ($isDirectory -and $entry.Length -ne 0)) { throw 'Stage ZIP exceeds extraction bounds or has an invalid directory.' }
        if ($name -ceq 'bin/CadenceStudio4.exe' -and -not $isDirectory -and $entry.Length -gt 0) { $hasExecutable = $true }
        $members.Add([pscustomobject]@{ Entry = $entry; Destination = $destination; Directory = $isDirectory })
    }
    if (-not $hasExecutable) { throw 'Stage ZIP does not contain the actual Cadence executable.' }

    # All provenance and archive preflight checks precede these first writes.
    New-Item -ItemType Directory -Path $StagePath | Out-Null
    foreach ($member in $members) {
        if ($member.Directory) { [void][IO.Directory]::CreateDirectory($member.Destination); continue }
        [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($member.Destination))
        $inputStream = $member.Entry.Open()
        try {
            $outputStream = [IO.File]::Open($member.Destination, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
            try { $inputStream.CopyTo($outputStream) } finally { $outputStream.Dispose() }
        } finally { $inputStream.Dispose() }
        if ((Get-Item -LiteralPath $member.Destination).Length -ne $member.Entry.Length) { throw 'Extracted member length differs from ZIP metadata.' }
    }
} finally { $zip.Dispose() }

$executable = Join-Path $StagePath 'bin/CadenceStudio4.exe'
if ((Hash $executable) -ne $manifest.executable_sha256) { throw 'Extracted executable SHA-256 mismatch; no stage program was executed.' }
foreach ($file in Get-ChildItem -LiteralPath $StagePath -Recurse -Force) {
    if ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Restored stage contains a reparse point.' }
}
$record = [ordered]@{
    schema_version = 1; status = 'retained-stage-restored-sha256-verified'
    repository = 'astrynome-byte/Music'; original_run_id = 42793810996; original_artifact_id = 13755702885
    original_source_commit = $expectedOriginalCommit; source_commit = $manifest.source_commit; source_tree = $expectedTree
    build_number = 1001; original_run_number = 1; original_run_attempt = 1
    stage_path = $StagePath; executable_path = $executable; executable_sha256 = Hash $executable
    original_stage_archive = $expectedArchive; original_stage_archive_sha256 = Hash $archivePath
    expected_outer_artifact_sha256 = '427ed2f9726dfd62c5c5c26b4942725f4b711a6a02f335cffe04802ba35c8166'
    expected_outer_artifact_bytes = 147534245; original_artifact_expires_utc = '2026-11-24T10:44:54Z'
    raw_outer_archive_digest_verified_by_this_script = $false
    download_transport = 'actions/download-artifact@v4; one pinned artifact-id/run-id with GITHUB_TOKEN actions:read'
    source_json_sha256 = Hash $sourceRecordPath; source_patch_sha256 = Hash $patchPath
    manifest_sha256 = $checksums['stage-manifest.json']; original_build_result_sha256 = $checksums['cadence-build-result.json']
    archive_digest_independently_hardcoded = $false
    provenance_scope = 'Pinned GitHub artifact id/run, unchanged Bootstrap source selection, original records and member SHA-256'
    application_recompiled = $false; application_executed_by_restore = $false; musical_editing_tested = $false
    restored_utc = [DateTime]::UtcNow.ToString('o')
}
[void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($ResultPath))
$record | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $ResultPath -Encoding utf8
Write-Host 'CADENCE_LIBRARY_ORIGINAL_STAGE_MANIFEST_BEGIN'
Write-Host (Get-Content -LiteralPath (Join-Path $ArtifactDirectory 'stage-manifest.json') -Raw)
Write-Host 'CADENCE_LIBRARY_ORIGINAL_STAGE_MANIFEST_END'
Write-Host 'CADENCE_LIBRARY_ORIGINAL_BUILD_RESULT_BEGIN'
Write-Host (Get-Content -LiteralPath (Join-Path $ArtifactDirectory 'cadence-build-result.json') -Raw)
Write-Host 'CADENCE_LIBRARY_ORIGINAL_BUILD_RESULT_END'
Write-Host "Verified nested stage archive SHA-256: $($record.original_stage_archive_sha256)"
Write-Host "Verified retained executable SHA-256: $($record.executable_sha256)"
Write-Host "PASS: retained library build 1001 restored and verified; no application program executed. Result: $ResultPath"
