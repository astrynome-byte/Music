# SPDX-License-Identifier: GPL-3.0-only
# Read-only MSI helpers. Dot-sourcing defines functions and performs no actions.

function Get-ComValue($Object, [string] $Name, [object[]] $Arguments = @()) {
    # Keep COM StringList objects intact; PowerShell otherwise enumerates them
    # before the explicit Count/Item reader receives them (including empty lists).
    return ,($Object.GetType().InvokeMember($Name, [Reflection.BindingFlags]::GetProperty, $null, $Object, $Arguments))
}
function Invoke-ComMethod($Object, [string] $Name, [object[]] $Arguments = @()) {
    return ,($Object.GetType().InvokeMember($Name, [Reflection.BindingFlags]::InvokeMethod, $null, $Object, $Arguments))
}
function Release-Com($Object) {
    if ($null -ne $Object -and [Runtime.InteropServices.Marshal]::IsComObject($Object)) {
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($Object)
    }
}
function Get-ComStringItems($List) {
    try {
        $count = [int](Get-ComValue $List 'Count')
        for ($i = 0; $i -lt $count; $i++) { [string](Get-ComValue $List 'Item' @($i)) }
    } finally { Release-Com $List }
}
function Get-MsiProperty($Database, [string] $Name) {
    # Name is an internal constant, never user-provided SQL.
    $view = $null; $record = $null
    try {
        $view = Invoke-ComMethod $Database 'OpenView' @("SELECT ``Value`` FROM ``Property`` WHERE ``Property``='$Name'")
        [void](Invoke-ComMethod $view 'Execute')
        $record = Invoke-ComMethod $view 'Fetch'
        if ($null -eq $record) { throw "MSI property missing: $Name" }
        [string](Get-ComValue $record 'StringData' @(1))
    } finally {
        if ($null -ne $view) { [void](Invoke-ComMethod $view 'Close') }
        Release-Com $record; Release-Com $view
    }
}
function Normalize-Guid([string] $Value) { '{' + ([guid]$Value).ToString().ToUpperInvariant() + '}' }

function Get-CoexistenceMsiMetadata($Installer, [string] $Path) {
    $database = $null; $summary = $null
    try {
        # msiOpenDatabaseModeReadOnly = 0. The caller retains Installer ownership.
        $database = Invoke-ComMethod $Installer 'OpenDatabase' @([IO.Path]::GetFullPath($Path), 0)
        $metadata = [ordered]@{
            product_name = Get-MsiProperty $database 'ProductName'
            product_code = Normalize-Guid (Get-MsiProperty $database 'ProductCode')
            product_version = Get-MsiProperty $database 'ProductVersion'
            upgrade_code = Normalize-Guid (Get-MsiProperty $database 'UpgradeCode')
            summary_template = $null
        }
        $summary = Get-ComValue $database 'SummaryInformation' @(0)
        $metadata.summary_template = [string](Get-ComValue $summary 'Property' @(7))
        [pscustomobject]$metadata
    } finally {
        Release-Com $summary; Release-Com $database
    }
}

function Get-CoexistenceProducts($Installer) {
    foreach ($code in @(Get-ComStringItems (Get-ComValue $Installer 'Products'))) {
        [pscustomobject][ordered]@{
            product_code = Normalize-Guid ([string]$code)
            product_name = [string](Get-ComValue $Installer 'ProductInfo' @([string]$code, 'ProductName'))
        }
    }
}

function Get-CoexistenceProductState($Installer, [string] $Code) {
    [int](Get-ComValue $Installer 'ProductState' @((Normalize-Guid $Code)))
}

function Get-CoexistenceRelated($Installer, [string] $UpgradeCode) {
    foreach ($code in @(Get-ComStringItems (Get-ComValue $Installer 'RelatedProducts' @((Normalize-Guid $UpgradeCode))))) {
        Normalize-Guid ([string]$code)
    }
}
