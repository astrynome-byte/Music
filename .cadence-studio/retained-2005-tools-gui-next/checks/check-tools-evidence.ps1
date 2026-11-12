# SPDX-License-Identifier: GPL-3.0-only
# Actual pure functions only; all UI claims are synthetic, no app/COM/network.
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$helper=Join-Path $PSScriptRoot '../Read-ExerciseEvidence.ps1'
. $helper
$fixtureDirectory=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../fixtures'))
$work=Join-Path ([IO.Path]::GetTempPath()) ('cadence-tools-evidence-'+[guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($work)
$rows=[Collections.Generic.List[object]]::new()
$base=[ordered]@{schema_version=1;pid=1234;sounds_navigation_delivered=$true;sounds_page_control_observed=$true;generaluser_offer_control_observed=$true;generaluser_download_size_control_observed=$true;generaluser_license_control_observed=$true;generaluser_license_text_observed=$true;lessons_navigation_delivered=$true;offline_lessons_tab_observed=$true;offline_lesson_count_observed=8;lesson_open_requested=$true;lesson_editor_title_observed=$true;lesson_editor_title='pulsation - Cadence Studio';window_caption_before_exercise_open='Cadence Studio';lesson_editor_window_class='Qt6102QWindowIcon'}
function NativeCase([string]$Name,[bool]$Expected,[scriptblock]$Mutate){
    $native=$base|ConvertTo-Json|ConvertFrom-Json
    & $Mutate $native
    $accepted=$true;$errorText=$null
    try{[void](Test-ToolsNativeClaims $native 1234)}catch{$accepted=$false;$errorText=$_.Exception.Message}
    $passed=$accepted-eq$Expected
    $rows.Add([ordered]@{case=$Name;passed=$passed;accepted=$accepted;expected=$Expected;error=$errorText;synthetic_UI_claims_only=$true})
    if(-not$passed){throw ('Native evidence case failed: '+$Name)}
}
NativeCase 'synthetic-full-claims-accepted-data-only' $true {param($x)}
NativeCase 'metadata-without-GUI-claims-refused' $false {param($x)$x.lesson_open_requested=$false;$x.generaluser_license_text_observed=$false}
NativeCase 'wrong-owned-pid-refused' $false {param($x)$x.pid=1235}
NativeCase 'boolean-schema-refused' $false {param($x)$x.schema_version=$true}
NativeCase 'boolean-pid-refused' $false {param($x)$x.pid=$true}
NativeCase 'seven-lessons-refused' $false {param($x)$x.offline_lesson_count_observed=7}
NativeCase 'floating-count-refused' $false {param($x)$x.offline_lesson_count_observed=8.0}
NativeCase 'string-true-is-not-native-bool' $false {param($x)$x.generaluser_license_text_observed='true'}
NativeCase 'unchanged-caption-refused' $false {param($x)$x.window_caption_before_exercise_open=$x.lesson_editor_title}
NativeCase 'wrong-caption-refused' $false {param($x)$x.lesson_editor_title='Another score'}
NativeCase 'wrong-window-class-refused' $false {param($x)$x.lesson_editor_window_class='ConsoleWindowClass'}
function CopyCase([string]$Name,[bool]$Expected,$ExitCode,[scriptblock]$Mutate){
    $root=Join-Path $work $Name;[void][IO.Directory]::CreateDirectory($root)
    $copy=Join-Path $root ('pulsation-'+[guid]::NewGuid().ToString('D'));[void][IO.Directory]::CreateDirectory($copy)
    foreach($fixtureName in @('pulsation.musicxml','LICENSE-CC0.txt')){[IO.File]::Copy((Join-Path $fixtureDirectory $fixtureName),(Join-Path $copy $fixtureName),$false)}
    & $Mutate $root $copy
    $accepted=$true;$errorText=$null
    try{[void](Test-CopiedExerciseEvidence $root $fixtureDirectory $ExitCode)}catch{$accepted=$false;$errorText=$_.Exception.Message}
    $passed=$accepted-eq$Expected
    if($Name-like'exit-*-no-read'){$passed=$passed-and$errorText-like'No confirmed clean application exit;*'}
    $rows.Add([ordered]@{case=$Name;passed=$passed;accepted=$accepted;expected=$Expected;error=$errorText;only_owned_fixture_copies=$true})
    if(-not$passed){throw ('Exercise evidence case failed: '+$Name)}
}
CopyCase 'actual-CC0-bytes-in-controlled-synthetic-UUID' $true 0 {param($root,$copy)}
CopyCase 'int64-zero-exit-accepted' $true ([long]0) {param($root,$copy)}
CopyCase 'exit-null-no-read' $false $null {param($root,$copy)Remove-Item -LiteralPath $copy -Recurse -Force}
CopyCase 'exit-bool-no-read' $false $false {param($root,$copy)Remove-Item -LiteralPath $copy -Recurse -Force}
CopyCase 'exit-nonzero-no-read' $false 1 {param($root,$copy)Remove-Item -LiteralPath $copy -Recurse -Force}
CopyCase 'wrong-score-bytes-refused' $false 0 {param($root,$copy)[IO.File]::WriteAllText((Join-Path $copy 'pulsation.musicxml'),'different')}
CopyCase 'missing-license-refused' $false 0 {param($root,$copy)Remove-Item -LiteralPath (Join-Path $copy 'LICENSE-CC0.txt')}
CopyCase 'extra-copy-file-refused' $false 0 {param($root,$copy)[IO.File]::WriteAllText((Join-Path $copy 'unexpected.txt'),'owned data')}
CopyCase 'multiple-UUID-folders-refused' $false 0 {param($root,$copy)[void][IO.Directory]::CreateDirectory((Join-Path $root ('pulsation-'+[guid]::NewGuid().ToString('D'))))}
CopyCase 'non-UUID-folder-refused' $false 0 {param($root,$copy)Rename-Item -LiteralPath $copy -NewName 'pulsation-existing'}
CopyCase 'read-only-personal-score-refused' $false 0 {param($root,$copy)$file=Get-Item -LiteralPath (Join-Path $copy 'pulsation.musicxml');$file.Attributes=$file.Attributes-bor[IO.FileAttributes]::ReadOnly}
# This explicit test demonstrates the exit guard also precedes manifest reads.
$accepted=$true;$message=$null
try{[void](Test-CopiedExerciseEvidence (Join-Path $work 'never-created') (Join-Path $work 'missing-fixtures') $null)}catch{$accepted=$false;$message=$_.Exception.Message}
$passed= -not$accepted-and$message-like'No confirmed clean application exit;*'
$rows.Add([ordered]@{case='no-manifest-read-without-exit';passed=$passed;error=$message})
if(-not$passed){throw 'The confirmed-exit guard did not precede source/manifest access.'}
$closeBase=[ordered]@{schema_version=1;pid=1234;close_requested=$true;discard_control_observed=$false;discard_delivered=$false;owned_modal_observed=$false;app_exit_observed=$true;exit_code=0;initial_caption='pulsation - Cadence Studio';initial_window_class='Qt6102QWindowIcon'}
function CloseCase([string]$Name,[bool]$Expected,[scriptblock]$Mutate){
 $native=$closeBase|ConvertTo-Json|ConvertFrom-Json;& $Mutate $native;$accepted=$true;$message=$null
 try{[void](Test-OwnedExerciseCloseClaims $native 1234)}catch{$accepted=$false;$message=$_.Exception.Message}
 $passed=$accepted-eq$Expected;$rows.Add([ordered]@{case=$Name;passed=$passed;accepted=$accepted;expected=$Expected;error=$message;synthetic_UI_claims_only=$true})
 if(-not$passed){throw ('Owned-close data case failed: '+$Name)}
}
CloseCase 'synthetic-close-without-prompt-accepted-data-only' $true {param($x)}
CloseCase 'synthetic-exact-discard-and-exit-accepted-data-only' $true {param($x)$x.discard_control_observed=$true;$x.discard_delivered=$true;$x.owned_modal_observed=$true}
CloseCase 'discard-not-delivered-refused' $false {param($x)$x.discard_control_observed=$true}
CloseCase 'unknown-modal-without-discard-refused' $false {param($x)$x.owned_modal_observed=$true}
CloseCase 'close-boolean-zero-refused' $false {param($x)$x.exit_code=$false}
CloseCase 'close-string-pid-refused' $false {param($x)$x.pid='1234'}
CloseCase 'close-wrong-pid-refused' $false {param($x)$x.pid=1235}
CloseCase 'close-wrong-initial-caption-refused' $false {param($x)$x.initial_caption='Another score'}
CloseCase 'close-wrong-initial-class-refused' $false {param($x)$x.initial_window_class='ConsoleWindowClass'}
CloseCase 'close-exit-not-observed-refused' $false {param($x)$x.app_exit_observed=$false}
[ordered]@{schema_version=1;passed=$true;scope='Actual pure evidence helper tested with synthetic UI claims and copies of frozen CC0 resources; no GUI/application/COM/firewall/network';helper_sha256=(Get-FileHash $helper -Algorithm SHA256).Hash.ToLowerInvariant();cases=$rows.ToArray();GUI_validated=$false;application_executed=$false;network_executed=$false;firewall_executed=$false}|ConvertTo-Json -Depth 12|Set-Content (Join-Path $PSScriptRoot 'tools-evidence-checks.json') -Encoding utf8NoBOM
Write-Host ('PASS: '+$rows.Count+' actual pure evidence guards; no GUI or network executed.')
