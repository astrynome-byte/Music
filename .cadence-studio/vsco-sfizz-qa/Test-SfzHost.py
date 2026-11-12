#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Qualify the real retained Windows Cadence host with an owned sfizz/CC0 subset.

Scan before downloading the sample set. No fabricated plugin register entries,
no global plugin install, and no claim of direct SFZ support in MuseScore.
"""
from __future__ import annotations
import argparse
import base64
import ctypes
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

EXE_SHA='35d8b076cacddb8b37a4f23aeea9899e6ab4ac9214e9a5b1125bbeccf26cf39e'
BASIC_SHA='5ea2375e8bd7d8e71def1036978c1621e85b66934169b6a2744b27b9b3c2d99c'
READER_SHA='b034341678fac5266faea3e361e5d1a618910e2f885bfd09a2dd4edd9d833f6f'
STATE_SHA='e4b37b0426712abd5fe29bdee95f2818cea26edcb4561ca11413a48f36b7bb01'
WAV_TOOL_SHA='f701874e7a37b8d3148f0bb99477b60b96865e804ed238372d75c06598027d82'


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def no_links(path):
    for item in [path,*path.parents]:
        if item.is_symlink() or getattr(item,'is_junction',lambda:False)():raise ValueError('Runtime paths cannot traverse links')


def owned(path):
    path=path.absolute();no_links(path);path=path.resolve()
    if Path(os.environ['RUNNER_TEMP']).resolve() not in path.parents:raise ValueError('Runtime paths must be strictly below RUNNER_TEMP')
    return path


def load_helper(name,filename,pin):
    path=Path(__file__).with_name(filename)
    if sha(path)!=pin:raise ValueError('Pinned helper changed: '+filename)
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module;spec.loader.exec_module(module);return module


def snapshot(root):
    result={}
    if root.is_dir():
        logs=list(root.rglob('*.log'))
        if len(logs)>32:raise ValueError('Unexpected fresh-profile log count')
        for path in logs:
            no_links(path)
            if path.stat().st_size>16777216:raise ValueError('Application log exceeds its bound')
            result[str(path)]=path.read_bytes()
    return result


def log_delta(before,after):
    return b'\n'.join(data[len(before.get(name,b'')):] if data.startswith(before.get(name,b'')) else data
                       for name,data in after.items()).decode('utf-8',errors='replace')


def native_audio(path):
    with zipfile.ZipFile(path) as archive:return json.loads(archive.read('audiosettings.json'))


def assign_plugin(base,target,registered,patch,state):
    with zipfile.ZipFile(base) as archive:
        masters=[name for name in archive.namelist() if name.endswith('.mscx') and '/' not in name]
        if len(masters)!=1:raise ValueError('Unique actual native master required')
        score=ET.fromstring(archive.read(masters[0]));tracks=[]
        for part in score.findall('./Score/Part'):
            for instrument in part.findall('Instrument'):
                if not part.get('id') or not instrument.get('id'):raise ValueError('Actual part/instrument IDs required')
                tracks.append({'partId':part.get('id'),'instrumentId':instrument.get('id'),
                    'in':state.audio_input_from_registered_plugin(registered,str(patch),volume_db=-12.0),
                    'out':{'balance':0,'volumeDb':0,'fxChain':{},'auxSends':[]},'soloMuteState':{'mute':False,'solo':False}})
        if len(tracks)!=1:raise ValueError('This small reader qualification requires exactly one real track')
        settings=native_audio(base);settings['activeSoundProfile']='MuseScore Basic';settings['tracks']=tracks
        # Dry and linear master/aux paths keep the controlled-gain proof meaningful.
        settings['master']={'balance':0,'volumeDb':0,'fxChain':{},'auxSends':[]};settings['aux']=[]
        with zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED) as output:
            for info in archive.infolist():output.writestr(info,json.dumps(settings,ensure_ascii=False).encode('utf-8') if info.filename=='audiosettings.json' else archive.read(info))
    return tracks


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--phase',choices=('scan','render'),required=True)
    p.add_argument('--stage',type=Path,required=True);p.add_argument('--assets',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if os.name!='nt' or platform.machine().lower() not in ('amd64','x86_64') or os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('CI')!='true' or os.environ.get('RUNNER_ENVIRONMENT')!='github-hosted':
        raise ValueError('Only disposable native Windows x64 GitHub-hosted runners allowed')
    stage=owned(args.stage);assets=owned(args.assets);output=owned(args.output)
    if len({stage,assets,output})!=3 or any(a in b.parents for a in (stage,assets,output) for b in (stage,assets,output) if a!=b):raise ValueError('Stage, assets and outputs must be separate owned directories')
    executable=stage/'bin/CadenceStudio4.exe';basic=list(stage.rglob('MS Basic.sf3'))
    if sha(executable)!=EXE_SHA or len(basic)!=1 or sha(basic[0])!=BASIC_SHA:raise ValueError('Retained executable/MS Basic identity differs')
    reader=json.loads((assets/'reader-assets.json').read_text());bundle=owned(Path(reader['assets']['bundle']));binary=owned(Path(reader['assets']['binary']))
    if not reader['passed'] or assets not in bundle.parents or sha(binary)!=READER_SHA:raise ValueError('Exact verified owned x64 reader required')
    local=Path(os.environ['LOCALAPPDATA'])/'CadenceStudio';roaming=Path(os.environ['APPDATA'])/'CadenceStudio'
    buffer=ctypes.create_unicode_buffer(32768)
    if ctypes.windll.shell32.SHGetFolderPathW(None,5,None,0,buffer)!=0:raise ValueError('Cannot resolve disposable Documents')
    documents=Path(buffer.value).resolve()/'CadenceStudio4'
    for path in (local,roaming,documents):no_links(path)
    registry=local/'CadenceStudio4/known_audio_plugins.json';logs=local/'CadenceStudio4/logs'
    if args.phase=='scan':
        if output.exists() or local.exists() or roaming.exists() or documents.exists():raise ValueError('Existing profiles/documents/output are never touched')
        output.mkdir();report={'schema_version':1,'status':'running_scan','retained_build':2002,'executable_sha256':EXE_SHA,
            'reader_binary_sha256':READER_SHA,'reader_bundle':str(bundle),'commands':[],'cases':[],
            'effects_disabled_for_gain_control':True,
            'fresh_profile_and_documents':True,'global_plugin_install_performed':False,'raw_SFZ_support_assumed':False,
            'new_manager_UI_tested':False,'human_listening_performed':False,'same_project_save_after_playback_tested':False,'error':None}
    else:
        report=json.loads((output/'sfz-host-report.json').read_text())
        if report['status']!='passed_actual_reader_scan' or report['reader_bundle']!=str(bundle) or not registry.is_file():raise ValueError('Successfully completed owned scan must precede render')
        if sha(registry)!=report['registered_plugins_sha256']:raise ValueError('Real scan registry changed before render')
        report['status']='running_render';report['error']=None
    env={key:value for key,value in os.environ.items() if not key.startswith(('QT_','QML_'))}
    env['PATH']=str(executable.parent)+';'+str(Path(os.environ['SystemRoot'])/'System32')
    report['child_PATH']=env['PATH'];report['inherited_Qt_QML_environment_removed']=True
    def run(name,arguments):
        before=snapshot(logs);start=time.monotonic();item={'name':name,'exit_code':None,'timed_out':False,'pid':None};report['commands'].append(item)
        with (output/(name+'.stdout.txt')).open('xb') as out,(output/(name+'.stderr.txt')).open('xb') as err:
            process=subprocess.Popen([str(executable),*map(str,arguments)],cwd=output,env=env,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
            item['pid']=process.pid
            try:item['exit_code']=process.wait(timeout=90)
            except subprocess.TimeoutExpired:item['timed_out']=True;process.kill();item['exit_code']=process.wait(timeout=10)
        item['seconds']=time.monotonic()-start;delta=log_delta(before,snapshot(logs));(output/(name+'.cadence-log.txt')).write_text(delta,encoding='utf-8')
        if item['timed_out'] or item['exit_code']!=0:raise RuntimeError('Owned native command failed: '+name)
        stdout_path=output/(name+'.stdout.txt');stderr_path=output/(name+'.stderr.txt')
        item['stdout_bytes']=stdout_path.stat().st_size;item['stderr_bytes']=stderr_path.stat().st_size
        if item['stdout_bytes']>16777216 or item['stderr_bytes']>16777216:raise RuntimeError('Owned process diagnostics exceeded their bound')
        return delta+'\n'+stdout_path.read_text(encoding='utf-8',errors='replace')+'\n'+stderr_path.read_text(encoding='utf-8',errors='replace')
    try:
        if args.phase=='scan':
            run('reader-register',['--register-audio-plugin',bundle])
            if not registry.is_file():raise RuntimeError('Actual CLI scan did not produce its native plugin register')
            registered=json.loads(registry.read_text());report['actual_scan_records']=registered
            matches=[item for item in registered if item.get('enabled') is True and Path(item.get('path','')).resolve()==bundle]
            if len(registered)!=1 or len(matches)!=1:raise RuntimeError('Expected exactly the single owned enabled reader from the real scan')
            value=matches[0];meta=value.get('meta',{})
            if meta.get('id')!='sfizz' or meta.get('type')!='VstPlugin' or 'Instrument' not in meta.get('attributes',{}).get('categories','').split('|'):raise RuntimeError('Actual registered reader has unexpected resource identity/category')
            report['registered_plugin']=value;report['registered_plugins_sha256']=sha(registry)
            report['real_native_reader_scan_verified']=True;report['SFZ_sample_load_tested']=False
            report['status']='passed_actual_reader_scan'
        else:
            state=load_helper('cadence_sfizz_state','sfizz_state.py',STATE_SHA);wavtool=load_helper('cadence_sfz_wav','corpus_run_exports.py',WAV_TOOL_SHA)
            sample_report=json.loads((assets/'sample-assets.json').read_text())
            if not sample_report['passed'] or sample_report['assets']['original_file_count']!=46:raise ValueError('Exact verified CC0 source subset required')
            sample=sample_report['assets'];report['sample_asset_receipt']=sample
            root=owned(Path(sample['root']))
            if assets not in root.parents:raise ValueError('Samples must stay under owned asset root')
            def check_assets():
                for pin in sample['original_records']:
                    path=root/pin['file'];no_links(path)
                    if root not in path.resolve().parents or path.stat().st_size!=pin['bytes'] or sha(path)!=pin['sha256']:return False
                derivative=root/sample['qa_derivative']['file']
                return sha(derivative)==sample['qa_derivative']['sha256'] and sha(binary)==READER_SHA and sha(executable)==EXE_SHA and sha(basic[0])==BASIC_SHA
            if not check_assets():raise ValueError('An inspected source/reader byte changed before render')
            fixture=Path(__file__).with_name('fixtures')/'sfz-probe.musicxml';pin=json.loads((fixture.parent/'pins.json').read_text())[fixture.name]
            if sha(fixture)!=pin:raise ValueError('Original CC0 exercise differs')
            copied=output/'sfz-probe-source.musicxml';shutil.copyfile(fixture,copied);base=output/'sfz-probe-base.mscz'
            run('import-original-exercise',['-o',base,copied])
            diagnostic_errors=('Unable to find vst plugin module','Unable to load vst plugin provider','Unable to initialize vst plugin provider','Component state restore failed','Controller state restore failed','[Sfizz] file not found:')
            for label,patch_name in (('flute','FluteSusVib.sfz'),('violin','SViolinVib.sfz'),('flute-minus18','Cadence-QA-Flute-minus18.sfz')):
                patch=owned(Path(sample['patches'][patch_name]));native=output/(label+'.mscz')
                if root not in patch.parents:raise ValueError('Patch outside owned CC0 subset')
                tracks=assign_plugin(base,native,report['registered_plugin'],patch,state);before=sha(native);wav=output/(label+'.wav')
                delta=run(label+'-render',['-o',wav,native]);audio=wavtool.inspect_wav(wav)
                bad=[text for text in diagnostic_errors if text.lower() in delta.lower()]
                value={'variant':label,'SFZ':patch_name,'requested_master_gain_db':-12.0,'requested_tracks':len(tracks),
                       'audio':audio,'wav_sha256':sha(wav),'native_source_sha256':before,'native_source_unchanged':sha(native)==before,
                       'vst_load_or_state_error_markers':bad,'SFZ_sample_load_not_inferred_from_nonquiet_audio_alone':True}
                report['cases'].append(value)
                if bad or not audio['passed'] or audio['channels']!=2 or not value['native_source_unchanged']:raise RuntimeError('VST load diagnostic or WAV/source validation failed')
                saved=output/(label+'-save-only.mscz');run(label+'-save-only',['-o',saved,native]);saved_tracks=native_audio(saved).get('tracks',[])
                wanted={(item['partId'],item['instrumentId']):item['in'] for item in tracks}
                actual={(item.get('partId'),item.get('instrumentId')):item.get('in',{}) for item in saved_tracks}
                value['save_only_track_resource_and_raw_state_preserved']=all(actual.get(key)==item for key,item in wanted.items()) and len(actual)==len(wanted)
                if not value['save_only_track_resource_and_raw_state_preserved'] or sha(native)!=before:raise RuntimeError('Save-only VST identity/state or source preservation failed')
                encoded=tracks[0]['in']['unitConfiguration']['componentState'];decoded=state.read_component_state(base64.b64decode(encoded,validate=True))
                value['requested_component_state']={'bytes':len(base64.b64decode(encoded)),'sha256':hashlib.sha256(base64.b64decode(encoded)).hexdigest(),'decoded':decoded}
            flute,violin,quiet=report['cases'];ratio=quiet['audio']['rms']/flute['audio']['rms'];expected=10**(-18.0/20.0)
            same_shape=all(flute['audio'][key]==quiet['audio'][key] for key in ('encoding','bits','channels','sample_rate','duration_seconds'))
            proof={'region_gain_delta_db':-18.0,'expected_rms_ratio':expected,'actual_rms_ratio':ratio,'relative_tolerance':0.03,
                   'matching_WAV_shape':same_shape,'gain_ratio_matches':abs(ratio/expected-1.0)<=0.03,
                   'flute_and_violin_WAV_differ':flute['wav_sha256']!=violin['wav_sha256'],
                   'raw_SFZ_direct_support_claimed':False,'proof_scope':'The registered real VST3 consumed the controlled SFZ gain change; ordinary nonquiet audio alone would not establish sample loading.'}
            report['controlled_SFZ_load_proof']=proof
            if not same_shape or not proof['gain_ratio_matches'] or not proof['flute_and_violin_WAV_differ']:raise RuntimeError('SFZ controlled-gain proof failed; default sine or another fallback is not accepted')
            report['registered_plugins_unchanged_after_render']=sha(registry)==report['registered_plugins_sha256']
            report['originals_and_reader_unchanged']=check_assets() and sha(copied)==pin and sha(fixture)==pin and report['registered_plugins_unchanged_after_render']
            if not report['originals_and_reader_unchanged']:raise RuntimeError('Original CC0 assets or reader changed')
            report['SFZ_sample_load_tested']=True;report['status']='passed_actual_sfizz_VST3_SFZ_controlled_render_and_save_only_checks'
    except Exception as error:report['status']='failed_or_blocked';report['error']=str(error)
    finally:
        (output/'sfz-host-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print('CADENCE_SFZ_HOST_REPORT_BEGIN');print(json.dumps(report,ensure_ascii=False));print('CADENCE_SFZ_HOST_REPORT_END')
    return 0 if report['status'].startswith('passed_') else 1
if __name__=='__main__':raise SystemExit(main())
