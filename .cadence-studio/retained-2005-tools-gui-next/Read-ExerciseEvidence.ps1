# SPDX-License-Identifier: GPL-3.0-only
# Pure corroboration/claims functions; no application, registry, network or UI call.
Set-StrictMode -Version Latest
function Assert-ToolsPlainPath([string]$Path) {
    $current=[IO.Path]::GetFullPath($Path)
    while($current){
        if((Test-Path -LiteralPath $current)-and((Get-Item -LiteralPath $current -Force).Attributes-band[IO.FileAttributes]::ReparsePoint)){throw 'Linked exercise path refused.'}
        $parent=[IO.Path]::GetDirectoryName($current.TrimEnd('\','/'));if(-not$parent-or$parent-eq$current){break};$current=$parent
    }
}
function Test-CopiedExerciseEvidence([string]$ExerciseRoot,[string]$FixtureDirectory,$OwnedExitCode) {
    # This precedes even reading a fixture/manifest: Dispose alone is not proof
    # that the process stopped. Only its actual integer exit0 enables reads.
    if(($OwnedExitCode-isnot[int]-and$OwnedExitCode-isnot[long])-or$OwnedExitCode-ne0){throw 'No confirmed clean application exit; exercise and fixture reads skipped.'}
    $expected=@{
        'pulsation.musicxml'=@{bytes=5101;sha256='39da44328324f7d33c22ff803000a0e50b558abe4678eba878d7e659ed11a4de'}
        'LICENSE-CC0.txt'=@{bytes=595;sha256='3767f335112a9088a11ae0a13fde590942543534b20e92d9e644ca22fd39814d'}
    }
    $ExerciseRoot=[IO.Path]::GetFullPath($ExerciseRoot);$FixtureDirectory=[IO.Path]::GetFullPath($FixtureDirectory)
    Assert-ToolsPlainPath $ExerciseRoot;Assert-ToolsPlainPath $FixtureDirectory
    $manifest=Get-Content -LiteralPath (Join-Path $FixtureDirectory 'manifest.json') -Raw -Encoding utf8|ConvertFrom-Json
    if($manifest.source_commit-cne'961c80b235d413dc9d123ea8f669ddb7f84ecd09'-or$manifest.source_tree-cne'c4780f1487559744fd4b2c2040b86ac37bb8c67b'-or$manifest.application_name-cne'CadenceStudio4'-or$manifest.exercise_id-cne'pulsation'-or$manifest.license-cne'CC0-1.0'){throw 'Frozen authorized exercise provenance differs.'}
    $children=@(Get-ChildItem -LiteralPath $ExerciseRoot -Force)
    if($children.Count-ne1-or-not$children[0].PSIsContainer-or$children[0].Name-cnotmatch'^pulsation-[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$'){throw 'Expected exactly one new UI-created pulsation UUID folder.'}
    $folder=$children[0].FullName;Assert-ToolsPlainPath $folder
    $files=@(Get-ChildItem -LiteralPath $folder -Force)
    if($files.Count-ne2-or@($files|Where-Object{$_.PSIsContainer}).Count){throw 'Exercise copy must contain exactly its score and CC0 license.'}
    $receipts=@()
    foreach($name in @('pulsation.musicxml','LICENSE-CC0.txt')){
        $copy=Join-Path $folder $name;$source=Join-Path $FixtureDirectory $name
        foreach($path in @($copy,$source)){
            Assert-ToolsPlainPath $path;$file=Get-Item -LiteralPath $path -Force
            if($file.PSIsContainer-or$file.Length-ne$expected[$name].bytes-or(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()-cne$expected[$name].sha256){throw ('Actual source/copy bytes differ: '+$name)}
        }
        $receipts += [ordered]@{name=$name;source_path=$source;copy_path=$copy;bytes=$expected[$name].bytes;sha256=$expected[$name].sha256;source_unchanged=$true;copy_byte_identical=$true}
    }
    $score=Get-Item -LiteralPath (Join-Path $folder 'pulsation.musicxml') -Force
    if($score.Attributes-band[IO.FileAttributes]::ReadOnly){throw 'The UI-created personal exercise copy remains read-only.'}
    return [ordered]@{schema_version=1;passed=$true;scope='Read only after confirmed owned exit0; actual new UUID folder and exact CC0 score/license bytes';exercise_root=$ExerciseRoot;copy_directory=$folder;exercise_id='pulsation';exercise_title='Garder la pulsation';copy_writable_attribute=$true;files=$receipts;application_executed_by_this_check=$false;gui_inferred_from_file_bytes=$false}
}
function Test-ToolsNativeClaims($Native,[int]$OwnedPid) {
    if(($Native.schema_version-isnot[int]-and$Native.schema_version-isnot[long])-or$Native.schema_version-ne1-or($Native.pid-isnot[int]-and$Native.pid-isnot[long])-or$Native.pid-ne$OwnedPid){throw 'Native report schema or owned PID differs.'}
    $required=@('sounds_navigation_delivered','sounds_page_control_observed','generaluser_offer_control_observed','generaluser_download_size_control_observed','generaluser_license_control_observed','generaluser_license_text_observed','lessons_navigation_delivered','offline_lessons_tab_observed','lesson_open_requested','lesson_editor_title_observed')
    foreach($name in $required){if($Native.$name-isnot[bool]-or-not$Native.$name){throw ('Actual native UI claim missing: '+$name)}}
    if(($Native.offline_lesson_count_observed-isnot[int]-and$Native.offline_lesson_count_observed-isnot[long])-or$Native.offline_lesson_count_observed-ne8){throw 'All eight distinct exercise controls must be observed.'}
    if($Native.lesson_editor_title-isnot[string]-or$Native.lesson_editor_title-cnotmatch'(?i:pulsation|Garder la pulsation)'-or$Native.window_caption_before_exercise_open-isnot[string]-or$Native.lesson_editor_title-ceq$Native.window_caption_before_exercise_open-or$Native.lesson_editor_window_class-isnot[string]-or-not$Native.lesson_editor_window_class.StartsWith('Qt',[StringComparison]::Ordinal)-or-not$Native.lesson_editor_window_class.Contains('QWindow')){throw 'Changed owned Qt editor caption was not established.'}
    return $true
}
function Test-OwnedExerciseCloseClaims($Native,[int]$OwnedPid) {
    if(($Native.schema_version-isnot[int]-and$Native.schema_version-isnot[long])-or$Native.schema_version-ne1-or($Native.pid-isnot[int]-and$Native.pid-isnot[long])-or$Native.pid-ne$OwnedPid){throw 'Owned close schema/PID differs.'}
    foreach($name in @('close_requested','app_exit_observed')){if($Native.$name-isnot[bool]-or-not$Native.$name){throw ('Actual owned close claim missing: '+$name)}}
    if(($Native.exit_code-isnot[int]-and$Native.exit_code-isnot[long])-or$Native.exit_code-ne0-or$Native.discard_control_observed-isnot[bool]-or$Native.discard_delivered-isnot[bool]-or$Native.owned_modal_observed-isnot[bool]-or$Native.owned_modal_observed-ne$Native.discard_control_observed-or$Native.discard_control_observed-ne$Native.discard_delivered){throw 'Clean exit0 or exact owned discard observation/delivery missing.'}
    if($Native.initial_caption-isnot[string]-or$Native.initial_caption-cnotmatch'(?i:pulsation|Garder la pulsation)'-or$Native.initial_window_class-isnot[string]-or-not$Native.initial_window_class.StartsWith('Qt',[StringComparison]::Ordinal)-or-not$Native.initial_window_class.Contains('QWindow')){throw 'Close did not start from the controlled Qt exercise caption.'}
    return $true
}
