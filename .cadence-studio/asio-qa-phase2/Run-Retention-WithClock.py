#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Exercise one GUI project's audio rendering and native save using own hooks.

No UI input injection, original-score overwrite, audio-plugin installation or
application rebuild. The hooks are original diagnostic notation extensions in
this disposable runner's fresh Cadence-only profile.
"""
from __future__ import annotations
import argparse
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import uuid

EXE_HASH='35d8b076cacddb8b37a4f23aeea9899e6ab4ac9214e9a5b1125bbeccf26cf39e'
FIXTURE_HASH='10ae5eb1fae2679d9ad32aa0b721fef06119ef24b78b4f8b9bd6b770582c289f'
BASIC_HASH='5ea2375e8bd7d8e71def1036978c1621e85b66934169b6a2744b27b9b3c2d99c'
SOURCE='0e05d04acbeee32f1b561f24493d7ef41c322081'
TREE='f95b7097a55dddf9c7f697fc826b95721071231a'
PROFILE_SCOPE_SHA='60b6bb2353467cf338e2c671151af37d3fd36d76748e52cda6a1e3ab22c4c27c'
# QA-only workaround for retained 0e performPoint(): it constructs action://
# then looks up that exact URI without converting back to musescore://.
# Kept hidden: this diagnostic namespace is not a normal distributable extension.
URI='action://extensions/cadence/resource-retention-qa'
MISSING_SF='Cadence-QA-Missing-SF-Retention-d92450af'


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def load_module(name,path,expected):
    if digest(path)!=expected:raise ValueError('Reused helper differs from its exact preparation hash')
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module;spec.loader.exec_module(module);return module


def owned_windows(pid):
    """Read only visible top-level windows belonging to this exact Popen PID."""
    from ctypes import wintypes
    user=ctypes.WinDLL('user32',use_last_error=True)
    callback_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    user.EnumWindows.argtypes=[callback_type,wintypes.LPARAM]
    user.EnumWindows.restype=wintypes.BOOL
    user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowThreadProcessId.restype=wintypes.DWORD
    user.IsWindowVisible.argtypes=[wintypes.HWND];user.IsWindowVisible.restype=wintypes.BOOL
    user.GetWindowTextW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
    user.GetClassNameW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
    rows=[]
    @callback_type
    def visit(window,_):
        owner=wintypes.DWORD();user.GetWindowThreadProcessId(window,ctypes.byref(owner))
        if owner.value==pid and user.IsWindowVisible(window):
            title=ctypes.create_unicode_buffer(512);kind=ctypes.create_unicode_buffer(128)
            user.GetWindowTextW(window,title,len(title));user.GetClassNameW(window,kind,len(kind))
            rows.append({'handle':int(window),'pid':pid,'title':title.value,'class':kind.value})
        return True
    user.EnumWindows(visit,0);return rows



def marker_payload(line, kind, token):
    """Strictly decode our own raw or QDebug-quoted API message, then JSON."""
    prefix='CADENCE_RETENTION_'+kind+' '
    pos=line.find(prefix)
    if pos<0 or line.find(prefix,pos+len(prefix))>=0:raise ValueError('Missing or ambiguous marker prefix')
    # LogApi forwards QString through kors::logger::Stream::qt_to_ss(QDebug).
    # Decode the entire quoted message, not just its escaped JSON suffix.
    if pos>0 and line[pos-1]=='"':
        message=json.loads(line[pos-1:].strip())
        if not isinstance(message,str):raise ValueError('Expected a quoted Qt API string')
    else:
        message=line[pos:].strip()
    if not message.startswith(prefix):raise ValueError('Unexpected API message start')
    payload=json.loads(message[len(prefix):])
    if not isinstance(payload,dict) or payload.get('token')!=token:raise ValueError('Marker nonce mismatch')
    return payload


def script_finished(log_root, token):
    if not log_root.is_dir():return False
    logs=list(log_root.rglob('*.log'))
    if len(logs)>32:raise ValueError('Unexpected log count in our fresh Cadence profile')
    for path in logs:
        if path.is_symlink():raise ValueError('Log symlink refused')
        with path.open('rb') as stream:
            stream.seek(max(0,path.stat().st_size-65536));tail=stream.read(65536).decode('utf-8',errors='replace')
        for line in tail.splitlines():
            if 'CADENCE_RETENTION_SCRIPT_FINISHED ' not in line or token not in line:continue
            try:
                marker_payload(line,'SCRIPT_FINISHED',token)
                return True
            except (ValueError,TypeError):
                continue
    return False


def close_owned_main(pid):
    from ctypes import wintypes
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.GetWindow.argtypes=[wintypes.HWND,wintypes.UINT];user.GetWindow.restype=wintypes.HWND
    user.IsWindowEnabled.argtypes=[wintypes.HWND];user.IsWindowEnabled.restype=wintypes.BOOL
    user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM];user.PostMessageW.restype=wintypes.BOOL
    windows=[w for w in owned_windows(pid) if 'Cadence' in w['title'] and w['class'].startswith('Qt')
             and not user.GetWindow(w['handle'],4) and user.IsWindowEnabled(w['handle'])]
    if len(windows)!=1:return None
    window=windows[0];owner=wintypes.DWORD();user.GetWindowThreadProcessId(window['handle'],ctypes.byref(owner))
    if owner.value!=pid:raise ValueError('Window ownership changed before close')
    return {**window,'message':'WM_CLOSE','posted':bool(user.PostMessageW(window['handle'],0x0010,0,0))}


def extension_files(folder,token,case_name,wav):
    """Use only supported GUI extension/API calls, no scripting of arbitrary paths."""
    folder.mkdir(exist_ok=True)
    manifest={'uri':URI,'type':'macros','title':'Cadence owned retention QA','apiversion':1,'ui_context':'ProjectOpened',
              'actions':[{'code':'render-save','path':'render.js','func':'main','show_on_toolbar':False,'show_on_appmenu':False},
                         {'code':'saved','path':'saved.js','func':'main','show_on_toolbar':False,'show_on_appmenu':False}]}
    (folder/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    context=json.dumps({'token':token,'case':case_name,'expectedScoreName':case_name+'-after-audio'},ensure_ascii=True)
    render='''// SPDX-License-Identifier: GPL-3.0-only
function main() {
    const context = CONTEXT;
    const score = api.engraving.curScore;
    if (!score || score.title !== "Piano : voix, accords et triolets" || score.nstaves !== 2 || score.scoreName !== context.expectedScoreName) {
        api.log.info("CADENCE_RETENTION_BLOCKED " + JSON.stringify(context));
        api.log.info("CADENCE_RETENTION_SCRIPT_FINISHED " + JSON.stringify(context));
        return;
    }
    context.title = score.title;
    context.scoreName = score.scoreName;
    context.measures = score.nmeasures;
    api.log.info("CADENCE_RETENTION_GUI_PROJECT " + JSON.stringify(context));
    const rendered = api.engraving.writeScore(score, WAV, "wav");
    context.rendered = rendered;
    api.log.info("CADENCE_RETENTION_RENDER_RETURNED " + JSON.stringify(context));
    if (rendered) {
        api.log.info("CADENCE_RETENTION_NATIVE_SAVE_REQUEST " + JSON.stringify(context));
        api.engraving.cmd("file-save");
        api.log.info("CADENCE_RETENTION_NATIVE_SAVE_RETURNED " + JSON.stringify(context));
    }
    api.log.info("CADENCE_RETENTION_SCRIPT_FINISHED " + JSON.stringify(context));
}
'''.replace('CONTEXT',context).replace('WAV',json.dumps(wav.as_posix(),ensure_ascii=True))
    saved='''// SPDX-License-Identifier: GPL-3.0-only
function main() {
    const context = CONTEXT;
    const score = api.engraving.curScore;
    context.title = score ? score.title : "";
    context.scoreName = score ? score.scoreName : "";
    api.log.info("CADENCE_RETENTION_NATIVE_SAVE_WITNESSED " + JSON.stringify(context));
}
'''.replace('CONTEXT',context)
    (folder/'render.js').write_text(render,encoding='utf-8');(folder/'saved.js').write_text(saved,encoding='utf-8')
    return {p.name:digest(p) for p in folder.iterdir() if p.is_file()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',type=Path,required=True);parser.add_argument('--restoration-record',type=Path,required=True)
    parser.add_argument('--profile-record',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if os.name!='nt' or platform.machine().lower() not in ('amd64','x86_64') or os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('CI')!='true' or os.environ.get('RUNNER_ENVIRONMENT')!='github-hosted':
        raise SystemExit('Only disposable native Windows x64 GitHub-hosted runners are permitted')
    here=Path(__file__).resolve().parent
    # Pin the reused parser/mutator/WAV checker rather than maintaining a second implementation.
    helpers=load_module('cadence_retention_helpers',here/'missing_audio_helpers.py','da45c66b2e9f2df6c91746f3cd1e34893b2aff1126abf5cebb4b431993de0f4a')
    checker=load_module('cadence_retention_wav',here/'corpus_run_exports.py','f701874e7a37b8d3148f0bb99477b60b96865e804ed238372d75c06598027d82')
    profile_scope=load_module('cadence_asio_profile_scope',here/'CadenceProfileScope.py',PROFILE_SCOPE_SHA)
    temporary=Path(os.environ['RUNNER_TEMP']).resolve()
    stage=helpers.require_below(args.stage,temporary);output=helpers.require_below(args.output,temporary)
    record_path=helpers.require_below(args.restoration_record,temporary)
    profile_record_path=helpers.require_below(args.profile_record,temporary)
    if output.exists() or stage in output.parents or output in stage.parents:raise ValueError('New independent output required')
    record=json.loads(record_path.read_text(encoding='utf-8-sig'));exe=stage/'bin/CadenceStudio4.exe';fixture=here/'fixtures/piano.mscx'
    banks=list(stage.rglob('MS Basic.sf3'))
    if len(banks)!=1 or digest(banks[0])!=BASIC_HASH or digest(exe)!=EXE_HASH or digest(fixture)!=FIXTURE_HASH or record.get('original_source_commit')!=SOURCE or record.get('source_tree')!=TREE or record.get('build_number')!=2002 or Path(record['executable_path']).resolve()!=exe:
        raise ValueError('Retained executable, source, fixture or MS Basic differs from the exact pins')
    # Qt uses Win32 KnownFolders. An APPDATA environment override alone does not
    # isolate its QSettings or QStandardPaths on Windows. Only the reviewed scope
    # may create these exact, previously absent Cadence-specific profile roots.
    profile=profile_scope.verify_record(profile_record_path)
    local=Path(profile['local_org_root']);roaming=Path(profile['roaming_org_root'])
    ini=Path(profile['settings_file']);output.mkdir();seed_hash=profile['seed_settings_sha256']
    report={'schema_version':1,'status':'running','source_commit':SOURCE,'source_tree':TREE,'build_number':2002,'executable_sha256':EXE_HASH,
            'scope':'Same GUI project renders actual audio, then native project file-save; own copied result was created before GUI opening',
            'profiles_were_absent':True,'first_launch_setup_seeded':True,'onboarding_tested':False,'seed_settings_sha256':seed_hash,
            'profile_scope_record_sha256':digest(profile_record_path),'profile_scope_owner':profile['owner'],
            'profile_location_method':'Actual SHGetKnownFolderPath; exact Cadence-only roots initially absent and marked',
            'profile_only_RUNNER_TEMP_boundary_exception':True,
            'required_audio_api':'ASIO','required_audio_device':'Cadence QA Clock (silent sink)',
            'physical_audio_output':False,'registered_QA_clock_used':True,
            'diagnostic_notation_extension_installed':True,'diagnostic_extension_uri':URI,'auto_hook_uri_workaround':True,'strict_QDebug_marker_decoding':True,'bounded_application_log_tails_in_report':True,'external_audio_plugins_installed':False,'human_listening_performed':False,
            'live_interactive_playback_tested':False,'gui_warning_tested':False,'keyboard_or_mouse_injection_used':False,
            'gui_close_policy':'WM_CLOSE only to the one enabled visible unowned top-level Qt Cadence window rechecked for the owned child PID; no global quit action',
            'commands':[],'cases':[],'error':None,'preservation_failures':[]}
    env=os.environ.copy();env['PATH']=str(exe.parent)+';'+str(Path(os.environ['SystemRoot'])/'System32')
    logs=Path(profile['log_root'])

    def run(name,arguments,gui=False,token=None):
        before=helpers.log_snapshot(logs);started=time.monotonic();row={'name':name,'gui':gui,'arguments':[str(exe),*map(str,arguments)],'pid':None,'exit_code':None,'timed_out':False,'forced':False,'owned_windows':[],'close_events':[]}
        report['commands'].append(row)
        stats=output/'clock-stats'/name;stats.mkdir(parents=True,exist_ok=False)
        process_env=env.copy();process_env['CADENCE_QA_CLOCK_STATS_DIR']=str(stats)
        with (output/(name+'.stdout.txt')).open('xb') as out,(output/(name+'.stderr.txt')).open('xb') as err:
            proc=subprocess.Popen(row['arguments'],stdout=out,stderr=err,cwd=output,env=process_env,creationflags=subprocess.CREATE_NO_WINDOW)
            row['pid']=proc.pid;seen=set()
            try:
                while proc.poll() is None:
                    if gui:
                        for window in owned_windows(proc.pid):
                            key=(window['handle'],window['title'])
                            if key not in seen and len(row['owned_windows'])<32:seen.add(key);row['owned_windows'].append(window)
                    if gui and token and not any(e['posted'] for e in row['close_events']) and script_finished(logs,token):
                        event=close_owned_main(proc.pid)
                        if event:row['close_events'].append(event)
                    if time.monotonic()-started>120:
                        row['timed_out']=True;row['forced']=True;proc.kill();break
                    time.sleep(0.1)
                row['exit_code']=proc.wait(timeout=10)
            finally:
                if proc.poll() is None:row['forced']=True;proc.kill();proc.wait(timeout=10)
        row['seconds']=time.monotonic()-started
        after=helpers.log_snapshot(logs)
        delta=helpers.log_delta(before,after);(output/(name+'.cadence-log-delta.txt')).write_text(delta,encoding='utf-8')
        row['clock_reports']=[]
        paths=list(stats.glob('clock-*.json'))
        if len(paths)>16:raise RuntimeError('Unexpected number of own-process clock reports')
        for path in sorted(paths):
            if path.is_symlink() or path.stat().st_size>4096:raise RuntimeError('Invalid bounded clock report')
            clock=json.loads(path.read_text(encoding='utf-8'))
            if type(clock.get('schema_version')) is not int or clock['schema_version']!=1 or clock.get('endpoint')!='Cadence QA Clock (silent sink)' or clock.get('physical_audio_output') is not False or clock.get('qualified_hardware') is not False:
                raise RuntimeError('Own-process clock report identifies another endpoint')
            for field in ('callbacks','frames','finite_samples','nonzero_samples','nonfinite_samples','clipped_samples','callback_errors','active_channels'):
                if type(clock.get(field)) is not int or clock[field]<0:raise RuntimeError('Invalid own-process clock counter '+field)
            if clock['frames']!=clock['callbacks']*256 or clock['finite_samples']!=clock['frames']*2 or clock['active_channels']!=2 or clock['nonfinite_samples'] or clock['callback_errors']:
                raise RuntimeError('Own-process clock counters are inconsistent')
            row['clock_reports'].append({'path':path.relative_to(output).as_posix(),'sha256':digest(path),'report':clock})
        row['actual_clock_callbacks']=sum(r['report']['callbacks'] for r in row['clock_reports'])
        row['clock_output_nonzero_samples']=sum(r['report']['nonzero_samples'] for r in row['clock_reports'])
        row['clock_driver_named_in_log']='driverName: Cadence QA Clock (silent sink)' in delta
        row['clock_thread_started_in_log']='ASIO thread started:' in delta
        if gui and (row['actual_clock_callbacks']<1 or not row['clock_driver_named_in_log'] or not row['clock_thread_started_in_log']):
            raise RuntimeError('Real GUI did not prove named ASIO driver startup and actual clock callbacks')
        if not gui and (row['timed_out'] or row['forced'] or row['exit_code']!=0):raise RuntimeError('Owned process failed; inspect '+name)
        return row,delta

    try:
        source_copy=output/'original-piano-copy.mscx';shutil.copyfile(fixture,source_copy)
        base=output/'native-base.mscz';run('prepare-native-base',['-o',base,source_copy])
        extension_root=Path(profile['extension_root']);extension_root.mkdir(parents=True,exist_ok=True)
        extension=extension_root/'cadence-retention-qa'
        config=[{'uri':URI,'actions':[{'code':'render-save','exec_point':'onpost_project_opened'},{'code':'saved','exec_point':'onpost_project_saved'}]}]
        (extension_root/'config.json').write_text(json.dumps(config,indent=2)+'\n',encoding='utf-8')
        shutil.copyfile(extension_root/'config.json',output/'diagnostic-extension-config.json')
        for name,identity in [('basic-control','MS Basic'),('missing-soundfont',MISSING_SF)]:
            meta={'id':identity,'vendor':'Fluid','type':'fluid_soundfont','hasNativeEditorSupport':False,'attributes':{'soundFontName':identity,'playbackSetupData':'generic'}}
            source=output/(name+'-source.mscz');expected=helpers.make_case(base,source,meta);source_hash=digest(source)
            working=output/(name+'-after-audio.mscz');shutil.copyfile(source,working);before_hash=digest(working);before_stat=working.stat()
            token=str(uuid.uuid4());wav=output/(name+'.wav');extension_hashes=extension_files(extension,token,name,wav)
            case={'name':name,'token':token,'source_sha256':source_hash,'working_copy_sha256_before':before_hash,'working_copy_created_before_GUI':True,'requested_input':expected['tracks'][0]['in'],'gui_audio_render_then_native_save_confirmed':False}
            report['cases'].append(case)
            snapshot=output/(name+'-diagnostic-extension');shutil.copytree(extension,snapshot)
            case['diagnostic_extension_hashes']=extension_hashes
            command,delta=run(name+'-gui',[working],gui=True,token=token)
            # Preserve diagnostic details even if parsing/sequence validation
            # blocks, so the real application log is reviewable from Actions.
            case['gui_log_tail']=delta[-32768:]
            for stream in ('stdout','stderr'):
                case[stream+'_tail']=(output/(name+'-gui.'+stream+'.txt')).read_bytes()[-8192:].decode('utf-8',errors='replace')
            markers={};case['markers']=markers;case['marker_counts']={}
            for kind in ('GUI_PROJECT','RENDER_RETURNED','NATIVE_SAVE_REQUEST','NATIVE_SAVE_WITNESSED','NATIVE_SAVE_RETURNED','SCRIPT_FINISHED'):
                prefix='CADENCE_RETENTION_'+kind+' '
                matches=[line for line in delta.splitlines() if prefix in line and token in line]
                case['marker_counts'][kind]=len(matches)
                if len(matches)!=1:raise RuntimeError('Expected one original GUI marker '+kind+' for '+name)
                payload=marker_payload(matches[0],kind,token);markers[kind]={'offset':delta.index(matches[0]),'payload':payload}
            for kind, marker in markers.items():
                if marker['payload'].get('title') != markers['GUI_PROJECT']['payload']['title'] or marker['payload'].get('scoreName') != markers['GUI_PROJECT']['payload']['scoreName']:
                    raise RuntimeError('GUI score identity changed during the same-project sequence')
            offsets=[markers[kind]['offset'] for kind in ('GUI_PROJECT','RENDER_RETURNED','NATIVE_SAVE_REQUEST','NATIVE_SAVE_WITNESSED','NATIVE_SAVE_RETURNED','SCRIPT_FINISHED')]
            if offsets!=sorted(offsets) or not markers['RENDER_RETURNED']['payload'].get('rendered'):raise RuntimeError('Render and real native save were not witnessed in order')
            if not any('Cadence' in w['title'] and w['class'].startswith('Qt') for w in command['owned_windows']):raise RuntimeError('No owned real Qt GUI window observed')
            case['gui_clean_exit']=command['exit_code']==0 and not command['timed_out'] and not command['forced']
            if not case['gui_clean_exit']:raise RuntimeError('Owned GUI did not close cleanly after the witnessed render/save sequence')
            case['audio']=checker.inspect_wav(wav)
            if not case['audio']['passed']:raise RuntimeError('Same-project WAV is silent, nonfinite or saturated')
            case['wav_sha256']=digest(wav);case['markers']=markers
            diagnostic='Not found: '+identity
            case['missing_sf_diagnostic_seen']=diagnostic in delta
            case['missing_sf_diagnostic_before_render_return']=diagnostic in delta and delta.index(diagnostic)<markers['RENDER_RETURNED']['offset']
            case['source_unchanged']=digest(source)==source_hash
            case['working_copy_sha256_after']=digest(working);case['working_copy_changed_by_native_save']=case['working_copy_sha256_after']!=before_hash
            case['working_copy_mtime_changed']=working.stat().st_mtime_ns!=before_stat.st_mtime_ns
            if not case['source_unchanged'] or not case['working_copy_changed_by_native_save']:raise RuntimeError('Immutable source changed or native output bytes were never saved')
            actual=helpers.read_audio(working);case['saved_audio_settings']=actual
            inputs=[track.get('in',{}) for track in actual.get('tracks',[]) if track.get('partId')=='1' and track.get('instrumentId')=='piano']
            if len(inputs)!=1:raise RuntimeError('Saved real project has no unique original piano audio track')
            applied=inputs[0];case['resource_identity_preserved']=applied.get('resourceMeta',{}).get('id')==identity and applied.get('resourceMeta',{}).get('type')=='fluid_soundfont'
            case['opaque_probe_state_preserved']=applied.get('unitConfiguration')==expected['tracks'][0]['in']['unitConfiguration']
            case['actual_saved_input']=applied;case['gui_audio_render_then_native_save_confirmed']=True
            case['same_GUI_project_clock_callbacks_WAV_nonmute_and_native_save_witnessed']=command['actual_clock_callbacks']>0 and case['audio']['passed']
            case['diagnostic_extension_unchanged']=all(digest(extension/leaf)==checksum for leaf,checksum in extension_hashes.items())
            if not case['resource_identity_preserved'] or not case['opaque_probe_state_preserved']:report['preservation_failures'].append(name)
            if not case['diagnostic_extension_unchanged']:raise RuntimeError('Own diagnostic extension bytes changed during execution')
            if name=='missing-soundfont' and not case['missing_sf_diagnostic_before_render_return']:raise RuntimeError('Same-project render/save inspected, but missing SF resolver was not witnessed before render return; no fallback-before-save claim')
            if not case['gui_clean_exit']:raise RuntimeError('Retention inspected, but GUI failed to close cleanly; no overall PASS')
        report['missing_wav_identical_to_control']=report['cases'][0].get('wav_sha256')==report['cases'][1].get('wav_sha256')
        report['fixture_unchanged']=digest(fixture)==FIXTURE_HASH and digest(source_copy)==FIXTURE_HASH
        verified_profile=profile_scope.verify_record(profile_record_path)
        report['ASIO_profile_settings_preserved']=verified_profile['owner']==profile['owner']
        shutil.copyfile(ini,output/'own-profile-settings-after.ini')
        report['executable_unchanged']=digest(exe)==EXE_HASH;report['MS_Basic_unchanged']=digest(banks[0])==BASIC_HASH
        if not all(report[k] for k in ('fixture_unchanged','executable_unchanged','MS_Basic_unchanged')):raise RuntimeError('A source fixture, program or supplied bank changed')
        report['status']='failed_resource_preservation' if report['preservation_failures'] else 'passed_same_GUI_project_resource_preservation'
    except Exception as error:
        report['status']='failed_or_blocked';report['error']=str(error)
    finally:
        # Record immutable inputs even when a hook or GUI operation was blocked.
        report['immutable_checks'] = {}
        for label,path,expected_hash in [('fixture',fixture,FIXTURE_HASH),('executable',exe,EXE_HASH),('MS_Basic',banks[0],BASIC_HASH)]:
            try:
                actual_hash=digest(path)
                report['immutable_checks'][label]={'passed':actual_hash==expected_hash,'sha256':actual_hash}
            except OSError as error:
                report['immutable_checks'][label]={'passed':False,'error':str(error)}
        for case in report['cases']:
            path=output/(case['name']+'-source.mscz')
            case['source_unchanged']=path.is_file() and digest(path)==case['source_sha256']
        if report['status']=='passed_same_GUI_project_resource_preservation' and (
            not all(item['passed'] for item in report['immutable_checks'].values()) or not all(case['source_unchanged'] for case in report['cases'])):
            report['status']='failed_input_immutability'
        (output/'retention-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print('CADENCE_RESOURCE_RETENTION_REPORT_BEGIN');print(json.dumps(report,ensure_ascii=False,indent=2));print('CADENCE_RESOURCE_RETENTION_REPORT_END')
    return 0 if report['status']=='passed_same_GUI_project_resource_preservation' else 1

if __name__=='__main__':raise SystemExit(main())
