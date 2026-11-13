#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Render a read-only Windows inspection workflow after the recipe commit exists; no network or publication."""
import argparse
import hashlib
from pathlib import Path
import re
import yaml

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--recipe-commit',required=True,help='Actual reviewed immutable recipe commit, not the producer application commit')
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
if not re.fullmatch('[a-f0-9]{40}',args.recipe_commit):raise SystemExit('Actual full recipe commit required')
if args.output.exists():raise SystemExit('Output must be new')
root=Path(__file__).with_name('files')
pins=('Inspect-DeliveryDataOnly.ps1','inspect_delivery.py','acquire_originals.py','windows_publication.py','GUIDE-FR.txt','target.json.template','expected-inputs.json','verify_stage_only_producer.py','stage-only-provenance.json')
helper='$helper="$env:GITHUB_WORKSPACE/driver/.cadence-studio/windows-2008-public-download-next"\n'
verify=helper+'''if(Test-Path -LiteralPath "$helper/target.json"){throw 'Pinned inspection recipe must not contain an activation target.'}
$pins=@{
'''+''.join("  '"+n+"'='"+hashlib.sha256((root/n).read_bytes()).hexdigest()+"'\n" for n in pins)+'''}
foreach($entry in $pins.GetEnumerator()){
    if((Get-FileHash -LiteralPath (Join-Path $helper $entry.Key) -Algorithm SHA256).Hash.ToLowerInvariant()-cne$entry.Value){throw ('Pinned inspection input changed: '+$entry.Key)}
}
'''
inspect=helper+'''& "$helper/Inspect-DeliveryDataOnly.ps1" -WorkDirectory "$env:RUNNER_TEMP/windows2008-inspection" -OutputPath "$env:RUNNER_TEMP/windows2008-inspection-receipt.json"
'''
receipts=helper+'''$receiptPath="$env:RUNNER_TEMP/windows2008-inspection-receipt.json"
$receipt=Get-Content -LiteralPath $receiptPath -Raw -Encoding utf8|ConvertFrom-Json
$expected=Get-Content -LiteralPath "$helper/expected-inputs.json" -Raw -Encoding utf8|ConvertFrom-Json
if($receipt.status-cne'actual-retained2008-data-inspected-seven-assets-prepared'-or
   $receipt.ready-isnot[bool]-or$receipt.ready-or
   $receipt.publication_authorized-isnot[bool]-or$receipt.publication_authorized-or
   $receipt.activation_target_written-isnot[bool]-or$receipt.activation_target_written-or
   $receipt.github_write_performed-isnot[bool]-or$receipt.github_write_performed-or
   $receipt.application_or_installer_executed-isnot[bool]-or$receipt.application_or_installer_executed-or
   $receipt.original_outer_digests_recomputed-isnot[bool]-or-not$receipt.original_outer_digests_recomputed){throw 'Explicit completed DATAONLY receipt required.'}
foreach($key in @('run_id','driver_commit','job_id','run_number','run_attempt')){if($receipt.producer.$key-cne$expected.producer.$key){throw 'Actual producer differs from selection.'}}
foreach($key in @('original_commit','tree','source_json_sha256','patch_sha256')){if($receipt.source.$key-cne$expected.source.$key){throw 'Actual source differs from selection.'}}
$reportNames=@('bootstrap','build','stage_manifest','release_manifest','cli','msi','notices','components','icu_policy','icu_exports','native_additions','practice','audio_transcription','omr_runner','authorized_wav_https','macro_profile','unity_syntax','retained_qualification','retained_packaging','retained_installer_wrapper')
if(@($receipt.reports.PSObject.Properties).Count-ne20-or@($receipt.asset_receipts).Count-ne7-or@($receipt.artifacts).Count-ne5){throw 'Exactly20reports,7assets,5originals required.'}
$folder="$env:RUNNER_TEMP/windows2008-inspection/observed-reports";$names=@('source.original.json')
foreach($kind in $reportNames){
    $name=$kind+'.original.json';$names+=$name;$file=Get-Item -LiteralPath (Join-Path $folder $name)
    if($file.PSIsContainer-or$file.Length-ne$receipt.reports.$kind.bytes-or(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()-cne$receipt.reports.$kind.sha256){throw ('Original report changed: '+$kind)}
}
if((Get-FileHash -LiteralPath (Join-Path $folder 'source.original.json') -Algorithm SHA256).Hash.ToLowerInvariant()-cne$expected.source.source_json_sha256){throw 'Original source.json changed.'}
[string[]]$actual=@(Get-ChildItem -LiteralPath $folder -File -Force|ForEach-Object Name)
[Array]::Sort($actual,[StringComparer]::Ordinal);[Array]::Sort($names,[StringComparer]::Ordinal)
if($actual.Count-ne21){throw 'Only20original JSON reports and source.json may be retained.'}
for($i=0;$i-lt21;$i++){if($actual[$i]-cne$names[$i]){throw 'Unexpected inspection output file; no binary upload permitted.'}}
$candidate=[ordered]@{schema_version=1;scope='Actual data for root review only';ready=$false;publication_authorized=$false;activation_target_written=$false;github_write_performed=$false;inspection_receipt_sha256=(Get-FileHash -LiteralPath $receiptPath -Algorithm SHA256).Hash.ToLowerInvariant();producer=$receipt.producer;stage_producer=$receipt.stage_producer;qualification_producer=$receipt.qualification_producer;source=$receipt.source;artifacts=$receipt.artifacts;reports=$receipt.reports;executable_sha256=$receipt.executable_sha256;msi_sha256=$receipt.msi_sha256;asset_receipts=$receipt.asset_receipts}
Write-Host 'CADENCE_WINDOWS2008_READYFALSE_CANDIDATE_BEGIN'
Write-Host ($candidate|ConvertTo-Json -Depth 100 -Compress)
Write-Host 'CADENCE_WINDOWS2008_READYFALSE_CANDIDATE_END'
'''
workflow={'name':'Cadence: inspect actual retained2008 data before publication review','on':{'push':{'branches':['cadence-studio/windows-build'],'paths':['.github/workflows/cadence-windows-2008-data-inspection.yml']}},'permissions':{'contents':'read','actions':'read'},'jobs':{'inspect-selected-retained2008-without-target':{'if':"github.repository == 'astrynome-byte/Music'",'runs-on':'windows-2022','timeout-minutes':60,'defaults':{'run':{'shell':'pwsh'}},'steps':[{'uses':'actions/checkout@v6','with':{'ref':args.recipe_commit,'path':'driver','fetch-depth':1,'persist-credentials':False}},{'uses':'actions/setup-python@v6','with':{'python-version':'3.12'}},{'name':'Verify nine immutable recipe inputs without an activation target','run':verify},{'name':'Inspect authenticated source-stage, successful QA and MSI producers and prepare seven local files without GitHub write','env':{'GH_TOKEN':'${{ github.token }}'},'run':inspect},{'name':'Verify20original report bytes and print nonactivating data receipts','run':receipts},{'name':'Retain only20original report JSON,source.json and receipt','if':'always()','uses':'actions/upload-artifact@v4','with':{'name':'cadence-windows2008-inspection-data-${{ github.run_number }}-${{ github.run_attempt }}','path':'${{ runner.temp }}/windows2008-inspection/observed-reports/*.original.json\n${{ runner.temp }}/windows2008-inspection-receipt.json','retention-days':14,'if-no-files-found':'warn'}}]}}}
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_text('# SPDX-License-Identifier: GPL-3.0-only\n# DATAONLY: no application launch, installation, activation target or GitHub write.\n'+yaml.safe_dump(workflow,sort_keys=False,allow_unicode=True,width=1000000))
print('Rendered read-only inspection workflow; not uploaded or activated:',args.output)
