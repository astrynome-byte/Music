#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Cadence Studio contributors
"""Windows2008 production WAV engine -> SMF -> real new Cadence import/reopen.

Standard library only; downloads nothing. Called inside the supplied owned Job
PowerShell controller. --validate-only performs portable fixture/parser checks
and launches no process. No GUI, listening or broad transcription accuracy proof.
"""
from __future__ import annotations
import argparse
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import time
import wave
from xml.etree import ElementTree as ET
import zipfile

GROUPS = [
    'melody/rest/source/SMF/rhythm/boundaries', 'seven sample rates',
    'PCM16/24/32 Float32 stereo channel', 'harmonic fundamentals/octave jumps/vibrato',
    'noise/silence/quiet/repeated pitch rests', 'cancellation before/during',
    'malformed/NaN/options/tempo/meter/grid collapse', 'anti-alias/duration/extensible',
    '1000 malformed WAV cases',
]


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_smf(path):
    b = Path(path).read_bytes()
    require(30 < len(b) <= 262144 and b[:4] == b'MThd', 'bounded SMF header required')
    require(struct.unpack('>IHHH', b[4:14]) == (6, 0, 1, 480), 'SMF0, one track, 480 PPQ required')
    require(b[14:18] == b'MTrk' and struct.unpack('>I', b[18:22])[0] == len(b)-22, 'exact MIDI track extent required')
    pos, tick, active, tempo, meter, ended = 22, 0, None, None, None, False
    notes = []
    def vlq():
        nonlocal pos
        value = 0
        for _ in range(4):
            require(pos < len(b), 'truncated MIDI VLQ')
            byte = b[pos]; pos += 1; value = (value << 7) | (byte & 127)
            if not byte & 128:
                return value
        raise ValueError('MIDI VLQ exceeds four bytes')
    while pos < len(b):
        tick += vlq(); require(pos < len(b), 'truncated MIDI event')
        status = b[pos]; pos += 1
        if status == 0xff:
            require(pos < len(b), 'missing MIDI meta type')
            kind = b[pos]; pos += 1; length = vlq()
            require(pos+length <= len(b), 'truncated MIDI metadata')
            body = b[pos:pos+length]; pos += length
            if kind == 0x51:
                require(tempo is None and length == 3, 'one MIDI tempo required'); tempo = int.from_bytes(body, 'big')
            elif kind == 0x58:
                require(meter is None and length == 4, 'one MIDI meter required'); meter = [body[0], 1 << body[1]]
            elif kind == 0x2f:
                require(length == 0 and pos == len(b) and active is None, 'MIDI EOT must end an inactive track'); ended = True
        elif status == 0xc0:
            require(pos < len(b) and b[pos] == 0, 'piano program required'); pos += 1
        elif status in (0x90, 0x80):
            require(pos+2 <= len(b), 'truncated MIDI note'); pitch, velocity = b[pos:pos+2]; pos += 2
            require(pitch < 128 and velocity < 128, 'invalid MIDI data byte')
            if status == 0x90:
                require(active is None and velocity > 0, 'monophonic MIDI note-on required'); active = (pitch, tick)
            else:
                require(active is not None and pitch == active[0] and tick > active[1], 'matching MIDI note-off required')
                notes.append([pitch, active[1], tick]); active = None
        else:
            raise ValueError('unexpected MIDI status in native engine output')
    require(ended and notes and tempo == 500000 and meter == [4, 4], 'complete MIDI at explicitly selected 120 bpm and 4/4 required')
    return {'ppq': 480, 'tempo_us': tempo, 'meter': meter, 'events': notes}


def read_musicxml(path):
    raw = Path(path).read_bytes()
    require(0 < len(raw) <= 4*1024*1024 and b'<!ENTITY' not in raw, 'bounded MusicXML without entities required')
    root = ET.fromstring(raw); require(root.tag == 'score-partwise', 'native partwise MusicXML expected')
    segments, meters, parts = [], [], root.findall('part')
    require(1 <= len(parts) <= 8, 'bounded native parts required')
    for part in parts:
        measure_start, divisions, nominal = Fraction(0), 1, Fraction(4)
        measures = part.findall('measure'); require(0 < len(measures) <= 256, 'bounded measures required')
        for measure in measures:
            cursor, previous, furthest = Fraction(0), Fraction(0), Fraction(0)
            for item in measure:
                if item.tag == 'attributes':
                    value = item.findtext('divisions')
                    if value:
                        divisions = int(value); require(0 < divisions <= 1000000, 'invalid MusicXML divisions')
                    meter = item.find('time')
                    if meter is not None:
                        beats, unit = int(meter.findtext('beats')), int(meter.findtext('beat-type'))
                        require(0 < beats <= 32 and unit in (1, 2, 4, 8, 16, 32), 'invalid native meter')
                        nominal = Fraction(4*beats, unit); meters.append([beats, unit])
                elif item.tag in ('backup', 'forward'):
                    duration = Fraction(int(item.findtext('duration', '0')), divisions)
                    require(duration >= 0, 'negative MusicXML duration')
                    cursor += duration if item.tag == 'forward' else -duration
                    require(cursor >= 0, 'MusicXML backup before measure')
                elif item.tag == 'note':
                    require(item.find('grace') is None, 'unexpected grace in quantized MIDI import')
                    duration = Fraction(int(item.findtext('duration', '0')), divisions)
                    require(duration > 0, 'positive native duration required')
                    chord = item.find('chord') is not None
                    start = previous if chord else cursor
                    if not chord:
                        previous = cursor; cursor += duration
                    if item.find('rest') is None:
                        pitch = item.find('pitch'); require(pitch is not None, 'pitched native note required')
                        step = pitch.findtext('step'); octave = int(pitch.findtext('octave'))
                        require(step is not None and step in 'CDEFGAB', 'native pitch step required')
                        midi = 12*(octave+1) + dict(C=0,D=2,E=4,F=5,G=7,A=9,B=11)[step] + int(pitch.findtext('alter','0'))
                        ties = {tie.get('type') for tie in item.findall('tie')}
                        segments.append({'midi':midi, 'start':measure_start+start, 'end':measure_start+start+duration,
                                         'voice':(part.get('id'),item.findtext('voice','1'),item.findtext('staff','1')),
                                         'start_tie':'start' in ties, 'stop_tie':'stop' in ties})
                furthest = max(furthest, cursor)
            measure_start += furthest if measure.get('implicit') == 'yes' else max(nominal, furthest)
    require(0 < len(segments) <= 10000, 'bounded native note segments required')
    events, active = [], {}
    for n in sorted(segments, key=lambda n:(n['start'],n['voice'],n['midi'])):
        key = (*n['voice'],n['midi'])
        if n['stop_tie']:
            require(key in active and active[key]['end'] == n['start'], 'native tied continuation must be contiguous')
            active[key]['end'] = n['end']
            if not n['start_tie']:
                events.append(active.pop(key))
        elif n['start_tie']:
            require(key not in active, 'duplicate native tie start'); active[key] = dict(n)
        else:
            events.append(n)
    require(not active, 'unclosed native ties')
    events.sort(key=lambda n:(n['start'],n['midi']))
    return {'events':[[n['midi'],str(n['start']),str(n['end'])] for n in events], 'meters':meters,
            'note_segments':len(segments), 'parts':len(parts), 'xml_bytes':len(raw), 'sha256':sha(path)}


def fixture_checks(here):
    manifest = json.loads((here/'fixtures/manifest.json').read_text())
    require(manifest['license'] == 'CC0-1.0' and len(manifest['cases']) == 2, 'two reviewed CC0 cases required')
    for case in manifest['cases']:
        for key in ('wav','reference_midi'):
            p = here/'fixtures'/case[key]['file']
            require(p.parent == here/'fixtures' and p.is_file() and p.stat().st_size == case[key]['bytes']
                    and sha(p) == case[key]['sha256'], 'fixture bytes differ: '+case[key]['file'])
        with wave.open(str(here/'fixtures'/case['wav']['file']), 'rb') as wav:
            require((wav.getnchannels(),wav.getsampwidth(),wav.getframerate(),wav.getnframes()) == (2,2,44100,352800), 'actual sampled 8 s stereo WAV required')
        require(read_smf(here/'fixtures'/case['reference_midi']['file'])['events'] == case['events'], 'reference MIDI differs from reviewed events')
    return manifest


def ctest_check(path):
    text = Path(path).read_text(encoding='utf-8-sig', errors='replace')
    require(re.findall(r'(?m)^(?:\d+:\s*)?PASS (.+?)\s*$', text) == GROUPS, 'all nine reviewed native test groups must pass exactly once')
    require(len(re.findall(r'(?m)^(?:\d+:\s*)?ALL TESTS PASSED\s*$', text)) == 1
            and '100% tests passed, 0 tests failed out of 1' in text, 'native CTest success required')
    return {'passed':True,'groups':GROUPS,'groups_observed':9,'ctest_tests_observed':1,'log_sha256':sha(path)}


def clean_environment(executable):
    env = dict(os.environ); removed = []
    for name in list(env):
        if re.match(r'^(QT|QML|CMAKE_|VCPKG_|VSCMD_|VSINSTALLDIR$|VCINSTALLDIR$|VCTools|INCLUDE$|LIB$|LIBPATH$|WindowsSdk|WindowsSDK|UniversalCRTSdkDir$|UCRTVersion$|DevEnvDir$|ExtensionSdkDir$|FrameworkDir|FrameworkVersion|GH_TOKEN$|GITHUB_TOKEN$)', name, re.I):
            removed.append(name); del env[name]
    env['PATH'] = str(executable.parent) + ';' + str(Path(os.environ['SystemRoot'])/'System32')
    return env, sorted(removed)


def run_qualification(args):
    require(os.name == 'nt' and struct.calcsize('P') == 8 and os.environ.get('GITHUB_ACTIONS') == 'true'
            and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted', 'disposable native Windows x64 GitHub CI required')
    require(os.environ.get('CADENCE_AUDIO_QA_OWNED_JOB') == str(os.getppid()), 'owned Job controller wrapper is required')
    here = Path(__file__).resolve().parent; output = args.output.resolve(); temporary = Path(os.environ['RUNNER_TEMP']).resolve()
    require(output.is_relative_to(temporary) and not output.exists(), 'new owned output below RUNNER_TEMP required')
    output.mkdir()
    report = {'schema_version':1,'status':'running','passed':False,'commands':[],'cases':[], 'errors':[],
              'downloads':False,'GUI_tested':False,'human_listening':False,'application_may_write_own_cadence_profile':True}
    try:
        manifest = fixture_checks(here); report['ctest'] = ctest_check(args.ctest_log)
        exe = args.executable.resolve(strict=True); engine = args.engine_executable.resolve(strict=True)
        state = json.loads(args.build_state.read_text(encoding='utf-8-sig'))
        result = json.loads(args.build_result.read_text(encoding='utf-8-sig'))
        expected = args.expected_executable_sha256
        require(re.fullmatch('[0-9a-f]{64}',expected) is not None and sha(exe) == expected == result['executable_sha256'], 'new stage EXE differs from authenticated build result')
        require(state['variant'] == 'Cadence' and state['build_number'] == 2008 and state['source_commit'] == result['source_commit']
                and not state['source_dirty_at_configure'] and not result['source_dirty_at_build'], 'exact clean Cadence2008 build state required')
        require(Path(result['executable']).resolve() == exe and Path(state['install_path']).resolve()/'bin'/'CadenceStudio4.exe' == exe, 'current build/stage executable paths differ')
        report.update(executable_sha256=expected,engine_executable_sha256=sha(engine),source_commit=state['source_commit'],build_number=2008)
        source = Path(state['source_path']).resolve()
        receipt = json.loads(args.engine_build_receipt.read_text(encoding='utf-8-sig'))
        require(receipt['source_commit'] == state['source_commit'] and receipt['engine_executable_sha256'] == sha(engine), 'engine binary/source identity differs from actual CMake receipt')
        report['engine_sources'] = {rel:sha(source/rel) for rel in ('src/importexport/audiotranscription/audiotranscription.cpp','src/importexport/audiotranscription/audiotranscription.h','test/cadence/audio_transcription/test_audiotranscription.cpp')}
        require(report['engine_sources'] == receipt['production_sources'], 'production engine sources changed after standalone compilation')
        report['engine_build_receipt_sha256'] = sha(args.engine_build_receipt)
        env, removed = clean_environment(exe); report['child_sdk_environment_removed_names'] = removed; report['child_path'] = env['PATH']
        def run(name, argv, is_application=False):
            row = {'name':name,'arguments':list(map(str,argv)),'exit_code':None,'timed_out':False,'application':is_application}
            report['commands'].append(row); start = time.monotonic()
            with (output/(name+'.stdout.log')).open('xb') as stdout,(output/(name+'.stderr.log')).open('xb') as stderr:
                p = subprocess.Popen(row['arguments'],env=env,cwd=output,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW)
                row['pid'] = p.pid
                try:
                    row['exit_code'] = p.wait(timeout=180 if is_application else 45)
                except subprocess.TimeoutExpired:
                    row['timed_out'] = True
                    # The controller drains the exact Job, including descendants,
                    # after this script exits. Never search/kill processes by name.
                    p.kill(); row['exit_code'] = p.wait(timeout=15)
            row['seconds'] = round(time.monotonic()-start,3)
            require(row['exit_code'] == 0 and not row['timed_out'], 'command failed: '+name)
        for case in manifest['cases']:
            folder = output/case['id']; folder.mkdir()
            source_wav = here/'fixtures'/case['wav']['file']; original_sha = sha(source_wav)
            copied = folder/'melody-copy.wav'; shutil.copyfile(source_wav,copied)
            midi = folder/'draft.mid'
            run(case['id']+'-native-engine',[engine,copied,midi])
            musical = read_smf(midi); require(musical['events'] == case['events'] and sha(midi) == case['reference_midi']['sha256'], 'Windows native engine differs from reviewed musical MIDI')
            midi_sha = sha(midi); score = folder/'Partition importée.mscz'; xml = folder/'Réouverture.musicxml'; pdf = folder/'Réouverture.pdf'
            run(case['id']+'-new-app-midi-import',[exe,'--test-mode','--midi-operations',here/'midi-operations.xml','-o',score,midi],True)
            with zipfile.ZipFile(score) as z:
                require(z.testzip() is None and 'META-INF/container.xml' in z.namelist() and sum(m.file_size for m in z.infolist()) < 8*1024*1024, 'native MSCZ container invalid')
            score_sha = sha(score)
            run(case['id']+'-new-app-native-reopen-xml',[exe,'--test-mode','-o',xml,score],True)
            facts = read_musicxml(xml)
            expected_events = [[p,str(Fraction(start,480)),str(Fraction(end,480))] for p,start,end in case['events']]
            row = {'id':case['id'],'midi':musical,'expected_native_events_quarters':expected_events,'native_musicxml':facts,
                   'exact_native_pitches_and_timing':facts['events'] == expected_events,'WAV_source_unchanged':sha(source_wav)==original_sha,
                   'WAV_working_copy_unchanged':sha(copied)==original_sha,'MIDI_unchanged_by_import':sha(midi)==midi_sha}
            report['cases'].append(row)
            run(case['id']+'-new-app-native-reopen-pdf',[exe,'--test-mode','-o',pdf,score],True)
            row.update(native_score_sha256=score_sha,native_score_unchanged_after_reopens=sha(score)==score_sha,pdf_sha256=sha(pdf),pdf_bytes=pdf.stat().st_size)
            require(pdf.stat().st_size > 100 and pdf.read_bytes()[:5] == b'%PDF-', 'native reopened PDF missing')
            require(row['exact_native_pitches_and_timing'] and row['WAV_source_unchanged'] and row['WAV_working_copy_unchanged']
                    and row['MIDI_unchanged_by_import'] and row['native_score_unchanged_after_reopens'], 'real import/reopen musical or preservation comparison differs')
        report['executable_unchanged'] = sha(exe) == expected
        require(len(report['cases']) == 2 and len(report['commands']) == 8 and report['executable_unchanged'], 'two complete engine + native-import + reopen cases required')
        report['passed'] = True; report['status'] = 'passed-Windows2008-native-WAV-engine-and-real-MIDI-import-reopen'
    except Exception as error:
        report['errors'].append(str(error)); report['status'] = 'failed-or-blocked'
    finally:
        (output/'audio-transcription-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print('CADENCE_AUDIO_TRANSCRIPTION_REPORT_BEGIN'); print(json.dumps(report,ensure_ascii=False,separators=(',',':'))); print('CADENCE_AUDIO_TRANSCRIPTION_REPORT_END')
    return 0 if report['passed'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validate-only',action='store_true')
    for name in ('executable','engine-executable','ctest-log','build-state','build-result','engine-build-receipt','output'):
        parser.add_argument('--'+name,type=Path)
    parser.add_argument('--expected-executable-sha256')
    args = parser.parse_args()
    if args.validate_only:
        cases = fixture_checks(Path(__file__).resolve().parent)['cases']
        print(json.dumps({'status':'passed-fixture-structure-and-reference-SMF-only','cases':len(cases),'application_executed':False}))
        return 0
    require(all(getattr(args,n.replace('-','_')) is not None for n in ('executable','engine-executable','ctest-log','build-state','build-result','engine-build-receipt','output','expected-executable-sha256')), 'all runtime options required')
    return run_qualification(args)

if __name__ == '__main__':
    raise SystemExit(main())
