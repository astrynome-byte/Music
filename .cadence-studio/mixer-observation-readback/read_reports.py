# SPDX-License-Identifier: GPL-3.0-only
"""Read exact22 JSON originals from the completed Windows DATAONLY artifact; execute none."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import stat
import urllib.request

EXPECTED = json.loads(Path(__file__).with_name('expected-readback.json').read_text())

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError('Metadata authentication cannot redirect')

def require(ok,message):
    if not ok:raise ValueError(message)

def verify_metadata(output):
    require(os.environ.get('GITHUB_REPOSITORY')=='astrynome-byte/Music','Exact repository context required')
    token=os.environ['GH_TOKEN'];opener=urllib.request.build_opener(NoRedirect);values={}
    for endpoint in (f"actions/runs/{EXPECTED['run_id']}",f"actions/artifacts/{EXPECTED['artifact_id']}"):
        request=urllib.request.Request('https://api.github.com/repos/astrynome-byte/Music/'+endpoint,
            headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','User-Agent':'Cadence-data-only-observation-reader'})
        with opener.open(request,timeout=30)as response:
            raw=response.read(2*1024**2+1)
            require(response.status==200 and len(raw)<=2*1024**2,'Bounded metadata HTTP200 required')
            values[endpoint]=json.loads(raw)
    run=values[f"actions/runs/{EXPECTED['run_id']}"];artifact=values[f"actions/artifacts/{EXPECTED['artifact_id']}"]
    require(run['head_sha']==EXPECTED['driver_commit'] and run['status']=='completed' and run['conclusion']=='success'
        and run['run_number']==1 and run['run_attempt']==1
        and run['path']=='.github/workflows/cadence-windows-2008-data-inspection.yml','Exact successful DATAONLY run required')
    require(artifact['id']==EXPECTED['artifact_id'] and artifact['digest']==EXPECTED['artifact_digest']
        and artifact['size_in_bytes']==EXPECTED['artifact_bytes'] and artifact['expired']is False
        and artifact['workflow_run']['id']==EXPECTED['run_id']
        and artifact['workflow_run']['head_sha']==EXPECTED['driver_commit'],'Exact DATAONLY artifact identity required')
    Path(output).write_text(json.dumps(values,indent=2)+'\n')

def read_reports(root,output):
    root,output=Path(root),Path(output)
    require(not root.is_symlink() and root.is_dir() and not output.exists(),'Plain input and new output required')
    selected=[];total=0
    def collect(name,sha,expected_bytes=None):
        nonlocal total
        path=root/name
        require(not path.is_symlink() and not any(x.is_symlink()for x in path.parents),'Linked evidence refused')
        info=path.stat(follow_symlinks=False)
        require(stat.S_ISREG(info.st_mode) and 0<info.st_size<=4*1024**2,'Bounded regular JSON required')
        raw=path.read_bytes();actual=hashlib.sha256(raw).hexdigest()
        require(actual==sha and(expected_bytes is None or len(raw)==expected_bytes),'Original JSON length/SHA differs: '+name)
        value=json.loads(raw.decode('utf-8-sig'));total+=len(raw)
        require(total<=8*1024**2 and len(selected)<22,'Bounded22 JSONs required')
        row={'path':name,'bytes':len(raw),'sha256':actual,'base64_original_bytes':base64.b64encode(raw).decode('ascii')}
        selected.append((Path(name),raw,row));return value
    receipt=collect('windows2008-inspection-receipt.json',EXPECTED['inspection_receipt_sha256'])
    require(receipt.get('status')=='actual-retained2008-data-inspected-seven-assets-prepared'
        and all(receipt.get(k)is False for k in('ready','publication_authorized','activation_target_written','github_write_performed','application_or_installer_executed'))
        and receipt.get('original_outer_digests_recomputed')is True
        and receipt.get('reports')==EXPECTED['reports'] and receipt.get('asset_receipts')==EXPECTED['assets']
        and receipt.get('source')==EXPECTED['source'] and receipt.get('producer')==EXPECTED['producer'],
        'Authentic nonactivating inspection receipt differs')
    for kind,row in EXPECTED['reports'].items():
        collect('windows2008-inspection/observed-reports/'+kind+'.original.json',row['sha256'],row['bytes'])
    collect('windows2008-inspection/observed-reports/source.original.json',EXPECTED['source_json_sha256'])
    expected_names={row['path']for _,_,row in selected}
    actual_names={x.relative_to(root).as_posix()for x in root.rglob('*')if x.is_file()}
    require(len(selected)==22 and actual_names==expected_names,'Exactly22 expected original JSON files required')
    # Emit nothing until every original identity has been checked.
    output.mkdir()
    for rel,raw,row in selected:
        path=output/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        print('CADENCE_WINDOWS2008_ORIGINAL_JSON_BEGIN')
        print(json.dumps(row,separators=(',',':')))
        print('CADENCE_WINDOWS2008_ORIGINAL_JSON_END')
    facts={'scope':'Exact original JSON bytes only; no application, MSI, SDK or acquired code executed','source_run':EXPECTED['run_id'],
        'source_artifact':EXPECTED['artifact_id'],'producer_file_bytes_recomputed':True,'public_release_published':False,
        'files':[{k:v for k,v in row.items()if k!='base64_original_bytes'}for _,_,row in selected]}
    (output/'readback-receipt.json').write_text(json.dumps(facts,indent=2)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--metadata-output');parser.add_argument('--root');parser.add_argument('--output');args=parser.parse_args()
    if args.metadata_output:verify_metadata(args.metadata_output)
    else:read_reports(args.root,args.output)
