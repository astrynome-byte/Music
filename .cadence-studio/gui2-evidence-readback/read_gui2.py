# SPDX-License-Identifier: GPL-3.0-only
"""Read only exact failed GUI6 evidence; never execute artifact code or payloads."""
from pathlib import Path
import argparse,base64,hashlib,importlib.util,json,os,urllib.request,zipfile
RUN=43428772768;JOB=131896686179;ARTIFACT=14038589017
DRIVER='655c9a21f8e5d44c8650f143c4b6840f737aaf8a'
SIZE=754064;SHA='b47541ea55b5b5a6d3f415a2f1edb2213f4e532babff699956a965c55cd33211'
NAMES={'8-after-import-key.json','phase-final.json','import-dialog-phase.json'}
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
          headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','User-Agent':'Cadence-GUI2-DataOnly/1.0'})
        return urllib.request.build_opener(reader.PublicRedirectOnly()if redirect else reader.NoRedirect()).open(request,timeout=30)
    values=[]
    for endpoint in (f'actions/runs/{RUN}',f'actions/jobs/{JOB}',f'actions/artifacts/{ARTIFACT}'):
        with get(endpoint)as response:raw=response.read(2*1024**2+1);require(response.status==200 and len(raw)<=2*1024**2,'Bounded metadata HTTP200 required');values.append(json.loads(raw))
    run,job,artifact=values
    require(run['id']==RUN and run['head_sha']==DRIVER and run['status']=='completed'and run['conclusion']=='failure'and run['run_attempt']==1,'Exact failed GUI6 run required')
    require(job['id']==JOB and job['run_id']==RUN and job['head_sha']==DRIVER and job['status']=='completed'and job['conclusion']=='failure','Exact failed GUI6 job required')
    require(artifact['id']==ARTIFACT and artifact['size_in_bytes']==SIZE and artifact['digest']=='sha256:'+SHA and artifact['expired']is False and artifact['workflow_run']['id']==RUN and artifact['workflow_run']['head_sha']==DRIVER,'Exact original754KB GUI6 artifact required')
    with get(f'actions/artifacts/{ARTIFACT}/zip',True)as response:raw=response.read(SIZE+1)
    require(len(raw)==SIZE and hashlib.sha256(raw).hexdigest()==SHA,'Original outer ZIP bytes differ')
    a.output.mkdir();archive_path=a.output/'original-GUI6-evidence.zip';archive_path.write_bytes(raw)
    rows=[];total=0
    with zipfile.ZipFile(archive_path)as archive:
        entries=reader.zip_rows(archive);print('CADENCE_GUI2_SELECTED_MEMBERS '+json.dumps([{'path':n,'original_ZIP_date_time_fields':i.date_time,'bytes':i.file_size}for n,i in entries.items()if '/04-close-wav/'in'/'+n and Path(n).name in NAMES]))
        for name,info in sorted(entries.items()):
            if '/04-close-wav/' not in '/'+name or Path(name).name not in NAMES:continue
            require(info.file_size<=2*1024**2,'Bounded evidence file required');data=archive.read(info);total+=len(data)
            require(total<=8*1024**2 and len(rows)<48,'Bounded selected evidence required')
            if name.endswith('.json'):json.loads(data.decode('utf-8-sig'))
            row={'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'original_bytes_base64':base64.b64encode(data).decode('ascii')};rows.append(row)
            print('CADENCE_GUI2_ORIGINAL_FILE_BEGIN');print(json.dumps(row,separators=(',',':')));print('CADENCE_GUI2_ORIGINAL_FILE_END')
    require({Path(r['path']).name for r in rows}==NAMES,'All three exact close-WAV original files required')
    receipt={'scope':'DATAONLY exact failed GUI6 original evidence; no application or SDK execution',
       'run':RUN,'job':JOB,'driver':DRIVER,'artifact':ARTIFACT,'outer_bytes':SIZE,'outer_sha256':SHA,
       'outer_independently_rehashed':True,'application_executed':False,'GUI_validated':False,
       'files':[{k:v for k,v in r.items()if k!='original_bytes_base64'}for r in rows]}
    (a.output/'readback-receipt.json').write_bytes((json.dumps(receipt,indent=2)+'\n').encode('utf-8'));print('CADENCE_GUI2_DATAONLY_RECEIPT '+json.dumps(receipt,separators=(',',':')))
if __name__=='__main__':main()
