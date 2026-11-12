#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Source-only preparation of native SF2 CLI qualification on retained build2005.

Generated two-bar MusicXML exercises are original CC0-1.0 test data. All scores,
WAVs, banks and stage bytes stay under RUNNER_TEMP. The enclosing PowerShell Job
owns every child and must prove drainage before the separate profile cleanup.
This script does not compile/install the app, register plugins, or play audio.
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
import shutil
import stat
import struct
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

ARCHIVE = 'CadenceStudio-v4.7.6-combined-system-aac-stage-build-2005-attempt-1-x64.zip'
ARCHIVE_SHA = '4707aea7e6f0f63361ced55edfff7c7cf591f15463f9219263bfac4de3f96f9b'
EXE_SHA = 'd957ffc99497cb01b1f00f82ba1d6e89ef84547708506c6c51423675805e140a'
BASIC_SHA = '5ea2375e8bd7d8e71def1036978c1621e85b66934169b6a2744b27b9b3c2d99c'
PROFILE_SHA = '60b6bb2353467cf338e2c671151af37d3fd36d76748e52cda6a1e3ab22c4c27c'
SOURCE = '961c80b235d413dc9d123ea8f669ddb7f84ecd09'
TREE = 'c4780f1487559744fd4b2c2040b86ac37bb8c67b'
EXPECTED_BANKS = {
    'Cadence-VSCO-Flute.sf2': ('flute', 73, 0),
    'Cadence-VSCO-Violin.sf2': ('violin', 40, 0),
    'Cadence-VSCO-Flute-minus18.sf2': ('flute', 73, -18),
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


def restore_stage(artifact, stage):
    archive = artifact / ARCHIVE
    no_links(archive)
    if not archive.is_file() or sha(archive) != ARCHIVE_SHA or stage.exists():
        raise ValueError('Exact original full2005 stage ZIP and new stage required')
    with zipfile.ZipFile(archive) as source:
        rows = source.infolist()
        if len(rows) > 10000 or sum(row.file_size for row in rows) > 2 * 1024**3:
            raise ValueError('Stage archive exceeds reviewed extraction bounds')
        seen = set()
        planned = []
        for row in rows:
            relative = relative_member(row.filename)
            folded = str(relative).casefold()
            if folded in seen or row.file_size > 512 * 1024**2 or ((row.external_attr >> 16) & 0o170000) == 0o120000:
                raise ValueError('Duplicate, linked or oversized stage member')
            seen.add(folded)
            planned.append((row, stage.joinpath(*relative.parts)))
        stage.mkdir()
        for row, target in planned:
            no_links(target)
            if row.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with source.open(row) as incoming, target.open('xb') as outgoing:
                shutil.copyfileobj(incoming, outgoing, 1024 * 1024)
    executable = stage / 'bin/CadenceStudio4.exe'
    if sha(executable) != EXE_SHA:
        raise ValueError('Restored original executable differs')
    return executable


def load_profile_helper():
    path = Path(__file__).with_name('CadenceProfileScope.py')
    if sha(path) != PROFILE_SHA:
        raise ValueError('Pinned profile-scope helper differs')
    spec = importlib.util.spec_from_file_location('cadence_vsco_profile_scope', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validate_banks(root):
    manifest = json.loads((root / 'banks-manifest.json').read_text(encoding='utf-8'))
    if manifest.get('schema_version') != 1 or manifest.get('status') != 'built-pinned-vsco-sf2':
        raise ValueError('Built pinned VSCO SF2 manifest required')
    rows = manifest.get('banks', [])
    if len(rows) != 3 or {row.get('file') for row in rows} != set(EXPECTED_BANKS):
        raise ValueError('Exactly the three reviewed SF2 banks required')
    for row in rows:
        instrument, program, gain = EXPECTED_BANKS[row['file']]
        path = root / row['file']
        no_links(path)
        name = path.stem
        if (row.get('instrument') != instrument or row.get('program') != program or row.get('bank') != 0
                or row.get('gain_delta_db') != gain or row.get('soundfont_name') != name
                or row.get('resource_id') != name + '\\0\\' + str(program)
                or path.stat().st_size != row.get('bytes') or sha(path) != row.get('sha256')):
            raise ValueError('SF2 bank bytes or exact native preset identity differs')
    return manifest, {row['file']: row for row in rows}


def score_xml(instrument):
    program = 74 if instrument == 'flute' else 41  # MusicXML programs are one-based.
    notes = [('C', 5), ('D', 5), ('E', 5), ('G', 5)] if instrument == 'flute' else [('G', 4), ('A', 4), ('B', 4), ('D', 5)]
    measures = []
    for index in range(2):
        attributes = '<attributes><divisions>1</divisions><key><fifths>0</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes>' if index == 0 else ''
        body = ''.join(f'<note><pitch><step>{step}</step><octave>{octave}</octave></pitch><duration>1</duration><type>quarter</type></note>' for step, octave in notes)
        measures.append(f'<measure number="{index+1}">{attributes}{body}</measure>')
    return (f'<?xml version="1.0" encoding="utf-8"?><score-partwise version="4.0"><work><work-title>Original CC0 {instrument} SF2 probe</work-title></work>'
            f'<identification><rights>CC0-1.0; original generated QA exercise</rights></identification><part-list><score-part id="P1"><part-name>{instrument.title()}</part-name>'
            f'<score-instrument id="I1"><instrument-name>{instrument.title()}</instrument-name></score-instrument><midi-instrument id="I1"><midi-channel>1</midi-channel><midi-program>{program}</midi-program></midi-instrument>'
            f'</score-part></part-list><part id="P1">{"".join(measures)}</part></score-partwise>\n').encode('utf-8')


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


def assign_soundfont(base, target, instrument, bank=None):
    settings, score = native_data(base)
    parts = score.findall('./Score/Part')
    if len(parts) != 1 or len(parts[0].findall('Instrument')) != 1:
        raise ValueError('Exactly one real imported instrument required')
    part = parts[0]
    actual = part.find('Instrument')
    if not part.get('id') or not actual.get('id') or instrument not in actual.get('id').lower():
        raise ValueError('Imported native score does not identify the requested instrument family')
    name = bank['soundfont_name'] if bank else 'MS Basic'
    attributes = {'soundFontName': name, 'playbackSetupData': 'generic'}
    if bank:
        attributes.update(presetBank='0', presetProgram=str(bank['program']))
    requested = {'resourceMeta': {'id': bank['resource_id'] if bank else name, 'vendor': 'Fluid',
                                 'type': 'fluid_soundfont', 'hasNativeEditorSupport': False, 'attributes': attributes},
                 'unitConfiguration': {}}
    track = {'partId': part.get('id'), 'instrumentId': actual.get('id'), 'in': requested,
             'out': {'balance': 0, 'volumeDb': 0, 'fxChain': {}, 'auxSends': []},
             'soloMuteState': {'mute': False, 'solo': False}}
    settings.update(activeSoundProfile='MuseScore Basic', tracks=[track],
                    master={'balance': 0, 'volumeDb': -12, 'fxChain': {}, 'auxSends': []}, aux=[])
    with zipfile.ZipFile(base) as source, zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_DEFLATED) as destination:
        for row in source.infolist():
            destination.writestr(row, json.dumps(settings, ensure_ascii=False).encode('utf-8') if row.filename == 'audiosettings.json' else source.read(row))
    return track


def inspect_wav(path):
    if path.stat().st_size > 128 * 1024**2:
        raise ValueError('WAV exceeds 128 MiB')
    with path.open('rb') as stream:
        header = stream.read(12)
        if header[:4] != b'RIFF' or header[8:] != b'WAVE':
            raise ValueError('RIFF/WAVE required')
        fmt = data = None
        while header := stream.read(8):
            if len(header) != 8:
                raise ValueError('Truncated WAV chunk')
            tag, size = struct.unpack('<4sI', header)
            offset = stream.tell()
            if offset + size > path.stat().st_size:
                raise ValueError('WAV chunk exceeds file')
            if tag == b'fmt ':
                if not 16 <= size <= 1024:
                    raise ValueError('Invalid WAV format size')
                fmt = struct.unpack('<HHIIHH', stream.read(16))
            elif tag == b'data':
                if data is not None:
                    raise ValueError('Multiple WAV data chunks refused')
                data = (offset, size)
            stream.seek(offset + size + (size & 1))
        if fmt is None or data is None:
            raise ValueError('WAV format/data missing')
        encoding, channels, rate, byte_rate, align, bits = fmt
        if (encoding, bits) not in {(1, 16), (1, 24), (1, 32), (3, 32), (3, 64)}:
            raise ValueError('Unsupported WAV sample encoding')
        width = bits // 8
        if channels != 2 or rate < 8000 or align != channels * width or byte_rate != rate * align or not data[1] or data[1] % align:
            raise ValueError('WAV frame format/length is invalid')
        stream.seek(data[0]); remaining = data[1]
        count = full_scale = nonfinite = 0
        squared = peak = 0.0
        while remaining:
            payload = stream.read(min(align * 4096, remaining))
            if not payload:
                raise ValueError('Truncated WAV samples')
            remaining -= len(payload)
            values = (row[0] for row in struct.iter_unpack('<f' if bits == 32 else '<d', payload)) if encoding == 3 else (int.from_bytes(payload[i:i+width], 'little', signed=True) / 2**(bits-1) for i in range(0, len(payload), width))
            for value in values:
                count += 1
                if not math.isfinite(value):
                    nonfinite += 1
                    continue
                amplitude = abs(value); peak = max(peak, amplitude); squared += value * value
                full_scale += amplitude >= (1.0 if encoding == 3 else (2**(bits-1)-1)/2**(bits-1))
        rms = math.sqrt(squared / count)
        duration = data[1] / byte_rate
        return {'encoding': encoding, 'bits': bits, 'channels': channels, 'sample_rate': rate,
                'duration_seconds': duration, 'rms': rms, 'peak': peak, 'nonfinite_samples': nonfinite,
                'full_scale_samples': full_scale, 'passed': rms > 1e-6 and not nonfinite and not full_scale and 1 <= duration <= 60}


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


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ('artifact', 'stage', 'banks', 'profile-record', 'output'):
        parser.add_argument('--' + argument, type=Path, required=True)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if (os.name != 'nt' or platform.machine().lower() not in ('amd64', 'x86_64')
            or os.environ.get('CI') != 'true' or os.environ.get('GITHUB_ACTIONS') != 'true'
            or os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted'):
        raise ValueError('Only disposable native Windows x64 GitHub-hosted CI may run this qualification')
    artifact, stage, banks, output = [owned(path) for path in (args.artifact, args.stage, args.banks, args.output)]
    roots = (artifact, stage, banks, output)
    if len(set(roots)) != 4 or any(left in right.parents for left in roots for right in roots if left != right) or output.exists():
        raise ValueError('Four distinct independent runtime roots and new output required')
    profile_path = owned(args.profile_record)
    profile_helper = load_profile_helper()
    profile = profile_helper.verify_record(profile_path)  # Check markers before changing the owned seed.
    manifest, bank_rows = validate_banks(banks)
    output.mkdir()
    report = {'schema_version': 1, 'status': 'running', 'build_number': 2005, 'source_commit': SOURCE, 'source_tree': TREE,
              'stage_archive_sha256': ARCHIVE_SHA, 'executable_sha256': EXE_SHA, 'banks_manifest': manifest,
              'profile_owner': profile['owner'], 'commands': [], 'cases': [], 'error': None,
              'native_SF2_loader_used': True, 'SFZ_or_VST_loader_used': False, 'application_recompiled': False,
              'gain_compensation_scope': {'target': 'Retained Cadence FluidSynth 2.3.3',
                                          'EMU_ATTENUATION_FACTOR': 0.4, 'raw_attenuation_units_per_db': 25,
                                          'minus18_raw_generator_delta': 450,
                                          'portable_gain_across_other_SF2_engines_claimed': False},
              'physical_playback_or_listening_tested': False, 'GUI_save_after_live_playback_tested': False,
              'cleanup_requires_enclosing_owned_Job_drain': True, 'generated_exercise_license': 'CC0-1.0'}
    try:
        executable = restore_stage(artifact, stage)
        basic = list(stage.rglob('MS Basic.sf3'))
        if len(basic) != 1 or sha(basic[0]) != BASIC_SHA:
            raise ValueError('The retained MS Basic positive control is missing or differs')
        ini = Path(profile['settings_file'])
        no_links(ini)
        ini.write_text('[application]\nhasCompletedFirstLaunchSetup=true\npaths\\mySoundfonts=' + banks.as_posix() + '\n\n[io]\naudioApi=WASAPI\noutputDevice=\nbufferSize=256\nsampleRate=48000\n', encoding='utf-8')
        report['owned_settings_sha256'] = sha(ini)
        env = {key: value for key, value in os.environ.items() if not key.startswith(('QT_', 'QML_', 'CADENCE_QA_CLOCK'))}
        env['PATH'] = str(executable.parent) + ';' + str(Path(os.environ['SystemRoot']) / 'System32')
        logs = Path(profile['log_root'])

        def run(name, arguments):
            before = snapshot(logs)
            row = {'name': name, 'arguments': [str(executable), *map(str, arguments)], 'pid': None, 'exit_code': None, 'timed_out': False}
            report['commands'].append(row)
            started = time.monotonic()
            with (output / (name + '.stdout.txt')).open('xb') as stdout, (output / (name + '.stderr.txt')).open('xb') as stderr:
                process = subprocess.Popen(row['arguments'], cwd=output, env=env, stdout=stdout, stderr=stderr, creationflags=subprocess.CREATE_NO_WINDOW)
                row['pid'] = process.pid
                try:
                    row['exit_code'] = process.wait(timeout=90)
                except subprocess.TimeoutExpired:
                    row['timed_out'] = True
                    process.kill()
                    row['exit_code'] = process.wait(timeout=10)
                finally:
                    if process.poll() is None:
                        process.kill(); process.wait(timeout=10)
            row['seconds'] = time.monotonic() - started
            after = snapshot(logs)
            delta = b'\n'.join(data[len(before.get(key, b'')):] if data.startswith(before.get(key, b'')) else data for key, data in after.items()).decode('utf-8', errors='replace')
            (output / (name + '.cadence-log-delta.txt')).write_text(delta, encoding='utf-8')
            text = delta
            for suffix in ('stdout', 'stderr'):
                path = output / (name + '.' + suffix + '.txt')
                if path.stat().st_size > 16 * 1024**2:
                    raise RuntimeError('Application transcript exceeds its bound')
                text += '\n' + path.read_text(encoding='utf-8', errors='replace')
            if row['timed_out'] or row['exit_code'] != 0:
                raise RuntimeError('Native CLI command failed: ' + name)
            return text

        bases = {}
        exercise_hashes = {}
        for instrument in ('flute', 'violin'):
            exercise = output / (instrument + '-original.musicxml')
            exercise.write_bytes(score_xml(instrument))
            exercise_hashes[instrument] = sha(exercise)
            base = output / (instrument + '-imported-base.mscz')
            run(instrument + '-import', ['-o', base, exercise])
            bases[instrument] = base
        cases = [('basic-flute', 'flute', None), ('flute', 'flute', 'Cadence-VSCO-Flute.sf2'),
                 ('flute-minus18', 'flute', 'Cadence-VSCO-Flute-minus18.sf2'),
                 ('basic-violin', 'violin', None), ('violin', 'violin', 'Cadence-VSCO-Violin.sf2')]
        by_name = {}
        for label, instrument, filename in cases:
            native = output / (label + '.mscz')
            requested = assign_soundfont(bases[instrument], native, instrument, bank_rows[filename] if filename else None)
            native_sha = sha(native)
            row = {'name': label, 'instrument': instrument, 'requested_track': requested,
                   'source_sha256': native_sha, 'source_unchanged': False, 'resource_preserved_on_save': False}
            report['cases'].append(row)
            wav = output / (label + '.wav')
            diagnostics = run(label + '-render', ['-o', wav, native])
            row['audio'] = inspect_wav(wav); row['wav_sha256'] = sha(wav)
            resource = requested['in']['resourceMeta']['id']
            if ('Not found: ' + resource in diagnostics or 'Failed parse SoundFont presets for' in diagnostics
                    or not row['audio']['passed']):
                raise RuntimeError('Native SF2 lookup, parser or nonmute WAV check failed: ' + label)
            saved = output / (label + '-save-only.mscz')
            run(label + '-save-only', ['-o', saved, native])
            row['resource_preserved_on_save'] = input_preserved(saved, requested)
            reopened_wav = output / (label + '-reopened.wav')
            reopened_diagnostics = run(label + '-reopen-render', ['-o', reopened_wav, saved])
            row['reopened_audio'] = inspect_wav(reopened_wav)
            row['reopened_wav_sha256'] = sha(reopened_wav)
            row['source_unchanged'] = sha(native) == native_sha
            if (not row['resource_preserved_on_save'] or not row['reopened_audio']['passed'] or not row['source_unchanged']
                    or 'Not found: ' + resource in reopened_diagnostics):
                raise RuntimeError('Saved native SF2 identity, reloaded render or immutable source check failed: ' + label)
            by_name[label] = row
        normal, quiet = by_name['flute'], by_name['flute-minus18']
        expected = 10**(-18 / 20)
        ratio = quiet['audio']['rms'] / normal['audio']['rms']
        reopened_ratio = quiet['reopened_audio']['rms'] / normal['reopened_audio']['rms']
        shape = all(normal['audio'][key] == quiet['audio'][key] for key in ('encoding', 'bits', 'channels', 'sample_rate', 'duration_seconds'))
        proof = {'expected_gain_delta_db': -18, 'expected_rms_ratio': expected, 'actual_rms_ratio': ratio,
                 'reopened_rms_ratio': reopened_ratio, 'relative_tolerance': 0.03, 'matching_WAV_shape': shape,
                 'gain_matches': abs(ratio / expected - 1) <= .03 and abs(reopened_ratio / expected - 1) <= .03,
                 'flute_differs_from_MS_Basic': normal['wav_sha256'] != by_name['basic-flute']['wav_sha256'],
                 'violin_differs_from_MS_Basic': by_name['violin']['wav_sha256'] != by_name['basic-violin']['wav_sha256']}
        report['native_SF2_load_gain_control'] = proof
        if not shape or not all(proof[key] for key in ('gain_matches', 'flute_differs_from_MS_Basic', 'violin_differs_from_MS_Basic')):
            raise RuntimeError('Controlled SF2 gain or mandatory positive-control distinction failed; nonmute fallback is not accepted')
        report['inputs_unchanged'] = (sha(executable) == EXE_SHA and sha(basic[0]) == BASIC_SHA
                                      and all(sha(banks / row['file']) == row['sha256'] for row in manifest['banks'])
                                      and all(sha(output / (key + '-original.musicxml')) == value for key, value in exercise_hashes.items()))
        if not report['inputs_unchanged']:
            raise RuntimeError('An input bank, program, supplied soundfont or generated original exercise changed')
        report['status'] = 'passed_native_SF2_render_gain_and_save_reload'
    except Exception as error:
        report['status'] = 'failed_or_blocked'; report['error'] = str(error)
    finally:
        (output / 'vsco-sf2-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print('CADENCE_VSCO_SF2_REPORT_BEGIN'); print(json.dumps(report, ensure_ascii=False)); print('CADENCE_VSCO_SF2_REPORT_END')
    return 0 if report['status'] == 'passed_native_SF2_render_gain_and_save_reload' else 1


if __name__ == '__main__':
    raise SystemExit(main())
