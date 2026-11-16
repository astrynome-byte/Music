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
foreach($phase in @('edit-save','undo-save','redo-save')){
 $directory=Join-Path $ResultPath $phase
 $nativePath=Join-Path $directory 'score-edit-phase.json'
 if(-not(Test-Path -LiteralPath $nativePath -PathType Leaf)){continue}
 try{
  foreach($ancestor in @($ResultPath,$directory)){
   $item=Get-Item -LiteralPath $ancestor -Force
   if(-not$item.PSIsContainer-or($item.Attributes-band[IO.FileAttributes]::ReparsePoint)){throw 'Plain phase directory required.'}
  }
  $native=Get-Item -LiteralPath $nativePath -Force
  if(($native.Attributes-band[IO.FileAttributes]::ReparsePoint)-or$native.Length-gt524288){throw 'Bounded plain native phase report required.'}
  $bytes=[IO.File]::ReadAllBytes($nativePath)
  $value=[Text.Encoding]::UTF8.GetString($bytes).TrimStart([char]0xfeff)|ConvertFrom-Json
  if($value.schema_version-ne1-or$value.phase-cne$phase){throw 'Native phase identity differs.'}
  Write-Host 'CADENCE_SCORE_EDIT_NATIVE_PHASE_READBACK_BEGIN'
  @{reader_only=$true;application_executed_by_reader=$false;phase=$phase;original_bytes=$bytes.Length;original_sha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant();report=$value}|ConvertTo-Json -Depth 30 -Compress|Write-Host
  Write-Host 'CADENCE_SCORE_EDIT_NATIVE_PHASE_READBACK_END'
 }catch{
  @{reader_only=$true;phase=$phase;native_phase_readback_available=$false;error=$_.Exception.Message}|ConvertTo-Json -Compress|Write-Host
 }
}
