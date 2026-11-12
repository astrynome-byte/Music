# SPDX-License-Identifier: GPL-3.0-only
# Source checkout and packaging preflight only. No application, compiler or SDK.
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $FrozenDriverPath,
    [Parameter(Mandatory)][string] $OutputDirectory
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitProcess -or
    $env:GITHUB_ACTIONS -ne 'true' -or $env:CI -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted') { throw 'Only disposable native Windows x64 hosted CI is permitted.' }
if (-not $env:RUNNER_TEMP) { throw 'RUNNER_TEMP is required.' }
$OutputDirectory=[IO.Path]::GetFullPath($OutputDirectory)
$temporary=[IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\','/')+[IO.Path]::DirectorySeparatorChar
if (-not $OutputDirectory.StartsWith($temporary,[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $OutputDirectory)) { throw 'Evidence output must be new and below RUNNER_TEMP.' }
$git=(Get-Command git -CommandType Application -ErrorAction Stop|Select-Object -First 1).Source
$pins=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'pins.json') -Raw -Encoding utf8|ConvertFrom-Json
function Hash([string]$Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
foreach($entry in @(@('source.json',$pins.original_source_json_sha256),@('changes.patch.gz',$pins.original_patch_sha256),@('Bootstrap.ps1',$pins.original_bootstrap_sha256))){if((Hash (Join-Path $FrozenDriverPath $entry[0])) -cne $entry[1]){throw 'Frozen original404 input changed before the checkout probe.'}}
$candidatePatch=Join-Path $PSScriptRoot 'candidate.patch'
if((Hash $candidatePatch)-cne$pins.candidate_patch_sha256){throw 'Reviewed small candidate patch changed.'}
function Invoke-ProbeGit([string]$Root,[string[]]$Arguments,[switch]$AllowFailure){
    $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$git;$info.UseShellExecute=$false;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    if($Root){$info.ArgumentList.Add('-C');$info.ArgumentList.Add($Root)}
    foreach($argument in $Arguments){$info.ArgumentList.Add($argument)}
    $process=[Diagnostics.Process]::new();$process.StartInfo=$info
    try{
        if(-not$process.Start()){throw 'Git metadata command did not start.'}
        $out=$process.StandardOutput.ReadToEndAsync();$err=$process.StandardError.ReadToEndAsync()
        if(-not$process.WaitForExit(60000)){$process.Kill($true);[void]$process.WaitForExit(5000);throw 'Owned Git metadata command timed out.'}
        $stdout=$out.GetAwaiter().GetResult();$stderr=$err.GetAwaiter().GetResult()
        if($stdout.Length-gt131072-or$stderr.Length-gt16384){throw 'Git metadata output exceeded the explicit bound.'}
        $result=[ordered]@{exit_code=$process.ExitCode;stdout=$stdout;stderr=$stderr}
        if(-not$AllowFailure-and$process.ExitCode-ne0){throw ('Git metadata operation failed: '+($Arguments -join ' ')+'; '+$stderr)}
        return $result
    }finally{try{if($process.Id-and-not$process.HasExited){$process.Kill($true);[void]$process.WaitForExit(5000)}}catch{};$process.Dispose()}
}
function GitText([string]$Root,[string[]]$Arguments){(Invoke-ProbeGit $Root $Arguments).stdout.Trim()}
function ConfigRecords([string]$Root){
    $records=@()
    foreach($key in @('core.autocrlf','core.eol','core.safecrlf','core.filemode','core.symlinks','core.ignorecase','core.longpaths')){
        $value=Invoke-ProbeGit $Root @('config','--show-origin','--get-all',$key) -AllowFailure
        if($value.exit_code-notin@(0,1)){throw 'Relevant Git configuration read failed.'}
        $records += [ordered]@{key=$key;exit_code=$value.exit_code;origin_and_value=$value.stdout.Trim()}
    }
    return $records
}
function WorktreeState([string]$Root){
    $status=(Invoke-ProbeGit $Root @('status','--porcelain=v1','--untracked-files=all','-z')).stdout
    $entries=@($status.Split([char]0)|Where-Object{$_})
    $records=@();[int]$position=0
    while($position-lt$entries.Count-and$records.Count-lt50){
        $entry=$entries[$position++];if($entry.Length-lt4){throw 'Invalid bounded porcelain record.'}
        $kind=$entry.Substring(0,2);$path=$entry.Substring(3)
        if($kind-match'R|C'){$position++}
        $full=[IO.Path]::GetFullPath((Join-Path $Root $path));$prefix=[IO.Path]::GetFullPath($Root).TrimEnd('\','/')+[IO.Path]::DirectorySeparatorChar
        if(-not$full.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)){throw 'Dirty path escaped the owned checkout.'}
        $index=Invoke-ProbeGit $Root @('rev-parse',(':'+$path)) -AllowFailure
        $raw=$null;$sha=$null;$bytes=$null
        if(Test-Path -LiteralPath $full -PathType Leaf){
            $file=Get-Item -LiteralPath $full
            if($file.Attributes-band[IO.FileAttributes]::ReparsePoint){throw 'Dirty path is linked; no content was read.'}
            $bytes=$file.Length
            if($bytes-le16777216){$raw=GitText $Root @('hash-object','--no-filters','--',$full);$sha=Hash $full}
        }
        $records += [ordered]@{status=$kind;path=$path;index_blob_sha1=if($index.exit_code-eq0){$index.stdout.Trim()}else{$null};working_raw_blob_sha1=$raw;working_sha256=$sha;working_bytes=$bytes
            eol=GitText $Root @('ls-files','--eol','--',$path);attributes=GitText $Root @('check-attr','text','eol','filter','ident','--',$path)}
    }
    return [ordered]@{clean=-not[bool]$status;porcelain_entries=$entries.Count;reported_paths=$records.Count;path_limit=50;tail_omitted=$position-lt$entries.Count;paths=$records}
}
[void][IO.Directory]::CreateDirectory($OutputDirectory)
$original=Join-Path $env:RUNNER_TEMP 'cadence-source-original404'
$candidate=Join-Path $env:RUNNER_TEMP 'cadence-source-candidate-fixed-attributes'
if((Test-Path $original)-or(Test-Path $candidate)){throw 'Both disposable source paths must be new.'}
$report=[ordered]@{schema_version=1;status='failed';passed=$false;scope='Packaging-only exact source checkout diagnostic and corrected attribute preflight; no application build'
    driver_commit=$env:GITHUB_SHA;run_id=$env:GITHUB_RUN_ID;original_source_commit=$pins.original_source_commit;candidate_source_commit=$pins.candidate_source_commit
    application_built=$false;application_executed=$false;compiler_executed=$false;sdk_installed=$false;original_bad_attributes_never_force_checked_out=$true
    original_bootstrap_error=$null;original=$null;candidate=$null;resource_test=$null;error=$null;started_utc=[DateTime]::UtcNow.ToString('o')}
try{
    try{& (Join-Path $FrozenDriverPath 'Bootstrap.ps1') -DriverPath $FrozenDriverPath -SourcePath $original -ResultPath (Join-Path $OutputDirectory 'original-bootstrap.json') *> $null}catch{$report.original_bootstrap_error=$_.Exception.Message}
    if(-not(Test-Path (Join-Path $original '.git'))){throw 'Original Bootstrap did not reach a source checkout; no normalization conclusion inferred.'}
    $originalTree=GitText $original @('rev-parse','HEAD^{tree}')
    if($originalTree-cne$pins.original_source_tree){throw 'Original HEAD tree differs from the exact404 reference.'}
    $report.original=[ordered]@{tree=$originalTree;source_ci_commit=GitText $original @('rev-parse','HEAD');configs=ConfigRecords $original;worktree=WorktreeState $original
        png_index_blob_sha1=GitText $original @('rev-parse',(':'+$pins.png_path));png_working_sha256=Hash (Join-Path $original $pins.png_path)}
    if($report.original.png_index_blob_sha1-cne$pins.png_original_blob_sha1-or$report.original.png_working_sha256-cne$pins.png_original_sha256){throw 'Original PNG bytes already differ; no unsafe checkout recovery attempted.'}
    [void](Invoke-ProbeGit '' @('clone','--shared','--no-hardlinks','--no-checkout',$original,$candidate))
    [void](Invoke-ProbeGit $candidate @('config','--local','core.autocrlf','false'))
    [void](Invoke-ProbeGit $candidate @('config','--local','core.eol','lf'))
    [void](Invoke-ProbeGit $candidate @('read-tree','HEAD'))
    [void](Invoke-ProbeGit $candidate @('apply','--cached','--binary',$candidatePatch))
    $candidateTree=GitText $candidate @('write-tree')
    if($candidateTree-cne$pins.candidate_source_tree){throw 'Small candidate patch did not reconstruct the reviewed exact tree.'}
    if((GitText $candidate @('rev-parse',(':'+$pins.png_path)))-cne$pins.png_original_blob_sha1){throw 'Candidate patch changed the original PNG blob.'}
    # Only this new candidate index, with corrected binary attributes already
    # installed, may be materialized. Never checkout the known-bad404 PNG rule.
    [void](Invoke-ProbeGit $candidate @('checkout-index','--all','--force'))
    [void](Invoke-ProbeGit $candidate @('-c','user.name=Cadence Source QA','-c','user.email=cadence-qa@example.invalid','-c','commit.gpgsign=false','commit','-m','Verify exact corrected source tree without building the application'))
    $after=WorktreeState $candidate
    $afterTree=GitText $candidate @('rev-parse','HEAD^{tree}')
    $pngSha=Hash (Join-Path $candidate $pins.png_path)
    $report.candidate=[ordered]@{tree=$afterTree;source_ci_commit=GitText $candidate @('rev-parse','HEAD');configs=ConfigRecords $candidate;worktree=$after
        png_index_blob_sha1=GitText $candidate @('rev-parse',(':'+$pins.png_path));png_working_sha256=$pngSha
        png_eol=GitText $candidate @('ls-files','--eol','--',$pins.png_path);png_attributes=GitText $candidate @('check-attr','text','eol','--',$pins.png_path)}
    if(-not$after.clean-or$afterTree-cne$pins.candidate_source_tree-or$pngSha-cne$pins.png_original_sha256){throw 'Corrected candidate is not clean with exact reviewed tree and original PNG bytes.'}
    Push-Location $candidate
    try{
        python -m unittest discover -s test/cadence -p test_resource_attributes.py -v *> (Join-Path $OutputDirectory 'resource-attributes-test.log')
        $testExit=$LASTEXITCODE
    }finally{Pop-Location}
    $testLog=[IO.File]::ReadAllText((Join-Path $OutputDirectory 'resource-attributes-test.log'))
    $passed=$testExit-eq0-and$testLog-match'(?m)^Ran 1 test in [0-9.]+s\s*$'-and$testLog-match'(?m)^OK\s*$'
    $report.resource_test=[ordered]@{exit_code=$testExit;one_real_test_two_autocrlf_subcases_passed=$passed;log='resource-attributes-test.log';sha256=Hash (Join-Path $OutputDirectory 'resource-attributes-test.log')}
    if(-not$passed){throw 'Actual resource checkout test did not pass its one real test and two autocrlf subcases.'}
    $report.passed=$true;$report.status='exact-candidate-clean-and-original-binary-resource-preserved'
}catch{$report.error=$_.Exception.Message}
finally{
    $report.finished_utc=[DateTime]::UtcNow.ToString('o')
    $report|ConvertTo-Json -Depth 15|Set-Content -LiteralPath (Join-Path $OutputDirectory 'source-worktree-probe.json') -Encoding utf8
    Write-Host 'CADENCE_SOURCE_WORKTREE_PROBE_BEGIN';Write-Host ($report|ConvertTo-Json -Depth 15 -Compress);Write-Host 'CADENCE_SOURCE_WORKTREE_PROBE_END'
}
if(-not$report.passed){throw 'Packaging-only source checkout probe failed; inspect exact metadata, no full build started.'}
