# SPDX-License-Identifier: GPL-3.0-only
# Reconstruct the exact source tree without storing a second application in the driver repository.
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $DriverPath,
    [Parameter(Mandatory)][string] $SourcePath,
    [Parameter(Mandatory)][string] $ResultPath
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Invoke-GitChecked([string[]] $Arguments) {
    & git @Arguments | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Git failed with exit status $LASTEXITCODE." }
}
function Get-GitText([string[]] $Arguments) {
    $value = & git @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Git failed with exit status $LASTEXITCODE." }
    ($value -join "`n").Trim()
}

# Only bounded path/EOL/hash metadata is printed if the exact checkout is dirty.
# No file contents, automatic renormalization or forced checkout is used here.
function Get-GitDiagnosticText([string[]] $Arguments) {
    $value = & git @Arguments 2>$null
    $code = $LASTEXITCODE
    $joined = ($value -join "`n").Trim()
    if ($joined.Length -gt 4096) { $joined = $joined.Substring(0,4096) + '[metadata truncated]' }
    return [ordered]@{ exit_code=$code; text=$joined }
}
function Write-DirtySourceDiagnostic([string] $Root, [string] $Porcelain) {
    $document=[ordered]@{schema_version=1;scope='Source checkout metadata only; no application compilation or file contents'
        maximum_paths=50;paths=@();configs=@();original_tree=$metadata.source.tree;automatic_recovery_attempted=$false;diagnostic_error=$null}
    try {
        foreach ($key in @('core.autocrlf','core.eol','core.safecrlf','core.filemode','core.symlinks','core.ignorecase')) {
            $document.configs += [ordered]@{key=$key;record=Get-GitDiagnosticText @('-C',$Root,'config','--show-origin','--get-all',$key)}
        }
        $entries=@($Porcelain.Split([char]0)|Where-Object { $_ })
        $document.porcelain_entries=$entries.Count
        $prefix=[IO.Path]::GetFullPath($Root).TrimEnd('\','/')+[IO.Path]::DirectorySeparatorChar
        for ($i=0;$i -lt $entries.Count -and $document.paths.Count -lt 50;$i++) {
            $entry=$entries[$i]
            if ($entry.Length -lt 4) { throw 'Invalid porcelain record.' }
            $kind=$entry.Substring(0,2);$relative=$entry.Substring(3)
            if ($kind -match 'R|C') { $i++ }
            if ($relative.Length -gt 1024) { throw 'Dirty path exceeds the bounded diagnostic size.' }
            $full=[IO.Path]::GetFullPath((Join-Path $Root $relative))
            if (-not $full.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)) { throw 'Diagnostic path escapes the source checkout.' }
            $plain=$true;$current=$full
            while ($current -and $current.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)) {
                if ((Test-Path -LiteralPath $current) -and ((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { $plain=$false;break }
                $current=[IO.Path]::GetDirectoryName($current)
            }
            $record=[ordered]@{status=$kind;path=$relative;index=Get-GitDiagnosticText @('-C',$Root,'rev-parse',(':'+$relative))
                eol=Get-GitDiagnosticText @('-C',$Root,'ls-files','--eol','--',$relative)
                attributes=Get-GitDiagnosticText @('-C',$Root,'check-attr','text','eol','filter','ident','--',$relative)
                working_bytes=$null;working_raw_blob=$null;working_sha256=$null;plain_path=$plain;file_contents_printed=$false}
            if ($plain -and (Test-Path -LiteralPath $full -PathType Leaf)) {
                $item=Get-Item -LiteralPath $full;$record.working_bytes=$item.Length
                if ($item.Length -le 16777216) {
                    $record.working_raw_blob=Get-GitDiagnosticText @('-C',$Root,'hash-object','--no-filters','--',$full)
                    $record.working_sha256=(Get-FileHash -LiteralPath $full -Algorithm SHA256).Hash.ToLowerInvariant()
                }
            }
            $document.paths += $record
        }
        $document.reported_paths=$document.paths.Count
    } catch { $document.diagnostic_error=$_.Exception.Message }
    Write-Host 'CADENCE_DIRTY_SOURCE_METADATA_BEGIN'
    Write-Host ($document|ConvertTo-Json -Depth 12 -Compress)
    Write-Host 'CADENCE_DIRTY_SOURCE_METADATA_END'
}

$DriverPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($DriverPath)
$SourcePath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($SourcePath)
$ResultPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($ResultPath)
if (Test-Path -LiteralPath $SourcePath) { throw 'SourcePath already exists. Bootstrap never deletes or replaces an existing checkout.' }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Git is required.' }
$metadata = Get-Content -LiteralPath (Join-Path $DriverPath 'source.json') -Raw | ConvertFrom-Json
if ($metadata.schema_version -ne 1) { throw 'Unsupported source.json schema_version.' }
if ($metadata.upstream.repository -ne 'https://github.com/musescore/MuseScore.git' -or
    $metadata.upstream.tag -ne 'v4.7.6' -or
    $metadata.upstream.commit -ne '96480d58445e3b24b230a3fe7d4725d639aa2eb3') {
    throw 'This driver is restricted to the audited MuseScore v4.7.6 upstream reference.'
}
if ($metadata.source.commit -notmatch '^[a-f0-9]{40}$' -or $metadata.source.tree -notmatch '^[a-f0-9]{40}$') {
    throw 'Source commit and tree must be full Git SHA-1 identifiers.'
}
if ($metadata.patch.file -ne 'changes.patch.gz' -or $metadata.patch.sha256 -notmatch '^[a-f0-9]{64}$') {
    throw 'Expected changes.patch.gz with a full lowercase SHA-256.'
}
$compressedPatch = Join-Path $DriverPath $metadata.patch.file
$actualHash = (Get-FileHash -LiteralPath $compressedPatch -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne $metadata.patch.sha256) { throw 'Compressed patch SHA-256 mismatch; source reconstruction aborted before Git operations.' }

# Only decompress local data after verifying its transport hash. The Git tree check below
# independently verifies all restored files, deletions and file modes.
$temporaryPatch = Join-Path ([IO.Path]::GetTempPath()) ('cadence-ci-' + [guid]::NewGuid() + '.patch')
$inputStream = $null; $gzipStream = $null; $outputStream = $null
try {
    try {
        $inputStream = [IO.File]::OpenRead($compressedPatch)
        $gzipStream = [IO.Compression.GZipStream]::new($inputStream, [IO.Compression.CompressionMode]::Decompress)
        $outputStream = [IO.File]::Create($temporaryPatch)
        $buffer = [byte[]]::new(65536)
        [long] $expandedSize = 0
        while (($bytesRead = $gzipStream.Read($buffer, 0, $buffer.Length)) -gt 0) {
            $expandedSize += $bytesRead
            if ($expandedSize -gt 536870912) { throw 'Expanded patch exceeds the 512 MiB limit.' }
            $outputStream.Write($buffer, 0, $bytesRead)
        }
    } finally {
        if ($outputStream) { $outputStream.Dispose() }
        if ($gzipStream) { $gzipStream.Dispose() }
        if ($inputStream) { $inputStream.Dispose() }
    }
    if ((Get-Item -LiteralPath $temporaryPatch).Length -eq 0) { throw 'Empty source patch.' }
    Invoke-GitChecked @('clone', '--depth', '1', '--no-checkout', '--branch', $metadata.upstream.tag,
        '--origin', 'upstream', $metadata.upstream.repository, $SourcePath)
    if ((Get-GitText @('-C', $SourcePath, 'rev-parse', 'HEAD')) -ne $metadata.upstream.commit) {
        throw 'The upstream tag no longer resolves to the audited commit.'
    }
    # Repository-local setting only. Keep checkout and patch application independent of
    # the runner's global core.autocrlf preference, and preserve exact source bytes.
    Invoke-GitChecked @('-C', $SourcePath, 'config', '--local', 'core.autocrlf', 'false')
    Invoke-GitChecked @('-C', $SourcePath, 'config', '--local', 'core.eol', 'lf')
    Invoke-GitChecked @('-C', $SourcePath, 'checkout', '--detach', $metadata.upstream.commit)
    Invoke-GitChecked @('-C', $SourcePath, 'apply', '--index', '--binary', $temporaryPatch)
    $restoredTree = Get-GitText @('-C', $SourcePath, 'write-tree')
    if ($restoredTree -ne $metadata.source.tree) { throw "Restored source tree mismatch: expected $($metadata.source.tree), got $restoredTree." }
    Invoke-GitChecked @('-C', $SourcePath, '-c', 'user.name=Cadence CI', '-c', 'user.email=cadence-ci@example.invalid',
        '-c', 'commit.gpgsign=false', 'commit', '-m', "Restore Cadence Studio source tree $($metadata.source.commit) for Windows CI")
    Invoke-GitChecked @('-C', $SourcePath, 'submodule', 'update', '--init', '--recursive')
    $sourcePorcelain=Get-GitText @('-C', $SourcePath, 'status', '--porcelain=v1', '--untracked-files=all', '-z')
    if ($sourcePorcelain) {
        Write-DirtySourceDiagnostic $SourcePath $sourcePorcelain
        throw 'Reconstructed source worktree is not clean; bounded metadata was printed without changing the checkout.'
    }
    $ciCommit = Get-GitText @('-C', $SourcePath, 'rev-parse', 'HEAD')
    $result = [ordered]@{
        schema_version = 1; original_source_commit = $metadata.source.commit
        source_tree = $restoredTree; ci_source_commit = $ciCommit
        upstream_tag = $metadata.upstream.tag; upstream_commit = $metadata.upstream.commit
        compressed_patch_sha256 = $actualHash; source_path = $SourcePath
        reconstructed_utc = [DateTime]::UtcNow.ToString('o'); windows_build_validated = $false
    }
    $result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $ResultPath -Encoding UTF8
    Write-Host "Exact Cadence source tree restored: $restoredTree (CI commit $ciCommit)."
    Write-Host 'No application compilation, installation or musical validation has happened in this step.'
} finally {
    if (Test-Path -LiteralPath $temporaryPatch) { Remove-Item -LiteralPath $temporaryPatch -Force }
}
