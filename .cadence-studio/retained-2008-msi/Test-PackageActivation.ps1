# SPDX-License-Identifier: GPL-3.0-only
#Requires -Version 7.2
[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if(-not[OperatingSystem]::IsWindows()-or-not[Environment]::Is64BitProcess-or
   $env:GITHUB_ACTIONS-cne'true'-or$env:RUNNER_ENVIRONMENT-cne'github-hosted'-or
   $env:GITHUB_REPOSITORY-cne'astrynome-byte/Music'){throw 'Disposable native Windows repository context required.'}
$target=Get-Content -LiteralPath "$PSScriptRoot/target.json" -Raw -Encoding utf8|ConvertFrom-Json
if($target.schema_version-ne1-or$target.ready-isnot[bool]-or$target.ready-cne$true-or$target.mode-cne'package-and-test-retained2008-no-application-rebuild'){
    throw 'MSI activation is inactive until real QA artifact pins have been reviewed.'
}
foreach($pair in @(@('helpers.manifest.json','helpers_manifest_sha256'),@('package-bindings.json','bindings_sha256'),@('qa-artifact.selection.json','qa_selection_sha256'))){
    $pin=[string]$target.($pair[1])
    if($pin-cnotmatch'^[a-f0-9]{64}$'-or(Get-FileHash -LiteralPath "$PSScriptRoot/$($pair[0])" -Algorithm SHA256).Hash.ToLowerInvariant()-cne$pin){throw 'Activation input bytes differ.'}
}
$manifest=Get-Content -LiteralPath "$PSScriptRoot/helpers.manifest.json" -Raw -Encoding utf8|ConvertFrom-Json
foreach($row in $manifest.files){
    $relative=[string]$row.name
    if(-not$relative-or$relative-match'(^|/)\.\.(/|$)|[\\:\x00-\x1f]' -or $relative.StartsWith('/')){throw 'Invalid helper manifest path.'}
    $path=Join-Path $PSScriptRoot $relative
    if((Get-Item -LiteralPath $path).Length-ne$row.bytes-or(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()-cne$row.sha256){throw 'Reviewed MSI helper bytes differ.'}
}
$selection=Get-Content -LiteralPath "$PSScriptRoot/qa-artifact.selection.json" -Raw -Encoding utf8|ConvertFrom-Json
$binding=Get-Content -LiteralPath "$PSScriptRoot/package-bindings.json" -Raw -Encoding utf8|ConvertFrom-Json
if($selection.ready-isnot[bool]-or$selection.ready-cne$true-or$binding.ready-isnot[bool]-or$binding.ready-cne$false-or$null-ne$binding.qualification_sha256){throw 'Activate acquisition only; bindings must await actual raw QA measurement.'}
Write-Host 'PASS reviewed retained2008 MSI activation; no application or installer executed.'
