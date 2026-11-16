# SPDX-License-Identifier: GPL-3.0-only
# Developer/CI only. Windows disposable runner; no application is launched.
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$MsiPath,
    [Parameter(Mandatory)][string]$InventoryPath,
    [Parameter(Mandatory)][string]$OutputDirectory,
    [string]$Python = 'python'
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (-not $IsWindows -or -not [Environment]::Is64BitProcess) { throw 'Windows x64 PowerShell 7 required.' }
if (-not $env:RUNNER_TEMP) { throw 'Disposable Windows CI RUNNER_TEMP required.' }
function PlainPath([string]$Value) {
    $full = [IO.Path]::GetFullPath($Value)
    for ($part = $full; $part; $part = [IO.Path]::GetDirectoryName($part)) {
        if ((Test-Path -LiteralPath $part) -and ((Get-Item -LiteralPath $part -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw 'Reparse path refused.'
        }
        if ($part -eq [IO.Path]::GetPathRoot($part)) { break }
    }
    return $full
}
function Hash([string]$Value) { return (Get-FileHash -LiteralPath $Value -Algorithm SHA256).Hash.ToLowerInvariant() }
$MsiPath = PlainPath $MsiPath
$InventoryPath = PlainPath $InventoryPath
$OutputDirectory = PlainPath $OutputDirectory
$temp = (PlainPath $env:RUNNER_TEMP).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
if (-not $OutputDirectory.StartsWith($temp, [StringComparison]::OrdinalIgnoreCase) -or
    (Test-Path -LiteralPath $OutputDirectory)) { throw 'New extraction beneath RUNNER_TEMP required.' }
if ((Get-Item -LiteralPath $MsiPath).Length -ne 120979784 -or
    (Hash $MsiPath) -ne 'a3f934273e2c2002cc035743974941082245655a7bbe4bc6d2540bb921e52a9e') { throw 'Exact public MSI2008 required.' }
if ((Get-Item -LiteralPath $InventoryPath).Length -ne 530785 -or
    (Hash $InventoryPath) -ne '7b3b721f01b0a57610b9dcc1cd72bd15e50747dcd751fcd5e31cfbb96a81a4a4') { throw 'Exact measured runtime inventory required.' }
# Read only before extraction. Product identity and File table count are checked
# independently of the administrative operation; the hash already fixes content.
$installer = New-Object -ComObject WindowsInstaller.Installer
$database = $installer.OpenDatabase($MsiPath, 0)
foreach ($pair in @(
    @('ProductCode', '{CA4AC56B-9ED9-568F-9F5A-0D9475D4CC26}'),
    @('ProductVersion', '4.7.6.2008'),
    @('UpgradeCode', '{319B992F-470A-465B-9A79-6B0CBFC7D6C7}')
)) {
    $view = $database.OpenView(('SELECT `Value` FROM `Property` WHERE `Property` = ''{0}''' -f $pair[0]))
    $view.Execute(); $record = $view.Fetch()
    if (-not $record -or $record.StringData(1) -ne $pair[1]) { throw 'Unexpected MSI product identity.' }
    $view.Close()
}
$view = $database.OpenView('SELECT `File` FROM `File`'); $view.Execute(); $count = 0
while ($null -ne $view.Fetch()) { $count++ }
$view.Close()
if ($count -ne 2712) { throw 'Expected2712 MSI File rows.' }
$template = $database.SummaryInformation(0).Property(7)
if ($template -ne 'x64;1033') { throw 'Expected exact x64 MSI summary template.' }
[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($view)
[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($database)
[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($installer)
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
@{
    schema_version=1; open_mode=0; product_version='4.7.6.2008';
    product_code='{CA4AC56B-9ED9-568F-9F5A-0D9475D4CC26}';
    upgrade_code='{319B992F-470A-465B-9A79-6B0CBFC7D6C7}';
    summary_template=$template; File_rows=$count
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $OutputDirectory 'msi-readonly-identity.json') -Encoding utf8NoBOM
$extracted = Join-Path $OutputDirectory 'administrative-image'
$log = Join-Path $OutputDirectory 'administrative-extraction.log'
$msiexec = Join-Path $env:SystemRoot 'System32/msiexec.exe'
$arguments = @('/a', ('"' + $MsiPath + '"'), '/qn', '/norestart', ('TARGETDIR="' + $extracted + '"'), '/L*v', ('"' + $log + '"'))
$process = Start-Process -FilePath $msiexec -ArgumentList $arguments -PassThru
if (-not $process.WaitForExit(180000)) { throw 'Administrative extraction timed out; disposable runner cleanup required.' }
if ($process.ExitCode -ne 0) { throw "Administrative extraction failed: $($process.ExitCode)" }
if ((Hash $MsiPath) -ne 'a3f934273e2c2002cc035743974941082245655a7bbe4bc6d2540bb921e52a9e') { throw 'Input MSI changed.' }
$report = Join-Path $OutputDirectory 'recovered-runtime-comparison.json'
& $Python (Join-Path $PSScriptRoot 'Compare-RecoveredRuntime.py') --extracted-root $extracted --measured-inventory $InventoryPath --output $report
if ($LASTEXITCODE -ne 0) { throw 'Recovered runtime differs; preserve report and do not use as stage.' }
Write-Host "Exact recovered runtime comparison: $report"
Write-Host 'No application launched. Not a portable mode or a completed GUI qualification.'
