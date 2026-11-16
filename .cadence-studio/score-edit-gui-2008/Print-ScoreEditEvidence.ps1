# SPDX-License-Identifier: GPL-3.0-only
# Existing evidence only: no input, application or profile operation.
param([Parameter(Mandatory)][string]$ResultPath)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$p=Join-Path $ResultPath 'score-edit-gui-report.json'
if(-not(Test-Path -LiteralPath $p -PathType Leaf)){Write-Host '{"reader_only":true,"results_available":false}';return}
$f=Get-Item -LiteralPath $p -Force
if(($f.Attributes-band[IO.FileAttributes]::ReparsePoint)-or$f.Length-gt2097152){throw 'Bounded plain report required.'}
$raw=[IO.File]::ReadAllBytes($p)
Write-Host 'CADENCE_SCORE_EDIT_GUI_REPORT_READBACK_BEGIN'
@{reader_only=$true;application_executed_by_reader=$false;original_bytes=$raw.Length;original_sha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($raw)).ToLowerInvariant();report=([Text.Encoding]::UTF8.GetString($raw).TrimStart([char]0xfeff)|ConvertFrom-Json)}|ConvertTo-Json -Depth 30 -Compress|Write-Host
Write-Host 'CADENCE_SCORE_EDIT_GUI_REPORT_READBACK_END'
