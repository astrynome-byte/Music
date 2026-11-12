# SPDX-License-Identifier: GPL-3.0-only
# Structural transport guard only. The inactive template never enables itself.
Set-StrictMode -Version Latest
function Read-PublicationTransport([string]$Path){
    # PowerShell7.5+ otherwise coerces ISO dates and loses their string type.
    # Older PowerShell keeps strings by default and has no DateKind parameter.
    $jsonOptions=@{}
    if((Get-Command ConvertFrom-Json -CommandType Cmdlet).Parameters.ContainsKey('DateKind')){$jsonOptions.DateKind='String'}
    $t=Get-Content -LiteralPath $Path -Raw -Encoding utf8|ConvertFrom-Json @jsonOptions
    if(($t.schema_version-isnot[int]-and$t.schema_version-isnot[long])-or$t.schema_version-ne1-or$t.ready-isnot[bool]-or-not$t.ready-or$t.repository-cne'astrynome-byte/Music'-or$t.version-cne'4.7.6-cadence.2007'-or$t.build_number-ne2007){throw 'The actual reviewed experimental2007 target is required; template is deliberately refused.'}
    if($t.review.approved-isnot[bool]-or-not$t.review.approved-or$t.review.reviewed_by-isnot[string]-or[string]::IsNullOrWhiteSpace($t.review.reviewed_by)){throw 'Actual asset/notices review has not been supplied.'}
    if(($t.producer.run_id-isnot[int]-and$t.producer.run_id-isnot[long])-or$t.producer.run_id-ne43266732201-or$t.producer.driver_commit-cne'c3421a217c76a1b2cc5d4fab74305d209491d82f'){throw 'Only the exact full2007 producer is accepted.'}
    if($t.source.original_commit-cne'5058d29dad67e6131ee46ee617258ccfed8ba4b0'-or$t.source.tree-cne'58d06a1c89e99173b0473587245187df5bc3b3cf'-or$t.source.ci_commit-isnot[string]-or$t.source.ci_commit-cnotmatch'^[a-f0-9]{40}$'-or$t.executable_sha256-isnot[string]-or$t.executable_sha256-cnotmatch'^[a-f0-9]{64}$'-or$t.msi_sha256-isnot[string]-or$t.msi_sha256-cnotmatch'^[a-f0-9]{64}$'){throw 'Actual frozen source/CI/EXE/MSI receipts are absent.'}
    if($t.release.prerelease-isnot[bool]-or-not$t.release.prerelease-or$t.release.target_commit_mode-cne'workflow_head'-or$null-ne$t.release.PSObject.Properties['target_commit']-or$t.release.tag-isnot[string]-or$t.release.tag-cnotmatch'^cadence-studio/v?4\.7\.6-cadence\.2007-experimental\.[1-9][0-9]*$'-or$t.release.title-isnot[string]-or$t.release.title-notmatch'(?i)exp[eé]rimental'-or$t.release.title.Length-gt140){throw 'Only a new explicitly experimental prerelease is permitted.'}
    if($t.limitations.tested_platform-cne'Windows Server 2022 (GitHub Actions)'){throw 'The actual CI platform must remain explicit.'}
    foreach($key in @('windows10_client_tested','windows11_client_tested','human_listening_completed','paid_equivalence_complete','final_gift')){if($t.limitations.$key-isnot[bool]-or$t.limitations.$key){throw 'Unvalidated client/listening/completeness claims are forbidden.'}}
    $artifacts=@($t.artifacts);$ids=[Collections.Generic.HashSet[long]]::new();$roles=[Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    if($artifacts.Count-ne3){throw 'Three original fullrun artifacts are required.'}
    foreach($a in $artifacts){
        if(($a.id-isnot[int]-and$a.id-isnot[long])-or$a.id-le0-or-not$ids.Add($a.id)-or$a.role-cnotin@('stage','delivery','logs')-or-not$roles.Add($a.role)-or$a.run_id-ne43266732201-or$a.digest-isnot[string]-or$a.digest-cnotmatch'^sha256:[a-f0-9]{64}$'-or($a.bytes-isnot[int]-and$a.bytes-isnot[long])-or$a.bytes-lt1-or$a.bytes-gt2147483648-or$a.expires_at-isnot[string]){throw 'Actual distinct artifact IDs, roles, digests, sizes and expiry are required.'}
        $expiry=[DateTimeOffset]::Parse($a.expires_at,[Globalization.CultureInfo]::InvariantCulture);if($expiry-le[DateTimeOffset]::UtcNow){throw 'Original fullrun artifact expired; preserve and re-review provenance.'}
    }
    if($t.android.audit_status-cne'reviewed-no-android-release-or-tag-trigger'-or$t.android.main_commit-cne'a6c90b63344b3fd60567fd9f001ac9ecba4b2081'-or$t.android.reviewed_by-isnot[string]-or[string]::IsNullOrWhiteSpace($t.android.reviewed_by)){throw 'Fresh exact main/tag/release trigger review is required.'}
    foreach($key in @('main_workflows','tag_workflows')){
        $rows=@($t.android.$key);$seen=[Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
        if($rows.Count-lt1-or$rows.Count-gt128){throw 'Complete bounded workflow inventory is absent.'}
        foreach($row in $rows){if($row.path-isnot[string]-or$row.path-cnotmatch'^\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml$'-or$row.blob_sha1-isnot[string]-or$row.blob_sha1-cnotmatch'^[a-f0-9]{40}$'-or-not$seen.Add($row.path)){throw 'Invalid/duplicate workflow identity.'}}
    }
    return $t
}
function Assert-PublicationProducerRunMetadata($Metadata,$Target){
    if($Metadata.id-ne43266732201-or$Metadata.head_sha-cne$Target.producer.driver_commit-or$Metadata.repository.full_name-cne'astrynome-byte/Music'-or$Metadata.status-cne'completed'-or$Metadata.conclusion-cne'success'-or$Metadata.run_number-ne7-or$Metadata.run_attempt-ne1){throw 'Actual successful full2007 producer differs.'}
}
function Assert-PublicationProducerArtifactMetadata($Metadata,$Target){
    $expected=@($Target.artifacts|Where-Object{$_.id-eq$Metadata.id})
    if($expected.Count-ne1-or$Metadata.workflow_run.id-ne43266732201-or$Metadata.workflow_run.head_sha-cne$Target.producer.driver_commit-or$Metadata.digest-cne$expected[0].digest-or$Metadata.name-cne$expected[0].name-or$Metadata.size_in_bytes-ne$expected[0].bytes-or$Metadata.expires_at-cne$expected[0].expires_at-or$Metadata.expired-isnot[bool]-or$Metadata.expired){throw 'Actual original artifact identity/origin/digest/availability differs.'}
}
function Assert-PublicationWorkflowHeadMetadata($Metadata,[string]$ExpectedHead){
    if($ExpectedHead-cnotmatch'^[a-f0-9]{40}$'-or$Metadata.sha-cne$ExpectedHead){throw 'Workflow HEAD differs from GITHUB_SHA.'}
    $files=@($Metadata.files)
    if($files.Count-ne1-or$files[0].filename-cne'.cadence-studio/windows-2007-public-download-next/target.json'-or$files[0].status-cne'added'){throw 'Activation must add only the reviewed target after recipe/workflow review.'}
}
