#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Render controlled CC0 copies with a real optional SF2 using retained Cadence2002.

This does not run the new manager UI or test saving the same GUI project after
playback. It proves native SoundFont loading/rendering with actual bank bytes.
"""
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
import xml.etree.ElementTree as ET
import zipfile

BANK_SHA = '9575028c7a1f589f5770fccc8cff2734566af40cd26ed836944e9a5152688cfe'
LICENSE_SHA = '7b32efefdf95ce38a043799f0659853ddc00fbaa14d8c50f0aca16b9b8b405be'
EXE_SHA = '35d8b076cacddb8b37a4f23aeea9899e6ab4ac9214e9a5b1125bbeccf26cf39e'
BASIC_SHA = '5ea2375e8bd7d8e71def1036978c1621e85b66934169b6a2744b27b9b3c2d99c'

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def snapshot(root):
    result = {}
    if root.is_dir():
        logs = list(root.rglob('*.log'))
        if len(logs) > 32:
            raise ValueError('Unexpected fresh-profile log count')
        for path in logs:
            if path.is_symlink() or path.stat().st_size > 16777216:
                raise ValueError('Unsafe or oversized test application log')
            result[str(path)] = path.read_bytes()
    return result

def log_delta(before, after):
    return b'\n'.join(data[len(before.get(name,b'')):] if data.startswith(before.get(name,b'')) else data
        for name,data in after.items()).decode('utf-8',errors='replace')

def native_audio(path):
    with zipfile.ZipFile(path) as archive:
        return json.loads(archive.read('audiosettings.json'))

def assign_bank(base, target, bank):
    with zipfile.ZipFile(base) as archive:
        masters = [n for n in archive.namelist() if n.endswith('.mscx') and '/' not in n]
        if len(masters) != 1:
            raise ValueError('A unique native master is required')
        score = ET.fromstring(archive.read(masters[0]))
        tracks = []
        for part in score.findall('./Score/Part'):
            for instrument in part.findall('Instrument'):
                if not part.get('id') or not instrument.get('id'):
                    raise ValueError('Actual part/instrument identifiers are required')
                tracks.append({'partId':part.get('id'),'instrumentId':instrument.get('id'),
                    'in':{'resourceMeta':{'id':bank,'vendor':'Fluid','type':'fluid_soundfont','hasNativeEditorSupport':False,
                        'attributes':{'soundFontName':bank,'playbackSetupData':'generic'}},'unitConfiguration':{}},
                    'out':{'balance':0,'volumeDb':0,'fxChain':{},'auxSends':[]},'soloMuteState':{'mute':False,'solo':False}})
        if not tracks or len({(t['partId'],t['instrumentId']) for t in tracks}) != len(tracks):
            raise ValueError('Unique actual instrument tracks are required')
        settings = native_audio(base);settings['activeSoundProfile']='MuseScore Basic';settings['tracks']=tracks
        with zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED) as output:
            for info in archive.infolist():
                output.writestr(info,json.dumps(settings,ensure_ascii=False).encode('utf-8') if info.filename=='audiosettings.json' else archive.read(info))
    return tracks

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage',type=Path,required=True);p.add_argument('--bank',type=Path,required=True)
    p.add_argument('--license',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if os.name!='nt' or platform.machine().lower() not in ('amd64','x86_64') or os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('CI')!='true' or os.environ.get('RUNNER_ENVIRONMENT')!='github-hosted':
        raise SystemExit('Only disposable native Windows x64 GitHub-hosted runners are allowed')
    temporary=Path(os.environ['RUNNER_TEMP']).resolve();stage=args.stage.resolve();output=args.output.resolve()
    if temporary not in stage.parents or temporary not in output.parents or output.exists() or stage in output.parents or output in stage.parents:
        raise ValueError('New runtime output and restored stage must be separate below RUNNER_TEMP')
    executable=stage/'bin/CadenceStudio4.exe';bank=args.bank.resolve();licence=args.license.resolve()
    basics=list(stage.rglob('MS Basic.sf3'))
    if sha(executable)!=EXE_SHA or sha(bank)!=BANK_SHA or bank.stat().st_size!=32319396 or sha(licence)!=LICENSE_SHA or len(basics)!=1 or sha(basics[0])!=BASIC_SHA:
        raise ValueError('Original executable, optional bank, licence or MS Basic pin differs')
    local=Path(os.environ['LOCALAPPDATA'])/'CadenceStudio';roaming=Path(os.environ['APPDATA'])/'CadenceStudio'
    document_buffer=ctypes.create_unicode_buffer(32768)
    if ctypes.windll.shell32.SHGetFolderPathW(None,5,None,0,document_buffer)!=0:
        raise ValueError('Cannot resolve this disposable Windows user Documents directory')
    documents=Path(document_buffer.value).resolve();cadence_documents=documents/'CadenceStudio4'
    if local.exists() or roaming.exists() or cadence_documents.exists():
        raise ValueError('Existing Cadence profiles/documents are never touched')
    for path in (local,roaming,cadence_documents,stage,output,bank,licence):
        for ancestor in [path,*path.parents]:
            if ancestor.is_symlink() or getattr(ancestor,'is_junction',lambda:False)():
                raise ValueError('Runtime/test paths must not traverse links')
    checker=Path(__file__).with_name('corpus_run_exports.py')
    if sha(checker)!='f701874e7a37b8d3148f0bb99477b60b96865e804ed238372d75c06598027d82':
        raise ValueError('Existing WAV inspector changed')
    spec=importlib.util.spec_from_file_location('cadence_free_bank_corpus',checker)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    pins=json.loads(Path(__file__).with_name('fixture-pins.json').read_text())
    fixtures=Path(__file__).with_name('fixtures')
    for name,value in pins.items():
        if sha(fixtures/name)!=value:
            raise ValueError('Original CC0 fixture differs')
    output.mkdir();soundfonts=cadence_documents/'SoundFonts';soundfonts.mkdir(parents=True)
    installed=soundfonts/'Cadence-GeneralUser-GS-2.0.3.sf2'
    with bank.open('rb') as source,installed.open('xb') as destination:
        shutil.copyfileobj(source,destination,1048576)
    if sha(installed)!=BANK_SHA:
        raise ValueError('Owned optional bank copy differs')
    report={'schema_version':1,'status':'running','retained_build':2002,'executable_sha256':EXE_SHA,
        'bank_sha256':BANK_SHA,'bank_bytes':32319396,'installed_bank':str(installed),
        'commands':[],'cases':[],'fresh_profile_and_documents':True,'native_manager_ui_tested':False,
        'human_listening_performed':False,'save_after_playback_same_project_tested':False,'error':None}
    env=os.environ.copy();env['PATH']=str(executable.parent)+';'+str(Path(os.environ['SystemRoot'])/'System32')
    logs=local/'CadenceStudio4/logs'
    def run(name,arguments):
        before=snapshot(logs);started=time.monotonic();item={'name':name,'exit_code':None,'timed_out':False,'pid':None};report['commands'].append(item)
        with (output/(name+'.stdout.txt')).open('xb') as out,(output/(name+'.stderr.txt')).open('xb') as err:
            process=subprocess.Popen([str(executable),*map(str,arguments)],cwd=output,env=env,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
            item['pid']=process.pid
            try:item['exit_code']=process.wait(timeout=90)
            except subprocess.TimeoutExpired:
                item['timed_out']=True;process.kill();item['exit_code']=process.wait(timeout=10)
        item['seconds']=time.monotonic()-started
        delta=log_delta(before,snapshot(logs));(output/(name+'.cadence-log.txt')).write_text(delta,encoding='utf-8')
        if item['timed_out'] or item['exit_code']!=0:
            raise RuntimeError('Owned command failed: '+name)
        return delta
    try:
        run('version',['--long-version'])
        for fixture in ('piano','voice','guitar','percussion','ensemble'):
            copied=output/(fixture+'-source.musicxml');shutil.copyfile(fixtures/(fixture+'.musicxml'),copied)
            base=output/(fixture+'-base.mscz');run(fixture+'-native',['-o',base,copied])
            case={'fixture':fixture,'variants':[]};report['cases'].append(case)
            for sound in ('MS Basic','Cadence-GeneralUser-GS-2.0.3'):
                suffix='basic' if sound=='MS Basic' else 'generaluser';native=output/(fixture+'-'+suffix+'.mscz')
                tracks=assign_bank(base,native,sound);before=sha(native);wav=output/(fixture+'-'+suffix+'.wav')
                delta=run(fixture+'-'+suffix+'-wav',['-o',wav,native]);audio=module.inspect_wav(wav)
                normalized=delta.replace('\\','/').lower()
                positive=any('success load soundfont:' in line and sound.lower()+'.sf' in line for line in normalized.splitlines())
                missing=('Not found: '+sound) in delta
                value={'bank':sound,'requested_tracks':len(tracks),'source_copy_sha256':before,'source_copy_unchanged':sha(native)==before,
                    'audio':audio,'wav_sha256':sha(wav),'actual_synth_soundfont_load_observed':positive,'missing_requested_resource_diagnostic':missing}
                case['variants'].append(value)
                if not audio['passed'] or not positive or missing or not value['source_copy_unchanged']:
                    raise RuntimeError('SoundFont was not confirmed at the actual synth, or audio/copy validation failed')
                saved=output/(fixture+'-'+suffix+'-save-only.mscz');run(fixture+'-'+suffix+'-save-only',['-o',saved,native])
                saved_ids={(t.get('partId'),t.get('instrumentId')):t.get('in',{}).get('resourceMeta',{}).get('id') for t in native_audio(saved).get('tracks',[])}
                value['save_only_resource_identity_preserved']=all(saved_ids.get((t['partId'],t['instrumentId']))==sound for t in tracks)
                if not value['save_only_resource_identity_preserved'] or sha(native)!=before:
                    raise RuntimeError('Save-only bank identity or source immutability failed')
            first,second=case['variants'];case['alternative_waveform_differs']=first['wav_sha256']!=second['wav_sha256']
            case['rms_ratio_alternative_to_basic']=second['audio']['rms']/first['audio']['rms']
            if sha(copied)!=pins[fixture+'.musicxml']:
                raise RuntimeError('Original controlled musicxml copy changed')
        report['bank_and_originals_unchanged']=sha(installed)==BANK_SHA and sha(bank)==BANK_SHA and sha(executable)==EXE_SHA and sha(basics[0])==BASIC_SHA and all(sha(fixtures/name)==value for name,value in pins.items())
        if not report['bank_and_originals_unchanged'] or not any(c['alternative_waveform_differs'] for c in report['cases']):
            raise RuntimeError('Originals changed or no alternate waveform was observed')
        report['status']='passed_actual_native_sf2_rendering_and_save_only_checks'
    except Exception as error:
        report['status']='failed_or_blocked';report['error']=str(error)
    finally:
        (output/'free-bank-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print('CADENCE_FREE_BANK_REPORT_BEGIN');print(json.dumps(report,ensure_ascii=False));print('CADENCE_FREE_BANK_REPORT_END')
    return 0 if report['status'].startswith('passed_') else 1
if __name__=='__main__':
    raise SystemExit(main())
