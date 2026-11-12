# SPDX-License-Identifier: GPL-3.0-only
# SOURCE ONLY until separately dispatched on a disposable Windows CI runner.
# Read named installed files as data; never load a candidate DLL or run a tool/app.
#Requires -Version 7.2
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $OutputDirectory,
    [string] $TargetManifestPath = (Join-Path $PSScriptRoot 'full2005-dll-targets.json')
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
# This guard precedes all path access, output creation and Windows metadata APIs.
if (-not [OperatingSystem]::IsWindows() -or $env:OS -ne 'Windows_NT' -or
    [Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne 'X64' -or
    [Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture -ne 'X64' -or
    -not [Environment]::Is64BitProcess -or $env:CI -ne 'true' -or
    $env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted') {
    throw 'Only disposable native Windows x64 GitHub-hosted CI is permitted; no paths accessed.'
}

$manifestSha='25af2bdca7ef2dc68409210698a117d259fb0e42fcd922b416b301e012f6048a'
$captureSha='3e31f457bab3cf92bb60ae7b5a1df06e68e2baf8ad802b9edce296ad61d4d210'
$executableSha='d957ffc99497cb01b1f00f82ba1d6e89ef84547708506c6c51423675805e140a'
$d3dNames=@('d3dcompiler_47.dll','dxcompiler.dll','dxil.dll')
$systemNames=@('d3dcompiler_47.dll','dxcompiler.dll','dxil.dll','icuuc.dll')
$crtNames=@('concrt140.dll','msvcp140.dll','msvcp140_1.dll','msvcp140_2.dll',
    'msvcp140_atomic_wait.dll','msvcp140_codecvt_ids.dll','vcruntime140.dll','vcruntime140_1.dll')
$allCaptureNames=@($systemNames+$crtNames+'opengl32sw.dll')

function Plain([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path) -or $Path.Length -gt 1024 -or
        $Path -match '[\x00-\x1f*?<>|\[\]"]' -or $Path -notmatch '^[A-Za-z]:\\' -or
        $Path.Substring(2).Contains(':') -or $Path -match '(^|\\)\.\.?($|\\)') {
        throw 'Only unambiguous absolute local drive paths are permitted.'
    }
    $full=[IO.Path]::GetFullPath($Path)
    foreach($component in $full.Substring(3).TrimEnd('\').Split('\')) {
        if($component.EndsWith(' ') -or $component.EndsWith('.')){throw 'Ambiguous path suffix refused.'}
    }
    for($current=$full;$current;$current=[IO.Path]::GetDirectoryName($current)) {
        try {$attributes=[IO.File]::GetAttributes($current)}
        catch [IO.FileNotFoundException] {continue}
        catch [IO.DirectoryNotFoundException] {continue}
        if($attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Reparse point refused for named metadata reads.'}
    }
    return $full.TrimEnd('\')
}
function Below([string]$Child,[string]$Parent) {
    $Child.StartsWith($Parent.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)
}
function Hash([string]$Path) {
    $stream=[IO.FileStream]::new($Path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
    $algorithm=[Security.Cryptography.SHA256]::Create()
    try {
        if($stream.Length -gt 67108864){throw 'Bounded hash input is too large.'}
        return [Convert]::ToHexString($algorithm.ComputeHash($stream)).ToLowerInvariant()
    }
    finally {$algorithm.Dispose();$stream.Dispose()}
}
function Read-BoundedBytes([string]$Path,[int]$Maximum) {
    [void](Plain $Path)
    $stream=[IO.FileStream]::new($Path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
    try {
        if($stream.Length -gt $Maximum){throw 'Bounded input is too large.'}
        $bytes=[byte[]]::new([int]$stream.Length);$offset=0
        while($offset -lt $bytes.Length) {
            $count=$stream.Read($bytes,$offset,$bytes.Length-$offset)
            if($count -le 0){throw 'Bounded input shortened while reading.'}
            $offset+=$count
        }
        return ,$bytes
    } finally {$stream.Dispose()}
}
function Write-NewBytes([string]$Path,[byte[]]$Bytes) {
    [void](Plain $Path)
    $stream=[IO.FileStream]::new($Path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    try {$stream.Write($Bytes,0,$Bytes.Length);$stream.Flush($true)} finally {$stream.Dispose()}
}
function New-OutputFolder([string]$Path) {
    [void](Plain $Path)
    if(Test-Path -LiteralPath $Path){throw 'Every output folder must be new.'}
    [void](New-Item -ItemType Directory -Path $Path -ErrorAction Stop)
}

$temporary=Plain $env:RUNNER_TEMP
$OutputDirectory=Plain $OutputDirectory
$TargetManifestPath=Plain $TargetManifestPath
if(-not (Test-Path -LiteralPath $temporary -PathType Container) -or
   -not (Below $OutputDirectory $temporary) -or (Test-Path -LiteralPath $OutputDirectory) -or
   -not (Test-Path -LiteralPath ([IO.Path]::GetDirectoryName($OutputDirectory)) -PathType Container)) {
    throw 'A new output directory with existing parent strictly below RUNNER_TEMP is required.'
}
if(-not (Test-Path -LiteralPath $TargetManifestPath -PathType Leaf)){throw 'Pinned full2005 target manifest is missing.'}
$manifestBytes=Read-BoundedBytes $TargetManifestPath 65536
$algorithm=[Security.Cryptography.SHA256]::Create()
try {$actualManifestSha=[Convert]::ToHexString($algorithm.ComputeHash($manifestBytes)).ToLowerInvariant()}
finally {$algorithm.Dispose()}
if($actualManifestSha -cne $manifestSha){throw 'Pinned full2005 target manifest differs.'}
$targets=[Text.UTF8Encoding]::new($false,$true).GetString($manifestBytes) | ConvertFrom-Json
if($targets.schema_version -ne 1 -or $targets.producer_run_id -cne '43207550870' -or
   $targets.producer_executable_sha256 -cne $executableSha -or
   $targets.source_capture_sha256 -cne $captureSha -or $targets.dlls.Count -ne 13) {
    throw 'Target manifest is not the exact retained full2005 capture extraction.'
}
$targetByName=@{}
foreach($target in $targets.dlls) {
    if($target.file -cnotmatch '^bin/([a-z0-9_]+\.dll)$' -or $target.sha256 -cnotmatch '^[a-f0-9]{64}$') {
        throw 'Unexpected target DLL record.'
    }
    $name=$target.file.Substring(4)
    if($name -cnotin $allCaptureNames -or $targetByName.ContainsKey($name)){throw 'Unexpected or duplicate target DLL name.'}
    $targetByName[$name]=$target
}
if($targetByName.Count -ne 13){throw 'All thirteen original context DLL records are required.'}

New-OutputFolder $OutputDirectory
$originalDirectory=Join-Path $OutputDirectory 'original-texts'
New-OutputFolder $originalDirectory
$report=[ordered]@{
    schema_version=1;status='collecting';scope='Named-file identity evidence from a new runner; not historical-copy proof or redistribution permission'
    original_producer_run_id='43207550870';original_executable_sha256=$executableSha
    original_capture_sha256=$captureSha;target_manifest_sha256=$manifestSha
    driver_commit=$env:GITHUB_SHA;run_id=$env:GITHUB_RUN_ID;run_attempt=$env:GITHUB_RUN_ATTEMPT;job=$env:GITHUB_JOB
    application_downloaded=$false;application_executed=$false;qt_sdk_downloaded=$false
    candidate_dll_loaded=$false;installed_files_modified=$false;registry_commands_or_writes_performed=$false
    recursive_or_user_scan_performed=$false;license_approval=$false
    image=[ordered]@{image_os=$env:ImageOS;image_version=$env:ImageVersion;runner_os=$env:RUNNER_OS
        os_description=[Runtime.InteropServices.RuntimeInformation]::OSDescription
        os_version=[Environment]::OSVersion.Version.ToString();process_architecture='X64';os_architecture='X64'}
    developer_environment=[ordered]@{};search_roots=@();candidates=@();matches=@();target_results=@()
    original_text_searches=@();original_texts=@();errors=@()
    excluded_targets=@([ordered]@{name='opengl32sw.dll';reason='Qt/Mesa target excluded from Microsoft roots; retained in the thirteen-DLL input context'})
    limits=[ordered]@{immediate_entries_per_directory=256;named_versions_per_parent=16;crt_directories_per_version=4
        candidate_files=512;dll_file_bytes=67108864;original_text_files=128;original_text_file_bytes=4194304
        original_text_total_bytes=33554432;recursive_depth=0}
    interpretation='An exact SHA match establishes equal bytes at the recorded new-runner path only. Version, signature and directory labels do not authorize redistribution; absence or mismatch leaves provenance unresolved.'
}
$candidateSeen=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$noticeRoots=[Collections.Generic.Dictionary[string,string]]::new([StringComparer]::OrdinalIgnoreCase)
$noticeSeen=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$textTotal=0L

function Add-NoticeRoot([string]$Path,[string]$Area) {
    $path=Plain $Path
    if(-not $noticeRoots.ContainsKey($path)){$noticeRoots.Add($path,$Area)}
}
function Named-Directories([string]$Path,[string]$Pattern,[int]$Maximum) {
    $path=Plain $Path
    if(-not (Test-Path -LiteralPath $path -PathType Container)){return}
    $count=0;$matchesFound=0
    foreach($name in [IO.Directory]::EnumerateDirectories($path)) {
        $count++;if($count -gt 256){throw 'Immediate directory listing exceeded its bound.'}
        if([IO.Path]::GetFileName($name) -match $Pattern) {
            $matchesFound++;if($matchesFound -gt $Maximum){throw 'Named directory matches exceeded their bound.'}
            Plain $name
        }
    }
}
function Certificate-Record($Certificate) {
    if(-not $Certificate){return $null}
    return [ordered]@{subject=$Certificate.Subject;issuer=$Certificate.Issuer;thumbprint=$Certificate.Thumbprint
        not_before=$Certificate.NotBefore.ToUniversalTime().ToString('o');not_after=$Certificate.NotAfter.ToUniversalTime().ToString('o')}
}
function Add-Candidate([string]$Folder,[string]$Name,[string]$Area) {
    if($Name -cnotin @($systemNames+$crtNames)){throw 'Only the twelve exact Microsoft target names may be read.'}
    $path=Plain (Join-Path $Folder $Name)
    if(-not $candidateSeen.Add($path)){return}
    if($candidateSeen.Count -gt 512){throw 'Named DLL candidate bound exceeded.'}
    $row=[ordered]@{name=$Name;area=$Area;path=$path;target_stage_sha256=$targetByName[$Name].sha256
        present=$false;sha256=$null;identical_to_original_stage=$false;bytes=$null;metadata=$null
        metadata_read_error=$null;read_error=$null}
    try {
        if(Test-Path -LiteralPath $path -PathType Leaf) {
            $row.present=$true
            $item=Get-Item -LiteralPath $path -Force
            if($item.Length -gt 67108864){throw 'Oversized named DLL candidate refused.'}
            $stream=[IO.FileStream]::new($path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
            $algorithm=[Security.Cryptography.SHA256]::Create()
            try {
                if($stream.Length -gt 67108864 -or $stream.Length -ne $item.Length){throw 'DLL changed before its bounded read.'}
                $row.sha256=[Convert]::ToHexString($algorithm.ComputeHash($stream)).ToLowerInvariant()
                $row.bytes=$stream.Length
                try {
                    $version=[Diagnostics.FileVersionInfo]::GetVersionInfo($path)
                    $signature=Get-AuthenticodeSignature -LiteralPath $path
                    $row.metadata=[ordered]@{company=$version.CompanyName;file_version=$version.FileVersion
                        product_version=$version.ProductVersion;original_filename=$version.OriginalFilename
                        description=$version.FileDescription;product=$version.ProductName;copyright=$version.LegalCopyright
                        signature_status=[string]$signature.Status;signature_status_message=$signature.StatusMessage
                        signer=Certificate-Record $signature.SignerCertificate;timestamp_signer=Certificate-Record $signature.TimeStamperCertificate}
                } catch {$row.metadata_read_error=$_.Exception.Message;$report.errors+=('DLL metadata '+$path+': '+$_.Exception.Message)}
            } finally {$algorithm.Dispose();$stream.Dispose()}
            [void](Plain $path)
            $row.identical_to_original_stage=$row.sha256 -ceq $row.target_stage_sha256
        } elseif(Test-Path -LiteralPath $path) {throw 'Named candidate is not a regular file.'}
    } catch {$row.identical_to_original_stage=$false;$row.read_error=$_.Exception.Message;$report.errors+=('DLL '+$path+': '+$_.Exception.Message)}
    $report.candidates+=,$row
    if($row.identical_to_original_stage){$report.matches+=,[ordered]@{name=$Name;area=$Area;path=$path;sha256=$row.sha256}}
}
function Retain-OriginalText([string]$Path,[string]$Area,[string]$Category) {
    $path=Plain $Path
    if(-not $noticeSeen.Add($path)){return}
    if($noticeSeen.Count -gt 128){throw 'Original text file count exceeded its bound.'}
    $item=Get-Item -LiteralPath $path -Force
    if($item.PSIsContainer -or $item.Length -gt 4194304 -or $script:textTotal+$item.Length -gt 33554432) {
        throw 'Original text byte bound exceeded; no truncation or substituted terms are permitted.'
    }
    $stream=[IO.FileStream]::new($path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
    try {
        if($stream.Length -ne $item.Length -or $stream.Length -gt 4194304 -or
           $script:textTotal+$stream.Length -gt 33554432){throw 'Original text changed before its bounded read.'}
        $memory=[IO.MemoryStream]::new()
        try {$stream.CopyTo($memory);$bytes=$memory.ToArray()}finally{$memory.Dispose()}
    } finally {$stream.Dispose()}
    if($bytes.Length -ne $item.Length){throw 'Original text changed during bounded read.'}
    $algorithm=[Security.Cryptography.SHA256]::Create()
    try {$digest=[Convert]::ToHexString($algorithm.ComputeHash($bytes)).ToLowerInvariant()}finally{$algorithm.Dispose()}
    $safeName=[IO.Path]::GetFileName($path) -replace '[^A-Za-z0-9._-]','_'
    if($safeName.Length -gt 100){$safeName=$safeName.Substring(0,100)}
    $retained=('original-texts/{0:D3}-{1}-{2}' -f $noticeSeen.Count,$digest,$safeName)
    Write-NewBytes (Join-Path $OutputDirectory $retained) $bytes
    $script:textTotal+=$bytes.Length
    $report.original_texts+=,[ordered]@{source_path=$path;area=$Area;category=$Category;bytes=$bytes.Length
        sha256=$digest;retained_path=$retained;full_original_bytes_retained=$true}
}

try {
    foreach($key in @('WindowsSdkDir','WindowsSDKVersion','WindowsSDKLibVersion','UCRTVersion','WindowsSdkBinPath',
            'VCToolsRedistDir','VCToolsInstallDir','VCToolsVersion','VSINSTALLDIR','VisualStudioVersion',
            'VSCMD_ARG_HOST_ARCH','VSCMD_ARG_TGT_ARCH')) {
        $report.developer_environment[$key]=[Environment]::GetEnvironmentVariable($key)
    }
    $systemRoot=Plain $env:SystemRoot
    $system32=Plain ([Environment]::SystemDirectory)
    if($system32 -ine (Plain (Join-Path $systemRoot 'System32'))){throw 'SystemRoot does not match the native System32 API path.'}
    $report.search_roots+=,[ordered]@{area='windows-system32';path=$system32;present=Test-Path -LiteralPath $system32 -PathType Container}
    foreach($name in $systemNames){Add-Candidate $system32 $name 'windows-system32'}
    $kernel=Plain (Join-Path $system32 'kernel32.dll')
    if(Test-Path -LiteralPath $kernel -PathType Leaf) {
        $kernelVersion=[Diagnostics.FileVersionInfo]::GetVersionInfo($kernel)
        $report.image['kernel32_file_version']=$kernelVersion.FileVersion
        $report.image['kernel32_sha256']=Hash $kernel
    }
    if($env:WindowsSdkDir) {
        $sdk=Plain $env:WindowsSdkDir
        $sdkAllowed=@((Join-Path ${env:ProgramFiles(x86)} 'Windows Kits'),(Join-Path $env:ProgramFiles 'Windows Kits'))
        if(-not @($sdkAllowed|Where-Object {Below $sdk (Plain $_)}).Count){throw 'SDK environment root must remain below installed Program Files/Windows Kits.'}
        Add-NoticeRoot $sdk 'windows-sdk'
        $redist=Plain (Join-Path $sdk 'Redist')
        Add-NoticeRoot $redist 'windows-sdk-redist'
        $redistVersions=@(Named-Directories $redist '^\d+\.\d+\.\d+\.\d+$' 16)
        foreach($root in @($redist)+$redistVersions) {
            Add-NoticeRoot $root 'windows-sdk-redist'
            $d3d=Plain (Join-Path $root 'D3D')
            $x64=Plain (Join-Path $d3d 'x64')
            Add-NoticeRoot $d3d 'windows-sdk-redist';Add-NoticeRoot $x64 'windows-sdk-redist'
            $report.search_roots+=,[ordered]@{area='windows-sdk-redist';path=$x64;present=Test-Path -LiteralPath $x64 -PathType Container}
            foreach($name in $d3dNames){Add-Candidate $x64 $name 'windows-sdk-redist'}
        }
        foreach($name in @('Licenses','License','licenses')) {
            $licenses=Plain (Join-Path $sdk $name)
            Add-NoticeRoot $licenses 'windows-sdk-terms'
            foreach($version in @(Named-Directories $licenses '^\d+\.\d+\.\d+\.\d+$' 16)) {
                Add-NoticeRoot $version 'windows-sdk-terms'
            }
        }
        foreach($name in @('SDKManifest.xml','Version.txt')) {
            $metadata=Plain (Join-Path $sdk $name)
            if(Test-Path -LiteralPath $metadata -PathType Leaf){Retain-OriginalText $metadata 'windows-sdk' 'original SDK identity metadata'}
        }
    } else {$report.search_roots+=,[ordered]@{area='windows-sdk-redist';path=$null;present=$false;reason='WindowsSdkDir not exported; no alternate install search'}}
    if($env:VCToolsRedistDir -and $env:VSINSTALLDIR) {
        $vs=Plain $env:VSINSTALLDIR
        $vsAllowed=@((Join-Path $env:ProgramFiles 'Microsoft Visual Studio'),(Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio'))
        if(-not @($vsAllowed|Where-Object {Below $vs (Plain $_)}).Count){throw 'VS environment root must remain below installed Program Files/Microsoft Visual Studio.'}
        $parent=Plain (Join-Path $vs 'VC/Redist/MSVC')
        $selected=Plain $env:VCToolsRedistDir
        if([IO.Path]::GetDirectoryName($selected) -ine $parent -or
           [IO.Path]::GetFileName($selected) -notmatch '^\d+\.\d+\.\d+(\.\d+)?$') {
            throw 'VCToolsRedistDir must be one named numeric version under the selected VS VC/Redist/MSVC root.'
        }
        Add-NoticeRoot $vs 'visual-studio';Add-NoticeRoot (Join-Path $vs 'VC/Redist') 'visual-c-redist'
        Add-NoticeRoot $parent 'visual-c-redist'
        $versions=@($selected)+@(Named-Directories $parent '^\d+\.\d+\.\d+(\.\d+)?$' 16)
        foreach($root in @($versions|Sort-Object -Unique)) {
            Add-NoticeRoot $root 'visual-c-redist'
            $x64=Plain (Join-Path $root 'x64')
            Add-NoticeRoot $x64 'visual-c-redist'
            $crtDirectories=@(Named-Directories $x64 '^Microsoft\.VC[0-9]+\.(CRT|ConCRT)$' 4)
            if(-not $crtDirectories.Count){$report.search_roots+=,[ordered]@{area='visual-c-redist';path=$x64;present=Test-Path -LiteralPath $x64 -PathType Container;matching_crt_directories=0}}
            foreach($crt in $crtDirectories) {
                Add-NoticeRoot $crt 'visual-c-redist'
                $report.search_roots+=,[ordered]@{area='visual-c-redist';path=$crt;present=$true}
                foreach($name in $crtNames){Add-Candidate $crt $name 'visual-c-redist'}
            }
        }
        $versionText=Plain (Join-Path $vs 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt')
        if(Test-Path -LiteralPath $versionText -PathType Leaf){Retain-OriginalText $versionText 'visual-studio' 'original toolset identity metadata'}
    } else {$report.search_roots+=,[ordered]@{area='visual-c-redist';path=$null;present=$false;reason='VSINSTALLDIR/VCToolsRedistDir not exported; no alternate install search'}}
    foreach($entry in $noticeRoots.GetEnumerator()|Sort-Object Key) {
        $row=[ordered]@{path=$entry.Key;area=$entry.Value;present=Test-Path -LiteralPath $entry.Key -PathType Container;immediate_files_considered=0;notice_names_found=@()}
        if($row.present) {
            foreach($file in [IO.Directory]::EnumerateFiles($entry.Key)) {
                $row.immediate_files_considered++
                if($row.immediate_files_considered -gt 256){throw 'Immediate original-text listing exceeded its bound.'}
                $name=[IO.Path]::GetFileName($file)
                if($name -match '(?i)redist|licen[cs]e|terms|notice|third.?party|copying|eula' -and
                   [IO.Path]::GetExtension($file) -match '^(?i)(\.(txt|rtf|html?|md|xml|list|pdf))?$') {
                    $row.notice_names_found+=,$name
                    Retain-OriginalText $file $entry.Value 'original installed notice/REDIST/terms candidate; applicability not inferred'
                }
            }
        }
        $report.original_text_searches+=,$row
    }
    $report.status=if($report.errors.Count){'completed-with-read-errors'}else{'completed'}
} catch {$report.status='failed';$report.errors+=,$_.Exception.Message}
finally {
    foreach($name in @($systemNames+$crtNames)) {
        $matching=@($report.matches|Where-Object {$_.name -ceq $name})
        $report.target_results+=,[ordered]@{name=$name;stage_sha256=$targetByName[$name].sha256
            matching_paths=@($matching|ForEach-Object {$_.path});matching_areas=@($matching|ForEach-Object {$_.area}|Sort-Object -Unique)
            status=if($matching.Count){'exact-bytes-observed-on-new-runner'}else{'unresolved-no-exact-match-in-named-roots'}}
    }
    $report['original_text_total_bytes']=$textTotal
    $report['originals_are_evidence_not_license_approval']=$true
    $json=$report|ConvertTo-Json -Depth 15
    Write-NewBytes (Join-Path $OutputDirectory 'named-redist-origins.json') ([Text.UTF8Encoding]::new($false).GetBytes($json+"`n"))
    Write-Host 'CADENCE_NAMED_REDIST_ORIGINS_BEGIN'
    Write-Host ($report|ConvertTo-Json -Depth 15 -Compress)
    Write-Host 'CADENCE_NAMED_REDIST_ORIGINS_END'
}
if($report.errors.Count){throw 'Named-file collection recorded failures; inspect its report and retained originals.'}
