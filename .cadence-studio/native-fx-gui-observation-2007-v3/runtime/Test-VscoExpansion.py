#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Native Windows2007 SF2 expansion qualification; no installation or app rebuild.

Run only through the enclosing owned Windows Job. These generated MusicXML
exercises are original CC0 data. CLI save-only is distinct from live-playback
then-save GUI testing. Gain and PCM controls detect silent fallback even though
2007 deliberately preserves requested metadata for absent resources.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import struct
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

SOURCE='5058d29dad67e6131ee46ee617258ccfed8ba4b0'
TREE='58d06a1c89e99173b0473587245187df5bc3b3cf'
CI_SOURCE='4bfd68815efcd3410419d47678792426e20e543b'
EXE_SHA='dcfbf9155c6c972c37966a4b2b0dcd212133c8e31fb397c644dda800ac7122be'
ARCHIVE='CadenceStudio-v4.7.6-combined-system-aac-stage-build-2007-attempt-1-x64.zip'
STAGE_MANIFEST_SHA='ba985694173769bded900789a57952eef564026626e8be68e3484c583541ad05'
STAGE_MANIFEST_BYTES=3776
BUILD_RESULT_SHA='8d77e9c7554fd1779abafa293350d51696b320f7247802f6efe892857c909e60'
SOURCE_JSON_SHA='e0e36a40d2bee76337d8117016d0ca064e24fb2be2b9713b69855d6182a61fa9'
PROFILE_SHA='60b6bb2353467cf338e2c671151af37d3fd36d76748e52cda6a1e3ab22c4c27c'
BASIC_SHA='5ea2375e8bd7d8e71def1036978c1621e85b66934169b6a2744b27b9b3c2d99c'
QUIET_FILE='Cadence-VSCO-Trumpet-QA-minus18.sf2'
FAMILIES={
 'cello':dict(collection='cello-ensemble',program=42,name='Violoncello',xml_id='strings.cello',ids=('violoncello','cello'),clef='F',step='C',octave=3,chromatic=0,diatonic=0),
 'trumpet':dict(collection='trumpet-vibrato',program=56,name='Trumpet',xml_id='brass.trumpet',ids=('trumpet',),clef='G',step='C',octave=4,chromatic=0,diatonic=0),
 'contrabass':dict(collection='contrabass-vibrato',program=43,name='Contrabass',xml_id='strings.contrabass',ids=('contrabass','double-bass'),clef='F',step='C',octave=3,chromatic=-12,diatonic=-7),
}


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def no_links(path):
    for current in (path, *path.parents):
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Runtime paths cannot traverse links or reparse points')


def owned(path):
    path = path.absolute()
    no_links(path)
    path = path.resolve()
    temporary = Path(os.environ['RUNNER_TEMP']).resolve()
    if temporary not in path.parents:
        raise ValueError('Runtime paths must be strictly below RUNNER_TEMP')
    return path


def relative_member(name):
    if name.startswith('./'):
        name = name[2:]
    path = PurePosixPath(name.rstrip('/'))
    if (not name or '\\' in name or ':' in name or path.is_absolute()
            or any(part in ('.', '..') for part in path.parts)
            or any(ord(char) < 32 for char in name)):
        raise ValueError('Unsafe archive member')
    for part in path.parts:
        if part.endswith(('.', ' ')):
            raise ValueError('Ambiguous archive member')
    return path


def load_profile_helper():
    path = Path(__file__).with_name('CadenceProfileScope.py')
    if sha(path) != PROFILE_SHA:
        raise ValueError('Pinned profile-scope helper differs')
    spec = importlib.util.spec_from_file_location('cadence_vsco_profile_scope', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def native_data(path):
    with zipfile.ZipFile(path) as archive:
        if len(archive.infolist()) > 256 or len(set(archive.namelist())) != len(archive.namelist()):
            raise ValueError('Unexpected native project ZIP')
        for row in archive.infolist():
            relative_member(row.filename)
            if row.file_size > 16 * 1024**2:
                raise ValueError('Oversized native project member')
        masters = [name for name in archive.namelist() if name.endswith('.mscx') and '/' not in name]
        if len(masters) != 1:
            raise ValueError('A unique native master is required')
        return json.loads(archive.read('audiosettings.json')), ET.fromstring(archive.read(masters[0]))


def snapshot(logs):
    result = {}
    paths = list(logs.rglob('*.log')) if logs.is_dir() else []
    if len(paths) > 32:
        raise ValueError('Unexpected fresh profile log count')
    for path in paths:
        no_links(path)
        if path.stat().st_size > 16 * 1024**2:
            raise ValueError('Profile log exceeds 16 MiB')
        result[str(path)] = path.read_bytes()
    return result


def input_preserved(path, requested):
    settings, _ = native_data(path)
    tracks = settings.get('tracks', [])
    return (len(tracks) == 1 and tracks[0].get('partId') == requested['partId']
            and tracks[0].get('instrumentId') == requested['instrumentId'] and tracks[0].get('in') == requested['in'])

def require(ok, message):
    if not ok: raise ValueError(message)


def ledger(root):
    """Validate the producer's existing bounded companion ledger, never make one."""
    path=root/'SHA256SUMS.txt'; no_links(path)
    raw=path.read_text(encoding='ascii'); result={}
    for line in raw.splitlines():
        m=re.fullmatch(r'([a-f0-9]{64})  (.+)',line)
        require(m is not None,'Malformed original companion ledger')
        rel=relative_member(m[2]); key=rel.as_posix()
        require(key not in result and len(result)<1024,'Duplicate or oversized companion ledger')
        target=root.joinpath(*rel.parts);no_links(target)
        require(target.is_file() and target.stat().st_size<=512*1024**2 and sha(target)==m[1], 'Original companion changed: '+key)
        result[key]=m[1]
    require(ARCHIVE in result and 'stage-manifest.json' in result,'Original archive/manifest absent from ledger')
    return result


def validate_stage_metadata(artifact):
    manifest=artifact/'stage-manifest.json'; no_links(manifest)
    require(manifest.is_file() and manifest.stat().st_size==STAGE_MANIFEST_BYTES and sha(manifest)==STAGE_MANIFEST_SHA,
            'The byte-exact actual2007 stage manifest is required; no guessed archive hash')
    doc=json.loads(manifest.read_text(encoding='utf-8-sig'))
    require(doc.get('schema_version')==1 and doc.get('status')=='experimental-stage-before-qa'
            and doc.get('variant')=='Cadence' and doc.get('build_number')==2007
            and doc.get('original_source_commit')==SOURCE and doc.get('source_commit')==CI_SOURCE
            and doc.get('source_tree')==TREE and doc.get('executable_sha256')==EXE_SHA
            and doc.get('stage_archive')==ARCHIVE and doc.get('windows_system_aac') is True
            and isinstance(doc.get('stage_archive_sha256'),str)
            and re.fullmatch('[a-f0-9]{64}',doc['stage_archive_sha256']), 'The actual2007 stage provenance differs')
    result=artifact/'cadence-build-result.json';no_links(result)
    require(result.is_file() and sha(result)==BUILD_RESULT_SHA,'Original build-result report changed')
    built=json.loads(result.read_text(encoding='utf-8-sig'))
    require(built.get('source_commit')==CI_SOURCE and built.get('executable_sha256')==EXE_SHA,'Original build/executable provenance differs')
    hashes=ledger(artifact)
    require(hashes['stage-manifest.json']==STAGE_MANIFEST_SHA and hashes[ARCHIVE]==doc['stage_archive_sha256'],
            'Original ledger and pinned manifest do not agree')
    return doc


def restore_stage(artifact,stage):
    doc=validate_stage_metadata(artifact)
    archive=artifact/ARCHIVE;no_links(archive)
    require(archive.is_file() and sha(archive)==doc['stage_archive_sha256'] and not stage.exists(),
            'Original actual2007 inner archive hash/new stage required')
    with zipfile.ZipFile(archive) as source:
        rows=source.infolist()
        require(len(rows)<=10000 and sum(r.file_size for r in rows)<=2*1024**3,'Stage extraction bound exceeded')
        seen=set(); planned=[]
        for row in rows:
            rel=relative_member(row.filename); key=rel.as_posix().casefold()
            require(key not in seen and row.file_size<=512*1024**2
                    and ((row.external_attr>>16)&0o170000)!=0o120000,'Duplicate, linked or oversized stage entry')
            seen.add(key);planned.append((row,stage.joinpath(*rel.parts)))
        stage.mkdir()
        for row,target in planned:
            no_links(target)
            if row.is_dir():target.mkdir(parents=True,exist_ok=True);continue
            target.parent.mkdir(parents=True,exist_ok=True)
            with source.open(row) as incoming,target.open('xb') as outgoing:shutil.copyfileobj(incoming,outgoing,1<<20)
    exe=stage/'bin/CadenceStudio4.exe'
    require(sha(exe)==EXE_SHA and not (stage/'bin/icuuc.dll').exists(),'Actual executable or no-local-system-ICU policy differs')
    return exe,doc


def inventory(root):
    result={}
    for path in sorted(root.rglob('*')):
        no_links(path)
        if path.is_file():
            require(len(result)<20000 and path.stat().st_size<=512*1024**2,'Input inventory exceeds bound')
            result[path.relative_to(root).as_posix()]={'bytes':path.stat().st_size,'sha256':sha(path)}
    return result


def validate_banks(root):
    lock=json.loads(Path(__file__).with_name('bank-lock.json').read_text(encoding='utf-8'))
    manifest=json.loads((root/'banks-manifest.json').read_text(encoding='utf-8'))
    require(manifest.get('schema_version')==1 and manifest.get('status')=='built-pinned-vsco-expansion-sf2'
            and manifest.get('source_commit')==lock['source_commit']
            and manifest.get('source_manifest_sha256')==lock['source_manifest_sha256']
            and len(manifest.get('banks',[]))==3,'Fresh three-collection source build required')
    rows={r['collection_id']:r for r in manifest['banks']}
    require(set(rows)=={r['collection_id'] for r in lock['banks']},'Exact three collection IDs required')
    for expected in lock['banks']:
        actual=rows[expected['collection_id']]
        require(all(actual.get(k)==v for k,v in expected.items()),'Exact reviewed SF2 row differs: '+expected['collection_id'])
        p=root/expected['file'];no_links(p)
        require(p.is_file() and p.stat().st_size==expected['bytes'] and sha(p)==expected['sha256'],
                'Exact actual SF2 bytes differ: '+p.name)
    return manifest,rows


def gain_delta_proof(core,normal,quiet):
    require(normal.stat().st_size==quiet.stat().st_size,'Gain control must preserve file shape')
    a=normal.read_bytes();b=quiet.read_bytes()
    location,length=core.sf2_chunks(normal)[b'pdta',b'igen']
    expected=bytearray(a);changed=0
    for pos in range(location,location+length,4):
        op,amount=struct.unpack_from('<HH',a,pos)
        if op==48:
            struct.pack_into('<H',expected,pos+2,amount+450);changed+=1
    require(changed>0 and bytes(expected)==b,'Only exact +450 attenuation generator changes are accepted')
    return {'changed_zone_attenuations':changed,'only_attenuation_generators_changed':True,
            'raw_delta_per_zone':450,'expected_gain_db':-18,'original_sha256':sha(normal),'quiet_sha256':sha(quiet)}


def prepare_quiet(root,trumpet):
    source=Path(__file__).with_name('converter')/'build_vsco_sf2.py'
    spec=importlib.util.spec_from_file_location('cadence_expansion_sf2_core',source)
    core=importlib.util.module_from_spec(spec);sys.modules[spec.name]=core;spec.loader.exec_module(core)
    quiet=root/QUIET_FILE;require(not quiet.exists(),'A new technical gain control is required')
    count=core.attenuate_bank(root/trumpet['file'],quiet,18)
    proof=gain_delta_proof(core,root/trumpet['file'],quiet)
    require(count==trumpet['zones']==proof['changed_zone_attenuations'],'Gain control must cover every exact stereo zone')
    row={**trumpet,'collection_id':'qa-trumpet-minus18','file':quiet.name,'bytes':quiet.stat().st_size,
         'sha256':sha(quiet),'soundfont_name':quiet.stem,'resource_id':quiet.stem+'\\0\\56',
         'gain_delta_db':-18,'technical_control_only':True}
    return row,proof


def score_xml(instrument):
    f=FAMILIES[instrument]; measures=[]
    pitch=f'<pitch><step>{f["step"]}</step><octave>{f["octave"]}</octave></pitch>'
    for i,dynamic in enumerate(('p','mf','f'),1):
        attributes=''
        if i==1:
            attributes=(f'<attributes><divisions>4</divisions><key><fifths>0</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time>'
                        f'<clef><sign>{f["clef"]}</sign><line>{4 if f["clef"]=="F" else 2}</line></clef>'
                        f'<transpose><diatonic>{f["diatonic"]}</diatonic><chromatic>{f["chromatic"]}</chromatic></transpose></attributes>'
                        '<direction><direction-type><metronome><beat-unit>quarter</beat-unit><per-minute>120</per-minute></metronome></direction-type><sound tempo="120"/></direction>')
        percent=(25,63,90)[i-1]
        direction=f'<direction placement="below"><direction-type><dynamics><{dynamic}/></dynamics></direction-type><sound dynamics="{percent}"/></direction>'
        body=f'<note>{pitch}<duration>4</duration><type>quarter</type></note><note><rest/><duration>12</duration><type>half</type><dot/></note>'
        measures.append(f'<measure number="{i}">{attributes}{direction}{body}</measure>')
    for j in range(10):
        ties=('<tie type="stop"/>' if j>0 else '')+('<tie type="start"/>' if j<9 else '')
        notations=('<tied type="stop"/>' if j>0 else '')+('<tied type="start"/>' if j<9 else '')
        direction=('<direction placement="below"><direction-type><dynamics><mf/></dynamics></direction-type><sound dynamics="63"/></direction>' if j==0 else '')
        body=f'<note>{pitch}<duration>16</duration>{ties}<type>whole</type><notations>{notations}</notations></note>'
        measures.append(f'<measure number="{j+4}">{direction}{body}</measure>')
    measures.append('<measure number="14"><note><rest/><duration>16</duration><type>whole</type></note></measure>')
    return (f'<?xml version="1.0" encoding="utf-8"?><score-partwise version="4.0"><work><work-title>Cadence original CC0 {instrument} dynamics and finite sustain probe</work-title></work>'
            f'<identification><rights>CC0-1.0; original generated Cadence QA exercise, no third-party score</rights></identification>'
            f'<part-list><score-part id="P1"><part-name>{f["name"]}</part-name><score-instrument id="I1"><instrument-name>{f["name"]}</instrument-name><instrument-sound>{f["xml_id"]}</instrument-sound></score-instrument>'
            f'<midi-instrument id="I1"><midi-channel>1</midi-channel><midi-program>{f["program"]+1}</midi-program></midi-instrument></score-part></part-list>'
            f'<part id="P1">{"".join(measures)}</part></score-partwise>\n').encode('utf-8')


def assign_soundfont(base,target,instrument,bank=None):
    settings,score=native_data(base);parts=score.findall('./Score/Part')
    require(len(parts)==1 and len(parts[0].findall('Instrument'))==1,'Exactly one imported instrument required')
    part=parts[0];actual=part.find('Instrument');family=FAMILIES[instrument]
    require(part.get('id') and actual.get('id') and any(s in actual.get('id').lower() for s in family['ids']),
            'Imported instrument family differs from the original GM exercise')
    programs=[int(p.get('value')) for p in actual.findall('./Channel/program')]
    require(family['program'] in programs,'Native imported GM program differs from MusicXML one-based binding')
    name=bank['soundfont_name'] if bank else 'MS Basic'
    attrs={'soundFontName':name,'playbackSetupData':'generic'}
    if bank:attrs.update(presetBank='0',presetProgram=str(bank['program']))
    request={'resourceMeta':{'id':bank['resource_id'] if bank else name,'vendor':'Fluid','type':'fluid_soundfont',
                             'hasNativeEditorSupport':False,'attributes':attrs},'unitConfiguration':{}}
    track={'partId':part.get('id'),'instrumentId':actual.get('id'),'in':request,
           'out':{'balance':0,'volumeDb':0,'fxChain':{},'auxSends':[]},'soloMuteState':{'mute':False,'solo':False}}
    settings.update(activeSoundProfile='MuseScore Basic',tracks=[track],master={'balance':0,'volumeDb':-18,'fxChain':{},'auxSends':[]},aux=[])
    with zipfile.ZipFile(base) as source,zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED) as destination:
        for row in source.infolist():destination.writestr(row,json.dumps(settings,ensure_ascii=False).encode('utf-8') if row.filename=='audiosettings.json' else source.read(row))
    return track,{'instrument_id':actual.get('id'),'imported_GM_programs_zero_based':programs,
                  'first_native_pitch':score.findtext('./Score/Staff/Measure/voice/Chord/Note/pitch'),
                  'transpose_chromatic':actual.findtext('transposeChromatic'),'original_musicxml_program_one_based':family['program']+1}


def read_wav(path):
    require(path.stat().st_size<=128*1024**2,'WAV exceeds128MiB')
    with path.open('rb') as stream:
        header=stream.read(12);require(header[:4]==b'RIFF' and header[8:]==b'WAVE','RIFF/WAVE required')
        fmt=data=None
        while header:=stream.read(8):
            require(len(header)==8,'Truncated WAV chunk')
            tag,size=struct.unpack('<4sI',header);offset=stream.tell()
            require(offset+size<=path.stat().st_size,'WAV chunk exceeds file')
            if tag==b'fmt ':
                require(16<=size<=1024,'WAV format bound');fmt=struct.unpack('<HHIIHH',stream.read(16))
            elif tag==b'data':require(data is None,'Multiple WAV data chunks');data=(offset,size)
            stream.seek(offset+size+(size&1))
        require(fmt is not None and data is not None,'WAV format/data missing')
        encoding,channels,rate,byte_rate,align,bits=fmt;width=bits//8
        require((encoding,bits) in {(1,16),(1,24),(1,32),(3,32),(3,64)} and channels==2 and rate>=8000
                and align==channels*width and byte_rate==rate*align and data[1]>0 and data[1]%align==0,'Unsupported WAV encoding/shape')
        stream.seek(data[0]);raw=stream.read(data[1]);require(len(raw)==data[1],'Truncated PCM')
    scalars=([r[0] for r in struct.iter_unpack('<f' if bits==32 else '<d',raw)] if encoding==3 else
             [int.from_bytes(raw[i:i+width],'little',signed=True)/2**(bits-1) for i in range(0,len(raw),width)])
    return scalars,rate,{'encoding':encoding,'bits':bits,'channels':channels,'sample_rate':rate,'duration_seconds':data[1]/byte_rate,'pcm_sha256':hashlib.sha256(raw).hexdigest()}


def window_rms(values,rate,start,end):
    lo=round(start*rate)*2;hi=round(end*rate)*2
    require(0<=lo<hi<=len(values),'Musical analysis window is outside the actual WAV')
    return math.sqrt(sum(v*v for v in values[lo:hi])/(hi-lo))


def goertzel(samples,rate,freq):
    # Only a spectrum diagnostic, never a fundamental/pitch pass/fail detector.
    coeff=2*math.cos(2*math.pi*freq/rate);q1=q2=0.0
    for i,s in enumerate(samples):
        sample=s*(.5-.5*math.cos(2*math.pi*i/max(1,len(samples)-1)))
        q0=sample+coeff*q1-q2;q2,q1=q1,q0
    return max(0.0,q1*q1+q2*q2-coeff*q1*q2)/max(1,len(samples))**2


def inspect_wav(path,instrument,expect_finite_sustain=False):
    values,rate,metrics=read_wav(path);count=len(values)
    nonfinite=sum(not math.isfinite(v) for v in values)
    finite=[v for v in values if math.isfinite(v)]
    peak=max(map(abs,finite),default=0);rms=math.sqrt(sum(v*v for v in finite)/max(1,count))
    onset=next((i//2/rate for i,v in enumerate(values[:rate*2]) if math.isfinite(v) and abs(v)>1e-6),None)
    metrics.update(nonfinite_samples=nonfinite,full_scale_samples=sum(abs(v)>=1.0 for v in finite),peak=peak,rms=rms,onset_seconds=onset)
    metrics['signal_passed']=not nonfinite and not metrics['full_scale_samples'] and rms>1e-6 and 27<=metrics['duration_seconds']<=60 and onset is not None and onset<.5
    if not metrics['signal_passed']:metrics['passed']=False;return metrics
    shift=onset
    dyn={name:window_rms(values,rate,shift+t+.10,shift+t+.32) for name,t in [('p',0),('mf',2),('f',4)]}
    metrics['dynamics']={'rms':dyn,'strictly_rising':dyn['mf']>dyn['p']*1.02 and dyn['f']>dyn['mf']*1.02,
                         'score_sound_dynamic_percent':[25,63,90],'actual_MIDI_velocities_measured':False}
    early=window_rms(values,rate,shift+6.1,shift+6.32)
    late=window_rms(values,rate,shift+23.0,shift+25.0)
    tail=window_rms(values,rate,shift+27.0,shift+27.5)
    release=window_rms(values,rate,shift+.55,shift+.75)
    after=window_rms(values,rate,shift+1.6,shift+1.85)
    metrics['envelope_observations']={'quarter_note_release_rms':release,'after_quarter_release_rms':after,
      'initial_held_rms':early,'late_held_17_to19seconds_rms':late,'after_20second_hold_release_rms':tail,
      'finite_unlooped_sample_ends_while_note_held':late<max(1e-7,early*1e-3),
      'release_has_signal':release>1e-8,'post_release_is_quiet':after<max(1e-7,dyn['p']*.02),
      'hold_tail_is_quiet':tail<max(1e-7,early*.02),'expected_finite_sustain_limitation':expect_finite_sustain}
    native_midi=12*(FAMILIES[instrument]['octave']+1)+{'C':0}[FAMILIES[instrument]['step']]+FAMILIES[instrument]['chromatic']
    nominal=440*2**((native_midi-69)/12)
    start=round((shift+.12)*rate);end=round((shift+.32)*rate)
    mono=[(values[i*2]+values[i*2+1])*.5 for i in range(start,end)]
    metrics['spectral_diagnostic_only']={'nominal_from_original_score_midi':native_midi,
      'nominal_from_original_score_hz':nominal,'powers':{str(m):goertzel(mono,rate,nominal*m) for m in (.5,1,2,3)},
      'used_as_qualification_gate':False,'fundamental_or_tuning_validated':False,
      'virtual_fundamental_warning':'Upper partials and release overlap can suggest a suboctave; no NSDF pitch pass is inferred.'}
    env=metrics['envelope_observations']
    metrics['passed']=metrics['signal_passed'] and metrics['dynamics']['strictly_rising']
    if expect_finite_sustain:
        metrics['passed']=metrics['passed'] and all(env[k] for k in ('release_has_signal','post_release_is_quiet','hold_tail_is_quiet','finite_unlooped_sample_ends_while_note_held'))
    return metrics


def build_parser():
    parser=argparse.ArgumentParser(description=__doc__)
    for argument in ('artifact','stage','banks','profile-record','output'):parser.add_argument('--'+argument,type=Path,required=True)
    return parser


def planned_cases(rows,quiet):
    cases=[]
    for instrument,f in FAMILIES.items():
        require(f['collection'] in rows and rows[f['collection']]['program']==f['program'],'Exact collection/family binding required')
        cases += [('basic-'+instrument,instrument,None),(instrument,instrument,rows[f['collection']])]
    missing={**rows['cello-ensemble'],'file':'not-installed.sf2','soundfont_name':'Cadence-VSCO-Missing-Expansion',
             'resource_id':'Cadence-VSCO-Missing-Expansion\\0\\42','missing_resource_control_only':True}
    return cases+[('trumpet-minus18','trumpet',quiet),('missing-cello','cello',missing)]


def main(argv=None):
    args=build_parser().parse_args(argv)
    require(os.name=='nt' and platform.machine().lower() in ('amd64','x86_64') and os.environ.get('CI')=='true'
            and os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted',
            'Only disposable native Windows x64 hosted CI may run this qualification')
    artifact,stage,banks,output=[owned(p) for p in (args.artifact,args.stage,args.banks,args.output)]
    roots=(artifact,stage,banks,output)
    require(len(set(roots))==4 and not any(a in b.parents for a in roots for b in roots if a!=b) and not output.exists(),'Distinct runtime roots/new output required')
    profile_path=owned(args.profile_record);profile_helper=load_profile_helper();profile=profile_helper.verify_record(profile_path)
    manifest,rows=validate_banks(banks);output.mkdir()
    report={'schema_version':1,'status':'running','build_number':2007,'source_commit':SOURCE,'source_tree':TREE,
      'ci_source_commit':CI_SOURCE,'executable_sha256':EXE_SHA,'stage_manifest_sha256':STAGE_MANIFEST_SHA,
      'banks_manifest':manifest,'profile_owner':profile['owner'],'commands':[],'cases':[],'error':None,
      'native_SF2_loader_used':True,'SFZ_or_VST_loader_used':False,'application_recompiled':False,
      'physical_playback_or_listening_tested':False,'GUI_save_after_live_playback_tested':False,
      'GUI_missing_bank_warning_tested':False,'generated_exercise_license':'CC0-1.0',
      'profile_namespace_contract_original_commit':'0e05d04acbeee32f1b561f24493d7ef41c322081',
      'scope':'Actual native renderer, independent gain control, saved requested identity; not a GUI or human-listening qualification'}
    try:
        quiet,gain_bytes=prepare_quiet(banks,rows['trumpet-vibrato']);report['technical_gain_control_bytes']=gain_bytes
        exe,stage_meta=restore_stage(artifact,stage);report['stage_archive_sha256_read_from_pinned_original_manifest']=stage_meta['stage_archive_sha256']
        stage_before=inventory(stage);banks_before=inventory(banks)
        basic=list(stage.rglob('MS Basic.sf3'));require(len(basic)==1 and sha(basic[0])==BASIC_SHA,'MS Basic positive control differs')
        ini=Path(profile['settings_file']);no_links(ini)
        ini.write_text('[application]\nhasCompletedFirstLaunchSetup=true\npaths\\mySoundfonts='+banks.as_posix()+'\n\n[io]\naudioApi=WASAPI\noutputDevice=\nbufferSize=256\nsampleRate=48000\n',encoding='utf-8')
        env={k:v for k,v in os.environ.items() if not k.startswith(('QT_','QML_','QML2_','CADENCE_QA_CLOCK','ACTIONS_','GITHUB_','GH_'))
             and not any(word in k.upper() for word in ('TOKEN','SECRET','PASSWORD'))}
        env['PATH']=str(exe.parent)+';'+str(Path(os.environ['SystemRoot'])/'System32')
        logs=Path(profile['log_root']);global_deadline=time.monotonic()+1200
        def run(name,arguments):
            require(time.monotonic()<global_deadline,'Native qualification global timeout')
            before=snapshot(logs);row={'name':name,'arguments':[str(exe),*map(str,arguments)],'pid':None,'exit_code':None,'timed_out':False};report['commands'].append(row)
            started=time.monotonic()
            with (output/(name+'.stdout.txt')).open('xb') as stdout,(output/(name+'.stderr.txt')).open('xb') as stderr:
                proc=subprocess.Popen(row['arguments'],cwd=output,env=env,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW);row['pid']=proc.pid
                try:row['exit_code']=proc.wait(timeout=min(90,max(.1,global_deadline-time.monotonic())))
                except subprocess.TimeoutExpired:row['timed_out']=True;proc.kill();row['exit_code']=proc.wait(timeout=10)
                finally:
                    if proc.poll() is None:proc.kill();proc.wait(timeout=10)
            row['seconds']=time.monotonic()-started;after=snapshot(logs)
            delta=b'\n'.join(b[len(before.get(k,b'')):] if b.startswith(before.get(k,b'')) else b for k,b in after.items()).decode('utf-8',errors='replace')
            (output/(name+'.cadence-log-delta.txt')).write_text(delta,encoding='utf-8')
            text=delta
            for suffix in ('stdout','stderr'):
                p=output/(name+'.'+suffix+'.txt');require(p.stat().st_size<=16*1024**2,'Application transcript bound');text+='\n'+p.read_text(encoding='utf-8',errors='replace')
            require(not row['timed_out'] and row['exit_code']==0,'Native CLI failed: '+name)
            return text
        bases={};originals={}
        for instrument in FAMILIES:
            exercise=output/(instrument+'-original.musicxml');exercise.write_bytes(score_xml(instrument));originals[instrument]=sha(exercise)
            base=output/(instrument+'-imported-base.mscz');run(instrument+'-import',['-o',base,exercise]);bases[instrument]=base
        cases=planned_cases(rows,quiet)
        by_name={}
        for label,instrument,bank in cases:
            native=output/(label+'.mscz');requested,imported=assign_soundfont(bases[instrument],native,instrument,bank);before=sha(native)
            row={'name':label,'instrument':instrument,'requested_track':requested,'imported_native':imported,
                 'source_sha256':before,'source_unchanged':False,'resource_preserved_on_save':False};report['cases'].append(row)
            finite=bank is not None and not bank.get('missing_resource_control_only',False)
            wav=output/(label+'.wav');diagnostics=run(label+'-render',['-o',wav,native]);row['audio']=inspect_wav(wav,instrument,finite);row['wav_sha256']=sha(wav)
            resource=requested['in']['resourceMeta']['id'];missing_case=label=='missing-cello'
            row['missing_resource_diagnostic_observed']=('Not found: '+resource in diagnostics)
            require(row['audio']['passed'] and (missing_case or ('Not found: '+resource not in diagnostics and 'Failed parse SoundFont presets for' not in diagnostics)),
                    'Native resource/render/dynamics/envelope gate failed: '+label)
            saved=output/(label+'-save-only.mscz');run(label+'-save-only',['-o',saved,native]);row['resource_preserved_on_save']=input_preserved(saved,requested)
            reopened=output/(label+'-reopened.wav');diagnostics=run(label+'-reopen-render',['-o',reopened,saved]);row['reopened_audio']=inspect_wav(reopened,instrument,finite)
            row['reopened_wav_sha256']=sha(reopened);row['source_unchanged']=sha(native)==before
            require(row['resource_preserved_on_save'] and row['source_unchanged'] and row['reopened_audio']['passed']
                    and (missing_case or 'Not found: '+resource not in diagnostics),'Saved input/reopened audio failed: '+label)
            by_name[label]=row
        normal,quietcase=by_name['trumpet'],by_name['trumpet-minus18'];ratio=quietcase['audio']['rms']/normal['audio']['rms'];again=quietcase['reopened_audio']['rms']/normal['reopened_audio']['rms'];expected=10**(-18/20)
        proof={'expected_db':-18,'expected_rms_ratio':expected,'actual_rms_ratio':ratio,'reopened_rms_ratio':again,'relative_tolerance':.03,
               'gain_matches':abs(ratio/expected-1)<=.03 and abs(again/expected-1)<=.03,
               'same_shape':all(normal['audio'][k]==quietcase['audio'][k] for k in ('encoding','bits','channels','sample_rate','duration_seconds')),
               'expansion_PCM_differs_from_MSBasic':{i:by_name[i]['audio']['pcm_sha256']!=by_name['basic-'+i]['audio']['pcm_sha256'] and by_name[i]['reopened_audio']['pcm_sha256']!=by_name['basic-'+i]['reopened_audio']['pcm_sha256'] for i in FAMILIES},
               'missing_cello_PCM_matches_MSBasic':by_name['missing-cello']['audio']['pcm_sha256']==by_name['basic-cello']['audio']['pcm_sha256'] and by_name['missing-cello']['reopened_audio']['pcm_sha256']==by_name['basic-cello']['reopened_audio']['pcm_sha256']}
        report['native_load_gain_and_fallback_controls']=proof
        require(proof['gain_matches'] and proof['same_shape'] and all(proof['expansion_PCM_differs_from_MSBasic'].values()) and proof['missing_cello_PCM_matches_MSBasic'],
                'Independent load/gain/fallback controls failed; preserved metadata/nonmute alone are insufficient')
        report['stage_files_hashed']=len(stage_before);report['stage_files_unchanged']=inventory(stage)==stage_before
        report['banks_unchanged']=inventory(banks)==banks_before
        report['original_exercises_unchanged']=all(sha(output/(i+'-original.musicxml'))==h for i,h in originals.items())
        require(report['stage_files_unchanged'] and report['banks_unchanged'] and report['original_exercises_unchanged'] and len(report['commands'])==27,'Inputs changed or expected command count differs')
        report['status']='passed-native-expansion-render-gain-save-reload-and-controls'
    except Exception as error:report['status']='failed_or_blocked';report['error']=str(error)
    finally:
        (output/'vsco-expansion-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print('CADENCE_VSCO_EXPANSION_REPORT_BEGIN');print(json.dumps(report,ensure_ascii=False));print('CADENCE_VSCO_EXPANSION_REPORT_END')
    return 0 if report['status']=='passed-native-expansion-render-gain-save-reload-and-controls' else 1

if __name__=='__main__':raise SystemExit(main())
