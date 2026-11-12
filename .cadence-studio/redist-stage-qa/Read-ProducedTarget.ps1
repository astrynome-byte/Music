# SPDX-License-Identifier: GPL-3.0-only
# Data-only guards. No network, archive extraction or application execution.
Set-StrictMode -Version Latest
function Get-NextGuiTarget([string] $TargetPath, [string] $SourceSelectionDirectory) {
    $target = Get-Content -LiteralPath $TargetPath -Raw -Encoding utf8 | ConvertFrom-Json
    if (($target.schema_version -isnot [int] -and $target.schema_version -isnot [long]) -or
        $target.schema_version -ne 1 -or $target.status -cne 'reviewed-produced-stage' -or
        $target.build_number -ne 2005 -or $target.run_number -ne 5) { throw 'A reviewed actually produced build2005 stage target is required.' }
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
    $expectedName = 'CadenceStudio-v4.7.6-combined-system-aac-stage-build-2005-attempt-' + $target.run_attempt + '-x64.zip'
    if ($target.stage.archive -cne $expectedName) { throw 'Stage archive does not identify the reviewed build2005 attempt.' }
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
    return $target
}
