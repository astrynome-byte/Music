# SPDX-License-Identifier: GPL-3.0-only
# Data-only guard. This file starts no process and modifies no profile.
Set-StrictMode -Version Latest
function Read-ActualImportTarget([string]$TargetPath,[string]$SelectionDirectory,[switch]$MetadataOnly) {
 $t=Get-Content -LiteralPath $TargetPath -Raw -Encoding UTF8|ConvertFrom-Json
 if($t.schema_version-ne1-or$t.status-cne'reviewed-produced-stage'-or$t.build_number-ne2008){throw 'Only a reviewed, actually produced stage2008 target is accepted; the pending template cannot run.'}
 foreach($v in @($t.producer_run_id,$t.artifact_id,$t.run_number,$t.run_attempt)){
  if(($v-isnot[long]-and$v-isnot[int])-or$v-lt1){throw 'Actual positive producer/artifact/attempt identifiers are required.'}
 }
 $producer=Get-Content -LiteralPath "$PSScriptRoot/producer-context.json" -Raw -Encoding UTF8|ConvertFrom-Json
 if($producer.status-cne'reviewed-launched-producer'-or
    ($producer.producer_run_id-isnot[long]-and$producer.producer_run_id-isnot[int])-or$producer.producer_run_id-lt1-or
    $producer.producer_run_id-eq43319506534-or$t.producer_run_id-ne$producer.producer_run_id-or
    $producer.producer_driver_commit-isnot[string]-or$producer.producer_driver_commit-cnotmatch'^[a-f0-9]{40}$'-or
    $t.producer_driver_commit-cne$producer.producer_driver_commit-or
    $t.run_number-ne$producer.producer_run_number-or$t.run_attempt-ne$producer.producer_run_attempt-or
    $t.build_number-ne$producer.expected_build_number){throw 'A reviewed replacement producer is required; the failed original run cannot be used for GUI.'}
 if($t.artifact_digest_from_github_metadata-isnot[string]-or$t.artifact_digest_from_github_metadata-cnotmatch'^sha256:[a-f0-9]{64}$'){throw 'Original artifact digest from GitHub metadata required.'}
 $expires=[DateTimeOffset]::Parse([string]$t.artifact_expires_utc,[Globalization.CultureInfo]::InvariantCulture)
 if($expires-le[DateTimeOffset]::UtcNow){throw 'The reviewed original stage artifact has expired.'}
 $expectedName='CadenceStudio-v4.7.6-combined-system-aac-stage-build-2008-attempt-'+$t.run_attempt+'-x64.zip'
 if($t.stage.archive-cne$expectedName-or$t.artifact_name-cne('cadence-combined-system-aac-stage-experimental-'+$t.run_number+'-'+$t.run_attempt)){throw 'Actual archive/artifact names must identify the reviewed stage2008 attempt.'}
 foreach($name in @('SHA256SUMS.txt','stage-manifest.json','cadence-build.json','cadence-build-result.json')){
  $property=$t.artifact_files.PSObject.Properties[$name]
  if($null-eq$property-or$property.Value.sha256-isnot[string]-or$property.Value.sha256-cnotmatch'^[a-f0-9]{64}$'-or
     ($property.Value.bytes-isnot[int]-and$property.Value.bytes-isnot[long])-or$property.Value.bytes-lt1){throw 'Independently measured external companion SHA256 and byte counts required.'}
 }
 foreach($v in @($t.source.original_commit,$t.source.ci_commit,$t.source.tree)){
  if($v-isnot[string]-or$v-cnotmatch'^[a-f0-9]{40}$'){throw 'Measured actual source commit/tree identifiers required.'}
 }
 # Known frozen source identity; these are not stage/build/executable claims.
 if($t.source.original_commit-cne'49272b75a4107c97130b8a46727af6a8c95d1c9a'-or
    $t.source.tree-cne'fae79e265b3a21431388cd432a853228ffd7676b'-or
    $t.source.patch_sha256-cne'c7654d9a8fa18adf9bcce0b6198c1ef907a2e5886a19339a08ed8ccb80f7b70d'){throw 'Produced target must use the reviewed corrected source2008 commit, tree and patch.'}
 foreach($v in @($t.source.source_json_sha256,$t.source.patch_sha256,$t.stage.archive_sha256,$t.stage.executable_sha256)){
  if($v-isnot[string]-or$v-cnotmatch'^[a-f0-9]{64}$'){throw 'Measured actual source/stage/EXE SHA-256 required.'}
 }
 foreach($v in @($t.stage.archive_bytes,$t.stage.executable_bytes)){
  if(($v-isnot[long]-and$v-isnot[int])-or$v-lt1){throw 'Actual archive and executable byte counts required.'}
 }
 # This mode permits only data-only restoration of the checkout's five pinned
 # binary source inputs. The workflow requires full validation before download.
 if($MetadataOnly){return $t}
 $selectionPath=Join-Path $SelectionDirectory 'source.json'
 $s=Get-Content -LiteralPath $selectionPath -Raw -Encoding UTF8|ConvertFrom-Json
 if($s.schema_version-ne1-or$s.upstream.repository-cne'https://github.com/musescore/MuseScore.git'-or
    $s.upstream.tag-cne'v4.7.6'-or$s.upstream.commit-cne'96480d58445e3b24b230a3fe7d4725d639aa2eb3'){throw 'Frozen source must retain the pinned MuseScore4.7.6 provenance.'}
 if((Get-FileHash $selectionPath -Algorithm SHA256).Hash.ToLowerInvariant()-cne$t.source.source_json_sha256-or
    $s.source.commit-cne$t.source.original_commit-or$s.source.tree-cne$t.source.tree-or$s.patch.sha256-cne$t.source.patch_sha256){throw 'Actual target differs from the frozen source selection.'}
 $patch=Join-Path $SelectionDirectory $s.patch.file
 if($s.patch.file-isnot[string]-or$s.patch.file-cnotmatch'^[A-Za-z0-9][A-Za-z0-9_.-]+$'-or$s.patch.file.Contains('..')){throw 'Frozen source patch must be a plain local filename.'}
 if((Get-FileHash $patch -Algorithm SHA256).Hash.ToLowerInvariant()-cne$t.source.patch_sha256){throw 'Frozen source patch bytes differ.'}
 return $t
}
