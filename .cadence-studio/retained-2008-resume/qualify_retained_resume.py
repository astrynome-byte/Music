#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Close actual Windows QA receipts for unchanged original2008 stage; no MSI claim."""
import argparse
import json
import importlib.util
from pathlib import Path
import sys
_spec=importlib.util.spec_from_file_location('retained_configuration',Path(__file__).with_name('check_retained_configuration.py'))
_configuration=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_configuration)
CI,TREE,EXE=_configuration.CI,_configuration.TREE,_configuration.EXE
check,read,require,sha,unique_suffix=(_configuration.check,_configuration.read,_configuration.require,_configuration.sha,_configuration.unique_suffix)

ORIGINAL='a2b7abaf045a8f3cb84ec2953d9e0e51b9e78903'

def receipt(path):
    return {'passed':True,'path':str(path.resolve()),'bytes':path.stat().st_size,'sha256':sha(path)}

def qualify(temp,source,report):
    report['configuration_check']=check(temp,source)
    gates=report['gates']
    def gate(name,path,condition):
        value=read(path)
        require(condition(value),'Actual qualification failed or incomplete: '+name)
        gates[name]=receipt(path)
        return value
    gate('native_practice',temp/'qa-practice-native/report.json',lambda d:d.get('passed') is True)
    logs=temp/'retained-data-originals/originals/logs'
    omr=unique_suffix(logs,'cadence-omr-runner-tests/runner-report.json')
    gate('native_omr',omr,lambda d:d.get('status')=='passed-native-Windows-OMR-runner-boundary' and d.get('test_group_counts')==[15,17] and d.get('windows_job_descendant_terminated') is True)
    audio=temp/'qa-audio-transcription/runtime/audio-transcription-report.json'
    audio_data=gate('audio_transcription_import',audio,lambda d:d.get('passed') is True and d.get('executable_sha256')==EXE and d.get('source_commit')==CI and len(d.get('cases',[]))==2 and len(d.get('commands',[]))==8 and all(r.get('exit_code')==0 and r.get('timed_out') is False for r in d.get('commands',[])))
    require(audio_data['ctest']['passed'] is True and audio_data['ctest']['groups_observed']==9 and audio_data['ctest']['ctest_tests_observed']==1,'Nine actual production transcription groups required')
    gates['native_transcription']=receipt(audio)
    gate('cli57',temp/'qa-cadence/report.json',lambda d:d.get('executable_sha256')==EXE and len(d.get('checks',[]))==57 and all(r.get('passed') is True for r in d.get('checks',[])))
    gate('musical_roundtrip',temp/'qa-roundtrip-cadence/roundtrip-report.json',lambda d:d.get('passed') is True and len(d.get('fixtures',[]))==5)
    gate('reference35',temp/'qa-combined-reference-bytes/report.json',lambda d:d.get('passed') is True and d.get('matching_outputs')==35 and d.get('candidate_executable_sha256')==EXE)
    gate('aac5',temp/'qa-system-aac-music/report.json',lambda d:d.get('passed') is True and len(d.get('cases',[]))==5 and all(r.get('passed') is True for r in d.get('cases',[])))
    gate('stage_notices',temp/'qa-stage-notices/stage-notices-report.json',lambda d:d.get('passed') is True)
    gate('stage_GUI',temp/'gui-cadence/gui-report.json',lambda d:d.get('status')=='startup_observed_closed_cleanly' and d.get('exit_status')==0 and d.get('executable_sha256')==EXE and d.get('startup',{}).get('status')=='visible_window_responding_observed' and d.get('shutdown',{}).get('exit_code')==0 and d.get('shutdown',{}).get('forced') is False and d.get('probe_forced') is False)
    https=unique_suffix(logs,'qa-authorized-wav-HTTPS/qualification-report.json')
    original={}
    d=read(https)
    require(d['status']=='passed-Windows-native-authorized-WAV-HTTPS-only' and len(d['pass_groups'])==14 and d['prerequisite_probe']['passed'] is True,'Original14 HTTPS report incomplete')
    original['native_HTTPS14']=receipt(https)
    macro=unique_suffix(logs,'macro-profile-prebuild.json')
    require(read(macro)['status']=='PASS' and read(macro)['error_count']==0,'Original macro gate incomplete')
    original['macro_profile']=receipt(macro)
    unity=unique_suffix(logs,'project-unity-prebuild/report.json')
    d=read(unity)
    require(d['status']=='PASS' and len(d['units'])==2 and all(x['passed'] is True and x['exit_code']==0 for x in d['units']),'Original MSVC Unity gate incomplete')
    original['MSVC_Unity2']=receipt(unity)
    report['original_successful_gates_from_failed_producer']=original
    optional=temp/'qa-practice-hook/report.json'
    require(read(optional)['passed'] is False and read(optional)['probe_attempted'] is False,'Optional unavailable app-library hook must remain unqualified')
    report['optional_app_library_hook']={'qualified':False,'reason':'Original application static libraries were not retained','report':receipt(optional)}
    report['optional_app_library_hook']['report']['passed']=False
    report.update(ready=True,passed=True,status='passed-actual-retained2008-QA-only-no-installer-produced',counts={'cli_checks':57,'reference_outputs':35,'music_aac_cases':5},original_producer_overall_conclusion='failure',original_producer_failed_step=31,original_build_run_id=43408309742,original_build_job_id=131828068954,application_recompiled=False,installer_produced=False,installer_tested=False,physical_MIDI_and_human_listening_performed=False)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--temporary-root',type=Path,required=True);p.add_argument('--source-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();require(not a.output.exists(),'New qualification report required')
    report={'schema_version':1,'ready':False,'passed':False,'status':'failed-or-incomplete','source_original_commit':ORIGINAL,'source_ci_commit':CI,'source_tree':TREE,'executable_sha256':EXE,'build_number':2008,'product_version':'4.7.6.2008','application_recompiled':False,'gates':{},'errors':[]}
    try:qualify(a.temporary_root,a.source_root,report)
    except Exception as error:report['errors'].append(str(error))
    a.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('CADENCE_RETAINED2008_QUALIFICATION_BEGIN');print(json.dumps(report,separators=(',',':')));print('CADENCE_RETAINED2008_QUALIFICATION_END')
    return 0 if report['passed'] else 1

if __name__=='__main__':sys.exit(main())
