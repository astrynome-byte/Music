# SPDX-License-Identifier: GPL-3.0-only
"""Read exact close-confirmation evidence from failed overall run; execute no payload."""
from pathlib import Path
import argparse,base64,hashlib,importlib.util,json,os,urllib.request,zipfile
RUN=43978017627;JOB=133686909049;ARTIFACT=14282296187
DRIVER='15ab578c556b5a8142d50fa74e3f71cd6766dde8'
SIZE=990813;SHA='a8ed115c4e01aecdff4aafc2baf75312b11b9df91d5fb9abc5055a8ca6731e8b'
PREFIX='_temp/import-dialogs-gui-results/'
REPORT=PREFIX+'import-dialogs-gui-report.json'
REPORT_BYTES=268350;REPORT_SHA='9d6e3bcdba28487a5168faf19505e30caaec3d4227933b1b31d4766d53fdf431'
MEMBERS={
    PREFIX+'08-close-saved-midi-score-blocked-passive.png':
        (19788,'7426df0a8bde39efd3ce58336e594b1e034ba815ebed88904ab8f2f3f9454201'),
    PREFIX+'08-close-saved-midi-score/import-dialog-phase.json':
        (15259,'0c431b865750263f27ba3b1b4b6ca4d63960b52f6904ad73d0dcb486c13faf65'),
}
EXPECTED_FOCUSED_QUESTION='Voulez-vous enregistrer les modifications de la partition "Cadence-QA-three-notes-transcription.mid" avant la fermeture ? Vos modifications seront perdues si vous ne les sauvegardez pas. Enregistrer'

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
          headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','User-Agent':'Cadence-CloseConfirmation-DataOnly/1.0'})
        return urllib.request.build_opener(reader.PublicRedirectOnly()if redirect else reader.NoRedirect()).open(request,timeout=30)
    values=[]
    for endpoint in (f'actions/runs/{RUN}',f'actions/jobs/{JOB}',f'actions/artifacts/{ARTIFACT}'):
        with get(endpoint)as response:raw=response.read(2*1024**2+1);require(response.status==200 and len(raw)<=2*1024**2,'Bounded metadata HTTP200 required');values.append(json.loads(raw))
    run,job,artifact=values
    require(run['id']==RUN and run['head_sha']==DRIVER and run['status']=='completed'and run['conclusion']=='failure'and run['run_attempt']==1,'Exact failed close-confirmation run required')
    require(job['id']==JOB and job['run_id']==RUN and job['head_sha']==DRIVER and job['status']=='completed'and job['conclusion']=='failure','Exact failed close-confirmation job required')
    steps={row['number']:row for row in job['steps']}
    require(steps[9]['conclusion']=='success' and steps[10]['conclusion']=='failure','Actual observer compile PASS and UI step failure required')
    require(artifact['id']==ARTIFACT and artifact['size_in_bytes']==SIZE and artifact['digest']=='sha256:'+SHA and artifact['expired']is False and artifact['workflow_run']['id']==RUN and artifact['workflow_run']['head_sha']==DRIVER,'Exact original990813-byte close-confirmation artifact required')
    with get(f'actions/artifacts/{ARTIFACT}/zip',True)as response:raw=response.read(SIZE+1)
    require(len(raw)==SIZE and hashlib.sha256(raw).hexdigest()==SHA,'Original outer ZIP bytes differ')
    a.output.mkdir();archive_path=a.output/'original-close-confirmation-evidence.zip';archive_path.write_bytes(raw)
    rows=[];total=0
    with zipfile.ZipFile(archive_path)as archive:
        entries=reader.zip_rows(archive)
        require((set(MEMBERS)|{REPORT})<=set(entries),'Two exact members and original report required')
        info=entries[REPORT];require(info.file_size==REPORT_BYTES,'Exact original report size required')
        report_raw=archive.read(info)
        require(len(report_raw)==REPORT_BYTES and hashlib.sha256(report_raw).hexdigest()==REPORT_SHA,'Original report must match actual runner receipt')
        report=json.loads(report_raw.decode('utf-8-sig'));phases=report['phases']
        require(report['status']=='failed-or-blocked' and report['app_close_forced'] is True and report['app_exit_code']==-1 and report['native_import_comparison'] is None and report['MIDI_saved_or_opened'] is False,'Preserve overall forced-close failure and absent CLI comparison')
        require(len(phases)==8 and all(r['client_exit_code']==0 and r['report']['status']=='passed_owned_import_dialog_phase' and r['report']['local_final_state_verified'] for r in phases[:7]),'Exactly seven earlier local GUI phases PASS required')
        blocked=phases[7];native=blocked['report'];last=native['close_last_observation']
        require(blocked['client_exit_code']==2 and blocked['phase']=='close-saved-midi-score' and native['status']=='blocked_or_failed_import_dialog_phase' and native['close_anchor_operation']=='question.element_bound' and native['close_confirmation_discarded'] is False and native['controlled_score_closed_to_home'] is False and native['close_confirmation_navigation_keys']==0,'Require refusal before any DontSave navigation/decision')
        require(last['stage']=='temporary_score_close_confirmation' and last['focused_name']==EXPECTED_FOCUSED_QUESTION and last['focused_type']==50000 and last['pid']==blocked['pid'] and last['local_focus_verified'] is True and last['keyboard_focus'] is True,'Exact owned focused complete question must be observed')
        require(all(r['action']=='import_owned_key' for r in native['actions']) and native['actions'][-1]['purpose']=='close_only_named_temporary_imported_score' and native['actions'][-1]['sent'] is True,'Only source file-menu close action is allowed before refusal')
        captures=[r for r in report['captures'] if r['path'].replace('\\','/').endswith('/08-close-saved-midi-score-blocked-passive.png')]
        require(len(captures)==1 and captures[0]['bytes']==19788 and captures[0]['sha256']==MEMBERS[PREFIX+'08-close-saved-midi-score-blocked-passive.png'][1] and blocked['sha256']==MEMBERS[PREFIX+'08-close-saved-midi-score/import-dialog-phase.json'][1],'Member pins must match actual runner receipts')
        for name,(expected_bytes,expected_sha256)in MEMBERS.items():
            info=entries[name]
            require(info.file_size==expected_bytes and info.file_size<=2*1024**2,'Exact bounded member size required')
            data=archive.read(info);total+=len(data)
            require(total<=128*1024 and len(rows)<2,'Bounded two-member evidence required')
            require(len(data)==expected_bytes and hashlib.sha256(data).hexdigest()==expected_sha256,'Original selected member bytes differ')
            if name.endswith('.json'):require(json.loads(data.decode('utf-8-sig'))==native,'Exact original native phase must match actual report object')
            else:require(data.startswith(b'\x89PNG\r\n\x1a\n'),'Pinned PNG signature required')
            row={'path':name,'bytes':len(data),'sha256':expected_sha256,'original_bytes_base64':base64.b64encode(data).decode('ascii')}
            if name.endswith('.png'):row['PNG_not_visually_reviewed']=True
            rows.append(row)
            print('CADENCE_GUI8_ORIGINAL_FILE_BEGIN');print(json.dumps(row,separators=(',',':')));print('CADENCE_GUI8_ORIGINAL_FILE_END')
    require(len(rows)==2 and {r['path']for r in rows}==set(MEMBERS)and total==sum(v[0]for v in MEMBERS.values()),'Exactly the two pinned originals are required')
    receipt={'scope':'DATAONLY exact failed close-confirmation originals; no application or SDK execution, no visual validation',
       'run':RUN,'job':JOB,'driver':DRIVER,'artifact':ARTIFACT,'outer_bytes':SIZE,'outer_sha256':SHA,
       'outer_independently_rehashed':True,'source_run_conclusion':'failure','source_app_close_forced':True,'source_CLI_comparison_executed':False,'source_DontSave_decision_sent':False,'original_report_sha256_verified':REPORT_SHA,'application_executed':False,'GUI_validated':False,'PNG_not_visually_reviewed':True,
       'normal_close_validated':False,'DontSave_decision_validated':False,'MusicXML_fidelity_validated':False,'listening_validated':False,
       'files':[{k:v for k,v in r.items()if k!='original_bytes_base64'}for r in rows]}
    (a.output/'readback-receipt.json').write_bytes((json.dumps(receipt,indent=2)+'\n').encode('utf-8'));print('CADENCE_GUI8_DATAONLY_RECEIPT '+json.dumps(receipt,separators=(',',':')))
if __name__=='__main__':main()
