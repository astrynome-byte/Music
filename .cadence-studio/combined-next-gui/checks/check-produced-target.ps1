# SPDX-License-Identifier: GPL-3.0-only
# Synthetic data-only control of the actual production function. No ZIP, DLL,
# executable, patch application, COM, MSI, network or Windows job is invoked.
param(
    [string]$HelperPath=(Join-Path $PSScriptRoot '../Read-ProducedTarget.ps1'),
    [string]$RestorePath=(Join-Path $PSScriptRoot '../Restore-NextStage.ps1'),
    [string]$TemplatePath=(Join-Path $PSScriptRoot '../target.json.template'),
    [Parameter(Mandatory)][string]$OutputPath
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$helperSha=(Get-FileHash -LiteralPath $HelperPath -Algorithm SHA256).Hash.ToLowerInvariant()
$restoreSha=(Get-FileHash -LiteralPath $RestorePath -Algorithm SHA256).Hash.ToLowerInvariant()
$tokens=$null;$parseErrors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($HelperPath,[ref]$tokens,[ref]$parseErrors)
if($parseErrors.Count){throw ($parseErrors|Out-String)}
$function=@($ast.FindAll({param($n)$n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -ceq 'Get-NextGuiTarget'},$true))
if($function.Count -ne 1){throw 'Actual Get-NextGuiTarget definition was not uniquely found.'}
. ([scriptblock]::Create($function[0].Extent.Text))
$tokens=$null;$parseErrors=$null
[void][Management.Automation.Language.Parser]::ParseFile($RestorePath,[ref]$tokens,[ref]$parseErrors)
if($parseErrors.Count){throw ($parseErrors|Out-String)}
$temporary=Join-Path ([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($OutputPath))) ('synthetic-target-'+[guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($temporary)
$sourceDirectory=Join-Path $temporary 'source'
[void][IO.Directory]::CreateDirectory($sourceDirectory)
$sourcePath=Join-Path $sourceDirectory 'source.json'
$patchPath=Join-Path $sourceDirectory 'changes.patch.gz'
$targetPath=Join-Path $temporary 'target.json'
$cases=[Collections.Generic.List[object]]::new()
function Save-Json($Value,[string]$Path){$Value|ConvertTo-Json -Depth 12|Set-Content -LiteralPath $Path -Encoding utf8NoBOM}
function Sha([string]$Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
function Copy-Data($Value){$Value|ConvertTo-Json -Depth 12|ConvertFrom-Json -AsHashtable}
function Case([string]$Name,$Data,[bool]$Expected){
    Save-Json $Data $targetPath
    $accepted=$true;$message=$null
    try{[void](Get-NextGuiTarget $targetPath $sourceDirectory)}catch{$accepted=$false;$message=$_.Exception.Message}
    $cases.Add([ordered]@{case=$Name;fixture='explicitly synthetic JSON and inert patch bytes';accepted=$accepted;expected_acceptance=$Expected;passed=$accepted -eq $Expected;rejection=$message})
}
try{
    # Intentionally not a gzip stream: this fixture must never be decompressed or applied.
    [IO.File]::WriteAllText($patchPath,"SYNTHETIC INERT PATCH BYTES; NEVER EXECUTED OR APPLIED`n",[Text.UTF8Encoding]::new($false))
    $source=[ordered]@{schema_version=1;synthetic_fixture=$true;upstream=@{repository='https://github.com/musescore/MuseScore.git';tag='v4.7.6';commit='96480d58445e3b24b230a3fe7d4725d639aa2eb3'};source=@{commit=('1'*40);tree=('2'*40)};patch=@{file='changes.patch.gz';sha256=Sha $patchPath}}
    Save-Json $source $sourcePath
    $base=[ordered]@{schema_version=1;status='reviewed-produced-stage';synthetic_fixture=$true;producer_run_id=[long]123;artifact_id=[long]456;artifact_digest_from_github_metadata=('sha256:'+('a'*64));artifact_expires_utc=[DateTimeOffset]::UtcNow.AddDays(2).ToString('o');build_number=2005;run_number=5;run_attempt=1;source=@{original_commit=('1'*40);ci_commit=('3'*40);tree=('2'*40);source_json_sha256=Sha $sourcePath;patch_sha256=Sha $patchPath};stage=@{archive='CadenceStudio-v4.7.6-combined-system-aac-stage-build-2005-attempt-1-x64.zip';archive_sha256=('b'*64);executable_sha256=('c'*64)}}
    Case 'synthetic valid target accepted (not a produced Windows stage)' $base $true
    $data=Get-Content -LiteralPath $TemplatePath -Raw|ConvertFrom-Json -AsHashtable
    Case 'unfilled production template refused' $data $false
    $data=Copy-Data $base;$data.build_number=2002
    Case 'old build2002 refused' $data $false
    $data=Copy-Data $base;$data.stage.archive='CadenceStudio-v4.7.6-combined-system-aac-stage-build-2002-attempt-1-x64.zip'
    Case 'archive naming old build2002 refused' $data $false
    $data=Copy-Data $base;$data.source.tree='4'*40
    Case 'wrong source tree refused against real source.json bytes' $data $false
    $data=Copy-Data $base;$data.source.source_json_sha256='d'*64
    Case 'wrong source.json SHA256 refused' $data $false
    $data=Copy-Data $base;$data.source.patch_sha256='e'*64
    Case 'wrong inert patch SHA256 refused' $data $false
    foreach($name in @('producer_run_id','artifact_id','run_attempt')){
        $data=Copy-Data $base;$data.Remove($name)
        Case ('missing '+$name+' refused') $data $false
        $data=Copy-Data $base;$data[$name]=$true
        Case ('boolean '+$name+' refused') $data $false
    }
    $data=Copy-Data $base;$data.artifact_expires_utc='2000-01-01T00:00:00Z'
    Case 'expired archive metadata refused' $data $false
    $data=Copy-Data $base;$data.stage.Remove('executable_sha256')
    Case 'missing executable SHA256 refused' $data $false
    $data=Copy-Data $base;$data.artifact_digest_from_github_metadata='metadata-digest-not-a-sha256'
    Case 'invalid original container digest refused' $data $false
    # Probe numeric identity fields too: PowerShell comparison can coerce true to 1.
    foreach($name in @('schema_version','build_number','run_number')){
        $data=Copy-Data $base;$data[$name]=$true
        Case ('boolean identity field '+$name+' refused') $data $false
    }
    $source.schema_version=$true;Save-Json $source $sourcePath
    $data=Copy-Data $base;$data.source.source_json_sha256=Sha $sourcePath
    Case 'boolean source schema_version refused despite matching file SHA' $data $false
    $source.schema_version=1;Save-Json $source $sourcePath
    $failed=@($cases|Where-Object {-not $_.passed})
    if((Sha $HelperPath) -cne $helperSha -or (Sha $RestorePath) -cne $restoreSha){throw 'Helper changed while testing; repeat against one frozen version.'}
    $report=[ordered]@{schema_version=1;status=if($failed.Count){'failed'}else{'passed'};scope='Actual Get-NextGuiTarget AST definition replayed with explicitly synthetic JSON and inert bytes; Restore-NextStage parse only';helper_path=$HelperPath;helper_sha256=$helperSha;restore_path=$RestorePath;restore_sha256=$restoreSha;helper_parse_errors=0;restore_parse_errors=0;cases=$cases.ToArray();cases_passed=$cases.Count-$failed.Count;cases_total=$cases.Count;application_executed=$false;patch_applied_or_executed=$false;zip_extracted=$false;COM_or_MSI_used=$false;windows_job_started=$false;product_or_helper_modified=$false;fixture_tree_deleted_after_checks=$true}
    Save-Json $report $OutputPath
    Write-Host ($report.status.ToUpperInvariant()+' '+$report.cases_passed+'/'+$report.cases_total+' synthetic data-only cases; no produced stage or Windows validation claimed.')
    if($failed.Count){$failed|ForEach-Object {Write-Host ('FAILED: '+$_.case)};exit 1}
}finally{
    if(Test-Path -LiteralPath $temporary){Remove-Item -LiteralPath $temporary -Recurse -Force}
}
