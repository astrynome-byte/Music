# SPDX-License-Identifier: GPL-3.0-only
Set-StrictMode -Version Latest
function Assert-NotesUiClaims($Document, [int] $ExpectedPid, [bool] $Restart) {
    if (($Document.schema_version -isnot [int] -and $Document.schema_version -isnot [long]) -or $Document.schema_version -ne 1 -or
        ($Document.pid -isnot [int] -and $Document.pid -isnot [long]) -or $Document.pid -ne $ExpectedPid -or
        $Document.verify_existing_requested -isnot [bool] -or $Document.verify_existing_requested -ne $Restart -or
        $Document.keyboard_failure_stops_sequence -isnot [bool] -or $Document.keyboard_failure_stops_sequence -or
        $Document.note_text -cne 'Cadence-QA-PrivateNote-2006') { throw 'The native private-notes report has the wrong identity, types or stopped keyboard sequence.' }
    $flags=@('library_content_observed','notes_panel_observed','annotations_enabled_control_observed','notes_view_ready_for_clean_close')
    $expectedStatus='private_note_saved_through_UIA_ready_for_close'
    if($Restart){$flags+=@('saved_note_choice_observed','restored_note_text_observed');$expectedStatus='private_note_restored_through_UIA_ready_for_close'}
    else{$flags+=@('owned_file_dialog_selected_copy','score_added_control_observed','compatibility_acknowledged_observed','typed_note_text_observed','save_action_delivered','saved_note_control_observed')}
    foreach($key in $flags){if($Document.$key -isnot [bool] -or -not $Document.$key){throw "Actual UI observation missing or not boolean: $key"}}
    if($Document.status -cne $expectedStatus){throw 'The native notes flow did not reach its exact complete status.'}
}
function Read-ClosedNotesCatalogue($ExitCode, [bool] $Forced, [string] $Path, $Fixture, [string] $SnapshotDirectory) {
    # Guard precedes all catalogue reads/copies/hashes. A stopped/killed/unknown
    # process can leave diagnostic files but can never supply a passing receipt.
    if(($ExitCode -isnot [int] -and $ExitCode -isnot [long]) -or $ExitCode -ne 0 -or $Forced){throw 'Clean owned application exit0 is required before catalogue corroboration.'}
    $file=Get-Item -LiteralPath $Path
    if($file.PSIsContainer -or ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $file.Length -gt 262144){throw 'Unexpected private-notes catalogue file.'}
    foreach($score in @(@($Fixture.source_path,$Fixture.source_sha256_before),@($Fixture.copy_path,$Fixture.sha256_before))){
        $item=Get-Item -LiteralPath $score[0]
        if($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
            (Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash.ToLowerInvariant() -cne $score[1]){throw 'A controlled musical source/copy changed.'}
    }
    $catalog=[IO.File]::ReadAllText($file.FullName)|ConvertFrom-Json
    if(($catalog.schema_version -isnot [int] -and $catalog.schema_version -isnot [long]) -or $catalog.schema_version -ne 3 -or
        @($catalog.entries).Count -ne 1 -or @($catalog.collections).Count -ne 0 -or @($catalog.annotations).Count -ne 1){throw 'Expected schema3, one score, no collections and one private note created through UI.'}
    $entry=@($catalog.entries)[0];$note=@($catalog.annotations)[0]
    $entryId=[guid]::Empty;$noteId=[guid]::Empty
    if(-not [guid]::TryParseExact([string]$entry.id,'D',[ref]$entryId) -or -not [guid]::TryParseExact([string]$note.id,'D',[ref]$noteId) -or
        $entry.title -cne $Fixture.title -or $entry.composer -cne $Fixture.composer -or
        -not [string]::Equals([IO.Path]::GetFullPath([string]$entry.path),[IO.Path]::GetFullPath($Fixture.copy_path),[StringComparison]::OrdinalIgnoreCase) -or
        $entry.favorite -isnot [bool] -or $entry.favorite -or $note.entry_id -cne $entry.id -or $note.text -cne 'Cadence-QA-PrivateNote-2006') {throw 'Persisted note identity/text or unchanged controlled entry differs.'}
    foreach($pair in @(@('measure',0),@('page',0),@('revision',1))){
        $v=$note.($pair[0]);if(($v -isnot [int] -and $v -isnot [long]) -or $v -ne $pair[1]){throw 'Private-note manual references/revision differ.'}
    }
    $backups=@(Get-ChildItem -LiteralPath $file.DirectoryName -File -Filter ($file.Name+'.before-private-notes-*.json'))
    if($backups.Count -ne 1 -or ($backups[0].Attributes -band [IO.FileAttributes]::ReparsePoint) -or $backups[0].Length -gt 262144){throw 'Exactly one bounded migration backup is required.'}
    $before=[IO.File]::ReadAllText($backups[0].FullName)|ConvertFrom-Json
    if(($before.schema_version -isnot [int] -and $before.schema_version -isnot [long]) -or $before.schema_version -ne 1 -or @($before.entries).Count -ne 1){throw 'Expected pre-activation schema1 backup.'}
    $old=@($before.entries)[0]
    foreach($key in @('id','path','title','composer','favorite')){if($old.$key -cne $entry.$key){throw 'The migration backup did not preserve the same entry.'}}
    $snapshot=Join-Path $SnapshotDirectory 'catalog-after-ui.json';[IO.File]::Copy($file.FullName,$snapshot,$false)
    $backupSnapshot=Join-Path $SnapshotDirectory 'catalog-before-private-notes.json';[IO.File]::Copy($backups[0].FullName,$backupSnapshot,$false)
    return [ordered]@{schema_version=1;status='passed_auxiliary_post_exit_only';catalogue_path=$file.FullName;snapshot_path=$snapshot;sha256=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant();catalogue_schema=3;entry_id=$entry.id;note_id=$note.id;note_text=$note.text;revision=$note.revision;measure=$note.measure;page=$note.page;note_count=1;collection_count=0;score_count=1;musical_source_and_copy_unchanged=$true;migration_backup_sha256=(Get-FileHash -LiteralPath $backups[0].FullName -Algorithm SHA256).Hash.ToLowerInvariant();backup_entries_equal_after_migration=$true;backup_original_byte_identity_not_inferred=$true;catalogue_read_only_after_clean_exit0=$true}
}
