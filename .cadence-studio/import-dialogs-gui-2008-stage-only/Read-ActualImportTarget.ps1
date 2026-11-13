# SPDX-License-Identifier: GPL-3.0-only
# Data-only guard. This file starts no process and modifies no profile.
Set-StrictMode -Version Latest
function Read-ActualImportTarget([string]$TargetPath,[string]$SelectionDirectory,[switch]$MetadataOnly) {
 $t=Get-Content -LiteralPath $TargetPath -Raw -Encoding UTF8|ConvertFrom-Json
 if($t.schema_version-ne1-or$t.status-cne'reviewed-actual-compiled-stage-known-failed31-GUI-only'-or$t.ready-isnot[bool]-or-not$t.ready-or$t.build_number-ne2008){throw 'Explicitly activated actual2008 StageOnly target required.'}
 if($t.scope-cne'known-failed31-compiled-stage-GUI-only-fullQA-and-MSI-pending'-or$t.producer_run_id-ne43408309742-or$t.producer_job_id-ne131828068954-or$t.run_number-ne12-or$t.run_attempt-ne1-or$t.producer_driver_commit-cne'a8470ae087841875fd39284188d0e9d11d95e32b'-or$t.producer_overall_conclusion-cne'failure'-or$t.expected_failed_step-ne31-or$t.artifact_id-ne14031621703-or$t.full_qualification_complete-isnot[bool]-or$t.full_qualification_complete-or$null-ne$t.MSI){throw 'Only the actually compiled failed31 stage is eligible for GUI; no successful full qualification or MSI is claimed.'}
 if($t.authentication_receipt_sha256-cne'83326738a0ce85a82e3ff3cec6609413c563c25cae77b1ffd2634b9d21cb8933'-or$t.stage.archive_sha256-cne'360ee31bcd6599af40b8d395aad16db732ec32ebabe76b777aed465c274ae830'-or$t.stage.executable_sha256-cne'13cd4e6d2f408d2e64b187d4c3bff1188ff4192ac7b670d3a12373bbeb37f6cd'-or$t.stage.executable_bytes-ne81236992-or$t.stage.archive_bytes-ne148420143-or$t.artifact_digest_from_github_metadata-cne'sha256:8cd00d5df8670837c3b15d3e3bd6e406df290222e404ef88599e4383de048178'){throw 'Exact observed stage/EXE/outer and authentication contract required.'}
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
 if($t.source.original_commit-cne'a2b7abaf045a8f3cb84ec2953d9e0e51b9e78903'-or
    $t.source.tree-cne'c5452043983a048ef0aeef085615af903de3f5b0'-or
    $t.source.patch_sha256-cne'ce7bc369062d6520785169c89d187bf8fa0c9e8dc069315a5e0d75e8f79247b9'){throw 'Produced target must use the reviewed corrected source2008 commit, tree and patch.'}
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
