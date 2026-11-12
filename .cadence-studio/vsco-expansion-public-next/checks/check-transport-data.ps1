# Data-only checks; never execute the publisher, a GitHub command, or an application.
param([Parameter(Mandatory)][string]$Support)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
. (Join-Path $Support 'Read-PublicationTransport.ps1')
$raw=Get-Content -LiteralPath (Join-Path $Support 'target.json.template') -Raw -Encoding utf8
$temporary=Join-Path ([IO.Path]::GetTempPath()) ('cadence-vsco-data-only-'+[guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($temporary)
$records=[Collections.Generic.List[object]]::new()
function Data-Target {
    $item=$raw|ConvertFrom-Json
    $item.ready=$true;$item.audit.approved=$true;$item.audit.reviewed_by='SYNTHETIC DATA TEST, NO APPROVAL'
    $item.android.audit_status='reviewed-no-android-release-or-tag-trigger'
    $item.android.reviewed_by='SYNTHETIC DATA TEST, NO APPROVAL'
    $item.android.tag_workflows=@([pscustomobject]@{path='.github/workflows/data-only.yml';blob_sha1=('0'*40)})
    return $item
}
function Check([string]$Name,$Data,[bool]$Accept) {
    $path=Join-Path $temporary ($Name+'.json')
    $Data|ConvertTo-Json -Depth 20|Set-Content -LiteralPath $path -Encoding utf8NoBOM
    $accepted=$false;$errorText=$null
    try{[void](Read-PublicationTransport $path);$accepted=$true}catch{$errorText=$_.Exception.Message}
    if($accepted-ne$Accept){throw ('Unexpected data guard result: '+$Name+': '+$errorText)}
    $records.Add([ordered]@{name=$Name;accepted=$accepted;expected_accept=$Accept;error=$errorText})
}
try {
    Check 'false-template' ($raw|ConvertFrom-Json) $false
    Check 'synthetic-structural-only' (Data-Target) $true
    $x=Data-Target;$x.ready='true';Check 'ready-string' $x $false
    $x=Data-Target;$x.ready=1;Check 'ready-integer' $x $false
    $x=Data-Target;$x.audit.approved='true';Check 'approval-string' $x $false
    $x=Data-Target;$x.source.application_included=$true;Check 'application-included' $x $false
    $x=Data-Target;$x.repository='someone/else';Check 'wrong-repository' $x $false
    $x=Data-Target;$x.release.prerelease=$false;Check 'final-release' $x $false
    $x=Data-Target;$x.release.tag='other/tag';Check 'other-tag' $x $false
    $x=Data-Target;$x.producer.run_id='43304846264';Check 'producer-id-string' $x $false
    $x=Data-Target;$x.artifacts[0].id='13983971420';Check 'artifact-id-string' $x $false
    $x=Data-Target;$x.android.tag_workflows=@();Check 'missing-workflow-inventory' $x $false
    $x=Data-Target;$x.assets[0].kind='msi';Check 'installer-kind' $x $false
    $x=Data-Target;$x.assets[0].bytes='91157947';Check 'asset-size-string' $x $false
    $receipt=[ordered]@{schema_version=1;scope='Synthetic transport/schema data only; no real approval or network';checks=$records.Count;records=$records;publication_performed=$false}
    $receipt|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $PSScriptRoot 'transport-data-results.json') -Encoding utf8NoBOM
    Write-Output ('PASS '+$records.Count+' actual PowerShell transport data checks; no network or publication.')
} finally {
    foreach($file in [IO.Directory]::GetFiles($temporary)){[IO.File]::Delete($file)}
    [IO.Directory]::Delete($temporary)
}
