# SPDX-License-Identifier: GPL-3.0-only
[CmdletBinding()]
param([switch]$ValidateOnly, [switch]$CleanupOnly)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (-not $IsWindows -or -not [Environment]::Is64BitProcess) { throw 'Windows x64 required.' }
if ($env:GITHUB_REPOSITORY -ne 'astrynome-byte/Music' -or
    $env:GITHUB_REF -ne 'refs/heads/cadence-studio/windows-build' -or
    $env:GITHUB_RUN_ID -notmatch '^\d{1,20}$' -or $env:GITHUB_RUN_ATTEMPT -notmatch '^\d{1,5}$' -or
    -not $env:RUNNER_TEMP) { throw 'Exact disposable GitHub driver environment required.' }
function Hash([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Require-Plain([string]$Path) {
    for ($part = [IO.Path]::GetFullPath($Path); $part; $part = [IO.Path]::GetDirectoryName($part)) {
        if ((Test-Path -LiteralPath $part) -and ((Get-Item -LiteralPath $part -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Reparse path refused.' }
        if ($part -eq [IO.Path]::GetPathRoot($part)) { break }
    }
}
$targetPath = Join-Path $PSScriptRoot 'target.json'
$target = Get-Content -LiteralPath $targetPath -Raw | ConvertFrom-Json
if ($target.schema_version -ne 1 -or $target.ready -ne $true -or
    $target.mode -ne 'public-MSI-administrative-extraction-and-runtime-comparison-only' -or
    $target.product_version -ne '4.7.6.2008' -or
    $target.msi_sha256 -ne 'a3f934273e2c2002cc035743974941082245655a7bbe4bc6d2540bb921e52a9e' -or
    $target.executable_sha256 -ne '13cd4e6d2f408d2e64b187d4c3bff1188ff4192ac7b670d3a12373bbeb37f6cd' -or
    $target.runtime_files -ne 2712 -or $target.notice_files -ne 338 -or
    $target.application_launch_requested -ne $false -or $target.build_requested -ne $false -or
    $target.helpers_manifest_sha256 -notmatch '^[a-f0-9]{64}$') { throw 'Reviewed exact MSI2008 QA activation required.' }
$manifestPath = Join-Path $PSScriptRoot 'helpers.manifest.json'
if ((Hash $manifestPath) -ne $target.helpers_manifest_sha256) { throw 'Helper manifest differs.' }
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
foreach ($row in $manifest.files) {
    if (($row.path -ne '.gitattributes' -and $row.path -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]*$') -or
        $row.sha256 -notmatch '^[a-f0-9]{64}$') { throw 'Unsafe manifest entry.' }
    $path = Join-Path $PSScriptRoot $row.path
    Require-Plain $path
    if ((Get-Item -LiteralPath $path).Length -ne $row.bytes -or (Hash $path) -ne $row.sha256) { throw "Helper differs: $($row.path)" }
}
$workflow = Join-Path $env:GITHUB_WORKSPACE 'driver/.github/workflows/cadence-recovered-msi-2008.yml'
if ((Hash $workflow) -ne (Hash (Join-Path $PSScriptRoot 'cadence-recovered-msi-2008.yml'))) { throw 'Active workflow differs from reviewed copy.' }
if ($ValidateOnly) { Write-Host 'Pinned MSI extraction/comparison QA activation verified; no download, installer or application executed.'; return }
$root = Join-Path $env:RUNNER_TEMP ("cadence-recovered-msi-2008-$($env:GITHUB_RUN_ID)-$($env:GITHUB_RUN_ATTEMPT)")
Require-Plain $root
$evidence = Join-Path $root 'evidence'
$working = Join-Path $root 'working'
$sentinel = Join-Path $root 'owner.json'
if ($CleanupOnly) {
    if (-not (Test-Path -LiteralPath $root)) { return }
    $owner = Get-Content -LiteralPath $sentinel -Raw | ConvertFrom-Json
    if ($owner.run_id -ne $env:GITHUB_RUN_ID -or $owner.run_attempt -ne $env:GITHUB_RUN_ATTEMPT) { throw 'Cleanup owner mismatch.' }
    $clean = [ordered]@{ schema_version = 1; run_id = $env:GITHUB_RUN_ID; temporary_runtime_removed = $false; application_launched_by_recipe = $false }
    if (Test-Path -LiteralPath $working) {
        foreach ($item in Get-ChildItem -LiteralPath $working -Recurse -Force) {
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked cleanup member refused.' }
        }
        Remove-Item -LiteralPath $working -Recurse -Force
    }
    $clean.temporary_runtime_removed = -not (Test-Path -LiteralPath $working)
    $clean | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $evidence 'cleanup.json') -Encoding utf8NoBOM
    Write-Host ('CADENCE_RECOVERED_MSI_CLEANUP ' + ($clean | ConvertTo-Json -Compress))
    return
}
if (Test-Path -LiteralPath $root) { throw 'Fresh recovery output required.' }
New-Item -ItemType Directory -Path $evidence, $working -Force | Out-Null
@{run_id=$env:GITHUB_RUN_ID;run_attempt=$env:GITHUB_RUN_ATTEMPT}|ConvertTo-Json|Set-Content -LiteralPath $sentinel -Encoding utf8NoBOM
$report = [ordered]@{
    schema_version=1; status='failed'; origin='public-MSI2008-administrative-extraction';
    github_run_id=$env:GITHUB_RUN_ID; github_run_attempt=$env:GITHUB_RUN_ATTEMPT;
    driver_commit=$env:GITHUB_SHA; product_version='4.7.6.2008';
    product_code='{CA4AC56B-9ED9-568F-9F5A-0D9475D4CC26}';
    upgrade_code='{319B992F-470A-465B-9A79-6B0CBFC7D6C7}';
    msi_sha256=$target.msi_sha256; download_anonymous_requested=$true; msi_bytes=$null;
    runtime_files_expected=2712; notice_files_expected=338; runtime_exact=$false;
    application_launch_requested=$false; compilation_requested=$false;
    product_install_requested=$false; sdk_install_requested=$false;
    original_stage_artifact_used=$false; original_producer_status_rewritten=$false;
    portable_qualified=$false; error=$null
}
$msi = Join-Path $working 'CadenceStudio-2008-public.msi'
$recovery = Join-Path $working 'recovery'
try {
    $url = 'https://github.com/astrynome-byte/Music/releases/download/cadence-studio/v4.7.6-cadence.2008-experimental.1/CadenceStudio-4.7.6-cadence.2008-x86_64.msi'
    # No Authorization, token, cookie session or credentials are supplied.
    Invoke-WebRequest -Uri $url -OutFile $msi -TimeoutSec 240 -MaximumRedirection 5 -UserAgent 'Cadence-public-MSI-runtime-QA'
    $report.msi_bytes = (Get-Item -LiteralPath $msi).Length
    if ($report.msi_bytes -ne 120979784 -or (Hash $msi) -ne $target.msi_sha256) { throw 'Anonymous MSI download differs from published fixed content.' }
    & (Join-Path $PSScriptRoot 'Recover-RuntimeFromMsi.ps1') -MsiPath $msi -InventoryPath (Join-Path $PSScriptRoot 'runtime-inventory.MEASURED.json') -OutputDirectory $recovery
    $comparison = Get-Content -LiteralPath (Join-Path $recovery 'recovered-runtime-comparison.json') -Raw | ConvertFrom-Json
    if ($comparison.exact_runtime_match -ne $true -or $comparison.actual_count -ne 2712 -or
        $comparison.notice_files_verified -ne 338 -or $comparison.local_icuuc_absent -ne $true -or
        $comparison.application_executed -ne $false) { throw 'Complete runtime, notices or ICU comparison did not pass.' }
    $report.runtime_exact = $true
    $report.status = 'passed-public-MSI2008-runtime-recovered-and-all2712-files-compared'
} catch {
    $report.error = $_.Exception.Message.Substring(0, [Math]::Min(1200, $_.Exception.Message.Length))
    throw
} finally {
    foreach ($name in @('recovered-runtime-comparison.json','administrative-extraction.log','msi-readonly-identity.json')) {
        $path = Join-Path $recovery $name
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            if ((Get-Item -LiteralPath $path).Length -le 8MB) { Copy-Item -LiteralPath $path -Destination (Join-Path $evidence $name) }
        }
    }
    $report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $evidence 'public-MSI-runtime-recovery.json') -Encoding utf8NoBOM
    Write-Host ('CADENCE_PUBLIC_MSI_RUNTIME_RECOVERY ' + ($report | ConvertTo-Json -Depth 10 -Compress))
    if (Test-Path -LiteralPath (Join-Path $evidence 'recovered-runtime-comparison.json')) {
        Write-Host ('CADENCE_PUBLIC_MSI_RUNTIME_COMPARISON ' + ((Get-Content -LiteralPath (Join-Path $evidence 'recovered-runtime-comparison.json') -Raw | ConvertFrom-Json) | ConvertTo-Json -Depth 10 -Compress))
    }
}
