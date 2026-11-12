# SPDX-License-Identifier: GPL-3.0-only
# Run real local restoration and refusal tests against the unchanged originals.
#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $DriverRoot,
    [Parameter(Mandatory)][string] $OriginalManifest,
    [string] $Loader = (Join-Path $PSScriptRoot 'Restore-Binaries.ps1')
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert($Condition, [string] $Message) { if (-not $Condition) { throw $Message } }
function Hash([string] $Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Read-Manifest([string] $Case) { [IO.File]::ReadAllText((Join-Path $Case 'binary-parts.json')) | ConvertFrom-Json -AsHashtable }
function Write-Manifest([string] $Case, $Manifest) {
    [IO.File]::WriteAllText((Join-Path $Case 'binary-parts.json'), ($Manifest | ConvertTo-Json -Depth 12), [Text.UTF8Encoding]::new($false))
}
function New-Case([string] $Name) {
    $case = Join-Path $testRoot $Name
    [void][IO.Directory]::CreateDirectory($case)
    Copy-Item -LiteralPath (Join-Path $DriverRoot 'binary-parts.json') -Destination $case
    Copy-Item -LiteralPath (Join-Path $DriverRoot 'binary-parts') -Destination $case -Recurse
    return $case
}
function Snapshot([string] $Case) {
    $rows = @(foreach ($item in Get-ChildItem -LiteralPath $Case -Recurse -Force | Sort-Object FullName) {
        $relative = [IO.Path]::GetRelativePath($Case, $item.FullName)
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { "$relative|link|$($item.LinkTarget)" }
        elseif ($item.PSIsContainer) { "$relative|directory" }
        else { "$relative|$($item.Length)|$(Hash $item.FullName)" }
    })
    return ($rows -join "`n")
}
function Reject([string] $Name, [scriptblock] $Mutate) {
    $case = New-Case $Name
    try {
        & $Mutate $case
        $before = Snapshot $case
        $message = $null
        try { & $Loader -Root $case } catch { $message = $_.Exception.Message }
        Assert ($null -ne $message) "Expected rejection: $Name"
        Assert ((Snapshot $case) -ceq $before) "Rejected invocation altered the case: $Name"
        Assert (@(Get-ChildItem -LiteralPath $case -Filter '.restore-binaries-*.tmp' -Force).Count -eq 0) "Temporary staging leaked: $Name"
        $script:passed++
        Write-Host "PASS refusal/$Name : $message"
    } finally { [IO.Directory]::Delete($case, $true) }
}
function First-Part([string] $Case) { (Read-Manifest $Case).entries[0].parts[0].path }
function Change-Text([string] $Path) {
    $bytes = [IO.File]::ReadAllBytes($Path)
    $bytes[0] = if ($bytes[0] -eq [byte][char]'A') { [byte][char]'B' } else { [byte][char]'A' }
    [IO.File]::WriteAllBytes($Path, $bytes)
}

$DriverRoot = [IO.Path]::GetFullPath($DriverRoot)
$OriginalManifest = [IO.Path]::GetFullPath($OriginalManifest)
$Loader = [IO.Path]::GetFullPath($Loader)
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('cadence-restore-tests-' + [Guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($testRoot)
$passed = 0
try {
    $case = New-Case 'real-five-original-binaries'
    try {
        & $Loader -Root $case
        $manifest = Read-Manifest $case
        $originals = [IO.File]::ReadAllText($OriginalManifest) | ConvertFrom-Json -AsHashtable
        Assert ($manifest.entries.Count -eq 5 -and $originals.binary_entries.Count -eq 5) 'Expected exactly five originals.'
        foreach ($entry in $manifest.entries) {
            $original = @($originals.binary_entries | Where-Object { $_.path.EndsWith('/' + $entry.path, [StringComparison]::Ordinal) })
            Assert ($original.Count -eq 1) "Original path ambiguity: $($entry.path)"
            $restored = Join-Path $case $entry.path
            Assert ((Get-Item -LiteralPath $restored).Length -eq $original[0].bytes) 'Restored original size mismatch.'
            Assert ((Hash $restored) -ceq $original[0].sha256 -and (Hash $original[0].file) -ceq $entry.sha256) 'Restored original SHA-256 mismatch.'
            Assert ([Linq.Enumerable]::SequenceEqual([byte[]][IO.File]::ReadAllBytes($restored), [byte[]][IO.File]::ReadAllBytes($original[0].file))) 'Restored bytes differ from the original.'
        }
        Assert (@(Get-ChildItem -LiteralPath $case -Filter '.restore-binaries-*.tmp' -Force).Count -eq 0) 'Success leaked temporary staging.'
        $passed++
        Write-Host 'PASS real-five-original-binaries: exact byte comparisons and SHA-256 for all five.'
        $before = Snapshot $case
        $rejected = $false
        try { & $Loader -Root $case } catch { $rejected = $true }
        Assert $rejected 'A second restoration must reject existing outputs.'
        Assert ((Snapshot $case) -ceq $before) 'Second restoration altered existing files.'
        $passed++
        Write-Host 'PASS refusal/repeated-restoration: all original restored bytes preserved.'
    } finally { [IO.Directory]::Delete($case, $true) }

    Reject 'tampered-part-text' { param($case) Change-Text (Join-Path $case (First-Part $case)) }
    Reject 'tampered-part-with-updated-text-hash' {
        param($case)
        $manifest = Read-Manifest $case
        $path = Join-Path $case $manifest.entries[0].parts[0].path
        Change-Text $path
        $manifest.entries[0].parts[0].sha256 = Hash $path
        Write-Manifest $case $manifest
    }
    Reject 'truncated-part-text' {
        param($case)
        $path = Join-Path $case (First-Part $case)
        $bytes = [IO.File]::ReadAllBytes($path)
        [IO.File]::WriteAllBytes($path, $bytes[0..($bytes.Length - 2)])
    }
    Reject 'existing-last-output' {
        param($case)
        $manifest = Read-Manifest $case
        $path = Join-Path $case $manifest.entries[-1].path
        [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($path))
        [IO.File]::WriteAllText($path, 'existing sentinel that must never change')
    }
    Reject 'existing-output-directory' { param($case) [void][IO.Directory]::CreateDirectory((Join-Path $case 'changes.patch.gz')) }
    Reject 'absolute-output' {
        param($case) $manifest = Read-Manifest $case; $manifest.entries[0].path = Join-Path $testRoot 'outside-output'; Write-Manifest $case $manifest
    }
    Reject 'parent-output' {
        param($case) $manifest = Read-Manifest $case; $manifest.entries[0].path = '../outside-output'; Write-Manifest $case $manifest
    }
    Reject 'wrong-case-output' {
        param($case) $manifest = Read-Manifest $case; $manifest.entries[0].path = $manifest.entries[0].path.ToUpperInvariant(); Write-Manifest $case $manifest
    }
    Reject 'parent-part' {
        param($case) $manifest = Read-Manifest $case; $manifest.entries[0].parts[0].path = 'binary-parts/../binary-parts/escape.b64'; Write-Manifest $case $manifest
    }
    Reject 'absolute-part' {
        param($case) $manifest = Read-Manifest $case; $manifest.entries[0].parts[0].path = Join-Path $testRoot 'outside.b64'; Write-Manifest $case $manifest
    }
    Reject 'oversized-part-bound' {
        param($case) $manifest = Read-Manifest $case; $manifest.entries[0].parts[0].bytes = 1000000000; Write-Manifest $case $manifest
    }
    Reject 'non-ascii-base64' {
        param($case)
        $manifest = Read-Manifest $case; $path = Join-Path $case $manifest.entries[0].parts[0].path
        $bytes = [IO.File]::ReadAllBytes($path); $bytes[0] = 255; [IO.File]::WriteAllBytes($path, $bytes)
        $manifest.entries[0].parts[0].sha256 = Hash $path; Write-Manifest $case $manifest
    }
    Reject 'whitespace-base64' {
        param($case)
        $manifest = Read-Manifest $case; $path = Join-Path $case $manifest.entries[0].parts[0].path
        $bytes = [IO.File]::ReadAllBytes($path); $bytes[0] = 10; [IO.File]::WriteAllBytes($path, $bytes)
        $manifest.entries[0].parts[0].sha256 = Hash $path; Write-Manifest $case $manifest
    }
    if (-not $IsWindows) {
        Reject 'linked-part' {
            param($case)
            $relative = First-Part $case; $path = Join-Path $case $relative
            [IO.File]::Delete($path)
            New-Item -ItemType SymbolicLink -Path $path -Target (Join-Path $DriverRoot $relative) | Out-Null
        }
        Reject 'dangling-linked-part' {
            param($case)
            $path = Join-Path $case (First-Part $case); [IO.File]::Delete($path)
            New-Item -ItemType SymbolicLink -Path $path -Target (Join-Path $testRoot 'missing-target') | Out-Null
        }
        Reject 'linked-output-parent' {
            param($case)
            New-Item -ItemType SymbolicLink -Path (Join-Path $case 'audio-transcription') -Target $testRoot | Out-Null
        }
        Reject 'dangling-linked-output' {
            param($case)
            New-Item -ItemType SymbolicLink -Path (Join-Path $case 'changes.patch.gz') -Target (Join-Path $testRoot 'missing-target') | Out-Null
        }
    }
    Write-Host "PASS: $passed real PowerShell restoration/refusal tests; only disposable test copies were changed."
} finally {
    if ([IO.Directory]::Exists($testRoot)) { [IO.Directory]::Delete($testRoot, $true) }
}
