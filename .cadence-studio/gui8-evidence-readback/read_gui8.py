# SPDX-License-Identifier: GPL-3.0-only
"""Read only exact successful score5 exports, captures and cleanup evidence."""
from pathlib import Path
import argparse,base64,hashlib,importlib.util,json,os,urllib.request,zipfile
RUN=43964745015;JOB=133641099654;ARTIFACT=14275846506
DRIVER='8620a230d553e2f16cb9b112981fc80bfcdd98c7'
SIZE=692733;SHA='7557883bf7c509d0bde9cd2c2342968c65b62f313dc72379016abb0b8bd3163f'
REPORT_SHA='59037b5e68549ce4531d06028f8b17733984e41f2a1fa6c704231c1937aca6c3'
NAMES={'baseline.musicxml','edited.musicxml','undo.musicxml','redo.musicxml',
       'edit-save.png','undo-save.png','redo-save.png','native-musical-comparison.json',
       'profile-scope.json','stage-final.json'}

def require(ok,message):
    if not ok:raise ValueError(message)

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    require(os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('GITHUB_REPOSITORY')=='astrynome-byte/Music','Exact hosted repository required')
    require(a.output.is_absolute() and not a.output.exists() and a.output.is_relative_to(Path(os.environ['RUNNER_TEMP'])),'New temporary output required')
    helper=Path(__file__).parent.parent/'retained-2008-data-readback/read_existing_stage.py'
    require(hashlib.sha256(helper.read_bytes()).hexdigest()=='9bdcbc4732057fc50f8ba5387578d68d292682864a21938b717d29df662875ae','Frozen safe DATAONLY reader required')
    spec=importlib.util.spec_from_file_location('safe_data_reader',helper);reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)
    token=os.environ['GH_TOKEN']
    def get(endpoint,redirect=False):
        req=urllib.request.Request('https://api.github.com/repos/astrynome-byte/Music/'+endpoint,
          headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','User-Agent':'Cadence-Score5-DataOnly/1.0'})
        return urllib.request.build_opener(reader.PublicRedirectOnly() if redirect else reader.NoRedirect()).open(req,timeout=30)
    values=[]
    for endpoint in (f'actions/runs/{RUN}',f'actions/jobs/{JOB}',f'actions/artifacts/{ARTIFACT}'):
        with get(endpoint) as response:
            data=response.read(2*1024**2+1);require(response.status==200 and len(data)<=2*1024**2,'Bounded metadata HTTP200 required');values.append(json.loads(data))
    run,job,artifact=values
    require(run['id']==RUN and run['head_sha']==DRIVER and run['status']=='completed' and run['conclusion']=='success' and run['run_attempt']==1,'Exact successful score5 run required')
    require(job['id']==JOB and job['run_id']==RUN and job['head_sha']==DRIVER and job['status']=='completed' and job['conclusion']=='success','Exact successful score5 job required')
    require(artifact['id']==ARTIFACT and artifact['size_in_bytes']==SIZE and artifact['digest']=='sha256:'+SHA and artifact['expired'] is False and artifact['workflow_run']['id']==RUN and artifact['workflow_run']['head_sha']==DRIVER,'Exact successful score5 artifact required')
    with get(f'actions/artifacts/{ARTIFACT}/zip',True) as response:data=response.read(SIZE+1)
    require(len(data)==SIZE and hashlib.sha256(data).hexdigest()==SHA,'Original outer ZIP bytes differ')
    a.output.mkdir();archive_path=a.output/'original-score5-evidence.zip';archive_path.write_bytes(data)
    rows=[];native_rows=[];seen_bytes={};total=0
    with zipfile.ZipFile(archive_path) as archive:
        entries=reader.zip_rows(archive)
        reports=[n for n in entries if n.endswith('/score-edit-gui-results/score-edit-gui-report.json')]
        require(len(reports)==1,'One original score result required');raw=archive.read(entries[reports[0]])
        require(len(raw)==143030 and hashlib.sha256(raw).hexdigest()==REPORT_SHA,'Original report differs from SHA already printed and locally reconstructed')
        report=json.loads(raw.decode('utf-8-sig'))
        require(report['status']=='passed_actual_GUI_edit_save_single_undo_redo_and_native_comparison' and report['app_exit_code']==0 and report['forced_owned_processes']==report['forced_descendants']==0 and report['profile_cleanup_verified'] and report['stage_unchanged'] and not report['errors'],'Exact successful musical and cleanup report required')
        expected={r['name']+'.mscz':{'bytes':r['bytes'],'sha256':r['sha256']} for r in report['snapshots']}
        for name,info in sorted(entries.items()):
            if '/score-edit-gui-results/' not in '/'+name:continue
            basename=Path(name).name
            if basename in expected and '/controlled-scores/' in '/'+name:
                measured=reader.stream_entry(archive,info);require(measured==expected[basename],'Original native snapshot differs from actual save receipt');native_rows.append({'path':name,**measured})
            if basename not in NAMES:continue
            require(info.file_size<=512*1024,'Bounded original evidence file required');raw=archive.read(info);total+=len(raw)
            require(total<=2*1024**2 and len(rows)<16,'Selected original evidence bound')
            if name.endswith('.json'):json.loads(raw.decode('utf-8-sig'))
            if name.endswith('.png'):require(raw.startswith(b'\x89PNG\r\n\x1a\n'),'Original PNG signature required')
            checksum=hashlib.sha256(raw).hexdigest();row={'path':name,'bytes':len(raw),'sha256':checksum}
            if checksum in seen_bytes:
                prior_name,prior_data=seen_bytes[checksum];require(raw==prior_data,'Duplicate original bytes must be exact');row['duplicate_original_bytes_of']=prior_name
            else:
                row['original_bytes_base64']=base64.b64encode(raw).decode('ascii');seen_bytes[checksum]=(name,raw)
            rows.append(row);print('CADENCE_SCORE5_ORIGINAL_FILE_BEGIN');print(json.dumps(row,separators=(',',':')));print('CADENCE_SCORE5_ORIGINAL_FILE_END')
    require({Path(r['path']).name for r in rows}==NAMES and len(rows)==len(NAMES),'All ten exact original exports/captures/cleanup files required')
    require({Path(r['path']).name for r in native_rows}==set(expected) and len(native_rows)==3,'All three immutable native snapshots must independently rehash')
    receipt={'scope':'DATAONLY successful score5 original evidence; no application, SDK, installer or profile operation',
       'run':RUN,'job':JOB,'driver':DRIVER,'artifact':ARTIFACT,'outer_bytes':SIZE,'outer_sha256':SHA,
       'outer_independently_rehashed':True,'report_original_SHA_verified':REPORT_SHA,'application_executed':False,
       'native_snapshots_independently_rehashed':native_rows,
       'files':[{k:v for k,v in r.items() if k!='original_bytes_base64'} for r in rows]}
    (a.output/'readback-receipt.json').write_bytes((json.dumps(receipt,indent=2)+'\n').encode('utf-8'))
    print('CADENCE_SCORE5_DATAONLY_RECEIPT '+json.dumps(receipt,separators=(',',':')))

if __name__=='__main__':main()
