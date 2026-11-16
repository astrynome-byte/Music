# SPDX-License-Identifier: GPL-3.0-only
# Data reader only. Starts no application or UIA client and sends no input.
param([Parameter(Mandatory)][string]$ResultPath)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath($ResultPath)
$consoleLimit=524288
$newline=[Environment]::NewLine
function Get-CheckedEvidenceItem([string]$Path,[bool]$Directory=$false){
 if($Path.Length-gt1024-or-not[IO.Path]::IsPathFullyQualified($Path)){throw 'Evidence path is oversized or not absolute.'}
 $p=[IO.Path]::GetFullPath($Path)
 if(-not$p.StartsWith($root.TrimEnd('\','/')+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw 'Evidence must be below its exact result directory.'}
 if([IO.Path]::GetRelativePath($root,$p).Contains(':')){throw 'Evidence streams are not admitted.'}
 $item=Get-Item -LiteralPath $p -Force
 if($item.PSIsContainer-ne$Directory){throw 'Evidence path has the wrong file/directory type.'}
 $ancestor=$item
 while($null-ne$ancestor){
  if($ancestor.Attributes-band[IO.FileAttributes]::ReparsePoint){throw 'Evidence path or ancestor is a reparse point.'}
  if($ancestor-is[IO.FileInfo]){$ancestor=$ancestor.Directory}else{$ancestor=$ancestor.Parent}
 }
 return $item
}
function Get-OriginalHash([byte[]]$Bytes){return [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($Bytes)).ToLowerInvariant()}
function Select-DiagnosticScalars([Collections.IDictionary]$Data,[string[]]$Names){
 $selected=[ordered]@{}
 foreach($name in $Names){
  if(-not$Data.Contains($name)){continue};$value=$Data[$name]
  if($null-eq$value-or$value-is[bool]-or$value-is[ValueType]){$selected[$name]=$value}
  elseif($value-is[string]){$selected[$name]=$value.Substring(0,[Math]::Min(512,$value.Length))}
 }
 return $selected
}
function Get-DiagnosticProjection([Collections.IDictionary]$Data){
 $p=Select-DiagnosticScalars $Data @('schema_version','phase','status','pid','bounded','max_nodes','max_depth','max_edges','walker_hresult','first_failure_operation','first_failure_hresult','deadline_reached','node_limit_reached','tree_incomplete','phase_observation_incomplete','observation_incomplete','blocking_observation_failure','local_focus_only_eligible','only_sibling_navigation_failure','local_focus_scope','full_tree_complete_claimed','raw_tree_incomplete_observed','partial_tree_local_focus_used','local_final_state_verified','native_chooser_observation_gap_observed','native_chooser_observation_gap_active','native_chooser_gap_frames','native_chooser_raw_resumptions','observation_gap','raw_tree_walk_performed','gap_reason','gap_owner_handle','gap_picker_handle','native_sample_owned','native_sample_error','native_foreground_handle','native_foreground_pid','native_focus_handle','native_focus_pid','native_windows_total','last_local_proof_timing','runtime_identity_unknown','foreign_node_refused','unique_runtime_ids','cycle_edges','duplicate_edges','keys','alt_taps','home_taps','next_row_taps','initial_OMR_document_right_taps','keyboard_failure','com_hresult','dialog_handle','dialog_title','MIDI_file_saved','GUI_imported_score_focus_verified','saved_midi_path','controlled_score_closed_to_home','close_confirmation_observed','close_confirmation_discarded','close_confirmation_navigation_keys','close_home_navigation_keys','temporary_score_close_gap_active','close_question_anchor_count','close_stable_question_anchors','close_anchor_operation','close_anchor_hresult','saved_score_focus_proof_attempts','saved_score_navigation_keys')
 foreach($field in @('nodes','graph_edges','inspected_windows')){
  $p[$field+'_count']=if(-not$Data.Contains($field)){$null}elseif($null-eq$Data[$field]){0}else{@($Data[$field]).Count}
 }
 $windows=[Collections.Generic.List[object]]::new()
 foreach($window in @($Data['inspected_windows']|Select-Object -First 8)){
  if($window-is[Collections.IDictionary]){$windows.Add((Select-DiagnosticScalars $window @('handle','title','pid','enabled','owner_handle','element_from_handle_hresult')))}
 }
 $p['inspected_windows_bounded_to8']=$windows.ToArray()
 $nativeWindows=[Collections.Generic.List[object]]::new()
 foreach($window in @($Data['native_windows_bounded_to8']|Select-Object -First 8)){
  if($window-is[Collections.IDictionary]){$nativeWindows.Add((Select-DiagnosticScalars $window @('handle','title','pid','enabled','owner_handle')))}
 }
 $p['native_windows_bounded_to8']=$nativeWindows.ToArray()
 if($Data['last_successful_local_focus_proof']-is[Collections.IDictionary]){
  $proof=$Data['last_successful_local_focus_proof']
  $p['last_successful_local_focus_proof_projection']=Select-DiagnosticScalars $proof @('expected_native_context','native_foreground','native_focus','focused_name','focused_role')
  $p['last_successful_local_focus_proof_projection']['ancestor_count']=@($proof['ancestors']).Count
 }
 $focused=[Collections.Generic.List[object]]::new();$focusCount=0
 foreach($node in @($Data['nodes'])){
  if($node-is[Collections.IDictionary]-and$node['keyboard_focus']-eq$true){
   ++$focusCount
   if($focused.Count-lt4){$focused.Add((Select-DiagnosticScalars $node @('name','control_type','pid','depth','enabled','offscreen','keyboard_focus')))}
  }
 }
 $p['focused_nodes_count']=if($Data.Contains('nodes')){$focusCount}else{$null}
 $p['focused_nodes_bounded_to4']=$focused.ToArray()
 $p['local_focus_evidence_count']=if($null-eq$Data['local_focus_evidence_bounded_to16']){0}else{@($Data['local_focus_evidence_bounded_to16']).Count}
 if($Data['diagnostics_only']-is[Collections.IDictionary]){
  $d=$Data['diagnostics_only']
  $p['diagnostics_only']=Select-DiagnosticScalars $d @('blocked_guard','COM_initialization_hresult','automation2_query_hresult','connection_timeout_hresult','transaction_timeout_hresult','readiness_entered','readiness_passed','readiness_iterations','readiness_root_attempts','readiness_root_timeout_waits','readiness_root_last_hresult','readiness_root_last_handle','local_focus_successful_proofs','local_focus_failure_operation','local_focus_failure_hresult')
  $p['diagnostics_only']['readiness_frames_count']=if($null-eq$d['readiness_frames_bounded_to8']){0}else{@($d['readiness_frames_bounded_to8']).Count}
 }
 foreach($field in @('saved_score_first_refusal','saved_score_last_refusal')){
  if($Data[$field]-is[Collections.IDictionary]){
   $d=$Data[$field]
   $selected=Select-DiagnosticScalars $d @('attempt','reason','hresult','main_handle','main_title','focused_name','focused_type','focused_pid','has_focus','blocking_observation_failure','local_focus_failure_operation','local_focus_failure_hresult')
   $ancestors=[Collections.Generic.List[object]]::new()
   foreach($node in @($d['ancestors_bounded_to18']|Select-Object -First 18)){
    if($node-is[Collections.IDictionary]){$ancestors.Add((Select-DiagnosticScalars $node @('name','type','pid')))}
   }
   $selected['ancestors_bounded_to18']=$ancestors.ToArray();$p[$field]=$selected
  }
 }
 return $p
}
function Get-ConsoleBlock([string]$Tag,[Collections.IDictionary]$Entry){
 return 'CADENCE_IMPORT_GUI_READER_'+$Tag+'_BEGIN'+$newline+(ConvertTo-Json -InputObject $Entry -Depth 30 -Compress -WarningAction Stop)+$newline+'CADENCE_IMPORT_GUI_READER_'+$Tag+'_END'+$newline
}
$reportPath=Join-Path $root 'import-dialogs-gui-report.json'
if(-not(Test-Path -LiteralPath $reportPath -PathType Leaf)){
 Write-Host 'CADENCE_IMPORT_GUI_READER_SUMMARY_BEGIN';Write-Host '{"reader_only":true,"application_executed_by_reader":false,"results_available":false}';Write-Host 'CADENCE_IMPORT_GUI_READER_SUMMARY_END';return
}
$file=Get-CheckedEvidenceItem $reportPath
if($file.Length-gt2097152){throw 'Original report is oversized.'}
$raw=[IO.File]::ReadAllBytes($reportPath)
if($raw.Length-ne$file.Length-or$raw.Length-gt2097152){throw 'Original report changed size while being read.'}
$report=[Text.Encoding]::UTF8.GetString($raw).TrimStart([char]0xfeff)|ConvertFrom-Json
# Plan all mandatory receipts/projections before emitting anything. Optional
# payloads consume only the space left after ALL mandatory blocks and summary.
$blocks=[Collections.Generic.List[object]]::new()
$entry=[ordered]@{reader_only=$true;application_executed_by_reader=$false;path=$file.Name;original_bytes=$raw.Length;original_sha256=(Get-OriginalHash $raw);representation='report_receipt_and_status_projection_only';report_status=$report.status;phase_count=@($report.phases).Count;optional_payload_included=$false;optional_payload_omitted_reason='total_console_budget'}
$blocks.Add(@{tag='JSON';entry=$entry;extra_key='reserialized_report';extra=$report;full_representation='reserialized_report_with_original_hash_receipt'})
$pngCount=0
foreach($capture in @($report.captures|Select-Object -First 2)){
 $p=[IO.Path]::GetFullPath($capture.path);$f=Get-CheckedEvidenceItem $p
 if($f.Length-gt1048576){throw 'Original capture exceeds the 1MiB reader limit.'}
 $bytes=[IO.File]::ReadAllBytes($p);$sha=Get-OriginalHash $bytes
 if($bytes.Length-gt1048576-or$sha-cne$capture.sha256-or$bytes.Length-ne$capture.bytes){throw 'Original image no longer matches its capture receipt.'}
 $entry=[ordered]@{reader_only=$true;application_executed_by_reader=$false;path=$f.Name;original_bytes=$bytes.Length;sha256=$sha;visual_review_performed=$false;representation='original_PNG_receipt_only';optional_payload_included=$false;optional_payload_omitted_reason='total_console_budget'}
 $blocks.Add(@{tag='PNG';entry=$entry;extra_key='original_PNG_base64';extra=[Convert]::ToBase64String($bytes);full_representation='original_PNG_bytes_base64_with_hash_receipt'});++$pngCount
}
$failureJSONCount=0;$failedPhase=$null;$phaseOrdinal=0;$phaseRows=@($report.phases)
if($phaseRows.Count-gt8){throw 'Unexpected number of native phases.'}
if($report.status-ceq'failed-or-blocked'){
 for($i=0;$i-lt$phaseRows.Count;++$i){
  $phase=$phaseRows[$i]
  if($phase.client_exit_code-ne0-or$phase.report.status-cne'passed_owned_import_dialog_phase'){$failedPhase=$phase;$phaseOrdinal=$i+1;break}
 }
}
if($null-ne$failedPhase){
 if($failedPhase.phase-cnotin@('open-omr','close-omr','open-wav','close-wav','analyze-wav','close-ready-wav','save-open-wav','close-saved-midi-score')){throw 'Unknown native phase name.'}
 $expectedDirectory=Join-Path $root ('{0:D2}-{1}'-f$phaseOrdinal,$failedPhase.phase)
 if($failedPhase.directory.Length-gt1024-or-not[IO.Path]::IsPathFullyQualified($failedPhase.directory)-or-not[IO.Path]::GetFullPath($failedPhase.directory).Equals($expectedDirectory,[StringComparison]::OrdinalIgnoreCase)){throw 'Failed phase directory differs from its exact report sequence and name.'}
 $phaseDirectory=(Get-CheckedEvidenceItem $expectedDirectory $true).FullName
 $names=[Collections.Generic.List[string]]::new()
 foreach($name in @('main-ready.json','phase-final.json','import-dialog-phase.json')){if(Test-Path -LiteralPath (Join-Path $phaseDirectory $name)){$names.Add($name)}}
 # Select at most the last numbered post-key frame; never print an inventory.
 $lastNumber=0;$lastName=$null;$candidateCount=0
 foreach($candidate in [IO.Directory]::EnumerateFiles($phaseDirectory,'*-after-import-key.json')){
  ++$candidateCount;if($candidateCount-gt70){throw 'Post-key evidence inventory exceeds the native key budget.'}
  $name=[IO.Path]::GetFileName($candidate)
  if($name-cmatch'^([1-9]|[1-6][0-9]|70)-after-import-key\.json$'-and[int]$Matches[1]-gt$lastNumber){$lastNumber=[int]$Matches[1];$lastName=$name}
 }
 if($null-ne$lastName){$names.Add($lastName)}
 foreach($name in $names){
  $p=Join-Path $phaseDirectory $name;$f=Get-CheckedEvidenceItem $p
  if($f.Length-gt8388608){throw 'Original native JSON exceeds the 8MiB reader limit.'}
  $bytes=[IO.File]::ReadAllBytes($p)
  if($bytes.Length-ne$f.Length-or$bytes.Length-gt8388608){throw 'Original native JSON changed size while being read.'}
  $sha=Get-OriginalHash $bytes
  if($name-ceq'import-dialog-phase.json'-and$sha-cne$failedPhase.sha256){throw 'Original native phase JSON no longer matches its report receipt.'}
  $data=[Text.Encoding]::UTF8.GetString($bytes).TrimStart([char]0xfeff)|ConvertFrom-Json -AsHashtable -Depth 32
  if($data-isnot[Collections.IDictionary]-or-not$data.Contains('pid')-or$data['pid']-ne$failedPhase.pid){throw 'Native evidence JSON does not identify its exact reported phase PID.'}
  $entry=[ordered]@{reader_only=$true;application_executed_by_reader=$false;path=$p;phase=$failedPhase.phase;phase_directory=$phaseDirectory;original_bytes=$bytes.Length;original_sha256=$sha;representation='diagnostic_projection_only';diagnostic_projection=(Get-DiagnosticProjection $data);original_JSON_base64_limit=131072;optional_payload_included=$false;optional_payload_omitted_reason='original_JSON_exceeds_128KiB'}
  $extra=$null;$extraKey=$null
  if($bytes.Length-le131072){$extra=[Convert]::ToBase64String($bytes);$extraKey='original_JSON_base64';$entry['optional_payload_omitted_reason']='total_console_budget'}
  $blocks.Add(@{tag='FAILURE_JSON';entry=$entry;extra_key=$extraKey;extra=$extra;full_representation='original_JSON_bytes_base64_with_diagnostic_projection'});++$failureJSONCount
 }
}
$minimumBytes=0
foreach($block in $blocks){$block['minimal_text']=Get-ConsoleBlock $block.tag $block.entry;$minimumBytes+=[Text.Encoding]::UTF8.GetByteCount($block.minimal_text)}
# Reserve 2KiB for the final summary; its actual exact UTF8 cost is checked.
if($minimumBytes-gt($consoleLimit-2048)){throw 'Mandatory evidence projections exceed the total console budget.'}
$usedBytes=$minimumBytes;$pngPrinted=0;$jsonOriginalsPrinted=0
foreach($block in $blocks){
 $block['text']=$block.minimal_text
 if($null-eq$block.extra_key){continue}
 $full=[ordered]@{};foreach($key in $block.entry.Keys){$full[$key]=$block.entry[$key]}
 $full[$block.extra_key]=$block.extra;$full['representation']=$block.full_representation;$full['optional_payload_included']=$true;$full['optional_payload_omitted_reason']=$null
 $text=Get-ConsoleBlock $block.tag $full
 $extraBytes=[Text.Encoding]::UTF8.GetByteCount($text)-[Text.Encoding]::UTF8.GetByteCount($block.minimal_text)
 if(($usedBytes+$extraBytes)-le($consoleLimit-2048)){
  $block['text']=$text;$usedBytes+=$extraBytes
  if($block.tag-ceq'PNG'){++$pngPrinted};if($block.tag-ceq'FAILURE_JSON'){++$jsonOriginalsPrinted}
 }
}
$summary=[ordered]@{reader_only=$true;application_executed_by_reader=$false;results_available=$true;original_PNGs_printed=$pngPrinted;original_PNG_receipts=$pngCount;failed_phase_JSON_receipts=$failureJSONCount;original_failure_JSONs_base64_printed=$jsonOriginalsPrinted;GUI_validation_inferred_by_reader=$false;console_limit_utf8_bytes=$consoleLimit;console_budget_scope='all reader blocks including report, PNG, failure JSON, markers and summary; runner log envelopes excluded';console_utf8_bytes=0}
do{$previousTotal=$summary.console_utf8_bytes;$summaryText=Get-ConsoleBlock 'SUMMARY' $summary;$summary.console_utf8_bytes=$usedBytes+[Text.Encoding]::UTF8.GetByteCount($summaryText)}while($summary.console_utf8_bytes-ne$previousTotal)
$summaryText=Get-ConsoleBlock 'SUMMARY' $summary
if($summary.console_utf8_bytes-gt$consoleLimit){throw 'Final evidence output exceeds the total console budget.'}
# Write the exact planned UTF8 text, without node/graph listings or inventories.
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
foreach($block in $blocks){[Console]::Write($block.text)}
[Console]::Write($summaryText)
