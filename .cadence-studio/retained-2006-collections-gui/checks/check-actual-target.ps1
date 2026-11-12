# SPDX-License-Identifier: GPL-3.0-only
# Real authenticated metadata plus controlled mutations; never execute an app/ZIP.
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
. (Join-Path $root 'Read-ProducedTarget.ps1')
$source=[IO.Path]::GetFullPath((Join-Path $root '../combined-2006-source'))
$work=Join-Path ([IO.Path]::GetTempPath()) ('cadence-collections2006-target-'+[guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($work)
$rows=[Collections.Generic.List[object]]::new()
$targetPath=Join-Path $work 'target.json'
$receiptPath=Join-Path $work 'data-authentication.json'
$base=Get-Content -LiteralPath (Join-Path $root 'target.json') -Raw -Encoding utf8|ConvertFrom-Json
function Case([string]$Name,[bool]$Expected,[scriptblock]$Mutate){
 $data=$base|ConvertTo-Json -Depth 16|ConvertFrom-Json
 [IO.File]::Copy((Join-Path $root 'data-authentication.json'),$receiptPath,$true)
 & $Mutate $data
 $data|ConvertTo-Json -Depth 16|Set-Content -LiteralPath $targetPath -Encoding utf8NoBOM
 $accepted=$true;$errorText=$null
 try{[void](Get-NextGuiTarget $targetPath $source)}catch{$accepted=$false;$errorText=$_.Exception.Message}
 $passed=$accepted-eq$Expected
 $rows.Add([ordered]@{case=$Name;passed=$passed;accepted=$accepted;expected=$Expected;error=$errorText})
 if(-not$passed){throw ('Target control failed: '+$Name)}
}
try{
 Case 'actual-authenticated2006-target-accepted-data-only' $true {param($d)}
 Case 'old2005-target-refused' $false {param($d)$d.build_number=2005;$d.run_number=5}
 Case 'boolean-schema-refused' $false {param($d)$d.schema_version=$true}
 Case 'boolean-artifact-id-refused' $false {param($d)$d.artifact_id=$true}
 Case 'wrong-producer-id-refused' $false {param($d)$d.producer_run_id=43207550870}
 Case 'wrong-source-json-SHA-refused' $false {param($d)$d.source.source_json_sha256='a'*64}
 Case 'wrong-source-tree-refused' $false {param($d)$d.source.tree='b'*40}
 Case 'wrong-EXE-SHA-refused' $false {param($d)$d.stage.executable_sha256='c'*64}
 Case 'wrong-innerZIP-SHA-refused' $false {param($d)$d.stage.archive_sha256='d'*64}
 Case 'floating-EXE-size-refused' $false {param($d)$d.stage.executable_bytes=[double]80068096}
 Case 'expired-artifact-refused' $false {param($d)$d.artifact_expires_utc='2000-01-01T00:00:00Z'}
 Case 'receipt-path-substitution-refused' $false {param($d)$d.evidence.receipt_file='../other.json'}
 Case 'wrong-receipt-SHA-refused' $false {param($d)$d.evidence.receipt_sha256='e'*64}
 Case 'altered-receipt-bytes-refused' $false {param($d)[IO.File]::AppendAllText($receiptPath,' ')}
 [ordered]@{schema_version=1;passed=$true;scope='Actual target accepted; controlled metadata mutations rejected by actual guard; no application, UIA, ZIP or patch execution';helper_sha256=(Get-FileHash (Join-Path $root 'Read-ProducedTarget.ps1') -Algorithm SHA256).Hash.ToLowerInvariant();cases=$rows.ToArray();application_executed=$false;GUI_validated=$false;source_and_receipt_originals_modified=$false}|ConvertTo-Json -Depth 12|Set-Content (Join-Path $PSScriptRoot 'actual-target-checks.json') -Encoding utf8NoBOM
 Write-Host ('PASS: '+$rows.Count+' actual target data controls; no app or GUI executed.')
}finally{if(Test-Path -LiteralPath $work){Remove-Item -LiteralPath $work -Recurse -Force}}
