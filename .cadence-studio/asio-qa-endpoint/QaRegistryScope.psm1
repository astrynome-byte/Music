# SPDX-License-Identifier: GPL-3.0-only
# Future second-phase CI only. Import defines functions; no registry write occurs.
#Requires -Version 7.0
Set-StrictMode -Version Latest
function Invoke-QaClockRegistryScope {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$DllPath,
        [Parameter(Mandatory)][string]$ExpectedDllSha256,
        [Parameter(Mandatory)][string]$ResultPath,
        [Parameter(Mandatory)][scriptblock]$Action
    )
    $ErrorActionPreference='Stop'
    if(-not [OperatingSystem]::IsWindows() -or -not [Environment]::Is64BitProcess -or
       [Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne 'X64' -or
       $env:GITHUB_ACTIONS -ne 'true' -or $env:CI -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted'){
        throw 'Registry scope is limited to disposable native Windows x64 GitHub-hosted CI.'
    }
    function Plain([string]$Path){
        if([string]::IsNullOrWhiteSpace($Path) -or $Path -match '[\x00\r\n]'){throw 'Invalid scope path.'}
        $path=[IO.Path]::GetFullPath($Path)
        for($current=$path;$current;$current=[IO.Path]::GetDirectoryName($current.TrimEnd('\','/'))){
            if((Test-Path -LiteralPath $current) -and ((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'Reparse scope path refused.'}
            if([IO.Path]::GetDirectoryName($current.TrimEnd('\','/')) -eq $current){break}
        };$path
    }
    $DllPath=Plain $DllPath;$ResultPath=Plain $ResultPath;$temporary=Plain $env:RUNNER_TEMP
    foreach($path in @($DllPath,$ResultPath)){
        if(-not $path.StartsWith($temporary.TrimEnd('\','/')+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw 'DLL/result must be strictly below RUNNER_TEMP.'}
    }
    if($ExpectedDllSha256 -cnotmatch '^[a-f0-9]{64}$' -or
       -not (Test-Path -LiteralPath $DllPath -PathType Leaf) -or
       (Get-FileHash -LiteralPath $DllPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $ExpectedDllSha256 -or
       (Test-Path -LiteralPath $ResultPath) -or -not (Test-Path -LiteralPath (Split-Path -Parent $ResultPath) -PathType Container) -or
       $env:CADENCE_QA_CLOCK_REGISTRY_SCOPE){throw 'Reviewed DLL/new result/nonnested scope required.'}
    if(-not ('Cadence.Qa.RegistryNativeV1' -as [type])){
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
namespace Cadence.Qa {
 public static class RegistryNativeV1 {
  public static readonly IntPtr Hklm = new IntPtr(unchecked((int)0x80000002));
  [DllImport("advapi32.dll", CharSet=CharSet.Unicode, ExactSpelling=true)]
  public static extern int RegCreateKeyExW(IntPtr root, string subkey, int reserved,
   string keyClass, int options, int access, IntPtr security, out IntPtr key, out uint disposition);
 }
}
'@
    }
    $base=[Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::LocalMachine,[Microsoft.Win32.RegistryView]::Registry64)
    $userBase=[Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::CurrentUser,[Microsoft.Win32.RegistryView]::Registry64)
    $parent='SOFTWARE\ASIO'
    $asio=$parent+'\Cadence QA Clock (silent sink)'
    $com='SOFTWARE\Classes\CLSID\{8176CDA0-8AF9-4483-A03D-45EE2F9E864E}'
    $owner=[guid]::NewGuid().ToString('D');$marker='CadenceQaScopeOwner'
    $owned=[Collections.Generic.List[object]]::new();$cleanupErrors=[Collections.Generic.List[string]]::new()
    $record=[ordered]@{schema_version=1;status='preflight';dll_sha256=$ExpectedDllSha256;scope_owner=$owner
        registry_view='Registry64';kernel_or_service_installed=$false;owned_key_paths=@();cleanup_verified=$false;error=$null;cleanup_errors=@()}
    function New-ScopeKey([string]$Path,[bool]$MustBeNew){
        [IntPtr]$handle=[IntPtr]::Zero;[uint32]$disposition=0
        # KEY_ALL_ACCESS | KEY_WOW64_64KEY. Disposition closes the check/create race.
        $status=[Cadence.Qa.RegistryNativeV1]::RegCreateKeyExW([Cadence.Qa.RegistryNativeV1]::Hklm,$Path,0,$null,0,0xF013F,[IntPtr]::Zero,[ref]$handle,[ref]$disposition)
        if($status -ne 0){throw "Cannot create/open the explicit QA key (Win32 $status)."}
        $safe=[Microsoft.Win32.SafeHandles.SafeRegistryHandle]::new($handle,$true)
        $key=[Microsoft.Win32.RegistryKey]::FromHandle($safe,[Microsoft.Win32.RegistryView]::Registry64)
        if($disposition -ne 1){if($MustBeNew){$key.Dispose();throw 'A QA key already exists; it was not modified.'};return @{key=$key;spec=$null}}
        $spec=@{values=@{};children=@{}};$spec.values[$marker]=$owner
        $owned.Add(@{path=$Path;spec=$spec})
        $key.SetValue($marker,$owner,[Microsoft.Win32.RegistryValueKind]::String)
        return @{key=$key;spec=$spec}
    }
    function Set-Value($Handle,$Spec,[string]$Name,[string]$Value){
        $Handle.SetValue($Name,$Value,[Microsoft.Win32.RegistryValueKind]::String);$Spec.values[$Name]=$Value
    }
    function Assert-OwnedTree([Microsoft.Win32.RegistryKey]$Key,$Spec){
        $names=@($Key.GetValueNames());$children=@($Key.GetSubKeyNames())
        if($names.Count -ne $Spec.values.Count -or $children.Count -ne $Spec.children.Count){throw 'Owned QA key acquired unexpected values/children; deletion refused.'}
        foreach($name in $names){
            if(-not $Spec.values.ContainsKey($name) -or $Key.GetValueKind($name) -ne [Microsoft.Win32.RegistryValueKind]::String -or
               $Key.GetValue($name,$null,[Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames) -cne $Spec.values[$name]){throw 'Owned QA key value changed; deletion refused.'}
        }
        foreach($name in $children){
            if(-not $Spec.children.ContainsKey($name)){throw 'Foreign child in QA key; deletion refused.'}
            $child=$Key.OpenSubKey($name,$false)
            try{Assert-OwnedTree $child $Spec.children[$name]}finally{$child.Dispose()}
        }
    }
    try{
        # HKCR merges per-user COM classes before machine classes. Refuse an
        # exact HKCU shadow as well; never touch or replace that user's class.
        $shadow=$userBase.OpenSubKey('Software\Classes\CLSID\{8176CDA0-8AF9-4483-A03D-45EE2F9E864E}',$false)
        if($shadow){$shadow.Dispose();throw 'Preexisting per-user COM shadow refused before any mutation.'}
        # Both unique endpoint keys are checked before the first write. Atomic
        # create disposition below refuses a key that appears after this check.
        foreach($path in @($asio,$com)){$existing=$base.OpenSubKey($path,$false);if($existing){$existing.Dispose();throw 'Preexisting endpoint/COM key refused before mutation.'}}
        $key=New-ScopeKey $parent $false;$key.key.Dispose()
        $class=New-ScopeKey $com $true
        try{
            Set-Value $class.key $class.spec '' 'Cadence QA Clock (silent sink)'
            $child=$class.key.CreateSubKey('InprocServer32',$true)
            $childSpec=@{values=@{};children=@{}};$childSpec.values[$marker]=$owner;$class.spec.children['InprocServer32']=$childSpec
            try{
                $child.SetValue($marker,$owner,[Microsoft.Win32.RegistryValueKind]::String)
                Set-Value $child $childSpec '' $DllPath
                Set-Value $child $childSpec 'ThreadingModel' 'Both'
            }finally{$child.Dispose()}
        }finally{$class.key.Dispose()}
        $endpoint=New-ScopeKey $asio $true
        try{
            Set-Value $endpoint.key $endpoint.spec 'CLSID' '{8176CDA0-8AF9-4483-A03D-45EE2F9E864E}'
            Set-Value $endpoint.key $endpoint.spec 'Description' 'Cadence QA Clock (silent sink)'
        }finally{$endpoint.key.Dispose()}
        foreach($item in $owned){
            # Parent ASIO may have the newly created endpoint; its cleanup
            # specification becomes empty again once that child is removed.
            if($item.path -ceq $parent){continue}
            $key=$base.OpenSubKey($item.path,$false);try{Assert-OwnedTree $key $item.spec}finally{$key.Dispose()}
        }
        $record.status='scope-active';$record.owned_key_paths=@($owned|ForEach-Object {$_.path})
        $env:CADENCE_QA_CLOCK_REGISTRY_SCOPE=$owner
        & $Action
        $record.status='action-returned-cleanup-pending'
    }catch{
        $record.status='failed';$record.error=$_.Exception.Message
        throw
    }finally{
        $env:CADENCE_QA_CLOCK_REGISTRY_SCOPE=$null
        $record.owned_key_paths=@($owned|ForEach-Object {$_.path})
        for($index=$owned.Count-1;$index -ge 0;$index--){
            $item=$owned[$index]
            try{
                $key=$base.OpenSubKey($item.path,$false)
                if($key){try{Assert-OwnedTree $key $item.spec}finally{$key.Dispose()};$base.DeleteSubKeyTree($item.path,$false)}
                $remaining=$base.OpenSubKey($item.path,$false)
                if($remaining){$remaining.Dispose();throw 'Owned QA key still exists after cleanup.'}
            }catch{$cleanupErrors.Add($_.Exception.Message)}
        }
        $base.Dispose();$userBase.Dispose();$record.cleanup_errors=$cleanupErrors.ToArray();$record.cleanup_verified=$cleanupErrors.Count -eq 0
        if($record.status -cne 'failed' -and $record.cleanup_verified){$record.status='action-returned-owned-keys-removed'}
        if($cleanupErrors.Count){$record.status='cleanup-failed'}
        $record|ConvertTo-Json -Depth 10|Set-Content -LiteralPath $ResultPath -Encoding utf8NoBOM
        if($cleanupErrors.Count){throw 'QA registry cleanup refused changed content or failed; inspect its owned-scope report.'}
    }
}
Export-ModuleMember -Function Invoke-QaClockRegistryScope
