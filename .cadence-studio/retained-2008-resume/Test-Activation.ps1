# SPDX-License-Identifier: GPL-3.0-only
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if (-not $IsWindows -or -not [Environment]::Is64BitProcess -or $env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted' -or $env:GITHUB_REPOSITORY -ne 'astrynome-byte/Music') { throw 'Hosted native Windows x64 context required' }
$target=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'target.json') -Raw -Encoding utf8 | ConvertFrom-Json
if ($target.schema_version -ne 1 -or $target.ready -ne $true -or $target.mode -ne 'qa-only-no-application-rebuild-no-MSI' -or $target.build_number -ne 2008 -or $target.source_original_commit -cne 'a2b7abaf045a8f3cb84ec2953d9e0e51b9e78903' -or $target.source_ci_commit -cne '95cebb22fe6cbde22919c94f2b480bd14c3eb8de' -or $target.source_tree -cne 'c5452043983a048ef0aeef085615af903de3f5b0' -or $target.executable_sha256 -cne '13cd4e6d2f408d2e64b187d4c3bff1188ff4192ac7b670d3a12373bbeb37f6cd') { throw 'Explicit reviewed exact original2008 QA-only target required' }
$manifestPath=Join-Path $PSScriptRoot 'helpers.manifest.json'
if ((Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $target.helpers_manifest_sha256) { throw 'Reviewed helper manifest changed' }
$manifest=Get-Content -LiteralPath $manifestPath -Raw -Encoding utf8 | ConvertFrom-Json
foreach ($row in $manifest.files) {
    if ($row.name -match '[/\\:]' -or $row.name -eq '..') { throw 'Only direct plain helper filenames allowed' }
    $file=Join-Path $PSScriptRoot $row.name
    if ((Get-Item -LiteralPath $file).Length -ne $row.bytes -or (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -cne $row.sha256) { throw "Reviewed helper changed: $($row.name)" }
}
Write-Host 'Exact immutable2008 stage QA-only activation authenticated; application build and MSI absent.'
