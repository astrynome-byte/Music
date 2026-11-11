# SPDX-License-Identifier: GPL-3.0-only
#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $StagePath,
    [Parameter(Mandatory)][string] $RestorationRecordPath,
    [Parameter(Mandatory)][string] $OutputDirectory
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
# This guard precedes all writes and all firewall/API access.
if (-not [OperatingSystem]::IsWindows() -or $env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitProcess -or
    [Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne 'X64' -or
    $env:GITHUB_ACTIONS -ne 'true' -or $env:CI -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted') {
    throw 'Only disposable native Windows x64 GitHub-hosted runners are permitted.'
}
if (-not $env:RUNNER_TEMP) { throw 'RUNNER_TEMP is required.' }
$expectedExeHash = '0aba4ced85a18a781c76c27f0072f2a761f7dee87f73610493887790f38fdb6a'
$expectedFixtureHash = '1b38cc5953cc56426976345411394c24d39e0ff22dbf6c350addcb68c770a3fb'
$expectedSoundfontHash = '5ea2375e8bd7d8e71def1036978c1621e85b66934169b6a2744b27b9b3c2d99c'
$fixture = Join-Path $PSScriptRoot 'fixtures/piano.musicxml'
function Full-Path([string] $Path) {
    if ([string]::IsNullOrWhiteSpace($Path) -or $Path -match '[;\r\n"\x00*?]') { throw 'Unsupported input path.' }
    [IO.Path]::GetFullPath($Path)
}
function Is-Below([string] $Child, [string] $Parent) {
    $Child.StartsWith($Parent.TrimEnd('\','/') + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)
}
function Assert-NoReparse([string] $Path) {
    while ($Path) {
        if ((Test-Path -LiteralPath $Path) -and ((Get-Item -LiteralPath $Path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Reparse points are forbidden.' }
        $parent = [IO.Path]::GetDirectoryName($Path.TrimEnd('\','/'))
        if (-not $parent -or $parent -eq $Path) { break }; $Path = $parent
    }
}
function Hash([string] $Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
$StagePath = Full-Path $StagePath
$RestorationRecordPath = Full-Path $RestorationRecordPath
$OutputDirectory = Full-Path $OutputDirectory
$temporaryRoot = Full-Path $env:RUNNER_TEMP
foreach ($path in @($StagePath, $RestorationRecordPath, $OutputDirectory)) {
    if (-not (Is-Below $path $temporaryRoot)) { throw 'All runtime paths must be strictly below RUNNER_TEMP.' }
    Assert-NoReparse $path
}
if ((Test-Path -LiteralPath $OutputDirectory) -or (Is-Below $OutputDirectory $StagePath) -or
    (Is-Below $StagePath $OutputDirectory) -or $StagePath -eq $OutputDirectory -or
    (Is-Below $RestorationRecordPath $OutputDirectory)) { throw 'OutputDirectory must be new and separate from stage and restoration record.' }
[void][IO.Directory]::CreateDirectory($OutputDirectory)
$utf8 = [Text.UTF8Encoding]::new($false)
$report = [ordered]@{
    schema_version=1; status='blocked'; phase='preflight'; error=$null
    scope='CLI version, import a CC0 piano copy, save MSCX, reopen saved MSCX for PDF and offline WAV export, numerical audio signal validation'
    started_utc=[DateTime]::UtcNow.ToString('o'); finished_utc=$null
    source_repository='astrynome-byte/Music'; source_run_id=42793810996; source_artifact_id=13755702885
    original_source_commit='76b51af495b721776945717a812e1de2394a689a'; source_tree='59d63e6f93b3bb7e8e5291cf57f57f9c5d61a06b'; build_number=1001
    executable=$null; executable_sha256=$null; fixture_sha256=$expectedFixtureHash
    stage_restoration_sha256=$null; isolated_path=$null; fresh_cadence_profile_observed=$false
    no_account_credentials_supplied=$true; application_executed=$false; commands=@(); outputs=@(); wave_signal=$null
    human_listening_performed=$false; gui_editing_tested=$false; physical_network_disconnected=$false
    network_scope='Windows Defender Firewall outbound Block/Any protocol/Any remote address, exact Cadence executable path only; local IPC remains possible; runner and GitHub transport remain online'
    network_probe_performed=$false; child_executable_network_coverage=$false; profile_settings_changed=$false
    firewall=[ordered]@{ rule_name=$null; creation_attempted=$false; created=$false; active_store_verified=$false; active_profiles=@(); service_states=@(); snapshots=@(); removed=$false; cleanup_error=$null }
}
$failure = $null; $cleanupFailure = $null; $ruleName = $null; $ruleCreationAttempted = $false
$executable = Join-Path $StagePath 'bin/CadenceStudio4.exe'
$ruleDescription = 'Cadence offline CLI smoke; exact owned disposable executable; ' + [guid]::NewGuid().ToString('D')

function Read-ExactRule([string] $Store) {
    # UUID contains no wildcard. Missing rule is a valid empty result; API errors
    # other than ObjectNotFound are not swallowed.
    $queryErrors = @()
    $rules = @(Get-NetFirewallRule -PolicyStore $Store -Name $ruleName -ErrorAction SilentlyContinue -ErrorVariable queryErrors)
    foreach ($problem in $queryErrors) {
        if ($problem.CategoryInfo.Category -ne [Management.Automation.ErrorCategory]::ObjectNotFound) { throw $problem }
    }
    return $rules
}
function Test-EffectiveEnforcement([int[]] $Values) {
    if ($null -eq $Values) { return $false }
    return ($Values.Count -gt 0 -and 1 -in $Values -and
        @($Values | Where-Object { $_ -notin @(1,5) }).Count -eq 0)
}
function Resolve-EnforcementValues($Rule, $Observation) {
    # Capture the adapted representation before trying any numeric conversion.
    $displayValues=@($Rule.EnforcementStatus)
    $Observation['enforcement_display_entries']=@($displayValues | ForEach-Object {
        [ordered]@{ value=[string]$_; runtime_type=if ($null -eq $_) { 'null' } else { $_.GetType().FullName } }
    })
    $rawRecord=[ordered]@{ available=$false; property_type=$null; entries=@(); error=$null; used=$false }
    $Observation['enforcement_raw_cim']=$rawRecord
    try {
        if ($Rule -is [Microsoft.Management.Infrastructure.CimInstance]) {
            $property=$Rule.CimInstanceProperties['EnforcementStatus']
            if ($null -ne $property) {
                $rawRecord.available=$true; $rawRecord.property_type=[string]$property.CimType
                $rawValues=@($property.Value)
                $rawRecord.entries=@($rawValues | ForEach-Object {
                    [ordered]@{ value=[string]$_; runtime_type=if ($null -eq $_) { 'null' } else { $_.GetType().FullName } }
                })
                if ([string]$property.CimType -eq 'UInt16Array' -and
                    @($rawValues | Where-Object { $_ -isnot [UInt16] }).Count -eq 0) {
                    $numeric=@($rawValues | ForEach-Object { [int]$_ })
                    $rawRecord.used=$true; $Observation['enforcement_numeric_source']='raw MSFT_NetFirewallRule.CimInstanceProperties UInt16Array'
                    $Observation['enforcement_entries']=@($rawValues | ForEach-Object {
                        [ordered]@{ name=[string]$_; numeric_value=[int]$_; runtime_type=$_.GetType().FullName; source='raw_cim' }
                    })
                    return $numeric
                }
            }
        }
    } catch { $rawRecord.error=$_.Exception.Message }

    # Some PowerShell adapters expose only labels. Resolve only the two
    # documented codes, and only after verifying their names/values against the
    # installed Microsoft NetSecurity CDXML metadata. Missing metadata blocks.
    $moduleRoot=Full-Path (Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/Modules/NetSecurity')
    Assert-NoReparse $moduleRoot
    $manifestPath=Join-Path $moduleRoot 'NetSecurity.psd1'
    Assert-NoReparse $manifestPath
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf) -or (Get-Item -LiteralPath $manifestPath).Length -gt 1048576) { throw 'Installed NetSecurity manifest unavailable or oversized; label mapping blocked.' }
    $manifest=Import-PowerShellDataFile -LiteralPath $manifestPath -ErrorAction Stop
    $moduleRecord=[ordered]@{
        manifest_path=$manifestPath; manifest_sha256=Hash $manifestPath; module_version=[string]$manifest.ModuleVersion
        company_name=[string]$manifest.CompanyName; files_examined=@(); verified_enums=@()
    }
    $Observation['enforcement_module_metadata']=$moduleRecord
    if ([string]$manifest.CompanyName -notmatch '^Microsoft(?:\s|$)' -or [string]::IsNullOrWhiteSpace([string]$manifest.ModuleVersion)) { throw 'Installed NetSecurity module metadata does not identify Microsoft and a version.' }
    $command=Get-Command Get-NetFirewallRule -ErrorAction Stop
    $moduleRecord['loaded_command_module']=$command.ModuleName
    $moduleRecord['loaded_command_version']=[string]$command.Version
    if ($command.ModuleName -cne 'NetSecurity') { throw 'Firewall command is not supplied by the NetSecurity module.' }
    $files=@(Get-ChildItem -LiteralPath $moduleRoot -File -Filter '*.cdxml' -ErrorAction Stop)
    if ($files.Count -lt 1 -or $files.Count -gt 64) { throw 'Installed NetSecurity CDXML file count outside inspection bounds.' }
    [long]$totalBytes=0
    foreach ($file in $files) {
        Assert-NoReparse $file.FullName
        $totalBytes+=$file.Length
        if ($file.Length -gt 2097152 -or $totalBytes -gt 16777216) { throw 'Installed NetSecurity CDXML metadata exceeds inspection bounds.' }
        $moduleRecord.files_examined+=$file.Name
        $settings=[Xml.XmlReaderSettings]::new(); $settings.DtdProcessing=[Xml.DtdProcessing]::Prohibit; $settings.XmlResolver=$null
        $reader=[Xml.XmlReader]::Create($file.FullName,$settings)
        try { $document=[Xml.XmlDocument]::new(); $document.XmlResolver=$null; $document.Load($reader) } finally { $reader.Dispose() }
        foreach ($enum in $document.SelectNodes('//*[local-name()="Enum"]')) {
            $enumName=$enum.GetAttribute('EnumName')
            if ($enumName -cne 'EnforcementStatus' -and -not $enumName.EndsWith('.EnforcementStatus',[StringComparison]::Ordinal)) { continue }
            $pairs=@($enum.SelectNodes('.//*[local-name()="EnumValue"]') | ForEach-Object { [ordered]@{ name=$_.GetAttribute('Name'); value=$_.GetAttribute('Value') } })
            $enforced=@($pairs | Where-Object { $_.name -ceq 'Enforced' })
            $inactive=@($pairs | Where-Object { $_.name -ceq 'ProfileInactive' })
            if ($enforced.Count -ne 1 -or $inactive.Count -ne 1 -or $enforced[0].value -cne '1' -or $inactive[0].value -cne '5') { throw 'Installed EnforcementStatus enum does not verify Enforced=1 and ProfileInactive=5.' }
            $moduleRecord.verified_enums += [ordered]@{ path=$file.FullName; sha256=Hash $file.FullName; enum_name=$enumName; enforced_value=1; profile_inactive_value=5 }
        }
    }
    if ($moduleRecord.verified_enums.Count -lt 1) { throw 'Installed Microsoft CDXML EnforcementStatus mapping was not found; labels remain untrusted.' }
    $resolved=[Collections.Generic.List[int]]::new()
    $entries=[Collections.Generic.List[object]]::new()
    foreach ($value in $displayValues) {
        $name=[string]$value
        if ($name -ceq 'Enforced') { $number=1 }
        elseif ($name -ceq 'ProfileInactive') { $number=5 }
        else { throw 'Unexpected enforcement label; only metadata-verified Enforced/ProfileInactive can be normalized.' }
        $resolved.Add($number)
        $entries.Add([ordered]@{ name=$name; numeric_value=$number; runtime_type=$value.GetType().FullName; source='verified_installed_cdxml' })
    }
    $Observation['enforcement_numeric_source']='installed Microsoft NetSecurity CDXML Enforced=1/ProfileInactive=5'
    $Observation['enforcement_entries']=@($entries.ToArray())
    return $resolved.ToArray()
}
function Assert-EffectiveRule([string] $Moment) {
    try {
    $profiles = @(Get-NetFirewallProfile -PolicyStore ActiveStore -ErrorAction Stop)
    if ($profiles.Count -ne 3 -or @($profiles | Where-Object { [string]$_.Enabled -ne 'True' }).Count) {
        throw 'All three effective firewall profiles must already be enabled; no profile will be changed.'
    }
    $rules = @(Read-ExactRule 'ActiveStore')
    if ($rules.Count -ne 1) { throw 'The exact new rule is absent or ambiguous in ActiveStore.' }
    $rule = $rules[0]
    $programs = @($rule | Get-NetFirewallApplicationFilter -ErrorAction Stop)
    $addresses = @($rule | Get-NetFirewallAddressFilter -ErrorAction Stop)
    $ports = @($rule | Get-NetFirewallPortFilter -ErrorAction Stop)
    $interfaces = @($rule | Get-NetFirewallInterfaceTypeFilter -ErrorAction Stop)
    # Capture returned values before deciding whether this exact rule is usable.
    # A failed observation never establishes effective network isolation.
    $observation=[ordered]@{
        moment=$Moment; checked_utc=[DateTime]::UtcNow.ToString('o'); verified=$false
        name=$rule.Name; description=$rule.Description; expected_name=$ruleName; expected_description=$ruleDescription; expected_program=$executable
        enabled=[string]$rule.Enabled; direction=[string]$rule.Direction; action=[string]$rule.Action
        profiles=[string]$rule.Profile; primary_status=[string]$rule.PrimaryStatus
        enforcement_status=[string]$rule.EnforcementStatus; policy_store_source=$rule.PolicyStoreSource
        application_filters=@($programs | ForEach-Object { [ordered]@{ program=[string]$_.Program } })
        address_filters=@($addresses | ForEach-Object { [ordered]@{ local_address=@($_.LocalAddress); remote_address=@($_.RemoteAddress) } })
        port_filters=@($ports | ForEach-Object { [ordered]@{ protocol=[string]$_.Protocol; local_port=@($_.LocalPort); remote_port=@($_.RemotePort) } })
        interface_filters=@($interfaces | ForEach-Object { [ordered]@{ interface_type=[string]$_.InterfaceType } })
        effective_profiles=@($profiles | ForEach-Object { [ordered]@{ name=[string]$_.Name; enabled=[string]$_.Enabled; allow_local_rules=[string]$_.AllowLocalFirewallRules } })
    }
    $report.firewall.snapshots += $observation
    # MSFT_NetFirewallRule documents uint16[]: Full=1, InactiveProfile=5.
    # NetSecurity renders these as Enforced/ProfileInactive on this runner.
    # Require actual enforcement, allow inactive-profile entries alongside it,
    # and reject all other codes. Empty/inactive-only states never qualify.
    # https://github.com/MicrosoftDocs/win32/blob/40f99e296680e6b3b6c4c52b03726e636e7096c1/desktop-src/FWP/wmi/wfascimprov/msft-netfirewallrule.md
    $enforcementValues=@(Resolve-EnforcementValues $rule $observation)
    $enforcementIsEffective=Test-EffectiveEnforcement $enforcementValues
    # Name each rejected field for diagnosis. These observations do not replace
    # or relax the strict assertion below, which remains unchanged.
    $criteria=[ordered]@{
        name=($rule.Name -ceq $ruleName); description=($rule.Description -ceq $ruleDescription)
        enabled=([string]$rule.Enabled -eq 'True'); direction=([string]$rule.Direction -eq 'Outbound')
        action=([string]$rule.Action -eq 'Block'); profiles=([string]$rule.Profile -eq 'Any')
        primary_status=([string]$rule.PrimaryStatus -eq 'OK'); enforcement_status=$enforcementIsEffective
        application_filter_count=($programs.Count -eq 1); address_filter_count=($addresses.Count -eq 1)
        port_filter_count=($ports.Count -eq 1); interface_filter_count=($interfaces.Count -eq 1)
    }
    if ($programs.Count -eq 1) { $criteria['program']=([string]$programs[0].Program -ieq $executable) }
    if ($addresses.Count -eq 1) {
        $criteria['remote_address']=((@($addresses[0].RemoteAddress) -join ',') -eq 'Any')
        $criteria['local_address']=((@($addresses[0].LocalAddress) -join ',') -eq 'Any')
    }
    if ($ports.Count -eq 1) {
        $criteria['protocol']=([string]$ports[0].Protocol -in @('Any','256'))
        $criteria['remote_port']=((@($ports[0].RemotePort) -join ',') -eq 'Any')
        $criteria['local_port']=((@($ports[0].LocalPort) -join ',') -eq 'Any')
    }
    if ($interfaces.Count -eq 1) { $criteria['interface_type']=([string]$interfaces[0].InterfaceType -eq 'Any') }
    $observation['criteria']=$criteria
    $observation['rejected_fields']=@($criteria.GetEnumerator() | Where-Object { -not $_.Value } | ForEach-Object { $_.Key })
    if ($rule.Name -cne $ruleName -or $rule.Description -cne $ruleDescription -or
        [string]$rule.Enabled -ne 'True' -or [string]$rule.Direction -ne 'Outbound' -or
        [string]$rule.Action -ne 'Block' -or [string]$rule.Profile -ne 'Any' -or
        [string]$rule.PrimaryStatus -ne 'OK' -or -not $enforcementIsEffective -or
        $programs.Count -ne 1 -or [string]$programs[0].Program -ine $executable -or
        $addresses.Count -ne 1 -or (@($addresses[0].RemoteAddress) -join ',') -ne 'Any' -or
        (@($addresses[0].LocalAddress) -join ',') -ne 'Any' -or
        $ports.Count -ne 1 -or [string]$ports[0].Protocol -notin @('Any','256') -or
        (@($ports[0].RemotePort) -join ',') -ne 'Any' -or (@($ports[0].LocalPort) -join ',') -ne 'Any' -or
        $interfaces.Count -ne 1 -or [string]$interfaces[0].InterfaceType -ne 'Any') {
        throw 'The exact executable outbound rule is not effectively enforced/Block/Any in ActiveStore; no application will start.'
    }
    $observation.verified=$true
    $report.firewall.active_store_verified=$true
    } catch {
        $report.status='blocked'
        $report.phase='firewall-verification-'+$Moment
        throw
    }
}
function Invoke-OwnedCli([string] $Name, [string[]] $Arguments, [int] $TimeoutSeconds) {
    $report.phase=$Name
    Assert-EffectiveRule ('before-' + $Name)
    if ((Hash $executable) -ne $expectedExeHash) { throw 'Executable changed before launch.' }
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName=$executable; $start.WorkingDirectory=$OutputDirectory
    $start.UseShellExecute=$false; $start.RedirectStandardOutput=$true; $start.RedirectStandardError=$true
    foreach ($arg in $Arguments) { $start.ArgumentList.Add($arg) }
    $start.Environment['PATH']=$report.isolated_path
    foreach ($key in @($start.Environment.Keys)) {
        if ($key -match '^(?i:QT|QML|CMAKE_|VCPKG_|VSCMD_|VSINSTALLDIR$|VCINSTALLDIR$|VCTools|INCLUDE$|LIB$|LIBPATH$|WindowsSdk|WindowsSDK|UniversalCRTSdkDir$|UCRTVersion$|DevEnvDir$|ExtensionSdkDir$|FrameworkDir|FrameworkVersion|.*_PROXY$|GITHUB_|GH_TOKEN$|ACTIONS_|AZURE_|AWS_|GOOGLE_|OPENAI_)') { [void]$start.Environment.Remove($key) }
    }
    $start.Environment['TEMP']=(Join-Path $OutputDirectory 'temp'); $start.Environment['TMP']=$start.Environment['TEMP']
    $entry=[ordered]@{ name=$Name; arguments=$Arguments; pid=$null; timeout_seconds=$TimeoutSeconds; exit_code=$null; timed_out=$false; stdout=$Name+'.stdout.log'; stderr=$Name+'.stderr.log'; elapsed_seconds=$null; cleanup_error=$null }
    $report.commands += $entry
    $process=[Diagnostics.Process]::new(); $process.StartInfo=$start
    $outTask=$null; $errTask=$null; $started=$false; $clock=[Diagnostics.Stopwatch]::StartNew()
    try {
        if (-not $process.Start()) { throw 'Owned Cadence CLI process did not start.' }
        $started=$true; $report.application_executed=$true; $entry.pid=$process.Id
        $outTask=$process.StandardOutput.ReadToEndAsync(); $errTask=$process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            $entry.timed_out=$true; $process.Kill($true)
            if (-not $process.WaitForExit(5000)) { throw 'Owned CLI process did not stop within the cleanup bound.' }
            throw "Owned CLI command exceeded $TimeoutSeconds seconds."
        }
        $entry.exit_code=$process.ExitCode
        if ($process.ExitCode -ne 0) { throw "Owned CLI command failed with exit code $($process.ExitCode)." }
    } finally {
        try {
            if ($started -and -not $process.HasExited) {
                $process.Kill($true)
                if (-not $process.WaitForExit(5000)) { throw 'Owned CLI process remained alive.' }
            }
            if ($null -ne $outTask) {
                if (-not $outTask.Wait(5000)) { throw 'CLI stdout stream did not close within bound.' }
                [IO.File]::WriteAllText((Join-Path $OutputDirectory $entry.stdout),$outTask.GetAwaiter().GetResult(),$utf8)
            }
            if ($null -ne $errTask) {
                if (-not $errTask.Wait(5000)) { throw 'CLI stderr stream did not close within bound.' }
                [IO.File]::WriteAllText((Join-Path $OutputDirectory $entry.stderr),$errTask.GetAwaiter().GetResult(),$utf8)
            }
        } catch { $entry.cleanup_error=$_.Exception.Message; throw }
        finally { $entry.elapsed_seconds=[Math]::Round($clock.Elapsed.TotalSeconds,3); $process.Dispose() }
    }
    Assert-EffectiveRule ('after-' + $Name)
}
function Inspect-Score([string] $Path) {
    if ((Get-Item -LiteralPath $Path).Length -gt 16777216) { throw 'Saved score exceeds the inspection bound.' }
    $settings=[Xml.XmlReaderSettings]::new(); $settings.DtdProcessing=[Xml.DtdProcessing]::Prohibit; $settings.XmlResolver=$null
    $reader=[Xml.XmlReader]::Create($Path,$settings)
    try { $document=[Xml.XmlDocument]::new(); $document.XmlResolver=$null; $document.Load($reader) } finally { $reader.Dispose() }
    $notes=$document.SelectNodes('/museScore/Score/Staff/Measure//Note').Count
    $staves=$document.SelectNodes('/museScore/Score/Staff').Count
    if ($document.DocumentElement.Name -cne 'museScore' -or $notes -lt 1 -or $staves -lt 2) { throw 'Saved MSCX does not contain the expected nonempty two-staff score.' }
    return [ordered]@{ format='MSCX'; notes=$notes; staves=$staves; reopened_by_pdf_and_wav_exports=$false }
}
try {
    $record=Get-Content -LiteralPath $RestorationRecordPath -Raw | ConvertFrom-Json
    if ($record.schema_version -ne 1 -or $record.status -cne 'retained-stage-restored-sha256-verified' -or
        $record.repository -cne 'astrynome-byte/Music' -or $record.original_run_id -ne 42793810996 -or
        $record.original_artifact_id -ne 13755702885 -or $record.build_number -ne 1001 -or
        $record.original_source_commit -cne $report.original_source_commit -or $record.source_tree -cne $report.source_tree -or
        (Full-Path $record.stage_path) -ine $StagePath -or (Full-Path $record.executable_path) -ine $executable -or
        $record.executable_sha256 -cne $expectedExeHash -or $record.application_recompiled -ne $false -or
        $record.application_executed_by_restore -ne $false) { throw 'Only the authenticated retained build 1001 restoration is accepted.' }
    foreach ($item in Get-ChildItem -LiteralPath $StagePath -Recurse -Force) {
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Stage contains a reparse point.' }
    }
    if ((Hash $executable) -ne $expectedExeHash -or (Hash $fixture) -ne $expectedFixtureHash) { throw 'Pinned executable or CC0 fixture SHA-256 differs.' }
    $report.executable=$executable; $report.executable_sha256=Hash $executable
    $report.stage_restoration_sha256=Hash $RestorationRecordPath
    $report.isolated_path=(Split-Path -Parent $executable)+';'+(Join-Path $env:SystemRoot 'System32')
    # Qt uses Windows known folders. Check the actual disposable user profile;
    # environment overrides alone would not establish an empty Qt profile.
    foreach ($folder in @([Environment+SpecialFolder]::ApplicationData,[Environment+SpecialFolder]::LocalApplicationData)) {
        $base=[Environment]::GetFolderPath($folder)
        $userRoot=Full-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::UserProfile))
        if (-not [IO.Path]::IsPathFullyQualified($base) -or -not (Is-Below (Full-Path $base) $userRoot)) { throw 'Actual Windows known folder does not belong to the disposable runner user.' }
        $cadenceProfile=Join-Path $base 'CadenceStudio'
        Assert-NoReparse $cadenceProfile
        if (Test-Path -LiteralPath $cadenceProfile) { throw 'A preexisting Cadence profile was left untouched; account-free precondition blocked.' }
    }
    $report.fresh_cadence_profile_observed=$true
    $soundfonts=@(Get-ChildItem -LiteralPath $StagePath -Recurse -File -Filter 'MS Basic.sf3')
    if ($soundfonts.Count -ne 1 -or $soundfonts[0].Length -ne 51278610) { throw 'Exactly one bundled MS Basic soundfont of 51,278,610 bytes is required.' }
    $soundfontHash=Hash $soundfonts[0].FullName
    if ($soundfontHash -cne $expectedSoundfontHash) { throw 'Bundled MS Basic soundfont differs from the retained build 1001 SHA-256.' }
    $report['soundfont']=[ordered]@{ path=$soundfonts[0].FullName; bytes=$soundfonts[0].Length; sha256=$soundfontHash; license='MIT'; profile='MuseScore Basic' }
    Add-Type -Path (Join-Path $PSScriptRoot 'WaveSignal.cs')
    [void][IO.Directory]::CreateDirectory((Join-Path $OutputDirectory 'temp'))
    $inputCopy=Join-Path $OutputDirectory 'piano-input.musicxml'
    Copy-Item -LiteralPath $fixture -Destination $inputCopy -ErrorAction Stop
    if ((Hash $inputCopy) -ne $expectedFixtureHash) { throw 'Fixture copy differs.' }
    $report.phase='firewall-prerequisites'
    if (-not ([Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Administrator token unavailable; no escalation or security changes attempted.' }
    foreach ($name in @('Get-NetFirewallRule','New-NetFirewallRule','Remove-NetFirewallRule','Get-NetFirewallApplicationFilter','Get-NetFirewallAddressFilter','Get-NetFirewallPortFilter','Get-NetFirewallInterfaceTypeFilter','Get-NetFirewallProfile')) {
        [void](Get-Command $name -ErrorAction Stop)
    }
    foreach ($name in @('MpsSvc','BFE')) {
        $service=Get-Service -Name $name -ErrorAction Stop
        $report.firewall.service_states += [ordered]@{ name=$name; status=[string]$service.Status }
        if ($service.Status -ne 'Running') { throw 'Firewall services must already be running; none will be changed.' }
    }
    $profiles=@(Get-NetFirewallProfile -PolicyStore ActiveStore -ErrorAction Stop)
    $report.firewall.active_profiles=@($profiles | ForEach-Object { [ordered]@{ name=[string]$_.Name; enabled=[string]$_.Enabled; allow_local_rules=[string]$_.AllowLocalFirewallRules } })
    if ($profiles.Count -ne 3 -or @($profiles | Where-Object { [string]$_.Enabled -ne 'True' }).Count) { throw 'All effective firewall profiles must already be enabled.' }
    $ruleName='CadenceOfflineQa-'+[guid]::NewGuid().ToString('D')
    $report.firewall.rule_name=$ruleName
    if (@(Read-ExactRule 'PersistentStore').Count -or @(Read-ExactRule 'ActiveStore').Count) { throw 'New UUID rule name unexpectedly exists; no rule was changed.' }
    $ruleCreationAttempted=$true; $report.firewall.creation_attempted=$true
    New-NetFirewallRule -PolicyStore PersistentStore -Name $ruleName -DisplayName $ruleName -Description $ruleDescription `
        -Program $executable -Direction Outbound -Action Block -Enabled True -Profile Any -Protocol Any `
        -LocalAddress Any -RemoteAddress Any -InterfaceType Any -ErrorAction Stop | Out-Null
    $report.firewall.created=$true
    Assert-EffectiveRule 'initial'
    $report.status='running'
    Invoke-OwnedCli 'version' @('--long-version') 30
    $version=(Get-Content -LiteralPath (Join-Path $OutputDirectory 'version.stdout.log') -Raw)+' '+(Get-Content -LiteralPath (Join-Path $OutputDirectory 'version.stderr.log') -Raw)
    if ($version -notmatch '(?i)Version\s+4\.7\.6(?:\D|$)') { throw 'Actual CLI did not report upstream version 4.7.6.' }
    $saved=Join-Path $OutputDirectory 'piano-saved.mscx'
    $pdf=Join-Path $OutputDirectory 'piano-reopened.pdf'
    $wav=Join-Path $OutputDirectory 'piano-reopened.wav'
    Invoke-OwnedCli 'import-save-mscX' @('-o',$saved,$inputCopy) 90
    $scoreCheck=Inspect-Score $saved
    Invoke-OwnedCli 'reopen-export-pdf' @('-o',$pdf,$saved) 90
    $pdfLength=(Get-Item -LiteralPath $pdf).Length
    if ($pdfLength -lt 1024 -or $pdfLength -gt 16777216) { throw 'PDF lies outside inspection size bounds.' }
    $pdfBytes=[IO.File]::ReadAllBytes($pdf)
    if ([Text.Encoding]::ASCII.GetString($pdfBytes,0,5) -cne '%PDF-' -or
        [Text.Encoding]::ASCII.GetString($pdfBytes,[Math]::Max(0,$pdfBytes.Length-1024),[Math]::Min(1024,$pdfBytes.Length)) -notmatch '%%EOF') { throw 'PDF is missing its header/trailer or lies outside size bounds.' }
    Invoke-OwnedCli 'reopen-export-wav' @('--sound-profile','MuseScore Basic','-o',$wav,$saved) 180
    $report.wave_signal=[CadenceOfflineWaveV1]::Inspect($wav)
    if (-not $report.wave_signal.Passed) { throw 'WAV is silent, non-finite or reaches the clipping threshold.' }
    $scoreCheck.reopened_by_pdf_and_wav_exports=$true; $report['saved_score']=$scoreCheck
    if ((Hash $fixture) -ne $expectedFixtureHash -or (Hash $inputCopy) -ne $expectedFixtureHash -or
        (Hash $executable) -ne $expectedExeHash -or (Hash $soundfonts[0].FullName) -ne $soundfontHash) { throw 'An original or copied input changed during the smoke.' }
    Assert-EffectiveRule 'final-before-removal'
    $report.phase='completed'; $report.status='passed'
} catch {
    $failure=$_; $report.error=$_.Exception.Message
    if ($report.status -ne 'blocked') { $report.status='failed' }
} finally {
    # Never enumerate and remove other rules. Even a partial New-* failure takes
    # this path because ownership was reserved only after UUID absence checks.
    if ($ruleCreationAttempted) {
        try {
            $owned=@(Read-ExactRule 'PersistentStore')
            if ($owned.Count -gt 1) { throw 'Exact UUID cleanup was ambiguous.' }
            if ($owned.Count -eq 1) {
                if ($owned[0].Name -cne $ruleName -or $owned[0].Description -cne $ruleDescription) { throw 'Exact UUID ownership changed; cleanup refused to touch another rule.' }
                Remove-NetFirewallRule -PolicyStore PersistentStore -Name $ruleName -ErrorAction Stop
            }
            if (@(Read-ExactRule 'PersistentStore').Count -or @(Read-ExactRule 'ActiveStore').Count) { throw 'Exact UUID firewall rule remained after removal.' }
            $report.firewall.removed=$true
        } catch {
            $cleanupFailure=$_; $report.firewall.cleanup_error=$_.Exception.Message; $report.status='cleanup_failed'
        }
    }
    foreach ($file in Get-ChildItem -LiteralPath $OutputDirectory -File | Sort-Object Name) {
        $report.outputs += [ordered]@{ path=$file.Name; bytes=$file.Length; sha256=Hash $file.FullName }
    }
    $report.finished_utc=[DateTime]::UtcNow.ToString('o')
    $reportText=$report | ConvertTo-Json -Depth 20
    [IO.File]::WriteAllText((Join-Path $OutputDirectory 'offline-qa-report.json'),$reportText+"`n",$utf8)
    $lines=@(Get-ChildItem -LiteralPath $OutputDirectory -File | Sort-Object Name | ForEach-Object { (Hash $_.FullName)+'  '+$_.Name })
    [IO.File]::WriteAllText((Join-Path $OutputDirectory 'SHA256SUMS.txt'),($lines -join "`n")+"`n",$utf8)
    Write-Host 'CADENCE_OFFLINE_QA_REPORT_BEGIN'; Write-Host $reportText; Write-Host 'CADENCE_OFFLINE_QA_REPORT_END'
}
if ($cleanupFailure) { throw $cleanupFailure }
if ($failure) { throw $failure }
Write-Host 'PASS: authenticated build 1001 imported/saved/reopened/exported under its verified exact-path outbound firewall rule; WAV signal checks passed; owned rule removed.'
