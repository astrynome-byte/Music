# SPDX-License-Identifier: GPL-3.0-only
# Structural transport guard. An incomplete selection or inactive template fails closed.
Set-StrictMode -Version Latest
function Read-PublicationJson([string]$Path){
    $options=@{}
    if((Get-Command ConvertFrom-Json -CommandType Cmdlet).Parameters.ContainsKey('DateKind')){$options.DateKind='String'}
    return (Get-Content -LiteralPath $Path -Raw -Encoding utf8|ConvertFrom-Json @options)
}
function Get-PublicationArtifactProducer($Target,[string]$Role){
    if($Role-cin@('stage','original_logs')){return $Target.stage_producer}
    if($Role-ceq'qa_logs'){return $Target.qualification_producer}
    if($Role-cin@('delivery','msi_logs')){return $Target.producer}
    throw 'Unknown retained artifact role.'
}
function Get-PublicationArtifactName($Expected,[string]$Role){
    $origin=Get-PublicationArtifactProducer $Expected $Role
    $suffix="$($origin.run_number)-$($origin.run_attempt)"
    switch -CaseSensitive ($Role){
        'stage' {return "cadence-combined-system-aac-stage-experimental-$suffix"}
        'original_logs' {return "cadence-combined-system-aac-logs-$suffix"}
        'qa_logs' {return "cadence-retained2008-resume-logs-$suffix"}
        'delivery' {return "cadence-retained2008-msi-delivery-$suffix"}
        'msi_logs' {return "cadence-retained2008-msi-logs-$suffix"}
    }
    throw 'Unknown retained artifact role.'
}
function Read-PublicationTransport([string]$Path){
    $t=Read-PublicationJson $Path
    $expected=Read-PublicationJson "$PSScriptRoot/expected-inputs.json"
    if($expected.build_number-ne2008-or$expected.product_version-cne'4.7.6.2008'){throw 'Reviewed application build2008 selection required.'}
    foreach($key in @('run_id','job_id','run_number','run_attempt')){
        if(($expected.producer.$key-isnot[int]-and$expected.producer.$key-isnot[long])-or$expected.producer.$key-le0){throw 'Retry producer selection is incomplete; failed attempts produced no MSI.'}
        if($t.producer.$key-ne$expected.producer.$key){throw 'Actual producer run/job/number/attempt differs from the reviewed recipe.'}
    }
    if($expected.producer.driver_commit-isnot[string]-or$expected.producer.driver_commit-cnotmatch'^[a-f0-9]{40}$'-or$t.producer.driver_commit-cne$expected.producer.driver_commit){throw 'Actual driver commit selection required.'}
    foreach($kind in @('stage_producer','qualification_producer')){
        $origin=$expected.$kind;$actual=$t.$kind
        foreach($key in @('run_id','job_id','run_number','run_attempt')){
            if(($origin.$key-isnot[int]-and$origin.$key-isnot[long])-or$origin.$key-le0-or$actual.$key-ne$origin.$key){throw 'Actual source-stage/QA producer differs.'}
        }
        if($origin.driver_commit-cnotmatch'^[a-f0-9]{40}$'-or$actual.driver_commit-cne$origin.driver_commit){throw 'Actual source-stage/QA commit differs.'}
    }
    foreach($key in @('original_commit','tree')){if($expected.source.$key-isnot[string]-or$expected.source.$key-cnotmatch'^[a-f0-9]{40}$'-or$t.source.$key-cne$expected.source.$key){throw 'Actual retry source commit/tree selection required.'}}
    foreach($key in @('source_json_sha256','patch_sha256')){if($expected.source.$key-isnot[string]-or$expected.source.$key-cnotmatch'^[a-f0-9]{64}$'-or$t.source.$key-cne$expected.source.$key){throw 'Actual retry source.json and patch receipts required.'}}
    if(($t.schema_version-isnot[int]-and$t.schema_version-isnot[long])-or$t.schema_version-ne1-or$t.ready-isnot[bool]-or-not$t.ready-or$t.repository-cne'astrynome-byte/Music'-or$t.version-cne'4.7.6-cadence.2008'-or$t.build_number-ne2008){throw 'The actual reviewed experimental2008 target is required; template refused.'}
    if($t.review.approved-isnot[bool]-or-not$t.review.approved-or$t.review.reviewed_by-isnot[string]-or[string]::IsNullOrWhiteSpace($t.review.reviewed_by)){throw 'Actual asset/source/notice review has not been supplied.'}
    if($t.source.ci_commit-isnot[string]-or$t.source.ci_commit-cnotmatch'^[a-f0-9]{40}$'-or$t.executable_sha256-isnot[string]-or$t.executable_sha256-cnotmatch'^[a-f0-9]{64}$'-or$t.msi_sha256-isnot[string]-or$t.msi_sha256-cnotmatch'^[a-f0-9]{64}$'){throw 'Actual frozen source/CI/EXE/MSI receipts are absent.'}
    if($t.source.ci_commit-cne$expected.source.ci_commit-or$t.executable_sha256-cne$expected.executable_sha256){throw 'Retained CI95 or EXE changed.'}
    if($t.release.prerelease-isnot[bool]-or-not$t.release.prerelease-or$t.release.target_commit_mode-cne'workflow_head'-or$null-ne$t.release.PSObject.Properties['target_commit']-or$t.release.tag-isnot[string]-or$t.release.tag-cnotmatch'^cadence-studio/v?4\.7\.6-cadence\.2008-experimental\.[1-9][0-9]*$'-or$t.release.title-isnot[string]-or$t.release.title-notmatch'(?i)exp[eé]rimental'-or$t.release.title.Length-gt140){throw 'Only a new explicitly experimental prerelease is permitted.'}
    if($t.limitations.tested_platform-cne'Windows Server 2022 (GitHub Actions)'){throw 'The actual CI platform must remain explicit.'}
    foreach($key in @('windows10_client_tested','windows11_client_tested','human_listening_completed','paid_equivalence_complete','final_gift','physical_audio_midi_hardware_tested','signed_installer')){if($t.limitations.$key-isnot[bool]-or$t.limitations.$key){throw 'Unvalidated client/listening/hardware/signature/completeness claims are forbidden.'}}
    $artifacts=@($t.artifacts);$ids=[Collections.Generic.HashSet[long]]::new();$roles=[Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    if($artifacts.Count-ne5){throw 'Five exact source-stage/QA/MSI artifact roles are required.'}
    foreach($a in $artifacts){
        $origin=Get-PublicationArtifactProducer $expected $a.role
        $name=Get-PublicationArtifactName $expected $a.role
        if(($a.id-isnot[int]-and$a.id-isnot[long])-or$a.id-le0-or-not$ids.Add($a.id)-or$a.role-cnotin@('stage','original_logs','qa_logs','delivery','msi_logs')-or-not$roles.Add($a.role)-or$a.run_id-ne$origin.run_id-or$a.name-cne$name-or$a.digest-isnot[string]-or$a.digest-cnotmatch'^sha256:[a-f0-9]{64}$'-or($a.bytes-isnot[int]-and$a.bytes-isnot[long])-or$a.bytes-lt1-or$a.bytes-gt2147483648-or$a.expires_at-isnot[string]){throw 'Actual distinct artifact origins/names/IDs/digests/sizes/expiry required.'}
        $known=$expected.original_artifacts.PSObject.Properties[$a.role]
        if($null-ne$known){
            if($a.id-ne$known.Value.id-or$a.digest-cne$known.Value.digest-or$a.bytes-ne$known.Value.size_in_bytes){throw 'Original compiled stage/log artifact changed.'}
        }
        $expiry=[DateTimeOffset]::Parse($a.expires_at,[Globalization.CultureInfo]::InvariantCulture);if($expiry-le[DateTimeOffset]::UtcNow){throw 'Original artifact expired; preserve and re-review provenance.'}
    }
    if($t.android.audit_status-cne'reviewed-no-android-release-or-tag-trigger'-or$t.android.main_commit-cne$expected.android_main_commit-or$t.android.main_commit-cnotmatch'^[a-f0-9]{40}$'-or$t.android.reviewed_by-isnot[string]-or[string]::IsNullOrWhiteSpace($t.android.reviewed_by)){throw 'Fresh exact main/tag/release trigger review is required.'}
    foreach($key in @('main_workflows','tag_workflows')){
        $rows=@($t.android.$key);$seen=[Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
        if($rows.Count-lt1-or$rows.Count-gt128){throw 'Complete bounded workflow inventory is absent.'}
        foreach($row in $rows){if($row.path-isnot[string]-or$row.path-cnotmatch'^\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml$'-or$row.blob_sha1-isnot[string]-or$row.blob_sha1-cnotmatch'^[a-f0-9]{40}$'-or-not$seen.Add($row.path)){throw 'Invalid/duplicate workflow identity.'}}
    }
    return $t
}
function Assert-PublicationProducerRunMetadata($Metadata,$Target){
    if($Metadata.id-ne$Target.producer.run_id-or$Metadata.head_sha-cne$Target.producer.driver_commit-or$Metadata.repository.full_name-cne'astrynome-byte/Music'-or$Metadata.status-cne'completed'-or$Metadata.conclusion-cne'success'-or$Metadata.run_number-ne$Target.producer.run_number-or$Metadata.run_attempt-ne$Target.producer.run_attempt){throw 'Actual successful full2008 producer differs.'}
}
function Assert-PublicationProducerArtifactMetadata($Metadata,$Target){
    $expected=@($Target.artifacts|Where-Object{$_.id-eq$Metadata.id})
    if($expected.Count-ne1){throw 'Exact original artifact ID absent.'}
    $origin=Get-PublicationArtifactProducer $Target $expected[0].role
    if($Metadata.workflow_run.id-ne$origin.run_id-or$Metadata.workflow_run.head_sha-cne$origin.driver_commit-or$Metadata.digest-cne$expected[0].digest-or$Metadata.name-cne$expected[0].name-or$Metadata.size_in_bytes-ne$expected[0].bytes-or$Metadata.expires_at-cne$expected[0].expires_at-or$Metadata.expired-isnot[bool]-or$Metadata.expired){throw 'Actual retained artifact identity/origin/digest/availability differs.'}
}
function Assert-PublicationWorkflowHeadMetadata($Metadata,[string]$ExpectedHead){
    if($ExpectedHead-cnotmatch'^[a-f0-9]{40}$'-or$Metadata.sha-cne$ExpectedHead){throw 'Workflow HEAD differs from GITHUB_SHA.'}
    $files=@($Metadata.files)
    if($files.Count-ne1-or$files[0].filename-cne'.cadence-studio/windows-2008-public-download-next/target.json'-or$files[0].status-cne'added'){throw 'Activation must add only the reviewed target after recipe/workflow review.'}
}
