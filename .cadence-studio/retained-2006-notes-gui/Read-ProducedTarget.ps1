# SPDX-License-Identifier: GPL-3.0-only
# Data-only guards. No network, archive extraction or application execution.
Set-StrictMode -Version Latest
function Get-NextGuiTarget([string] $TargetPath, [string] $SourceSelectionDirectory) {
    $target = Get-Content -LiteralPath $TargetPath -Raw -Encoding utf8 | ConvertFrom-Json
    if (($target.schema_version -isnot [int] -and $target.schema_version -isnot [long]) -or
        $target.schema_version -ne 1 -or $target.status -cne 'reviewed-produced-stage' -or
        $target.build_number -ne 2006 -or $target.run_number -ne 6) { throw 'A reviewed actually produced build2006 stage target is required.' }
    foreach ($value in @($target.producer_run_id,$target.artifact_id,$target.run_attempt,$target.build_number,$target.run_number)) {
        if (($value -isnot [long] -and $value -isnot [int]) -or $value -lt 1) { throw 'Actual positive producer run/artifact/attempt identifiers are required.' }
    }
    foreach ($value in @($target.source.original_commit,$target.source.ci_commit,$target.source.tree)) {
        if ($value -isnot [string] -or $value -cnotmatch '^[a-f0-9]{40}$') { throw 'Full actually produced source commit/tree identities are required.' }
    }
    foreach ($value in @($target.source.source_json_sha256,$target.source.patch_sha256,$target.stage.archive_sha256,$target.stage.executable_sha256)) {
        if ($value -isnot [string] -or $value -cnotmatch '^[a-f0-9]{64}$') { throw 'Full actually measured SHA256 values are required.' }
    }
    if ($target.artifact_digest_from_github_metadata -isnot [string] -or $target.artifact_digest_from_github_metadata -cnotmatch '^sha256:[a-f0-9]{64}$') { throw 'Record the original container digest explicitly as GitHub metadata.' }
    $expires = [DateTimeOffset]::Parse([string]$target.artifact_expires_utc,[Globalization.CultureInfo]::InvariantCulture)
    if ($expires -le [DateTimeOffset]::UtcNow) { throw 'The retained stage artifact has expired; no old download is silently substituted.' }
    $expectedName = 'CadenceStudio-v4.7.6-combined-system-aac-stage-build-2006-attempt-' + $target.run_attempt + '-x64.zip'
    if ($target.stage.archive -cne $expectedName) { throw 'Stage archive does not identify the reviewed build2006 attempt.' }
    $sourcePath = Join-Path $SourceSelectionDirectory 'source.json'
    $patchPath = Join-Path $SourceSelectionDirectory 'changes.patch.gz'
    if ((Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $target.source.source_json_sha256 -or
        (Get-FileHash -LiteralPath $patchPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $target.source.patch_sha256) { throw 'Frozen source selection/patch bytes differ from the reviewed produced stage.' }
    $source = Get-Content -LiteralPath $sourcePath -Raw -Encoding utf8 | ConvertFrom-Json
    if (($source.schema_version -isnot [int] -and $source.schema_version -isnot [long]) -or
        $source.schema_version -ne 1 -or $source.upstream.repository -cne 'https://github.com/musescore/MuseScore.git' -or
        $source.upstream.tag -cne 'v4.7.6' -or $source.upstream.commit -cne '96480d58445e3b24b230a3fe7d4725d639aa2eb3' -or
        $source.source.commit -cne $target.source.original_commit -or $source.source.tree -cne $target.source.tree -or
        $source.patch.file -cne 'changes.patch.gz' -or $source.patch.sha256 -cne $target.source.patch_sha256) { throw 'Produced target differs from the frozen Cadence source provenance.' }
    # Bind this one actual stage to the authenticated DATAONLY receipt. No new
    # stage-manifest is synthesized; restoration reads its original artifact.
    if ($target.producer_run_id -ne 43233124321 -or $target.artifact_id -ne 13955301913 -or $target.run_attempt -ne 1 -or
        $target.source.original_commit -cne 'ac9a24933f78f22ea630570910848201baad3d3b' -or
        $target.source.ci_commit -cne '536d13cf1caba07197deccefc9f880d8a77902e0' -or
        $target.source.tree -cne 'a94a09974229c47e7b90b593a7649c29d6a6d190' -or
        $target.source.source_json_sha256 -cne '0d6c5944374cfa2b58ee8f81a3912b36585ed263ed79ffb3ff1968f2bd07ca1b' -or
        $target.source.patch_sha256 -cne 'cba5d10112b8cd7ce470577e07cc70fb8d1cd849ec412b652c0a6b71bf4e3ce7' -or
        $target.stage.archive_sha256 -cne 'b6b6bb9160250282879543b44e1ca8217494285e86c47fb2003f8b24dd93954c' -or
        $target.stage.executable_sha256 -cne 'c29d7c8c76b213b79d7390acd65cbabc6fb940f06e3e7f86c0ce60be7e9b9520' -or
        $target.artifact_digest_from_github_metadata -cne 'sha256:c93aa9eb68a5a7e21b80c19b150d9d9731532e91d2abb778f87342317417443b') {
        throw 'Target differs from the one actually authenticated stage2006.'
    }
    foreach ($pair in @(@($target.stage.archive_bytes,148007535),@($target.stage.executable_bytes,80068096))) {
        if (($pair[0] -isnot [int] -and $pair[0] -isnot [long]) -or $pair[0] -ne $pair[1]) { throw 'Actually measured stage/EXE byte counts differ.' }
    }
    $receiptPath = Join-Path ([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($TargetPath))) 'data-authentication.json'
    if ($target.evidence.receipt_file -cne 'data-authentication.json' -or
        $target.evidence.receipt_sha256 -cne '3ddf8d61b2a2223c23e836b7d063e218418c7f9013895741c83bdd17bc28e4cd' -or
        (Get-FileHash -LiteralPath $receiptPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $target.evidence.receipt_sha256) {
        throw 'The reviewed authenticated-marker receipt bytes differ.'
    }
    $receipt = Get-Content -LiteralPath $receiptPath -Raw -Encoding utf8 | ConvertFrom-Json
    if ($receipt.status -cne 'authenticated-actual-2006-stage-and-delivery-as-data' -or $null -ne $receipt.error -or
        $receipt.application_executed -isnot [bool] -or $receipt.application_executed -or
        $receipt.original_source_commit -cne $target.source.original_commit -or $receipt.source_commit -cne $target.source.ci_commit -or
        $receipt.source_tree -cne $target.source.tree -or $receipt.source_json_sha256 -cne $target.source.source_json_sha256 -or
        $receipt.source_patch_sha256 -cne $target.source.patch_sha256 -or $receipt.producer_run_id -ne $target.producer_run_id -or
        $receipt.stage_archive.sha256 -cne $target.stage.archive_sha256 -or $receipt.executable.sha256 -cne $target.stage.executable_sha256 -or
        $receipt.inner_stage_files_equal -isnot [bool] -or -not $receipt.inner_stage_files_equal -or $receipt.inner_stage_files_hashed -ne 2705) {
        throw 'The authenticated receipt no longer corroborates this stage target.'
    }
    return $target
}
