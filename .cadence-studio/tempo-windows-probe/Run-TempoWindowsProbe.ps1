# SPDX-License-Identifier: GPL-3.0-only
# Compile only the real TempoMap/transport test with two native Windows compilers.
[CmdletBinding()]
param([Parameter(Mandatory)][string]$FrozenDriverPath,[Parameter(Mandatory)][string]$OutputDirectory)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$PSNativeCommandUseErrorActionPreference=$false
if($env:OS-ne'Windows_NT'-or-not[Environment]::Is64BitProcess-or$env:GITHUB_ACTIONS-ne'true'-or$env:CI-ne'true'-or$env:RUNNER_ENVIRONMENT-ne'github-hosted'){throw 'Disposable native Windows x64 hosted CI required.'}
if(-not$env:RUNNER_TEMP){throw 'RUNNER_TEMP is required.'}
$OutputDirectory=[IO.Path]::GetFullPath($OutputDirectory)
$prefix=[IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\','/')+[IO.Path]::DirectorySeparatorChar
if(-not$OutputDirectory.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)-or(Test-Path -LiteralPath $OutputDirectory)){throw 'Output must be new below RUNNER_TEMP.'}
$source=Join-Path $env:RUNNER_TEMP 'cadence-tempo-source-candidate'
if(Test-Path -LiteralPath $source){throw 'Source checkout must be new; no existing path is reused.'}
function Hash([string]$Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
function Get-ProbeGitText([string[]]$Arguments){$text=&git @Arguments 2>&1;$exit=$LASTEXITCODE;if($exit-ne0){throw('Git source operation failed: '+($Arguments-join' ')+'; '+($text-join' '))};return($text-join"`n").Trim()}
$pins=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'pins.json') -Raw -Encoding utf8|ConvertFrom-Json
foreach($entry in @(@('source.json',$pins.source_json_sha256),@('changes.patch.gz',$pins.original_patch_sha256),@('Bootstrap.ps1',$pins.bootstrap_sha256))){if((Hash (Join-Path $FrozenDriverPath $entry[0]))-cne$entry[1]){throw 'Immutable source053 Bootstrap inputs changed.'}}
$patch=Join-Path $PSScriptRoot 'tempo-harness.patch'
if((Hash $patch)-cne$pins.test_patch_sha256){throw 'Reviewed test-only patch changed.'}
[void][IO.Directory]::CreateDirectory($OutputDirectory)
$report=[ordered]@{schema_version=1;status='failed';passed=$false;scope='Two real Windows compiler paths for the production TempoMap transport test only; no Qt or application build'
    driver_commit=$env:GITHUB_SHA;run_id=$env:GITHUB_RUN_ID;original_source_commit=$pins.original_source_commit;candidate_source_commit=$pins.candidate_source_commit;candidate_source_tree=$pins.candidate_source_tree
    application_built=$false;application_executed=$false;qt_installed=$false;compilers=@();source_files=@();error=$null;started_utc=[DateTime]::UtcNow.ToString('o')}
$previousCxx=$env:CXX
try{
    & (Join-Path $FrozenDriverPath 'Bootstrap.ps1') -DriverPath $FrozenDriverPath -SourcePath $source -ResultPath (Join-Path $OutputDirectory 'source-bootstrap.json') *> $null
    if((Get-ProbeGitText @('-C',$source,'rev-parse','HEAD^{tree}'))-cne$pins.original_source_tree){throw 'Original source053 tree differs.'}
    [void](Get-ProbeGitText @('-C',$source,'apply','--index','--binary',$patch))
    if((Get-ProbeGitText @('-C',$source,'write-tree'))-cne$pins.candidate_source_tree){throw 'Reviewed test-only patch did not reconstruct the exact candidate tree.'}
    [void](Get-ProbeGitText @('-C',$source,'-c','user.name=Cadence Tempo QA','-c','user.email=cadence-qa@example.invalid','-c','commit.gpgsign=false','commit','-m','Qualify only the reviewed Windows test macro fix'))
    if(Get-ProbeGitText @('-C',$source,'status','--porcelain','--untracked-files=all')){throw 'Candidate checkout is not clean before testing.'}
    foreach($name in @('test/cadence/test_tempo_change_position.py','src/playback/internal/tempochangeposition.h','src/engraving/dom/tempo.cpp','src/framework/global/thirdparty/kors_logger/src/logger.cpp','src/framework/global/thirdparty/kors_logger/src/logdefdest.cpp','src/framework/global/thirdparty/kors_profiler/profiler/profiler.cpp')){
        $file=Join-Path $source $name;$report.source_files += [ordered]@{path=$name;sha256=Hash $file;bytes=(Get-Item -LiteralPath $file).Length}
    }
    Push-Location $source
    try{
        foreach($compiler in @('g++','cl')){
            $env:CXX=$compiler
            $exe=(Get-Command $compiler -CommandType Application -ErrorAction Stop|Select-Object -First 1).Source
            $name=if($compiler-eq'g++'){'gnu'}else{'msvc'};$log=Join-Path $OutputDirectory ('tempo-'+$name+'.log')
            python -m unittest discover -s test/cadence -p test_tempo_change_position.py -v *> $log
            $exit=$LASTEXITCODE;$text=[IO.File]::ReadAllText($log)
            $passed=$exit-eq0-and$text-match'(?m)^Ran 1 test in [0-9.]+s\s*$'-and$text-match'(?m)^OK\s*$'-and[regex]::Matches($text,'(?m)^PASS:').Count-eq4-and[regex]::Matches($text,'(?m)^PROPERTIES: 1024\s*$').Count-eq1
            $report.compilers += [ordered]@{cxx=$compiler;compiler_path=$exe;exit_code=$exit;passed=$passed;actual_unittest_count=if($passed){1}else{$null};actual_musical_properties=if($passed){1024}else{$null};actual_property_group_passes=if($passed){4}else{$null};log=[IO.Path]::GetFileName($log);log_sha256=Hash $log;log_text=$text}
        }
    }finally{Pop-Location}
    foreach($file in $report.source_files){if((Hash (Join-Path $source $file.path))-cne$file.sha256){throw 'A source changed during the two real compiler tests.'}}
    if((Get-ProbeGitText @('-C',$source,'rev-parse','HEAD^{tree}'))-cne$pins.candidate_source_tree-or(Get-ProbeGitText @('-C',$source,'status','--porcelain','--untracked-files=all'))){throw 'Candidate tree/worktree changed during testing.'}
    if(@($report.compilers).Count-ne2-or@($report.compilers|Where-Object{-not$_.passed}).Count-ne0){throw 'Both GNU and MSVC must pass the real musical transport test without skipping.'}
    $report.passed=$true;$report.status='gnu-and-msvc-production-tempomap-1024-properties-each-passed'
}catch{$report.error=$_.Exception.Message}
finally{
    $env:CXX=$previousCxx;$report.finished_utc=[DateTime]::UtcNow.ToString('o')
    $report|ConvertTo-Json -Depth 12|Set-Content -LiteralPath (Join-Path $OutputDirectory 'tempo-windows-probe.json') -Encoding utf8
    Write-Host 'CADENCE_TEMPO_WINDOWS_PROBE_BEGIN';Write-Host ($report|ConvertTo-Json -Depth 12 -Compress);Write-Host 'CADENCE_TEMPO_WINDOWS_PROBE_END'
}
if(-not$report.passed){throw 'Targeted Windows tempo compiler qualification failed; no full application build started.'}
