# SPDX-License-Identifier: GPL-3.0-only
# Definitions only: exact four verified enforcement helpers reused from offline-qa/Run-OfflineQa.ps1.
# The owning wrapper creates/removes only its new UUID rule after hosted-Windows guards.
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
