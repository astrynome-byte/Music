# SPDX-License-Identifier: GPL-3.0-only
# Replay only the actual read-only catalogue corroboration block on owned data.
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$source=Join-Path $PSScriptRoot '../Run-CollectionsUiProbe.ps1'
$tokens=$null;$parseErrors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($source,[ref]$tokens,[ref]$parseErrors)
if(@($parseErrors).Count){throw($parseErrors|Out-String)}
$node=@($ast.FindAll({param($x) $x -is [Management.Automation.Language.TryStatementAst] -and $x.Body.Extent.Text.Contains('$catalogPath = Join-Path $localDataDirectory')},$true))
if($node.Count-ne1){throw 'Expected one real catalogue corroboration block.'}
$body=$node[0].Body.Extent.Text
$scriptBlock=[scriptblock]::Create($body.Substring(1,$body.Length-2))
$work=Join-Path '/tmp' ('cadence-ui-data-gate-'+[guid]::NewGuid().ToString('N'));[void][IO.Directory]::CreateDirectory($work)
$rows=[Collections.Generic.List[object]]::new()
function Check([string]$Name,[bool]$ExpectedAccept,[bool]$ExpectedUiPass,[scriptblock]$Mutate){
 $caseRoot=Join-Path $work $Name;$OutputDirectory=Join-Path $caseRoot 'evidence';$localDataDirectory=Join-Path $caseRoot 'profile';$CollectionName='Cadence-QA-2005'
 [void][IO.Directory]::CreateDirectory($OutputDirectory);[void][IO.Directory]::CreateDirectory((Join-Path $localDataDirectory 'CadenceStudio4'))
 $original=Join-Path $caseRoot 'original.mscx';$copy=Join-Path $caseRoot 'copy.mscx'
 [IO.File]::WriteAllText($original,'owned data fixture, not executed or parsed as a score');[IO.File]::Copy($original,$copy)
 $hash=(Get-FileHash $original -Algorithm SHA256).Hash.ToLowerInvariant()
 $report=[ordered]@{fixture=[ordered]@{source_path=$original;copy_path=$copy;source_sha256_before=$hash;sha256_before=$hash;title='Owned fixture';composer='QA data'};error=$null;cleanup=[ordered]@{error=$null;forced=$false;exit_code=0};probe_cleanup_forced=$false;score_added_control_observed=$true;favorite_action_delivered=$true;favorite_remove_label_observed=$true;collections_enabled_observed=$true;collection_created_control_observed=$true;collection_member_control_observed=$true;collection_filter_observed=$true;favorites_tested=$false;collections_tested=$false;catalog_validation=$null;catalog_actual_snapshot_path=$null;status='synthetic-claims-not-GUI-evidence'}
 $catalog=[ordered]@{schema_version=2;entries=@([ordered]@{id='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';path=$copy;title='Owned fixture';composer='QA data';favorite=$true});collections=@([ordered]@{id='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';name=$CollectionName;entry_ids=@('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa')})}
 & $Mutate $report $catalog
 $catalog|ConvertTo-Json -Depth 8|Set-Content (Join-Path $localDataDirectory 'CadenceStudio4/local_library.json') -Encoding utf8
 $accepted=$false;$errorText=$null
 try{. $scriptBlock;$accepted=$true}catch{$errorText=$_.Exception.Message}
 $uiPass=$report.favorites_tested-and$report.collections_tested
 $passed=$accepted-eq$ExpectedAccept-and$uiPass-eq$ExpectedUiPass
 $rows.Add([ordered]@{case=$Name;passed=$passed;accepted=$accepted;expected_accept=$ExpectedAccept;ui_claims_passed=$uiPass;expected_ui_claims_pass=$ExpectedUiPass;error=$errorText;only_synthetic_native_claims=$true})
 if(-not$passed){throw "UI evidence gate data case failed: $Name"}
}
Check 'synthetic-complete-claims-and-actual-metadata' $true $true {param($report,$catalog)}
Check 'metadata-alone-cannot-validate-GUI' $true $false {param($report,$catalog)
 foreach($name in @('score_added_control_observed','favorite_action_delivered','favorite_remove_label_observed','collections_enabled_observed','collection_created_control_observed','collection_member_control_observed','collection_filter_observed')){$report[$name]=$false}
}
Check 'missing-member-UI-claim-refused' $true $false {param($report,$catalog) $report.collection_member_control_observed=$false}
Check 'favorite-label-not-observed-refused' $true $false {param($report,$catalog) $report.favorite_remove_label_observed=$false}
Check 'forced-close-refused' $true $false {param($report,$catalog) $report.cleanup.forced=$true}
Check 'nonzero-close-refused' $true $false {param($report,$catalog) $report.cleanup.exit_code=1}
Check 'missing-persisted-member-refused' $false $false {param($report,$catalog) $catalog.collections[0].entry_ids=@()}
Check 'wrong-persisted-collection-name-refused' $false $false {param($report,$catalog) $catalog.collections[0].name='Other'}
Check 'old-schema1-catalogue-refused' $false $false {param($report,$catalog) $catalog.schema_version=1}
Check 'favorite-not-persisted-refused' $false $false {param($report,$catalog) $catalog.entries[0].favorite=$false}
[ordered]@{schema_version=1;passed=$true;scope='Actual wrapper AST catalogue corroboration block replayed on owned synthetic data and synthetic native claims; no UIA, Windows GUI, app or musical parser executed';source_sha256=(Get-FileHash $source -Algorithm SHA256).Hash.ToLowerInvariant();cases=@($rows.ToArray());application_executed=$false;gui_validated=$false;fixture_directory=$work}|ConvertTo-Json -Depth 12|Set-Content (Join-Path $PSScriptRoot 'ui-evidence-gate-checks.json') -Encoding utf8
Write-Host ('PASS: '+$rows.Count+' actual evidence-gate data cases; metadata alone never validates GUI.')
