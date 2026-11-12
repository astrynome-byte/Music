# SPDX-License-Identifier: GPL-3.0-only
# Restore the five unchanged local driver binaries; no network or credentials.
#Requires -Version 7.0
[CmdletBinding()]
param([Parameter(Mandatory)][string] $Root)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$chunkBytes = 65520
$maxPartBytes = 87360
$expected = @{
    'changes.patch.gz' = @{ bytes = 5228780L; sha256 = 'c7654d9a8fa18adf9bcce0b6198c1ef907a2e5886a19339a08ed8ccb80f7b70d' }
    'audio-transcription/fixtures/cello-ensemble.wav' = @{ bytes = 1411244L; sha256 = '305e5fdf924535fcfd0f3d04ae83b28a3a9307f0872ddae6cb0af17310899519' }
    'audio-transcription/fixtures/cello-ensemble.expected.mid' = @{ bytes = 148L; sha256 = '824ecc0d3b9b41dc84249c4ebed11b61c2f2a2ce327ad38f9847fc1d442cad5b' }
    'audio-transcription/fixtures/trumpet-vibrato.wav' = @{ bytes = 1411244L; sha256 = 'f005adb920ffa11638162d9051c0acaa389005513f01b31640393ec85b9d9c58' }
    'audio-transcription/fixtures/trumpet-vibrato.expected.mid' = @{ bytes = 148L; sha256 = '7ccb3071eb514282def53c653bfa7fea85d7e5edd317a92ee2ef67cb66e7db6f' }
}

function Get-AttributesOrNull([string] $Path) {
    try { return [IO.File]::GetAttributes($Path) }
    catch [IO.FileNotFoundException] { return $null }
    catch [IO.DirectoryNotFoundException] { return $null }
}
function Assert-NoLinks([string] $Path) {
    $current = $Path
    while ($current) {
        $attributes = Get-AttributesOrNull $current
        if ($null -ne $attributes -and ($attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "Linked/reparse path is forbidden: $current"
        }
        $parent = [IO.Path]::GetDirectoryName($current)
        if ($parent -eq $current) { break }
        $current = $parent
    }
}
function Assert-Fields($Value, [string[]] $Names, [string] $Label) {
    if ($null -eq $Value -or $Value -isnot [Collections.IDictionary] -or $Value.Count -ne $Names.Count) {
        throw "Invalid $Label fields."
    }
    foreach ($name in $Names) {
        if (-not $Value.Contains($name)) { throw "Missing $Label field: $name" }
    }
}
function Assert-Integer($Value, [long] $Minimum, [long] $Maximum, [string] $Label) {
    if (($Value -isnot [long] -and $Value -isnot [int]) -or $Value -lt $Minimum -or $Value -gt $Maximum) {
        throw "Invalid bounded integer: $Label"
    }
}
function Resolve-Relative([object] $Value) {
    if ($Value -isnot [string] -or [string]::IsNullOrWhiteSpace($Value) -or
        $Value -match '[\\<>:"|?*\x00-\x20]' -or [IO.Path]::IsPathRooted($Value)) {
        throw 'Only safe relative paths with forward slashes are allowed.'
    }
    foreach ($segment in $Value.Split('/')) {
        if ($segment -in @('', '.', '..') -or $segment.EndsWith('.') -or
            $segment -match '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)') {
            throw "Unsafe relative path: $Value"
        }
    }
    $full = [IO.Path]::GetFullPath([IO.Path]::Combine($Root, $Value))
    if (-not $full.StartsWith($rootPrefix, $pathComparison)) { throw 'Path escapes Root.' }
    Assert-NoLinks $full
    return $full
}
function Assert-RegularFile([string] $Path) {
    Assert-NoLinks $Path
    $attributes = Get-AttributesOrNull $Path
    if ($null -eq $attributes -or ($attributes -band [IO.FileAttributes]::Directory)) {
        throw "An ordinary input file is required: $Path"
    }
}
function Get-Sha256([string] $Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}
function Assert-FileDigest([string] $Path, [long] $Bytes, [string] $Sha256) {
    Assert-RegularFile $Path
    if ((Get-Item -LiteralPath $Path -Force).Length -ne $Bytes -or (Get-Sha256 $Path) -cne $Sha256) {
        throw "Binary length/SHA-256 mismatch: $Path"
    }
}

if ([string]::IsNullOrWhiteSpace($Root) -or $Root.StartsWith('\\') -or $Root.StartsWith('//') -or
    -not [IO.Path]::IsPathFullyQualified($Root) -or
    $Root -match '[\x00-\x1f]' -or '..' -in ($Root -split '[/\\]')) {
    throw 'Root must be an explicit absolute local directory without parent traversal.'
}
$Root = [IO.Path]::GetFullPath($Root)
Assert-NoLinks $Root
$rootAttributes = Get-AttributesOrNull $Root
if ($null -eq $rootAttributes -or -not ($rootAttributes -band [IO.FileAttributes]::Directory)) {
    throw 'Root must already exist as an ordinary directory.'
}
$rootPrefix = $Root.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
$pathComparison = if ($IsWindows) { [StringComparison]::OrdinalIgnoreCase } else { [StringComparison]::Ordinal }
$manifestPath = Resolve-Relative 'binary-parts.json'
Assert-RegularFile $manifestPath
if ((Get-Item -LiteralPath $manifestPath -Force).Length -gt 1048576) { throw 'Manifest exceeds the 1 MiB bound.' }
$manifest = [IO.File]::ReadAllText($manifestPath, [Text.UTF8Encoding]::new($false, $true)) | ConvertFrom-Json -AsHashtable
Assert-Fields $manifest @('schema_version', 'entries') 'manifest'
Assert-Integer $manifest.schema_version 1 1 'schema_version'
if ($manifest.entries -isnot [array] -or $manifest.entries.Count -ne $expected.Count) {
    throw 'Manifest must describe exactly the five pinned driver binaries.'
}

# Validate every destination and the full input plan before creating anything.
$entries = [Collections.Generic.List[object]]::new()
$destinations = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$partPaths = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($entry in $manifest.entries) {
    Assert-Fields $entry @('path', 'bytes', 'sha256', 'parts') 'entry'
    $destination = Resolve-Relative $entry.path
    if ($entry.path -cnotin @($expected.Keys) -or -not $destinations.Add($entry.path)) {
        throw 'Unexpected or duplicate binary destination.'
    }
    $pin = $expected[$entry.path]
    Assert-Integer $entry.bytes $pin.bytes $pin.bytes 'entry.bytes'
    if ($entry.sha256 -isnot [string] -or $entry.sha256 -cne $pin.sha256) { throw 'Binary SHA-256 differs from the pinned original.' }
    if ($null -ne (Get-AttributesOrNull $destination)) { throw "Output already exists; refusing replacement: $($entry.path)" }
    $requiredParts = [int][Math]::Ceiling($entry.bytes / [double]$chunkBytes)
    if ($entry.parts -isnot [array] -or $entry.parts.Count -ne $requiredParts) { throw 'Invalid bounded part count.' }
    $parts = [Collections.Generic.List[object]]::new()
    for ($index = 0; $index -lt $entry.parts.Count; $index++) {
        $part = $entry.parts[$index]
        Assert-Fields $part @('path', 'bytes', 'sha256') 'part'
        $partPath = Resolve-Relative $part.path
        if (-not $part.path.StartsWith('binary-parts/', [StringComparison]::Ordinal) -or
            -not $part.path.EndsWith('.b64', [StringComparison]::Ordinal) -or -not $partPaths.Add($part.path)) {
            throw 'Part paths must be unique .b64 files below binary-parts/.'
        }
        $rawBytes = [Math]::Min($chunkBytes, $entry.bytes - ([long]$index * $chunkBytes))
        $textBytes = [long](4 * [Math]::Ceiling($rawBytes / 3.0))
        Assert-Integer $part.bytes $textBytes $textBytes 'part.bytes'
        if ($part.bytes -gt $maxPartBytes -or $part.sha256 -isnot [string] -or $part.sha256 -cnotmatch '^[a-f0-9]{64}$') {
            throw 'Invalid bounded part size or SHA-256.'
        }
        Assert-RegularFile $partPath
        if ((Get-Item -LiteralPath $partPath -Force).Length -ne $part.bytes) { throw "Part text length mismatch: $($part.path)" }
        $parts.Add(@{ path = $partPath; bytes = $part.bytes; sha256 = $part.sha256; raw_bytes = $rawBytes })
    }
    $entries.Add(@{ relative = $entry.path; destination = $destination; bytes = $entry.bytes; sha256 = $entry.sha256; parts = $parts })
}

$staging = $null
$completed = $false
$moved = [Collections.Generic.List[object]]::new()
try {
    $staging = Join-Path $Root ('.restore-binaries-' + [Guid]::NewGuid().ToString('N') + '.tmp')
    # New-Item without -Force and CreateNew never replace an existing object.
    New-Item -ItemType Directory -Path $staging | Out-Null
    for ($index = 0; $index -lt $entries.Count; $index++) {
        $entry = $entries[$index]
        $temporary = Join-Path $staging "$index.bin"
        $entry.temporary = $temporary
        $output = [IO.File]::Open($temporary, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        try {
            foreach ($part in $entry.parts) {
                Assert-RegularFile $part.path
                $input = [IO.File]::Open($part.path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
                try {
                    if ($input.Length -ne $part.bytes) { throw 'Part length changed after preflight.' }
                    $buffer = [byte[]]::new([int]$part.bytes)
                    $offset = 0
                    while ($offset -lt $buffer.Length) {
                        $read = $input.Read($buffer, $offset, $buffer.Length - $offset)
                        if ($read -eq 0) { throw 'Truncated part text.' }
                        $offset += $read
                    }
                    if ($input.ReadByte() -ne -1) { throw 'Part grew after preflight.' }
                } finally { $input.Dispose() }
                $hasher = [Security.Cryptography.SHA256]::Create()
                try { $digest = [BitConverter]::ToString($hasher.ComputeHash($buffer)).Replace('-', '').ToLowerInvariant() }
                finally { $hasher.Dispose() }
                if ($digest -cne $part.sha256) { throw "Part text SHA-256 mismatch: $($part.path)" }
                foreach ($value in $buffer) { if ($value -gt 127) { throw 'Part text must be ASCII base64.' } }
                $text = [Text.Encoding]::ASCII.GetString($buffer)
                if ($text -cnotmatch '^[A-Za-z0-9+/]+={0,2}$') { throw 'Part must be one canonical base64 block without whitespace.' }
                $decoded = [Convert]::FromBase64String($text)
                if ($decoded.Length -ne $part.raw_bytes -or $decoded.Length -gt $chunkBytes -or
                    [Convert]::ToBase64String($decoded) -cne $text) { throw 'Non-canonical or incorrectly bounded decoded part.' }
                $output.Write($decoded, 0, $decoded.Length)
                if ($output.Length -gt $entry.bytes) { throw 'Decoded binary exceeds its bound.' }
            }
            $output.Flush($true)
        } finally { $output.Dispose() }
        Assert-FileDigest $temporary $entry.bytes $entry.sha256
    }
    # No final file is written until all five staged binaries are authenticated.
    foreach ($entry in $entries) {
        Assert-NoLinks $entry.destination
        if ($null -ne (Get-AttributesOrNull $entry.destination)) { throw 'Output appeared during restoration; refusing replacement.' }
    }
    foreach ($entry in $entries) {
        $parent = [IO.Path]::GetDirectoryName($entry.destination)
        Assert-NoLinks $parent
        [void][IO.Directory]::CreateDirectory($parent)
        Assert-NoLinks $entry.destination
        [IO.File]::Move($entry.temporary, $entry.destination, $false)
        $moved.Add($entry)
        Assert-FileDigest $entry.destination $entry.bytes $entry.sha256
    }
    $completed = $true
} finally {
    try {
        if (-not $completed) {
            foreach ($entry in $moved) {
                # Roll back only an unchanged file created by this invocation.
                Assert-NoLinks $entry.destination
                if ([IO.File]::Exists($entry.destination) -and
                    (Get-Item -LiteralPath $entry.destination -Force).Length -eq $entry.bytes -and
                    (Get-Sha256 $entry.destination) -ceq $entry.sha256) { [IO.File]::Delete($entry.destination) }
            }
        }
    } finally {
        # Still attempt staging cleanup if rollback itself encounters an I/O error.
        if ($staging -and [IO.Directory]::Exists($staging)) {
            Assert-NoLinks $staging
            [IO.Directory]::Delete($staging, $true)
        }
    }
}
foreach ($entry in $entries) { Write-Host "Verified $($entry.relative): $($entry.bytes) bytes; SHA-256 $($entry.sha256)" }
Write-Host 'PASS: all five original driver binaries restored locally without replacement.'
