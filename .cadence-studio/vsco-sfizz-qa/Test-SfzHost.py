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


class PositiveFixtureControlError(RuntimeError):
    pass


class OwnedDebuggerCollectionError(RuntimeError):
    pass


def valid_fast_fail_code(value):
    return value is None or (type(value) is int and 0<=value<=65535)


def native_failure_observed(commands):
    return any((item.get('native_exit_observed') not in (None,0)) if item.get('execution_wrapper')=='owned_debugger'
               else (item.get('exit_code') not in (None,0) or item.get('timed_out',False)) for item in commands)


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


def has_exact_export_shutdown_signature(item,diagnostics,expected_path):
    """Continue diagnostics only; a recognized crash remains a failed native exit."""
    if item['timed_out'] or item['exit_code']!=1:return False
    text=diagnostics.replace('\\','/').lower()
    saved=any('successfully saved sound track by path:' in line and str(expected_path).replace('\\','/').lower() in line for line in text.splitlines())
    goodbye=text.rfind('goodbye!! code: 0');crash=text.rfind('application crashed with signal: [11]')
    return saved and goodbye>=0 and crash>goodbye and 'sigsegv-invalid memory reference' in text[crash:]


def native_audio(path):
    with zipfile.ZipFile(path) as archive:return json.loads(archive.read('audiosettings.json'))


def assign_plugin(base,target,registered,patch,state,*,factory_control=False):
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
        if factory_control:
            for track in tracks:track['in']['unitConfiguration']={}
        if len(tracks)!=1:raise ValueError('This small reader qualification requires exactly one real track')
        settings=native_audio(base);settings['activeSoundProfile']='MuseScore Basic';settings['tracks']=tracks
        # Dry and linear master/aux paths keep the controlled-gain proof meaningful.
        settings['master']={'balance':0,'volumeDb':0,'fxChain':{},'auxSends':[]};settings['aux']=[]
        with zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED) as output:
            for info in archive.infolist():output.writestr(info,json.dumps(settings,ensure_ascii=False).encode('utf-8') if info.filename=='audiosettings.json' else archive.read(info))
    return tracks



def assign_basic(base,target):
    """Explicit MS Basic on the same actual native IDs and dry linear mix path."""
    with zipfile.ZipFile(base) as archive:
        masters=[name for name in archive.namelist() if name.endswith('.mscx') and '/' not in name]
        if len(masters)!=1:raise ValueError('Unique actual master required for the positive control')
        score=ET.fromstring(archive.read(masters[0]));tracks=[]
        for part in score.findall('./Score/Part'):
            for instrument in part.findall('Instrument'):
                if not part.get('id') or not instrument.get('id'):raise ValueError('Actual control part/instrument IDs required')
                tracks.append({'partId':part.get('id'),'instrumentId':instrument.get('id'),
                    'in':{'resourceMeta':{'id':'MS Basic','vendor':'Fluid','type':'fluid_soundfont','hasNativeEditorSupport':False,
                        'attributes':{'soundFontName':'MS Basic','playbackSetupData':'generic'}},'unitConfiguration':{}},
                    'out':{'balance':0,'volumeDb':0,'fxChain':{},'auxSends':[]},'soloMuteState':{'mute':False,'solo':False}})
        if len(tracks)!=1:raise ValueError('Exactly one actual track required for the control')
        settings=native_audio(base);settings['activeSoundProfile']='MuseScore Basic';settings['tracks']=tracks
        settings['master']={'balance':0,'volumeDb':0,'fxChain':{},'auxSends':[]};settings['aux']=[]
        with zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED) as output:
            for info in archive.infolist():output.writestr(info,json.dumps(settings,ensure_ascii=False).encode('utf-8') if info.filename=='audiosettings.json' else archive.read(info))
    return tracks


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--phase',choices=('scan','render'),required=True)
    p.add_argument('--stage',type=Path,required=True);p.add_argument('--assets',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--debug-export-tool',type=Path)
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
    debug_tool=None
    if args.debug_export_tool is not None:
        if args.phase!='render':raise ValueError('Owned debugging is scoped only to controlled exports')
        debug_tool=owned(args.debug_export_tool)
        build=json.loads((debug_tool.parent/'debugger-build-report.json').read_text(encoding='utf-8-sig'))
        source_pin=json.loads((Path(__file__).parent/'debugger/source-pin.json').read_text())
        if build.get('status')!='compiled_native_debugger_only' or build.get('source')!=source_pin or sha(debug_tool)!=build.get('executable_sha256'):
            raise ValueError('Only the exact reviewed debugger compiled by this job is allowed')
        report['owned_debugger_source']=source_pin;report['owned_debugger_executable_sha256']=sha(debug_tool)
    report['owned_debugger_used_for_exports']=debug_tool is not None
    report['debugger_changes_process_timing']=debug_tool is not None
    if debug_tool is not None:report['un_debugged_stability_validated_by_this_run']=False
    env={key:value for key,value in os.environ.items() if not key.startswith(('QT_','QML_'))}
    env['PATH']=str(executable.parent)+';'+str(Path(os.environ['SystemRoot'])/'System32')
    report['child_PATH']=env['PATH'];report['inherited_Qt_QML_environment_removed']=True
    def run(name,arguments,expected_export=None):
        before=snapshot(logs);start=time.monotonic();item={'name':name,'exit_code':None,'timed_out':False,'pid':None};report['commands'].append(item)
        with (output/(name+'.stdout.txt')).open('xb') as out,(output/(name+'.stderr.txt')).open('xb') as err:
            command=[str(executable),*map(str,arguments)];events_path=None
            if debug_tool is not None and expected_export is not None:
                events_path=output/(name+'.debug-events.jsonl')
                item['execution_wrapper']='owned_debugger'
            else:item['execution_wrapper']='direct_native'
            if events_path is not None:
                command=[str(debug_tool),str(executable),str(output),str(events_path),str(expected_export),str(arguments[-1])]
            process=subprocess.Popen(command,cwd=output,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
            item['pid']=process.pid;item['launcher_pid']=process.pid
            if events_path is None:item['native_pid']=process.pid
            try:item['exit_code']=process.wait(timeout=90)
            except subprocess.TimeoutExpired:item['timed_out']=True;process.kill();item['exit_code']=process.wait(timeout=10)
        item['seconds']=time.monotonic()-start;delta=log_delta(before,snapshot(logs));(output/(name+'.cadence-log.txt')).write_text(delta,encoding='utf-8')
        stdout_path=output/(name+'.stdout.txt');stderr_path=output/(name+'.stderr.txt')
        item['stdout_bytes']=stdout_path.stat().st_size;item['stderr_bytes']=stderr_path.stat().st_size
        if item['stdout_bytes']>16777216 or item['stderr_bytes']>16777216:raise RuntimeError('Owned process diagnostics exceeded their bound')
        diagnostics=delta+'\n'+stdout_path.read_text(encoding='utf-8',errors='replace')+'\n'+stderr_path.read_text(encoding='utf-8',errors='replace')
        if events_path is not None:
            if not events_path.is_file() or events_path.stat().st_size>1048576:raise OwnedDebuggerCollectionError('Owned debugger event file missing or oversized')
            try:events=[json.loads(line) for line in events_path.read_text(encoding='utf-8').splitlines()]
            except (OSError,UnicodeError,json.JSONDecodeError) as error:raise OwnedDebuggerCollectionError('Owned debugger metadata could not be decoded') from error
            allowed={
                'owned_process_started':{'event','pid','debug_only_this_process','environment_allowlist','memory_dump_created','data_memory_captured'},
                'module_loaded':{'event','module','base','image_bytes'},'module_unloaded':{'event','base'},
                'initial_loader_breakpoint':{'event','thread_id','first_chance','module_identified','module','module_state','module_offset'},
                'exception':{'event','thread_id','code','first_chance','instruction_pointer','context_RIP','fast_fail_code','module','module_state','module_offset'},
                'owned_process_exit':{'event','pid','exit_code'},
                'owned_process_timeout':{'event','termination_request_succeeded','exit_observed_within_5s'},'debugger_tool_failed':{'event'}}
            if len(events)>1024 or any(value.get('event') not in allowed or set(value)!=allowed[value['event']] for value in events):raise OwnedDebuggerCollectionError('Unexpected owned-debugger data schema')
            if any(value['event']=='exception' and not valid_fast_fail_code(value['fast_fail_code']) for value in events):raise OwnedDebuggerCollectionError('Unexpected fast-fail metadata type or range')
            starts=[value for value in events if value['event']=='owned_process_started'];exits=[value for value in events if value['event']=='owned_process_exit']
            item['native_pid']=starts[0]['pid'] if len(starts)==1 else None
            item['native_exit_observed']=exits[0]['exit_code'] if len(exits)==1 else None
            item['owned_debugger_events']={'file':events_path.name,'sha256':sha(events_path),'count':len(events),
                'native_process_start':starts,'native_process_exit':exits,'exceptions':[value for value in events if value['event']=='exception'],
                'module_load_count':sum(value['event']=='module_loaded' for value in events),'module_unload_count':sum(value['event']=='module_unloaded' for value in events)}
            if len(starts)!=1 or len(exits)!=1 or starts[0]['pid']!=exits[0]['pid'] or exits[0]['exit_code']!=item['exit_code'] or not starts[0]['debug_only_this_process'] or not starts[0]['environment_allowlist'] or starts[0]['memory_dump_created'] or starts[0]['data_memory_captured']:
                raise OwnedDebuggerCollectionError('Owned debugger did not confirm the real native process exit and restricted collection')
        if item['timed_out'] or item['exit_code']!=0:
            item['terminal_shutdown_crash_after_export']=expected_export is not None and expected_export.is_file() and has_exact_export_shutdown_signature(item,diagnostics,expected_export)
            if not item['terminal_shutdown_crash_after_export']:raise RuntimeError('Owned native command failed: '+name)
            # Collect the other controlled cases, but never turn this exit into success.
            report.setdefault('native_exit_failures',[]).append({'name':name,'exit_code':item['exit_code'],'terminal_shutdown_crash_after_export':True})
        return diagnostics
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
            report['positive_controls']=[]
            control=output/'positive-msbasic.mscz';assign_basic(base,control);before_control=sha(control);control_wav=output/'positive-msbasic.wav'
            control_log=run('positive-msbasic-render',['-o',control_wav,control],expected_export=control_wav);control_audio=wavtool.inspect_wav(control_wav)
            observed=any('success load soundfont:' in line and 'ms basic.sf3' in line for line in control_log.replace('\\','/').lower().splitlines())
            basic_control={'id':'same-exercise-msbasic','role':'Positive note/event/mix-path control, not an alternative-bank validation',
                'audio':control_audio,'wav_sha256':sha(control_wav),'actual_basic_synth_load_observed':observed,'source_unchanged':sha(control)==before_control}
            basic_control['passed']=control_audio['passed'] and observed and basic_control['source_unchanged'];report['positive_controls'].append(basic_control)
            if not basic_control['passed']:raise PositiveFixtureControlError('The same exercise/mix path failed its actual MS Basic positive control')
            factory=output/'positive-sfizz-factory.mscz'
            assign_plugin(base,factory,report['registered_plugin'],Path(sample['patches']['FluteSusVib.sfz']),state,factory_control=True)
            if native_audio(factory)['tracks'][0]['in']['unitConfiguration']!={}:raise RuntimeError('Factory control unexpectedly contains component state')
            before_factory=sha(factory);factory_wav=output/'positive-sfizz-factory.wav'
            factory_log=run('positive-sfizz-factory-render',['-o',factory_wav,factory],expected_export=factory_wav);factory_audio=wavtool.inspect_wav(factory_wav)
            factory_control={'id':'same-exercise-sfizz-factory','role':'Internal sine test tone only; no sampled orchestral instrument or SFZ claimed',
                'source_reference':'SfizzVstProcessor.cpp:24 defaultSfzText sample=*sine',
                'componentState_omitted':True,'audio':factory_audio,'wav_sha256':sha(factory_wav),'source_unchanged':sha(factory)==before_factory,
                'sfizz_engine_init_observed':'[sfizz] new synth' in factory_log.lower()}
            factory_control['passed']=factory_audio['passed'] and factory_control['source_unchanged'] and factory_control['sfizz_engine_init_observed'];report['positive_controls'].append(factory_control)
            report['positive_controls_passed']=all(value['passed'] for value in report['positive_controls'])
            diagnostic_errors=('Unable to find vst plugin module','Unable to load vst plugin provider','Unable to initialize vst plugin provider','Component state restore failed','Controller state restore failed','[Sfizz] file not found:')
            for label,patch_name in (('flute','FluteSusVib.sfz'),('violin','SViolinVib.sfz'),('flute-minus18','Cadence-QA-Flute-minus18.sfz')):
                patch=owned(Path(sample['patches'][patch_name]));native=output/(label+'.mscz')
                if root not in patch.parents:raise ValueError('Patch outside owned CC0 subset')
                tracks=assign_plugin(base,native,report['registered_plugin'],patch,state);before=sha(native);wav=output/(label+'.wav')
                delta=run(label+'-render',['-o',wav,native],expected_export=wav);audio=wavtool.inspect_wav(wav)
                bad=[text for text in diagnostic_errors if text.lower() in delta.lower()]
                value={'variant':label,'SFZ':patch_name,'requested_master_gain_db':-12.0,'requested_tracks':len(tracks),
                       'audio':audio,'wav_sha256':sha(wav),'native_source_sha256':before,'native_source_unchanged':sha(native)==before,
                       'vst_load_or_state_error_markers':bad,'SFZ_sample_load_not_inferred_from_nonquiet_audio_alone':True}
                report['cases'].append(value)
                value['audio_and_load_checks_passed']=not bad and audio['passed'] and audio['channels']==2 and value['native_source_unchanged']
                if not value['native_source_unchanged']:raise RuntimeError('Controlled native source changed')
                saved=output/(label+'-save-only.mscz');run(label+'-save-only',['-o',saved,native]);saved_tracks=native_audio(saved).get('tracks',[])
                wanted={(item['partId'],item['instrumentId']):item['in'] for item in tracks}
                actual={(item.get('partId'),item.get('instrumentId')):item.get('in',{}) for item in saved_tracks}
                value['save_only_track_resource_and_raw_state_preserved']=all(actual.get(key)==item for key,item in wanted.items()) and len(actual)==len(wanted)
                if not value['save_only_track_resource_and_raw_state_preserved'] or sha(native)!=before:raise RuntimeError('Save-only VST identity/state or source preservation failed')
                encoded=tracks[0]['in']['unitConfiguration']['componentState'];decoded=state.read_component_state(base64.b64decode(encoded,validate=True))
                value['requested_component_state']={'bytes':len(base64.b64decode(encoded)),'sha256':hashlib.sha256(base64.b64decode(encoded)).hexdigest(),'decoded':decoded}
            flute,violin,quiet=report['cases'];ratio=quiet['audio']['rms']/flute['audio']['rms'] if flute['audio']['rms']>0 else None;expected=10**(-18.0/20.0)
            same_shape=all(flute['audio'][key]==quiet['audio'][key] for key in ('encoding','bits','channels','sample_rate','duration_seconds'))
            proof={'region_gain_delta_db':-18.0,'expected_rms_ratio':expected,'actual_rms_ratio':ratio,'relative_tolerance':0.03,
                   'matching_WAV_shape':same_shape,'gain_ratio_matches':ratio is not None and abs(ratio/expected-1.0)<=0.03,
                   'flute_and_violin_WAV_differ':flute['wav_sha256']!=violin['wav_sha256'],
                   'raw_SFZ_direct_support_claimed':False,'proof_scope':'This tests whether the registered real VST3 consumed the controlled SFZ gain change; ordinary nonquiet audio alone does not establish sample loading. Assess gain_ratio_matches and all case audio checks.'}
            report['controlled_SFZ_load_proof']=proof
            report['controlled_audio_checks_passed']=report['positive_controls_passed'] and same_shape and proof['gain_ratio_matches'] and proof['flute_and_violin_WAV_differ'] and all(value['audio_and_load_checks_passed'] for value in report['cases'])
            report['registered_plugins_unchanged_after_render']=sha(registry)==report['registered_plugins_sha256']
            report['originals_and_reader_unchanged']=check_assets() and sha(copied)==pin and sha(fixture)==pin and report['registered_plugins_unchanged_after_render']
            if not report['originals_and_reader_unchanged']:raise RuntimeError('Original CC0 assets or reader changed')
            report['SFZ_sample_load_tested']=True;report['SFZ_controlled_load_validated']=report['controlled_audio_checks_passed']
            if report.get('native_exit_failures'):
                report['status']='failed_native_exit';report['error']='Actual native process exit failed after export; audio diagnostics do not validate stability.'
            elif not report['controlled_audio_checks_passed']:
                report['status']='failed_audio_checks';report['error']='Controlled SFZ gain or WAV checks failed; fallback audio is not accepted.'
            else:report['status']='passed_actual_sfizz_VST3_SFZ_controlled_render_and_save_only_checks'
    except Exception as error:
        report['status']='failed_fixture_control' if isinstance(error,PositiveFixtureControlError) else 'failed_debugger_collection' if isinstance(error,OwnedDebuggerCollectionError) else 'failed_native_exit' if native_failure_observed(report['commands']) else 'failed_or_blocked'
        report['error']=str(error)
    finally:
        (output/'sfz-host-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print('CADENCE_SFZ_HOST_REPORT_BEGIN');print(json.dumps(report,ensure_ascii=False));print('CADENCE_SFZ_HOST_REPORT_END')
    return 0 if report['status'].startswith('passed_') else 1
if __name__=='__main__':raise SystemExit(main())
