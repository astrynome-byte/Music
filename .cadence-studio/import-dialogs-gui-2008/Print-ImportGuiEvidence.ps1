# SPDX-License-Identifier: GPL-3.0-only
# Data reader only. Starts no application or UIA client and sends no input.
param([Parameter(Mandatory)][string]$ResultPath)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath($ResultPath)
$reportPath=Join-Path $root 'import-dialogs-gui-report.json'
if(-not(Test-Path -LiteralPath $reportPath -PathType Leaf)){
 Write-Host 'CADENCE_IMPORT_GUI_READER_SUMMARY_BEGIN';Write-Host '{"reader_only":true,"application_executed_by_reader":false,"results_available":false}';Write-Host 'CADENCE_IMPORT_GUI_READER_SUMMARY_END';return
}
$file=Get-Item -LiteralPath $reportPath -Force
if(($file.Attributes-band[IO.FileAttributes]::ReparsePoint)-or$file.Length-gt2097152){throw 'Original report is unsafe or oversized.'}
$raw=[IO.File]::ReadAllBytes($reportPath);$report=[Text.Encoding]::UTF8.GetString($raw).TrimStart([char]0xfeff)|ConvertFrom-Json
Write-Host 'CADENCE_IMPORT_GUI_READER_JSON_BEGIN'
@{reader_only=$true;application_executed_by_reader=$false;path=$file.Name;original_bytes=$raw.Length;original_sha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($raw)).ToLowerInvariant();reserialized_report=$report}|ConvertTo-Json -Depth 30 -Compress|Write-Host
Write-Host 'CADENCE_IMPORT_GUI_READER_JSON_END'
$printed=0
foreach($capture in @($report.captures|Select-Object -First 2)){
 $p=[IO.Path]::GetFullPath($capture.path)
 if(-not$p.StartsWith($root.TrimEnd('\','/')+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw 'Capture must be below its exact result directory.'}
 $f=Get-Item -LiteralPath $p -Force
 if($f.PSIsContainer-or($f.Attributes-band[IO.FileAttributes]::ReparsePoint)-or$f.Length-gt1048576){throw 'Original capture is unsafe or exceeds the1MiB reader limit.'}
 $bytes=[IO.File]::ReadAllBytes($p);$sha=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()
 if($sha-cne$capture.sha256-or$bytes.Length-ne$capture.bytes){throw 'Original image no longer matches its capture receipt.'}
 Write-Host 'CADENCE_IMPORT_GUI_READER_PNG_BEGIN'
 @{reader_only=$true;application_executed_by_reader=$false;path=$f.Name;original_bytes=$bytes.Length;sha256=$sha;original_PNG_base64=[Convert]::ToBase64String($bytes);visual_review_performed=$false}|ConvertTo-Json -Depth 5 -Compress|Write-Host
 Write-Host 'CADENCE_IMPORT_GUI_READER_PNG_END';++$printed
}
Write-Host 'CADENCE_IMPORT_GUI_READER_SUMMARY_BEGIN'
@{reader_only=$true;application_executed_by_reader=$false;results_available=$true;original_PNGs_printed=$printed;GUI_validation_inferred_by_reader=$false}|ConvertTo-Json -Compress|Write-Host
Write-Host 'CADENCE_IMPORT_GUI_READER_SUMMARY_END'
