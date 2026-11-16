# SPDX-License-Identifier: GPL-3.0-only
"""Read exact complete successful WAV/MIDI-import evidence; execute no payload."""
from pathlib import Path
import argparse,base64,hashlib,importlib.util,json,os,urllib.request,zipfile
RUN=43981373919;JOB=133698411256;ARTIFACT=14281754685
DRIVER='e1f403ce652b3d9e7bfa1c75a71121d60b25e086'
SIZE=1027617;SHA='4bbbc9a02db12e246091475c4813c272f726adf6a3efb3fd61f8be15df5e938c'
PREFIX='_temp/import-dialogs-gui-results/'
REPORT=PREFIX+'import-dialogs-gui-report.json'
REPORT_BYTES=272714;REPORT_SHA='22c6ef60c323070feae5f4d08a9e1bbc0414038745fb29751800051e3a7e0132'
MIDI=PREFIX+'controlled-inputs/Cadence-QA-three-notes-transcription.mid'
XML=PREFIX+'controlled-inputs/native-import.musicxml'
COMPARISON=PREFIX+'saved-midi-comparison.json'
MEMBERS={
 XML:(6909,'11b5d7a143c9b48560a86d4d0bd6a10daaf9cb2d13f9690008a21e306e57c842'),
 COMPARISON:None,
 PREFIX+'07-save-open-wav.png':(79209,'84f419556df95b6936a7122bbce499b1f0405300c96abcf15a67201705c9df4c'),
 PREFIX+'08-close-saved-midi-score.png':(56386,'6aaecabbddb4c2a043533b2fc78446ed884bdc8da4916f0c2d2237514bd89559'),
}

def require(ok,message):
    if not ok:raise ValueError(message)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    require(os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('GITHUB_REPOSITORY')=='astrynome-byte/Music','Exact hosted repository required')
    require(args.output.is_absolute() and not args.output.exists() and args.output.is_relative_to(Path(os.environ['RUNNER_TEMP'])),'New temporary output required')
    helper=Path(__file__).parent.parent/'retained-2008-data-readback/read_existing_stage.py'
    require(hashlib.sha256(helper.read_bytes()).hexdigest()=='9bdcbc4732057fc50f8ba5387578d68d292682864a21938b717d29df662875ae','Frozen safe DATAONLY helper required')
    spec=importlib.util.spec_from_file_location('safe_data_reader',helper);reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)
    token=os.environ['GH_TOKEN']
    def get(endpoint,redirect=False):
        request=urllib.request.Request('https://api.github.com/repos/astrynome-byte/Music/'+endpoint,
          headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','User-Agent':'Cadence-Successful-MIDI-Import-DataOnly/1.0'})
        return urllib.request.build_opener(reader.PublicRedirectOnly() if redirect else reader.NoRedirect()).open(request,timeout=30)
    values=[]
    for endpoint in (f'actions/runs/{RUN}',f'actions/jobs/{JOB}',f'actions/artifacts/{ARTIFACT}'):
        with get(endpoint) as response:
            raw=response.read(2*1024**2+1);require(response.status==200 and len(raw)<=2*1024**2,'Bounded HTTP200 metadata required');values.append(json.loads(raw))
    run,job,artifact=values
    require(run['id']==RUN and run['head_sha']==DRIVER and run['status']=='completed' and run['conclusion']=='success' and run['run_attempt']==1,'Exact successful full SaveFixture run required')
    require(job['id']==JOB and job['run_id']==RUN and job['head_sha']==DRIVER and job['status']=='completed' and job['conclusion']=='success','Exact successful full SaveFixture job required')
    steps={step['number']:step for step in job['steps']}
    require(steps[9]['conclusion']=='success' and steps[10]['conclusion']=='success','Actual observer compile and GUI/native comparison step PASS required')
    require(artifact['id']==ARTIFACT and artifact['size_in_bytes']==SIZE and artifact['digest']=='sha256:'+SHA and artifact['expired'] is False and artifact['workflow_run']['id']==RUN and artifact['workflow_run']['head_sha']==DRIVER,'Exact successful original artifact required')
    with get(f'actions/artifacts/{ARTIFACT}/zip',True) as response:outer=response.read(SIZE+1)
    require(len(outer)==SIZE and hashlib.sha256(outer).hexdigest()==SHA,'Original authenticated ZIP differs')
    args.output.mkdir();archive_path=args.output/'original-successful-midi-import-evidence.zip';archive_path.write_bytes(outer)
    rows=[];total=0
    with zipfile.ZipFile(archive_path) as archive:
        entries=reader.zip_rows(archive);require((set(MEMBERS)|{REPORT,MIDI})<=set(entries),'Four selected originals, source report and saved MIDI required')
        report_info=entries[REPORT];require(report_info.file_size==REPORT_BYTES,'Exact report size required');raw=archive.read(report_info)
        require(len(raw)==REPORT_BYTES and hashlib.sha256(raw).hexdigest()==REPORT_SHA,'Original source report must match runner receipt')
        report=json.loads(raw.decode('utf-8-sig'))
        require(report['status']=='passed_actual_import_dialogs_and_clean_owned_exit' and report['app_exit_code']==0 and report['app_close_forced'] is False and report['probe_forced'] is False and report['native_export_forced'] is False and report['forced_descendants']==0 and report['profile_cleanup_verified'] is True and report['job_closed_cleanly'] is True and not report['errors'] and not report['qml_error_matches'],'Exact clean application/profile/owned-process result required')
        phases=report['phases'];require([p['phase'] for p in phases]==['open-omr','close-omr','open-wav','close-wav','open-wav','analyze-wav','save-open-wav','close-saved-midi-score'] and all(p['client_exit_code']==0 and p['report']['status']=='passed_owned_import_dialog_phase' and p['report']['local_final_state_verified'] and not p['report']['blocking_observation_failure'] for p in phases),'Eight exact local GUI phases PASS required')
        close=phases[-1]['report']
        require(close['controlled_score_closed_to_home'] is True and close['close_confirmation_discarded'] is True,'Exact temporary score discard and Home return required')
        comparison=report['native_import_comparison'];require(report['MIDI_saved_or_opened'] is True and comparison['status']=='passed_actual_saved_MIDI_and_native_import_exact' and comparison['midi_vs_musicxml_timing_exact'] is True,'Actual native import comparison PASS required')
        require(comparison['musicxml']['bytes']==MEMBERS[XML][0] and comparison['musicxml']['sha256']==MEMBERS[XML][1],'Native XML member pin must match report')
        midi=reader.stream_entry(archive,entries[MIDI])
        require(midi=={'bytes':116,'sha256':'913bf49867eadb1895a9438d8a4b64e1aa5038a41b1ebe018b21a91920647c8a'} and report['saved_MIDI_receipt']['bytes']==midi['bytes'] and report['saved_MIDI_receipt']['sha256']==midi['sha256'],'Same actual saved MIDI must independently rehash; do not re-emit duplicate bytes')
        for name,pin in MEMBERS.items():
            info=entries[name];require(0<info.file_size<=131072,'Bounded selected member required')
            if pin is not None:require(info.file_size==pin[0],'Exact pinned member size required')
            else:require(info.file_size<=16384,'Bounded original comparison JSON required')
            data=archive.read(info);total+=len(data);require(len(data)==info.file_size and total<=262144 and len(rows)<4,'Four-original total bound required')
            checksum=hashlib.sha256(data).hexdigest()
            if pin is not None:require(checksum==pin[1],'Original pinned member SHA differs')
            if name==COMPARISON:require(json.loads(data.decode('utf-8-sig'))==comparison,'Original comparison JSON must equal actual report object')
            if name.endswith('.png'):
                require(data.startswith(b'\x89PNG\r\n\x1a\n'),'Original PNG signature required')
                matches=[c for c in report['captures'] if c['path'].replace('\\','/').endswith('/'+Path(name).name)]
                require(len(matches)==1 and matches[0]['bytes']==len(data) and matches[0]['sha256']==checksum,'PNG must match actual capture receipt')
            row={'path':name,'bytes':len(data),'sha256':checksum,'original_bytes_base64':base64.b64encode(data).decode('ascii'),
                 'member_identity_source':'new measurement inside authenticated ZIP plus equality to report comparison object' if pin is None else 'actual runner size/SHA receipt'}
            if name.endswith('.png'):row['PNG_not_visually_reviewed']=True
            rows.append(row);print('CADENCE_GUI8_ORIGINAL_FILE_BEGIN');print(json.dumps(row,separators=(',',':')));print('CADENCE_GUI8_ORIGINAL_FILE_END')
    require(len(rows)==4 and {r['path'] for r in rows}==set(MEMBERS),'Exactly four selected originals required')
    receipt={'scope':'DATAONLY originals from successful complete SaveFixture run; reader executes no application',
       'run':RUN,'job':JOB,'driver':DRIVER,'artifact':ARTIFACT,'outer_bytes':SIZE,'outer_sha256':SHA,'outer_independently_rehashed':True,
       'original_report_sha256_verified':REPORT_SHA,'source_run_conclusion':'success','source_GUI_phases_passed':8,'source_app_exit_code':0,
       'source_app_close_forced':False,'source_profile_clean':True,'source_native_CLI_comparison_executed':True,'actual_saved_MIDI_independently_rehashed':midi,
       'post_GUI_full_2712_file_inventory_claimed':False,'application_executed_by_reader':False,'GUI_validated_by_reader':False,'PNGs_not_visually_reviewed':True,
       'notes_reparsed_by_this_reader':False,'human_listening_performed':False,'files':[{k:v for k,v in r.items() if k!='original_bytes_base64'} for r in rows]}
    (args.output/'readback-receipt.json').write_bytes((json.dumps(receipt,indent=2)+'\n').encode('utf-8'))
    print('CADENCE_GUI8_DATAONLY_RECEIPT '+json.dumps(receipt,separators=(',',':')))

if __name__=='__main__':main()
