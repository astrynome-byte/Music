# SPDX-License-Identifier: GPL-3.0-only
"""Read bounded original failed score2 evidence only; never execute artifact code."""
from pathlib import Path
import argparse, base64, hashlib, importlib.util, json, os, urllib.request, zipfile

RUN=43958651459; JOB=133619832102; ARTIFACT=14272668268
DRIVER='217beb0b39b363c373751002fd9c310b8d6eea0f'
SIZE=461876; SHA='71c5c9de174bc609afba06d384bb9ff8925319b359e2e4cefd29f46ac2222883'
NAMES={'score-edit-gui-report.json','score-edit-phase.json','failed-before-close.png'}
SNAPSHOTS={'tree-before.json','tree-after.json'}

def require(ok,message):
    if not ok:raise ValueError(message)

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    require(os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('GITHUB_REPOSITORY')=='astrynome-byte/Music','Exact hosted repository required')
    require(a.output.is_absolute() and not a.output.exists() and a.output.is_relative_to(Path(os.environ['RUNNER_TEMP'])),'New temporary output required')
    helper=Path(__file__).parent.parent/'retained-2008-data-readback/read_existing_stage.py'
    require(hashlib.sha256(helper.read_bytes()).hexdigest()=='9bdcbc4732057fc50f8ba5387578d68d292682864a21938b717d29df662875ae','Frozen safe DATAONLY ZIP reader required')
    spec=importlib.util.spec_from_file_location('safe_data_reader',helper);reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)
    token=os.environ['GH_TOKEN']
    def get(endpoint,redirect=False):
        request=urllib.request.Request('https://api.github.com/repos/astrynome-byte/Music/'+endpoint,
          headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','User-Agent':'Cadence-Score2-DataOnly/1.0'})
        return urllib.request.build_opener(reader.PublicRedirectOnly() if redirect else reader.NoRedirect()).open(request,timeout=30)
    values=[]
    for endpoint in (f'actions/runs/{RUN}',f'actions/jobs/{JOB}',f'actions/artifacts/{ARTIFACT}'):
        with get(endpoint) as response:
            raw=response.read(2*1024**2+1);require(response.status==200 and len(raw)<=2*1024**2,'Bounded metadata HTTP200 required');values.append(json.loads(raw))
    run,job,artifact=values
    require(run['id']==RUN and run['head_sha']==DRIVER and run['status']=='completed' and run['conclusion']=='failure' and run['run_attempt']==1,'Exact failed score2 run required')
    require(job['id']==JOB and job['run_id']==RUN and job['head_sha']==DRIVER and job['status']=='completed' and job['conclusion']=='failure','Exact failed score2 job required')
    require(artifact['id']==ARTIFACT and artifact['size_in_bytes']==SIZE and artifact['digest']=='sha256:'+SHA and artifact['expired'] is False and artifact['workflow_run']['id']==RUN and artifact['workflow_run']['head_sha']==DRIVER,'Exact original score2 artifact required')
    with get(f'actions/artifacts/{ARTIFACT}/zip',True) as response:raw=response.read(SIZE+1)
    require(len(raw)==SIZE and hashlib.sha256(raw).hexdigest()==SHA,'Original outer ZIP bytes differ')
    a.output.mkdir();archive_path=a.output/'original-score2-evidence.zip';archive_path.write_bytes(raw)
    rows=[];total=0
    with zipfile.ZipFile(archive_path) as archive:
        entries=reader.zip_rows(archive)
        print('CADENCE_SCORE2_SELECTED_MEMBERS '+json.dumps([{'path':n,'bytes':i.file_size} for n,i in entries.items() if '/score-edit-gui-results/' in '/'+n and Path(n).name in NAMES|SNAPSHOTS],separators=(',',':')))
        for name,info in sorted(entries.items()):
            if '/score-edit-gui-results/' not in '/'+name or Path(name).name not in NAMES|SNAPSHOTS:continue
            require(info.file_size<=2*1024**2,'Bounded original evidence file required')
            data=archive.read(info);total+=len(data);require(total<=8*1024**2 and len(rows)<24,'Selected evidence total bound')
            if name.endswith('.json'):value=json.loads(data.decode('utf-8-sig'))
            if name.endswith('.png'):require(data.startswith(b'\x89PNG\r\n\x1a\n'),'Original PNG signature required')
            if Path(name).name in SNAPSHOTS:
                require(isinstance(value,dict) and isinstance(value.get('nodes'),list),'Native diagnostic snapshot structure required')
                focused=[n for n in value['nodes'] if n.get('keyboard_focus') is True]
                scores=[n for n in value['nodes'] if str(n.get('name','')).startswith('Score')]
                projection={'projection_only':True,'path':name,'original_bytes':len(data),'original_sha256':hashlib.sha256(data).hexdigest(),
                    'snapshot_metadata':{k:v for k,v in value.items() if k not in ('nodes','graph_edges')},
                    'observed_nodes':len(value['nodes']),'focused_nodes':focused[:8],'score_context_nodes':scores[:8]}
                print('CADENCE_SCORE2_SNAPSHOT_FOCUS_PROJECTION '+json.dumps(projection,separators=(',',':')))
                continue
            row={'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'original_bytes_base64':base64.b64encode(data).decode('ascii')};rows.append(row)
            print('CADENCE_SCORE2_ORIGINAL_FILE_BEGIN');print(json.dumps(row,separators=(',',':')));print('CADENCE_SCORE2_ORIGINAL_FILE_END')
    names={Path(r['path']).name for r in rows}
    require({'score-edit-gui-report.json','score-edit-phase.json'}<=names,'Required failed native phase and result originals absent')
    receipt={'scope':'DATAONLY original failed score2 evidence; no application, SDK or profile operation',
       'run':RUN,'job':JOB,'driver':DRIVER,'artifact':ARTIFACT,'outer_bytes':SIZE,'outer_sha256':SHA,
       'outer_independently_rehashed':True,'application_executed':False,'GUI_validated':False,
       'files':[{k:v for k,v in r.items() if k!='original_bytes_base64'} for r in rows]}
    (a.output/'readback-receipt.json').write_bytes((json.dumps(receipt,indent=2)+'\n').encode('utf-8'))
    print('CADENCE_SCORE2_DATAONLY_RECEIPT '+json.dumps(receipt,separators=(',',':')))

if __name__=='__main__':main()
