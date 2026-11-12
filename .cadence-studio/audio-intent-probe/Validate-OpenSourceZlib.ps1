# SPDX-License-Identifier: GPL-3.0-only
# Data validation shared by Configure and Read-CadenceBuildState. The public
# callers already require native Windows x64; this helper executes no payload.
function Get-OpenSourceZlibProfile {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string] $PackageRoot,
          [Parameter(Mandatory)][string] $LockPath,
          [switch] $RequirePinnedCi)
    $PackageRoot = [IO.Path]::GetFullPath($PackageRoot)
    if ($PackageRoot -match '[;\r\n"]') { throw 'Unsupported zlib package path.' }
    if (-not (Test-Path -LiteralPath $PackageRoot -PathType Container) -or ((Get-Item -LiteralPath $PackageRoot).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Missing or linked zlib package root.' }
    $rootPrefix = $PackageRoot.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    function ProfileFile([string] $Relative) {
        $file = [IO.Path]::GetFullPath((Join-Path $PackageRoot ($Relative -replace '/', [IO.Path]::DirectorySeparatorChar)))
        if (-not $file.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase) -or
            -not (Test-Path -LiteralPath $file -PathType Leaf) -or
            ((Get-Item -LiteralPath $file).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "Missing, linked or unsafe source-zlib package file: $Relative"
        }
        $parent = [IO.Path]::GetDirectoryName($file)
        while ($parent -ne $PackageRoot.TrimEnd('\', '/')) {
            if ((Get-Item -LiteralPath $parent).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Linked source-zlib directory: $Relative" }
            $parent = [IO.Path]::GetDirectoryName($parent)
        }
        $file
    }
    function ProfileHash([string] $Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
    $lock = Get-Content -LiteralPath $LockPath -Raw | ConvertFrom-Json
    $manifestFile = ProfileFile 'zlib-profile-manifest.json'
    $manifestHash = ProfileHash $manifestFile
    $m = Get-Content -LiteralPath $manifestFile -Raw | ConvertFrom-Json
    if ($lock.schema_version -ne 1 -or $m.schema_version -ne 1 -or $m.component -ne 'zlib' -or $m.version -ne $lock.version -or
        $m.upstream_commit -ne $lock.source_commit -or $m.archive_sha256 -ne $lock.source_archive_sha256 -or
        $m.status -ne 'component-tested-awaiting-Cadence-link-and-file-compatibility-tests' -or
        $m.target_platform -ne 'Windows x64' -or $m.linkage -ne 'static' -or $m.runtime -ne '/MD' -or $m.configuration -ne 'Release' -or
        -not $m.source_unchanged -or -not $m.upstream_tests_passed -or -not $m.installed_api_probe_passed -or $null -ne $m.error) {
        throw 'The zlib package is not a tested, unchanged Windows x64 /MD static source profile.'
    }
    if ((ProfileHash (ProfileFile 'sources/zlib-1.3.2.tar.gz')) -ne $lock.source_archive_sha256) { throw 'Original zlib source archive changed.' }
    $sumsFile = ProfileFile 'SHA256SUMS.txt'
    $sumsHash = ProfileHash $sumsFile
    $sums = @{}
    foreach ($line in Get-Content -LiteralPath $sumsFile) {
        if ($line -notmatch '^([0-9a-f]{64})  (.+)$') { throw 'Invalid zlib SHA256SUMS line.' }
        $digest = $Matches[1]; $relative = $Matches[2]
        if ($sums.ContainsKey($relative)) { throw 'Duplicate zlib SHA256SUMS path.' }
        if ((ProfileHash (ProfileFile $relative)) -ne $digest) { throw "Source-zlib checksum mismatch: $relative" }
        $sums[$relative] = $digest
    }
    if (-not $sums.ContainsKey('zlib-profile-manifest.json') -or $sums['zlib-profile-manifest.json'] -ne $manifestHash) { throw 'Native zlib manifest is not covered by its checksums.' }
    $actual = [ordered]@{}
    foreach ($relative in @('lib/zs.lib', 'include/zlib.h', 'include/zconf.h')) {
        $digest = ProfileHash (ProfileFile "stage/$relative")
        $property = $m.artifact_sha256.PSObject.Properties[$relative]
        if ($null -eq $property -or $property.Value -ne $digest -or $sums["stage/$relative"] -ne $digest) { throw "Source-zlib installed file changed: $relative" }
        if ($RequirePinnedCi -and $lock.ci.files_sha256.PSObject.Properties[$relative].Value -ne $digest) { throw "Source-zlib CI pin mismatch: $relative" }
        $actual[$relative] = $digest
    }
    if ((Get-Content -LiteralPath (ProfileFile 'stage/include/zlib.h') -Raw) -notmatch ('(?m)^#define ZLIB_VERSION "' + [regex]::Escape($lock.version) + '"')) { throw 'Unexpected source-zlib header version.' }
    if ((Get-Content -LiteralPath (ProfileFile 'stage/include/zconf.h') -Raw) -match '(?m)^\s*#\s*define\s+Z_PREFIX(?:\s|$)') { throw 'Symbol-prefixed zlib is incompatible with the archive engine.' }
    if ($RequirePinnedCi -and ($manifestHash -ne $lock.ci.manifest_sha256 -or $sumsHash -ne $lock.ci.checksum_file_sha256 -or
        [string]$m.ci_run_id -ne [string]$lock.ci.run_id)) { throw 'The source-zlib CI package does not match the qualified retained artifact.' }
    [pscustomobject][ordered]@{
        package_root = $PackageRoot; prefix = (Join-Path $PackageRoot 'stage')
        manifest_sha256 = $manifestHash; checksum_file_sha256 = $sumsHash
        files_sha256 = [pscustomobject]$actual; source_archive_sha256 = $m.archive_sha256; source_commit = $m.upstream_commit
        producer_run_id = $(if ($m.PSObject.Properties['ci_run_id']) { $m.ci_run_id } else { $null }); pinned_ci_verified = [bool]$RequirePinnedCi
        fingerprint = ($manifestHash + ':' + ($actual.Values -join ':') + ':' + $sumsHash)
    }
}
