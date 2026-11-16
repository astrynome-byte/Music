# SPDX-License-Identifier: GPL-3.0-only
"""Read exact successful WAV-analysis draft evidence only; execute no payload."""
from pathlib import Path
import argparse,base64,hashlib,importlib.util,json,os,urllib.request,zipfile
RUN=43968843424;JOB=133655319453;ARTIFACT=14278325466
DRIVER='e7ffe1a3faa7104cdd7a710dea75db086b47bd0b'
SIZE=882345;SHA='866201c770533c18a1dd87676889d39a24539dbdebdb450f2fbe1e0a3a83077d'
MEMBERS={
    '_temp/import-dialogs-gui-results/06-analyze-wav.png':
        (97041,'90d70bfd6c475eb63ef3cf6750e6b89d2b3a52ac7bd48b2d54fa9f425eb5a5b6'),
    '_temp/import-dialogs-gui-results/06-analyze-wav/import-dialog-phase.json':
        (16012,'60e49fe7b5e771eaa4dde6ed99848e1dfcaf3750c2e5d8a0e76603889bf6c219'),
}
def require(ok,message):
    if not ok:raise ValueError(message)
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    require(os.environ.get('GITHUB_ACTIONS')=='true'and os.environ.get('GITHUB_REPOSITORY')=='astrynome-byte/Music','Exact hosted repository context required')
    require(not a.output.exists()and a.output.is_absolute()and a.output.is_relative_to(Path(os.environ['RUNNER_TEMP'])),'New temporary data directory required')
    helper=Path(__file__).parent.parent/'retained-2008-data-readback/read_existing_stage.py'
    require(hashlib.sha256(helper.read_bytes()).hexdigest()=='9bdcbc4732057fc50f8ba5387578d68d292682864a21938b717d29df662875ae','Frozen safe DATAONLY reader required')
    spec=importlib.util.spec_from_file_location('safe_data_reader',helper);reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)
    token=os.environ['GH_TOKEN']
    def get(endpoint,redirect=False):
        request=urllib.request.Request('https://api.github.com/repos/astrynome-byte/Music/'+endpoint,
          headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','User-Agent':'Cadence-GUI8-Analysis-DataOnly/1.0'})
        return urllib.request.build_opener(reader.PublicRedirectOnly()if redirect else reader.NoRedirect()).open(request,timeout=30)
    values=[]
    for endpoint in (f'actions/runs/{RUN}',f'actions/jobs/{JOB}',f'actions/artifacts/{ARTIFACT}'):
        with get(endpoint)as response:raw=response.read(2*1024**2+1);require(response.status==200 and len(raw)<=2*1024**2,'Bounded metadata HTTP200 required');values.append(json.loads(raw))
    run,job,artifact=values
    require(run['id']==RUN and run['head_sha']==DRIVER and run['status']=='completed'and run['conclusion']=='success'and run['run_attempt']==1,'Exact successful analysis run required')
    require(job['id']==JOB and job['run_id']==RUN and job['head_sha']==DRIVER and job['status']=='completed'and job['conclusion']=='success','Exact successful analysis job required')
    require(artifact['id']==ARTIFACT and artifact['size_in_bytes']==SIZE and artifact['digest']=='sha256:'+SHA and artifact['expired']is False and artifact['workflow_run']['id']==RUN and artifact['workflow_run']['head_sha']==DRIVER,'Exact original883KB analysis artifact required')
    with get(f'actions/artifacts/{ARTIFACT}/zip',True)as response:raw=response.read(SIZE+1)
    require(len(raw)==SIZE and hashlib.sha256(raw).hexdigest()==SHA,'Original outer ZIP bytes differ')
    a.output.mkdir();archive_path=a.output/'original-analysis-draft-evidence.zip';archive_path.write_bytes(raw)
    rows=[];total=0
    with zipfile.ZipFile(archive_path)as archive:
        entries=reader.zip_rows(archive)
        require(set(MEMBERS)<=set(entries),'Both exact selected archive members are required')
        for name,(expected_bytes,expected_sha256)in MEMBERS.items():
            info=entries[name]
            require(info.file_size==expected_bytes and info.file_size<=2*1024**2,'Exact bounded member size required')
            data=archive.read(info);total+=len(data)
            require(total<=128*1024 and len(rows)<2,'Bounded two-member evidence required')
            require(len(data)==expected_bytes and hashlib.sha256(data).hexdigest()==expected_sha256,'Original selected member bytes differ')
            if name.endswith('.json'):json.loads(data.decode('utf-8-sig'))
            else:require(data.startswith(b'\x89PNG\r\n\x1a\n'),'Pinned PNG signature required')
            row={'path':name,'bytes':len(data),'sha256':expected_sha256,'original_bytes_base64':base64.b64encode(data).decode('ascii')}
            if name.endswith('.png'):row['PNG_not_visually_reviewed']=True
            rows.append(row)
            print('CADENCE_GUI8_ORIGINAL_FILE_BEGIN');print(json.dumps(row,separators=(',',':')));print('CADENCE_GUI8_ORIGINAL_FILE_END')
    require(len(rows)==2 and {r['path']for r in rows}==set(MEMBERS)and total==sum(v[0]for v in MEMBERS.values()),'Exactly the two pinned originals are required')
    receipt={'scope':'DATAONLY exact successful controlled-WAV analysis draft originals; no application or SDK execution, no visual validation',
       'run':RUN,'job':JOB,'driver':DRIVER,'artifact':ARTIFACT,'outer_bytes':SIZE,'outer_sha256':SHA,
       'outer_independently_rehashed':True,'application_executed':False,'GUI_validated':False,'PNG_not_visually_reviewed':True,
       'MIDI_save_or_import_validated':False,'notes_accuracy_validated':False,'listening_validated':False,
       'files':[{k:v for k,v in r.items()if k!='original_bytes_base64'}for r in rows]}
    (a.output/'readback-receipt.json').write_bytes((json.dumps(receipt,indent=2)+'\n').encode('utf-8'));print('CADENCE_GUI8_DATAONLY_RECEIPT '+json.dumps(receipt,separators=(',',':')))
if __name__=='__main__':main()
