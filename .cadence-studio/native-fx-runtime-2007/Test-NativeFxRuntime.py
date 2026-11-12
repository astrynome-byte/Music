#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Private CLI/render qualification of native FX in the original app2007.

Only the enclosing Windows owned Job may invoke main. Preparation tests may
import pure functions. No installer, app rebuild, plugin or publication.
"""
from __future__ import annotations
import argparse
import base64
import copy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import zipfile

_spec = importlib.util.spec_from_file_location('retained2007_nativefx', Path(__file__).with_name('Retained2007.py'))
r = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(r)

EQ = 'Cadence EQ'
COMP = 'Cadence Compressor'
EQ_PARAMS = {'cadence.fx.schema':'1','lowGainDb':'0','midGainDb':'0','midFrequencyHz':'1000',
             'midQ':'1','highGainDb':'0','outputGainDb':'-6'}
COMP_PARAMS = {'cadence.fx.schema':'1','thresholdDb':'0','ratio':'1','kneeDb':'0',
               'attackMs':'10','releaseMs':'100','makeupDb':'6'}
REDUCTION_PARAMS = {**COMP_PARAMS, 'thresholdDb':'-60', 'ratio':'4', 'attackMs':'0.1', 'releaseMs':'10', 'makeupDb':'0'}
DRY = [{'signalAmount':0.0,'active':False},{'signalAmount':0.0,'active':False}]
MASTER_DB = -24
PASS = 'passed-original2007-native-fx-render-save-reopen-controls'


def fx(effect, active, reduction=False):
    r.require(effect in (EQ, COMP) and isinstance(active,bool), 'Unknown FX or active flag')
    params = EQ_PARAMS if effect == EQ else REDUCTION_PARAMS if reduction else COMP_PARAMS
    return {'active':active, 'chainOrder':0,
            'resourceMeta':{'id':effect,'type':'muse_plugin','vendor':'Cadence','hasNativeEditorSupport':True,
                            'attributes':{'categories':'EQ' if effect == EQ else 'Dynamics'}},
            'unitConfiguration':{key:base64.b64encode(value.encode('ascii')).decode('ascii') for key,value in params.items()}}


def cases():
    result = [{'name':'baseline','location':None,'effect':None,'active':False,'reduction':False,'expected_gain_db':0}]
    for location in ('track','master'):
        for effect,label,gain in ((EQ,'eq',-6),(COMP,'compressor',6)):
            for active in (False,True):
                result.append({'name':location+'-'+label+('-active' if active else '-bypass'), 'location':location,
                               'effect':effect,'active':active,'reduction':False,'expected_gain_db':gain if active else 0})
        result.append({'name':location+'-compressor-reduction','location':location,'effect':COMP,
                       'active':True,'reduction':True,'expected_gain_db':None})
    return result


def assign(base, target, case):
    settings, score = r.native_data(base)
    parts = score.findall('./Score/Part')
    r.require(len(parts)==1 and len(parts[0].findall('Instrument'))==1, 'One imported instrument required')
    part=parts[0];instrument=part.find('Instrument')
    r.require(part.get('id') and instrument.get('id') and 'violoncello' in instrument.get('id').lower(),
              'Original cello fixture must import as a real native cello')
    programs=[int(p.get('value')) for p in instrument.findall('./Channel/program')]
    r.require(42 in programs, 'Original MusicXML43 must become native GM42')
    resource={'id':'MS Basic','vendor':'Fluid','type':'fluid_soundfont','hasNativeEditorSupport':False,
              'attributes':{'soundFontName':'MS Basic','playbackSetupData':'generic'}}
    track={'partId':part.get('id'),'instrumentId':instrument.get('id'),
           'in':{'resourceMeta':resource,'unitConfiguration':{}},
           'out':{'balance':0,'volumeDb':0,'fxChain':{},'auxSends':copy.deepcopy(DRY)},
           'soloMuteState':{'mute':False,'solo':False}}
    settings.update(activeSoundProfile='MuseScore Basic',tracks=[track],
                    master={'balance':0,'volumeDb':MASTER_DB,'fxChain':{},'auxSends':copy.deepcopy(DRY)},aux=[])
    if case['effect']:
        output = track['out'] if case['location']=='track' else settings['master']
        output['fxChain']={'0':fx(case['effect'],case['active'],case['reduction'])}
    with zipfile.ZipFile(base) as source, zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED) as destination:
        for row in source.infolist():
            destination.writestr(row,json.dumps(settings,ensure_ascii=False).encode('utf-8') if row.filename=='audiosettings.json' else source.read(row))
    return settings


def preserved(path, requested):
    actual,_=r.native_data(path)
    r.require(actual.get('activeSoundProfile')==requested['activeSoundProfile'], 'Sound profile changed on application save')
    tracks=actual.get('tracks',[])
    r.require(len(tracks)==1, 'Application save changed native track count')
    expected=requested['tracks'][0];track=tracks[0]
    for key in ('partId','instrumentId','in'):
        r.require(track.get(key)==expected[key], 'Application save changed track '+key)
    for actual_out, expected_out in ((track.get('out',{}),expected['out']),(actual.get('master',{}),requested['master'])):
        for key in ('balance','volumeDb','fxChain','auxSends'):
            r.require(actual_out.get(key)==expected_out[key], 'Application save changed mixer/FX '+key)
    # A default aux channel can exist after open, but the two sends must remain
    # explicitly off/zero. It has no audible input and cannot become a dry return.
    return True


def inspect(path):
    samples,rate,meta=r.read_wav(path)
    finite=all(math.isfinite(value) for value in samples)
    peak=max((abs(value) for value in samples),default=0) if finite else None
    rms=math.sqrt(math.fsum(value*value for value in samples)/len(samples)) if finite else None
    # Require float output for a strict gain oracle without PCM quantization.
    passed=finite and meta['encoding']==3 and meta['bits']==32 and 8<=meta['duration_seconds']<=20 and rms>1e-7 and 1e-6<peak<.95
    return {**meta,'nonfinite_samples':sum(not math.isfinite(value) for value in samples),
            'full_scale_samples':sum(abs(value)>=1 for value in samples if math.isfinite(value)),
            'peak':peak,'rms':rms,'passed':bool(passed)}


def compare(reference, candidate, expected_db=0, reduction=False):
    a,ar,am=r.read_wav(reference);b,br,bm=r.read_wav(candidate)
    same_shape=ar==br and len(a)==len(b) and all(am[key]==bm[key] for key in ('encoding','bits','channels'))
    r.require(same_shape and all(math.isfinite(x) for x in a+b), 'Gain comparison requires finite aligned PCM')
    power=math.fsum(x*x for x in a)
    r.require(power>1e-12, 'A silent baseline cannot qualify a processor')
    ratio=math.sqrt(math.fsum(y*y for y in b)/power)
    if reduction:
        # Source gain=10^(-reduction/20), reduction>=0 for this hard-knee
        # threshold/ratio. This checks actual attenuation, not a quality claim.
        excess=max((abs(y)-abs(x) for x,y in zip(a,b)),default=0)
        passed=0<ratio<.9 and excess<=max(abs(x) for x in a)*1e-5
        return {'scope':'actual-compression-reduction','rms_ratio':ratio,'maximum_pointwise_gain_excess':excess,
                'no_amplification_relative_tolerance':1e-5,'required_rms_ratio_below':.9,'passed':passed}
    expected=10**(expected_db/20)
    residual=math.sqrt(math.fsum((y-expected*x)**2 for x,y in zip(a,b))/power)/expected
    relative_error=abs(ratio/expected-1)
    passed=relative_error<=.003 and residual<=.0001
    return {'scope':'analytic-gain-control','expected_gain_db':expected_db,'expected_linear_gain':expected,
            'actual_rms_ratio':ratio,'relative_gain_error':relative_error,'normalized_waveform_residual':residual,
            'relative_gain_tolerance':.003,'residual_tolerance':.0001,
            'same_pcm':am['pcm_sha256']==bm['pcm_sha256'],'passed':passed}


def main(argv=None):
    parser=argparse.ArgumentParser()
    for name in ('artifact','stage','profile-record','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args(argv)
    r.require(os.name=='nt' and platform.machine().lower() in ('amd64','x86_64') and os.environ.get('CI')=='true'
              and os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted',
              'Only disposable native Windows x64 hosted CI may run this qualification')
    artifact,stage,output=[r.owned(p) for p in (args.artifact,args.stage,args.output)]
    roots=(artifact,stage,output)
    r.require(len(set(roots))==3 and not any(a in b.parents for a in roots for b in roots if a!=b)
              and not output.exists(), 'Distinct runtime roots and new output required')
    profile=r.load_profile_helper().verify_record(r.owned(args.profile_record))
    output.mkdir()
    report={'schema_version':1,'status':'running','build_number':2007,'source_commit':r.SOURCE,'source_tree':r.TREE,
            'ci_source_commit':r.CI_SOURCE,'executable_sha256':r.EXE_SHA,'stage_manifest_sha256':r.STAGE_MANIFEST_SHA,
            'commands':[],'cases':[],'error':None,'application_recompiled':False,'installer_executed':False,
            'VST_or_external_plugin_used':False,'physical_playback_or_listening_tested':False,
            'GUI_live_playback_or_controls_tested':False,'source2008_runtime_qualified':False,
            'scope':'Original2007 CLI renderer, track/master FX, gain/bypass/compression and native save/reopen',
            'original_fixture_license':'CC0-1.0','profile_owner':profile['owner']}
    stage_before=None;inputs_before=None
    try:
        exe,meta=r.restore_stage(artifact,stage)
        report['stage_archive_sha256_read_from_pinned_original_manifest']=meta['stage_archive_sha256']
        stage_before=r.inventory(stage)
        basics=list(stage.rglob('MS Basic.sf3'))
        r.require(len(basics)==1 and r.sha(basics[0])==r.BASIC_SHA, 'Original MS Basic bank differs')
        fixture=Path(__file__).parent/'fixtures/native-fx-cello.musicxml'
        inputs_before={str(fixture):r.sha(fixture)}
        ini=Path(profile['settings_file']);r.no_links(ini)
        ini.write_text('[application]\nhasCompletedFirstLaunchSetup=true\n\n[io]\naudioApi=WASAPI\noutputDevice=\nbufferSize=256\nsampleRate=48000\n',encoding='utf-8')
        env={k:v for k,v in os.environ.items() if not k.startswith(('QT_','QML_','QML2_','CADENCE_QA_CLOCK','ACTIONS_','GITHUB_','GH_'))
             and not any(word in k.upper() for word in ('TOKEN','SECRET','PASSWORD'))}
        env['PATH']=str(exe.parent)+';'+str(Path(os.environ['SystemRoot'])/'System32')
        logs=Path(profile['log_root']);deadline=time.monotonic()+1500
        def run(name,arguments):
            r.require(time.monotonic()<deadline, 'Global native QA timeout')
            before=r.snapshot(logs)
            row={'name':name,'arguments':[str(exe),*map(str,arguments)],'pid':None,'exit_code':None,'timed_out':False}
            report['commands'].append(row);started=time.monotonic()
            with (output/(name+'.stdout.txt')).open('xb') as stdout,(output/(name+'.stderr.txt')).open('xb') as stderr:
                proc=subprocess.Popen(row['arguments'],cwd=output,env=env,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW)
                row['pid']=proc.pid
                try:row['exit_code']=proc.wait(timeout=min(90,max(.1,deadline-time.monotonic())))
                except subprocess.TimeoutExpired:row['timed_out']=True;proc.kill();row['exit_code']=proc.wait(timeout=10)
                finally:
                    if proc.poll() is None:proc.kill();proc.wait(timeout=10)
            row['seconds']=time.monotonic()-started;after=r.snapshot(logs)
            text=b'\n'.join(b[len(before.get(k,b'')):] if b.startswith(before.get(k,b'')) else b for k,b in after.items()).decode('utf-8',errors='replace')
            (output/(name+'.cadence-log-delta.txt')).write_text(text,encoding='utf-8')
            for suffix in ('stdout','stderr'):
                path=output/(name+'.'+suffix+'.txt');r.require(path.stat().st_size<=16*1024**2, 'Bounded native transcript required')
                text+='\n'+path.read_text(encoding='utf-8',errors='replace')
            r.require(not row['timed_out'] and row['exit_code']==0, 'Actual native CLI failed: '+name)
            r.require('Not found: MS Basic' not in text and 'Failed parse SoundFont presets for' not in text, 'Native bank load failed')
        exercise=output/'original.musicxml';exercise.write_bytes(fixture.read_bytes())
        inputs_before[str(exercise)]=r.sha(exercise)
        base=output/'imported-base.mscz';run('import',['-o',base,exercise]);inputs_before[str(base)]=r.sha(base)
        for case in cases():
            label=case['name'];native=output/(label+'.mscz');requested=assign(base,native,case)
            inputs_before[str(native)]=r.sha(native)
            row={**case,'requested_audio_settings':requested,'source_sha256':r.sha(native),'save_preserved':False};report['cases'].append(row)
            wav=output/(label+'.wav');run(label+'-render',['-o',wav,native]);row['audio']=inspect(wav)
            row['fresh_wav_sha256']=r.sha(wav)
            r.require(row['audio']['passed'], 'Fresh native PCM finite/nonmute/headroom gate failed: '+label)
            saved=output/(label+'-saved.mscz');run(label+'-save',['-o',saved,native]);row['save_preserved']=preserved(saved,requested)
            saved_sha=r.sha(saved);reopened=output/(label+'-reopened.wav');run(label+'-reopen-render',['-o',reopened,saved])
            row['saved_project_sha256']=saved_sha;row['reopened_wav_sha256']=r.sha(reopened)
            row['reopened_audio']=inspect(reopened)
            r.require(row['reopened_audio']['passed'] and r.sha(saved)==saved_sha, 'Reopened native PCM or immutable saved project failed')
            row['reopen_preserved']=preserved(saved,requested)
            row['fresh_reopened_control']=compare(wav,reopened,0)
            r.require(row['fresh_reopened_control']['passed'], 'Save/reopen changed actual PCM: '+label)
        for row in report['cases']:
            label=row['name']
            for suffix,key in (('', 'fresh_control'),('-reopened','reopened_control')):
                row[key]=compare(output/('baseline'+suffix+'.wav'), output/(label+suffix+'.wav'), row['expected_gain_db'], row['reduction'])
                r.require(row[key]['passed'], 'Independent audio FX control failed: '+label+' '+key)
        r.require(len(report['commands'])==34 and len(report['cases'])==11, 'Native command/case plan differs')
        report['status']=PASS
    except Exception as error:
        report['status']='failed_or_blocked';report['error']=str(error)
    finally:
        try:
            report['stage_files_hashed']=len(stage_before) if stage_before is not None else 0
            report['stage_files_unchanged']=stage_before is not None and r.inventory(stage)==stage_before
            report['source_projects_and_fixture_unchanged']=inputs_before is not None and all(r.sha(Path(path))==digest for path,digest in inputs_before.items())
            if report['status']==PASS and not (report['stage_files_unchanged'] and report['source_projects_and_fixture_unchanged']):
                report['status']='failed_or_blocked';report['error']='Stage or input sources changed'
        except Exception as error:report['status']='failed_or_blocked';report['error']='Integrity check: '+str(error)
        (output/'native-fx-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print('CADENCE_NATIVE_FX_REPORT_BEGIN');print(json.dumps(report,ensure_ascii=False));print('CADENCE_NATIVE_FX_REPORT_END')
    return 0 if report['status']==PASS else 1


if __name__=='__main__':raise SystemExit(main())
