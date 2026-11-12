# SPDX-License-Identifier: GPL-3.0-only
#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $OldArtifactDirectory,
    [Parameter(Mandatory)][string] $CandidateArtifactDirectory,
    [Parameter(Mandatory)][string] $OutputDirectory
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if (-not [OperatingSystem]::IsWindows() -or $env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitProcess -or
    [Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne 'X64' -or $env:GITHUB_ACTIONS -ne 'true' -or
    $env:CI -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted') {
    throw 'Input verification requires a disposable native Windows x64 GitHub-hosted runner.'
}
if (-not $env:RUNNER_TEMP) { throw 'RUNNER_TEMP is required.' }
function Hash([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function FullPath([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path) -or $Path -match '[;\r\n"\x00*?]') { throw 'Unsupported input path.' }
    $full=[IO.Path]::GetFullPath($Path);$current=$full
    while ($current) {
        if ((Test-Path -LiteralPath $current) -and ((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Reparse points are forbidden.' }
        $parent=[IO.Path]::GetDirectoryName($current.TrimEnd('\','/'));if(-not $parent -or $parent -eq $current){break};$current=$parent
    }
    $full
}
function IsBelow([string]$Child,[string]$Parent) { $Child.StartsWith($Parent.TrimEnd('\','/')+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase) }
function ReadJson([string]$Path) { Get-Content -LiteralPath $Path -Raw -Encoding utf8 | ConvertFrom-Json }
function WriteJson($Value,[string]$Name) { $Value | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath (Join-Path $OutputDirectory $Name) -Encoding utf8NoBOM }
$OldArtifactDirectory=FullPath $OldArtifactDirectory;$CandidateArtifactDirectory=FullPath $CandidateArtifactDirectory;$OutputDirectory=FullPath $OutputDirectory
$temp=FullPath $env:RUNNER_TEMP
foreach($path in @($OldArtifactDirectory,$CandidateArtifactDirectory,$OutputDirectory)) { if(-not(IsBelow $path $temp)){throw 'All paths must be strictly below RUNNER_TEMP.'} }
if((Test-Path -LiteralPath $OutputDirectory) -or (IsBelow $OutputDirectory $OldArtifactDirectory) -or (IsBelow $OldArtifactDirectory $OutputDirectory) -or
   (IsBelow $OutputDirectory $CandidateArtifactDirectory) -or (IsBelow $CandidateArtifactDirectory $OutputDirectory) -or
   $OutputDirectory -eq $OldArtifactDirectory -or $OutputDirectory -eq $CandidateArtifactDirectory) { throw 'New output and both original artifacts must be separate.' }
[void][IO.Directory]::CreateDirectory($OutputDirectory)
$selection=ReadJson (Join-Path $PSScriptRoot 'selection.json')
$report=[ordered]@{schema_version=1;status='blocked';started_utc=[DateTime]::UtcNow.ToString('o');finished_utc=$null;error=$null;selection=$selection;old=$null;candidate=$null;application_executed=$false;installer_executed=$false;application_recompiled=$false;original_files_modified=$false;outer_zip_raw_digest_verified_by_this_script=$false;transport='actions/download-artifact@v4 pinned immutable artifact-id and run-id; its download log reports transport digest';source_validation_scope='Source archive bytes authenticated against complete checksums in the pinned immutable delivery; identity linked by original stage and retained package records. Source tree is not independently reconstructed.'}
function CheckSums([string]$Root) {
    $sums=Join-Path $Root 'SHA256SUMS.txt';if(-not(Test-Path -LiteralPath $sums -PathType Leaf)){throw 'Complete delivery SHA256SUMS.txt is required.'}
    $entries=@{}
    foreach($line in Get-Content -LiteralPath $sums) {
        if($line -notmatch '^([a-fA-F0-9]{64})  (.+)$'){throw 'Malformed artifact checksum line.'}
        $digest=$Matches[1].ToLowerInvariant();$name=$Matches[2].Replace('\','/')
        if($name.StartsWith('/') -or $name -match '[:\x00-\x1f]' -or $name.Split('/') -contains '..' -or $name.Split('/') -contains '.' -or $entries.ContainsKey($name) -or $name -eq 'SHA256SUMS.txt'){throw 'Unsafe/duplicate checksum path.'}
        $file=FullPath (Join-Path $Root $name)
        if(-not(IsBelow $file $Root) -or -not(Test-Path -LiteralPath $file -PathType Leaf) -or (Hash $file) -ne $digest){throw "Artifact member hash mismatch: $name"}
        $entries[$name]=$digest
    }
    foreach($file in Get-ChildItem -LiteralPath $Root -Recurse -Force) {
        if($file.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Artifact contains a reparse point.'}
        if($file.PSIsContainer){continue}
        $relative=[IO.Path]::GetRelativePath($Root,$file.FullName).Replace('\','/')
        if($relative -ne 'SHA256SUMS.txt' -and -not $entries.ContainsKey($relative)){throw "Artifact member is not covered by SHA256SUMS: $relative"}
    }
    [pscustomobject]@{checksum_sha256=Hash $sums;members=$entries}
}
function VerifyDelivery([string]$Directory,$Pin) {
    $msis=@(Get-ChildItem -LiteralPath $Directory -Recurse -File -Filter $Pin.msi_filename)
    if($msis.Count -ne 1){throw 'Expected exactly one pinned MSI.'}
    $root=FullPath $msis[0].DirectoryName;$checks=CheckSums $root
    if((Hash $msis[0].FullName) -ne $Pin.msi_sha256){throw 'Actual MSI does not match the independent pin.'}
    $original=Join-Path $root 'original-stage';$originalChecks=CheckSums $original
    $manifest=ReadJson (Join-Path $original 'stage-manifest.json')
    $build=ReadJson (Join-Path $original 'cadence-build.json');$result=ReadJson (Join-Path $original 'cadence-build-result.json')
    $package=ReadJson (Join-Path $root 'retained-package-manifest.json')
    if($manifest.schema_version -ne 1 -or $build.schema_version -ne 1 -or $result.schema_version -ne 1 -or $package.schema_version -ne 1 -or
       $manifest.variant -ne 'Cadence' -or $build.variant -ne 'Cadence' -or $manifest.build_number -ne $Pin.build_number -or $build.build_number -ne $Pin.build_number -or
       $manifest.source_tree -ne $Pin.source_tree -or
       $manifest.source_commit -ne $Pin.payload_ci_commit -or $build.source_commit -ne $Pin.payload_ci_commit -or $result.source_commit -ne $Pin.payload_ci_commit -or
       $manifest.configuration -ne 'Release' -or $build.configuration -ne 'Release' -or $build.source_dirty_at_configure -ne $false -or $result.source_dirty_at_build -ne $false -or
       $manifest.upstream_tag -ne 'v4.7.6' -or $manifest.upstream_commit -ne '96480d58445e3b24b230a3fe7d4725d639aa2eb3' -or
       $manifest.qt_version -ne '6.10.2' -or $build.qt_version -ne '6.10.2' -or
       $manifest.executable_sha256 -ne $Pin.executable_sha256 -or $result.executable_sha256 -ne $Pin.executable_sha256 -or
       $manifest.stage_archive_sha256 -ne $Pin.stage_archive_sha256 -or $originalChecks.members[$manifest.stage_archive] -ne $Pin.stage_archive_sha256 -or
       $package.original_source_commit -ne $Pin.original_source_commit -or $package.payload_source_commit -ne $Pin.payload_ci_commit -or
       $package.payload_source_tree -ne $Pin.source_tree -or $package.packaging_source_tree -ne $Pin.source_tree -or $package.build_number -ne $Pin.build_number -or
       $package.application_recompiled -ne $false -or $package.source_unchanged -ne $true -or $package.payload_unchanged -ne $true -or
       $package.original_stage_archive_sha256 -ne $Pin.stage_archive_sha256 -or $package.installer -ne $Pin.msi_filename -or $package.installer_sha256 -ne $Pin.msi_sha256){throw 'Source/stage/package provenance does not identify the pinned immutable MSI payload.'}
    foreach($name in @($Pin.source_archive,$Pin.source_patch)) {if(-not $checks.members.ContainsKey($name)){throw 'Corresponding source archive/patch is missing.'}}
    if($Pin.build_number -eq 2002) {
        if($checks.checksum_sha256 -ne $Pin.delivery_checksum_sha256 -or $checks.members.Count -ne 37 -or
            $checks.members[$Pin.source_archive] -ne $Pin.source_archive_sha256 -or $checks.members[$Pin.source_patch] -ne $Pin.source_patch_sha256 -or
            (Get-Item -LiteralPath (Join-Path $root $Pin.source_archive)).Length -ne $Pin.source_archive_bytes -or
            (Get-Item -LiteralPath (Join-Path $root $Pin.source_patch)).Length -ne $Pin.source_patch_bytes -or
            $msis[0].Length -ne $Pin.msi_bytes){throw 'Independent complete-delivery/source/MSI2002 byte pins differ.'}
        if($manifest.original_source_commit -ne $Pin.original_source_commit){throw 'Candidate original source commit differs.'}
        foreach($property in $selection.candidate_original_raw_pins.PSObject.Properties) {
            $path=Join-Path $original $property.Name;if((Hash $path) -ne $property.Value){throw "Pinned raw stage metadata differs: $($property.Name)"}
        }
        if($build.windows_system_aac -ne $true -or $build.open_source_zlib.pinned_ci_verified -ne $true -or
            $checks.members['Cadence-zlib-1.3.2-corresponding-source.zip'] -ne '7254e29e7c3aed673cd29d46353aa8ddd758b22b4b1ee41b6d4d194155b740ae'){throw 'Candidate system AAC/open-source zlib/source records differ.'}
    }
    $zip=[IO.Compression.ZipFile]::OpenRead((Join-Path $original $manifest.stage_archive))
    try {
        $names=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase);[long]$expanded=0
        foreach($entry in $zip.Entries) {
            $name=$entry.FullName.Replace('\','/');while($name.StartsWith('./')){$name=$name.Substring(2)}
            if($name -in @('','.','/')){continue};$normalized=$name.TrimEnd('/')
            if($name.StartsWith('/') -or $name -match '[:\x00-\x1f]' -or $name.Split('/') -contains '..' -or -not $names.Add($normalized) -or
               (($entry.ExternalAttributes -shr 16) -band 61440) -eq 40960 -or ($entry.ExternalAttributes -band 1024)){throw 'Unsafe/linked/duplicate original stage ZIP member.'}
            $expanded+=$entry.Length;if($expanded -gt 5368709120 -or $zip.Entries.Count -gt 100000){throw 'Original stage ZIP exceeds bounds.'}
        }
        $exe=$zip.GetEntry('bin/CadenceStudio4.exe');if($null -eq $exe -or $exe.Length -ne $Pin.executable_bytes){throw 'Original executable entry length differs.'}
        $stream=$exe.Open();try{$digest=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($stream)).ToLowerInvariant()}finally{$stream.Dispose()}
        if($digest -ne $Pin.executable_sha256){throw 'Original executable bytes differ before any installation or execution.'}
    } finally {$zip.Dispose()}
    [pscustomobject]@{artifact_id=$Pin.artifact_id;run_id=$Pin.run_id;delivery_root=$root;msi_path=$msis[0].FullName;msi_sha256=$Pin.msi_sha256;executable_sha256=$digest;source_archive=$Pin.source_archive;source_archive_sha256=$checks.members[$Pin.source_archive];source_patch=$Pin.source_patch;source_patch_sha256=$checks.members[$Pin.source_patch];source_tree=$Pin.source_tree;source_commit=$Pin.original_source_commit;payload_ci_commit=$Pin.payload_ci_commit;delivery_checksum_sha256=$checks.checksum_sha256;verified_delivery_members=$checks.members.Count;original_checksum_sha256=$originalChecks.checksum_sha256;original_stage_manifest=$manifest;retained_package_manifest=$package}
}
try {
    $report.old=VerifyDelivery $OldArtifactDirectory $selection.old
    $report.candidate=VerifyDelivery $CandidateArtifactDirectory $selection.candidate
    $report.status='passed'
} catch {$report.error=$_.Exception.Message;throw}
finally {$report.finished_utc=[DateTime]::UtcNow.ToString('o');WriteJson $report 'input-verification.json';Write-Host 'CADENCE_UPGRADE_INPUTS_BEGIN';Write-Host ($report | ConvertTo-Json -Depth 30 -Compress);Write-Host 'CADENCE_UPGRADE_INPUTS_END'}
