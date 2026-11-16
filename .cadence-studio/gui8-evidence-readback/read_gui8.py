# SPDX-License-Identifier: GPL-3.0-only
"""Read two originals from a failed forced-close run; execute no payload.

The seven GUI phases passed, but forced closure prevented CLI comparison.
Reading the saved MIDI never changes that overall failed conclusion.
"""
from pathlib import Path
import argparse,base64,hashlib,importlib.util,json,os,urllib.request,zipfile
RUN=43973123714;JOB=133670148499;ARTIFACT=14279677013
DRIVER='19aa2916a4665e520c0e06d3f6ef5b0ca1273045'
SIZE=951776;SHA='cd40dbf5c2d52d77700b11e2b6209e1df1a7e92bae5d9b680d44fb221152de41'
PREFIX='_temp/import-dialogs-gui-results/'
PNG=PREFIX+'07-save-open-wav.png'
MIDI=PREFIX+'controlled-inputs/Cadence-QA-three-notes-transcription.mid'
REPORT=PREFIX+'import-dialogs-gui-report.json'
PNG_BYTES=79153;PNG_SHA='3f71cbb3ef3b7721119dbd48ee42571cc78b8fbc229aabfb8802625cc391df74'
REPORT_BYTES=229957;REPORT_SHA='7396e600c58078b9b05dbe27f50f8b87a230c166daf22bd08dd23c059fc7809b'

def require(ok,message):
    if not ok:raise ValueError(message)

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    require(os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('GITHUB_REPOSITORY')=='astrynome-byte/Music','Exact hosted repository context required')
    require(not a.output.exists() and a.output.is_absolute() and a.output.is_relative_to(Path(os.environ['RUNNER_TEMP'])),'New temporary data directory required')
    helper=Path(__file__).parent.parent/'retained-2008-data-readback/read_existing_stage.py'
    require(hashlib.sha256(helper.read_bytes()).hexdigest()=='9bdcbc4732057fc50f8ba5387578d68d292682864a21938b717d29df662875ae','Frozen safe DATAONLY reader required')
    spec=importlib.util.spec_from_file_location('safe_data_reader',helper);reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)
    token=os.environ['GH_TOKEN']
    def get(endpoint,redirect=False):
        request=urllib.request.Request('https://api.github.com/repos/astrynome-byte/Music/'+endpoint,
          headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','User-Agent':'Cadence-Saved-MIDI-DataOnly/1.0'})
        return urllib.request.build_opener(reader.PublicRedirectOnly() if redirect else reader.NoRedirect()).open(request,timeout=30)
    values=[]
    for endpoint in (f'actions/runs/{RUN}',f'actions/jobs/{JOB}',f'actions/artifacts/{ARTIFACT}'):
        with get(endpoint) as response:
            raw=response.read(2*1024**2+1)
            require(response.status==200 and len(raw)<=2*1024**2,'Bounded metadata HTTP200 required');values.append(json.loads(raw))
    run,job,artifact=values
    require(run['id']==RUN and run['head_sha']==DRIVER and run['status']=='completed' and run['conclusion']=='failure' and run['run_attempt']==1,'Exact failed overall SaveFixture run required')
    require(job['id']==JOB and job['run_id']==RUN and job['head_sha']==DRIVER and job['status']=='completed' and job['conclusion']=='failure','Exact failed SaveFixture job required')
    steps={s['number']:s for s in job['steps']}
    require(steps[9]['conclusion']=='success' and steps[10]['conclusion']=='failure','Actual observer compile PASS and GUI/cleanup failure required')
    require(artifact['id']==ARTIFACT and artifact['size_in_bytes']==SIZE and artifact['digest']=='sha256:'+SHA and artifact['expired'] is False and artifact['workflow_run']['id']==RUN and artifact['workflow_run']['head_sha']==DRIVER,'Exact original SaveFixture artifact required')
    with get(f'actions/artifacts/{ARTIFACT}/zip',True) as response:raw=response.read(SIZE+1)
    require(len(raw)==SIZE and hashlib.sha256(raw).hexdigest()==SHA,'Original outer ZIP bytes differ')
    a.output.mkdir();archive_path=a.output/'original-saved-midi-evidence.zip';archive_path.write_bytes(raw)
    rows=[];total=0
    with zipfile.ZipFile(archive_path) as archive:
        entries=reader.zip_rows(archive)
        require({PNG,MIDI,REPORT}<=set(entries),'Two exact selected members and report required')
        info=entries[REPORT];require(info.file_size==REPORT_BYTES,'Exact original report size required')
        raw=archive.read(info)
        require(len(raw)==REPORT_BYTES and hashlib.sha256(raw).hexdigest()==REPORT_SHA,'Original report must match actual runner receipt')
        report=json.loads(raw.decode('utf-8-sig'))
        require(report['status']=='failed-or-blocked' and report['app_close_forced'] is True and report['app_exit_code']==-1 and report['MIDI_file_saved'] is True and report['GUI_imported_score_focus_verified'] is True and report['MIDI_saved_or_opened'] is False and report['native_import_comparison'] is None,'Preserve forced-close failure and absent musical comparison')
        require(len(report['phases'])==7 and all(p['client_exit_code']==0 and p['report']['status']=='passed_owned_import_dialog_phase' and p['report']['local_final_state_verified'] for p in report['phases']),'Seven actual local GUI phases PASS required')
        captures=[c for c in report['captures'] if c['path'].replace('\\','/').endswith('/07-save-open-wav.png')]
        require(len(captures)==1 and captures[0]['bytes']==PNG_BYTES and captures[0]['sha256']==PNG_SHA,'PNG pin must match actual original capture receipt')
        for name in (PNG,MIDI):
            info=entries[name];require(0<info.file_size<=256*1024,'Bounded exact member required')
            data=archive.read(info);total+=len(data)
            require(len(data)==info.file_size and total<=256*1024 and len(rows)<2,'Bounded two-member evidence required')
            checksum=hashlib.sha256(data).hexdigest()
            if name==PNG:
                require(len(data)==PNG_BYTES and checksum==PNG_SHA and data.startswith(b'\x89PNG\r\n\x1a\n'),'Pinned original PNG required')
            else:require(len(data)>=22 and data[:4]==b'MThd','Bounded saved MIDI required; no notes inferred by reader')
            row={'path':name,'bytes':len(data),'sha256':checksum,'original_bytes_base64':base64.b64encode(data).decode('ascii'),
                 'member_identity_source':'actual runner capture receipt' if name==PNG else 'new size/SHA observation inside authenticated ZIP; not previously pinned'}
            if name==PNG:row['PNG_not_visually_reviewed']=True
            rows.append(row)
            print('CADENCE_GUI8_ORIGINAL_FILE_BEGIN');print(json.dumps(row,separators=(',',':')));print('CADENCE_GUI8_ORIGINAL_FILE_END')
    require(len(rows)==2 and {r['path'] for r in rows}=={PNG,MIDI},'Exactly two original members required')
    receipt={'scope':'DATAONLY saved MIDI and score PNG from overall failed forced-close run; no application execution',
       'run':RUN,'job':JOB,'driver':DRIVER,'artifact':ARTIFACT,'outer_bytes':SIZE,'outer_sha256':SHA,
       'outer_independently_rehashed':True,'original_report_SHA_verified':REPORT_SHA,'source_run_conclusion':'failure',
       'source_app_close_forced':True,'source_CLI_comparison_executed':False,'application_executed_by_reader':False,
       'GUI_validated_by_reader':False,'PNG_not_visually_reviewed':True,'notes_accuracy_validated_by_reader':False,
       'MusicXML_fidelity_validated':False,'listening_validated':False,
       'files':[{k:v for k,v in r.items() if k!='original_bytes_base64'} for r in rows]}
    (a.output/'readback-receipt.json').write_bytes((json.dumps(receipt,indent=2)+'\n').encode('utf-8'))
    print('CADENCE_GUI8_DATAONLY_RECEIPT '+json.dumps(receipt,separators=(',',':')))

if __name__=='__main__':main()
