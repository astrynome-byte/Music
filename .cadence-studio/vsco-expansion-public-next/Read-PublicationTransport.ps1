# SPDX-License-Identifier: GPL-3.0-only
# Data-only guard for a future exact sounds release; never enables itself.
Set-StrictMode -Version Latest
function Read-PublicationTransport([string]$Path) {
    $target=Get-Content -LiteralPath $Path -Raw -Encoding utf8|ConvertFrom-Json
    if(($target.schema_version-isnot[int]-and$target.schema_version-isnot[long])-or$target.schema_version-ne1-or$target.ready-isnot[bool]-or-not$target.ready){throw 'The actual reviewed ready=true sound target is required.'}
    if($target.repository-isnot[string]-or$target.repository-cne'astrynome-byte/Music'-or$target.scope-cne'vsco_cc0_sounds_only'-or$target.version-cne'1.1.0-exp.1'){throw 'Only this exact sounds-only repository/version is allowed.'}
    if($target.audit.approved-isnot[bool]-or-not$target.audit.approved-or$target.audit.reviewed_by-isnot[string]-or[string]::IsNullOrWhiteSpace($target.audit.reviewed_by)){throw 'Root review of actual bytes and metadata is still required.'}
    if($target.source.application_included-isnot[bool]-or$target.source.application_included-or$target.source.samples_license-cne'CC0-1.0'-or$target.source.converter_license-cne'GPL-3.0-only'-or$target.source.samples_commit-cne'28092772094b2d9f1148d84cea97f4545b8c687d'){throw 'Only the qualified CC0 sounds and independent GPL converter may be distributed.'}
    if($target.release.prerelease-isnot[bool]-or-not$target.release.prerelease-or$target.release.tag-cne'cadence-studio/sounds-vsco-ce-expansion-1.1.0-exp.1'-or$target.release.target_commit_mode-cne'workflow_head'-or$null-ne$target.release.PSObject.Properties['target_commit']-or$target.release.title-isnot[string]-or$target.release.title-notmatch'(?i)sons.*exp[eé]riment'-or$target.release.title.Length-gt140){throw 'An explicitly experimental immutable sounds-only prerelease is required.'}
    if(($target.producer.run_id-isnot[int]-and$target.producer.run_id-isnot[long])-or$target.producer.run_id-ne43304846264-or$target.producer.driver_commit-cne'21e29c9633f13c3e1b4681e5bddbcb5dfc8f4ce5'){throw 'The original successful Windows sound producer must remain pinned.'}
    $ids=@($target.producer.full_run_artifact_ids)
    if($ids.Count-ne1-or($ids[0]-isnot[int]-and$ids[0]-isnot[long])-or$ids[0]-ne13983971420){throw 'Only the actual sound qualification artifact is accepted.'}
    $artifacts=@($target.artifacts)
    if($artifacts.Count-ne1-or($artifacts[0].id-isnot[int]-and$artifacts[0].id-isnot[long])-or($artifacts[0].run_id-isnot[int]-and$artifacts[0].run_id-isnot[long])-or$artifacts[0].id-ne13983971420-or$artifacts[0].run_id-ne43304846264-or$artifacts[0].digest-cne'sha256:bfde75816db71387893d5409ce64a24e456003b27db3d1981f03b9dd334120e8'){throw 'Sound qualification artifact metadata differs.'}
    $expires=[DateTimeOffset]::Parse([string]$artifacts[0].expires_at,[Globalization.CultureInfo]::InvariantCulture)
    if($expires-le[DateTimeOffset]::UtcNow){throw 'The original qualification artifact expired; review proof availability before publishing.'}
    if($target.android.audit_status-cne'reviewed-no-android-release-or-tag-trigger'-or$target.android.main_commit-cne'a6c90b63344b3fd60567fd9f001ac9ecba4b2081'-or$target.android.reviewed_by-isnot[string]-or[string]::IsNullOrWhiteSpace($target.android.reviewed_by)){throw 'Current Android/main/tag trigger review is required.'}
    foreach($name in @('main_workflows','tag_workflows')) {
        $files=@($target.android.$name);if($files.Count-lt1-or$files.Count-gt128){throw 'Exhaustive bounded workflow inventory required.'}
        $seen=[Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
        foreach($file in $files){if($file.path-isnot[string]-or$file.path-cnotmatch'^\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml$'-or$file.blob_sha1-isnot[string]-or$file.blob_sha1-cnotmatch'^[a-f0-9]{40}$'-or-not$seen.Add($file.path)){throw 'Invalid or duplicate workflow identity.'}}
    }
    $rows=@($target.assets);$kinds=[Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    if($rows.Count-ne8){throw 'Exactly eight reviewed sound/source/legal assets required.'}
    foreach($row in $rows){
        if($row.kind-isnot[string]-or$row.kind-cnotin@('sounds','sources','notice','license','checksums','cello_sf2','trumpet_sf2','contrabass_sf2')-or-not$kinds.Add($row.kind)-or$row.name-isnot[string]-or$row.name-cnotmatch'^Cadence-VSCO-(?:CE-[A-Za-z0-9.-]+\.(zip|txt)|(?:Cello-Ensemble|Trumpet|Contrabass)\.sf2)$'-or$row.member_path-cne$row.name-or($row.bytes-isnot[int]-and$row.bytes-isnot[long])-or$row.bytes-lt1-or$row.bytes-gt150000000-or$row.sha256-isnot[string]-or$row.sha256-cnotmatch'^[a-f0-9]{64}$'){throw 'Invalid sound asset identity; no application/MSI is allowed.'}
    }
    return $target
}
function Assert-PublicationProducerRunMetadata($Metadata,$Target) {
    if(($Metadata.id-isnot[int]-and$Metadata.id-isnot[long])-or$Metadata.id-ne43304846264-or$Metadata.head_sha-cne$Target.producer.driver_commit-or$Metadata.repository.full_name-cne'astrynome-byte/Music'-or$Metadata.status-cne'completed'-or$Metadata.conclusion-cne'success'){throw 'Actual successful Windows sound producer metadata differs.'}
}
function Assert-PublicationProducerArtifactMetadata($Metadata,$Target) {
    if(($Metadata.id-isnot[int]-and$Metadata.id-isnot[long])-or$Metadata.id-ne13983971420-or$Metadata.workflow_run.id-ne$Target.producer.run_id-or$Metadata.workflow_run.head_sha-cne$Target.producer.driver_commit-or$Metadata.digest-cne$Target.artifacts[0].digest-or$Metadata.expired-isnot[bool]-or$Metadata.expired){throw 'Actual sound artifact origin/digest/availability differs.'}
}
function Assert-PublicationWorkflowHeadMetadata($Metadata,[string]$ExpectedHead) {
    if($ExpectedHead-cnotmatch'^[a-f0-9]{40}$'-or$Metadata.sha-cne$ExpectedHead){throw 'Actual workflow HEAD differs from GITHUB_SHA.'}
    $files=@($Metadata.files)
    if($files.Count-ne1-or$files[0].filename-cne'.cadence-studio/vsco-expansion-public-next/target.json'-or$files[0].status-cne'added'){throw 'The publishing HEAD must add only the reviewed sound target; recipe/workflows are reviewed in advance.'}
}
