#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Read a retained Cadence build, exercise only generated CC0 score copies.

No resource is uninstalled, no plugin is loaded or downloaded. This is CLI QA,
not GUI acknowledgement, listening or save-after-playback persistence proof.
"""
from __future__ import annotations
import argparse
import base64
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

# A byte-identical existing corpus checker is loaded by exact local path below.

EXE_HASH = '35d8b076cacddb8b37a4f23aeea9899e6ab4ac9214e9a5b1125bbeccf26cf39e'
FIXTURE_HASH = '10ae5eb1fae2679d9ad32aa0b721fef06119ef24b78b4f8b9bd6b770582c289f'
BASIC_HASH = '5ea2375e8bd7d8e71def1036978c1621e85b66934169b6a2744b27b9b3c2d99c'
SOURCE = '0e05d04acbeee32f1b561f24493d7ef41c322081'
TREE = 'f95b7097a55dddf9c7f697fc826b95721071231a'
MISSING_SF = 'Cadence-QA-Missing-SF-74bc3d1a'
MISSING_VST = 'Cadence-QA-Missing-VST-b46213b9'


def sha(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require_below(path: Path, root: Path):
    path = path.resolve()
    if path == root or root not in path.parents:
        raise ValueError('Every runtime path must be strictly under RUNNER_TEMP')
    p = path
    while p != p.parent:
        if p.exists() and (p.is_symlink() or getattr(p, 'is_junction', lambda: False)()):
            raise ValueError('Runtime paths must contain no reparse points')
        p = p.parent
    return path


def read_audio(path: Path) -> dict:
    with zipfile.ZipFile(path) as z:
        if len(z.namelist()) > 256 or len(set(z.namelist())) != len(z.namelist()):
            raise ValueError('Unexpected native fixture ZIP members')
        return json.loads(z.read('audiosettings.json'))


def make_case(base: Path, output: Path, meta: dict) -> dict:
    """Inject the real serialized resource fields on a controlled piano copy."""
    with zipfile.ZipFile(base) as z:
        score_names = [n for n in z.namelist() if n.endswith('.mscx') and '/' not in n]
        if len(score_names) != 1:
            raise ValueError('Expected exactly one master MSCX in the CC0 native copy')
        root = ET.fromstring(z.read(score_names[0]))
        parts = root.findall('./Score/Part')
        if len(parts) != 1 or parts[0].get('id') != '1' or parts[0].find('Instrument').get('id') != 'piano':
            raise ValueError('The injected audio track must match the real piano Part/Instrument identifiers')
        settings = read_audio(base)
        settings['activeSoundProfile'] = 'MuseScore Basic'
        settings['tracks'] = [{
            'partId': '1', 'instrumentId': 'piano',
            'in': {'resourceMeta': meta, 'unitConfiguration': {
                'cadenceQaOpaqueState': base64.b64encode(b'QA-only-not-a-plugin-state').decode('ascii')}},
            'out': {'balance': 0, 'volumeDb': 0, 'fxChain': {}, 'auxSends': []},
            'soloMuteState': {'mute': False, 'solo': False},
        }]
        with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as dst:
            for info in z.infolist():
                if info.file_size > 8388608 or info.filename.startswith('/') or '..' in Path(info.filename).parts:
                    raise ValueError('Unsafe or oversized generated native fixture member')
                dst.writestr(info, json.dumps(settings, ensure_ascii=False, indent=2).encode() if info.filename == 'audiosettings.json' else z.read(info))
    if read_audio(output) != settings:
        raise ValueError('Synthetic audio identity was not written exactly')
    return settings


def log_snapshot(log_root: Path) -> dict:
    result = {}
    if not log_root.is_dir():
        return result
    logs = list(log_root.rglob('*.log'))
    if len(logs) > 32:
        raise ValueError('Cadence log file count exceeds the fresh-profile bound')
    for path in logs:
        if path.is_symlink() or path.stat().st_size > 16777216:
            raise ValueError('Unsafe or oversized Cadence log')
        result[str(path)] = path.read_bytes()
    return result


def log_delta(before: dict, after: dict) -> str:
    chunks = []
    for name, data in after.items():
        old = before.get(name, b'')
        chunks.append(data[len(old):] if data.startswith(old) else data)
    return b'\n'.join(chunks).decode('utf-8', errors='replace')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', required=True, type=Path)
    parser.add_argument('--restoration-record', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    # These guards precede file creation, executable invocation and profile reads.
    if os.name != 'nt' or platform.machine().lower() not in ('amd64', 'x86_64') or \
        os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('CI') != 'true' or \
        os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted':
        raise SystemExit('Only disposable native Windows x64 GitHub-hosted runners are permitted')
    root = Path(os.environ['RUNNER_TEMP']).resolve()
    stage = require_below(args.stage, root)
    output = require_below(args.output, root)
    record_path = require_below(args.restoration_record, root)
    if output.exists() or stage in output.parents or output in stage.parents:
        raise ValueError('Output must be new and separate from the unchanged stage')
    record = json.loads(record_path.read_text(encoding='utf-8-sig'))
    executable = stage / 'bin/CadenceStudio4.exe'
    fixture = Path(__file__).parent / 'fixtures/piano.mscx'
    soundfonts = list(stage.rglob('MS Basic.sf3'))
    if len(soundfonts) != 1:
        raise ValueError('Expected exactly one included MS Basic.sf3 in the authenticated stage')
    basic = soundfonts[0]
    if record.get('original_source_commit') != SOURCE or record.get('source_tree') != TREE or record.get('build_number') != 2002 or \
        record.get('executable_sha256') != EXE_HASH or Path(record['executable_path']).resolve() != executable or \
        sha(executable) != EXE_HASH or sha(fixture) != FIXTURE_HASH or sha(basic) != BASIC_HASH:
        raise ValueError('The retained stage, source, fixture or included MS Basic differs from the pins')
    profile_local = Path(os.environ['LOCALAPPDATA']) / 'CadenceStudio'
    profile_roaming = Path(os.environ['APPDATA']) / 'CadenceStudio'
    if profile_local.exists() or profile_roaming.exists():
        raise ValueError('This test requires a fresh Cadence-only profile; existing data is never removed')
    checker = Path(__file__).with_name('corpus_run_exports.py')
    if sha(checker) != 'f701874e7a37b8d3148f0bb99477b60b96865e804ed238372d75c06598027d82':
        raise ValueError('The reused corpus WAV checker changed')
    spec = importlib.util.spec_from_file_location('cadence_corpus_run_exports', checker)
    checker_module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = checker_module
    spec.loader.exec_module(checker_module)
    inspect_wav = checker_module.inspect_wav
    output.mkdir()
    report = {
        'schema_version': 1, 'status': 'running', 'source_commit': SOURCE, 'source_tree': TREE,
        'retained_build_number': 2002, 'executable_sha256': EXE_HASH,
        'scope': 'CLI missing-SF resolver diagnostic and numerical export; synthetic VST-request export observation; save-only identity roundtrip',
        'commands': [], 'cases': [], 'fresh_cadence_profile_before_first_process': True,
        'human_listening_performed': False, 'gui_message_tested': False,
        'save_after_playback_in_same_project_tested': False, 'plugin_installation_performed': False,
        'source_resources_removed': False, 'network_block_tested': False,
        'error': None, 'identity_failures': [],
    }
    env = os.environ.copy()
    env['PATH'] = str(executable.parent) + ';' + str(Path(os.environ['SystemRoot'])/'System32')
    logs = profile_local / 'CadenceStudio4/logs'

    def run(name: str, arguments: list[str]):
        before = log_snapshot(logs)
        command = [str(executable), *map(str, arguments)]
        out_file, err_file = output/f'{name}.stdout.txt', output/f'{name}.stderr.txt'
        started = time.monotonic()
        item = {'name': name, 'arguments': command, 'timeout_seconds': 90, 'pid': None,
                'exit_code': None, 'timed_out': False, 'owned_process_terminated': False}
        report['commands'].append(item)
        with out_file.open('xb') as out_stream, err_file.open('xb') as err_stream:
            proc = subprocess.Popen(command, stdout=out_stream, stderr=err_stream, env=env,
                                    cwd=output, creationflags=subprocess.CREATE_NO_WINDOW)
            item['pid'] = proc.pid
            try:
                item['exit_code'] = proc.wait(timeout=90)
            except subprocess.TimeoutExpired:
                item['timed_out'] = True
                proc.kill()  # The exact child handle created above, no name lookup or tree kill.
                item['owned_process_terminated'] = True
                item['exit_code'] = proc.wait(timeout=10)
        item['duration_seconds'] = time.monotonic()-started
        after = log_snapshot(logs)
        delta = log_delta(before, after)
        (output/f'{name}.cadence-log-delta.txt').write_text(delta, encoding='utf-8')
        item['new_log_bytes'] = len(delta.encode('utf-8'))
        if item['timed_out'] or item['exit_code'] != 0:
            raise RuntimeError(f'Owned command failed: {name}; inspect retained logs')
        return delta

    try:
        copied_fixture = output/'piano-source-copy.mscx'
        shutil.copyfile(fixture, copied_fixture)
        run('version', ['--long-version'])
        base = output/'piano-native-control.mscz'
        run('native-base', ['-o', base, copied_fixture])
        metas = [
            ('basic-control', {'id':'MS Basic','vendor':'Fluid','type':'fluid_soundfont','hasNativeEditorSupport':False,
                               'attributes':{'soundFontName':'MS Basic','playbackSetupData':'generic'}}),
            ('missing-soundfont', {'id':MISSING_SF,'vendor':'Fluid','type':'fluid_soundfont','hasNativeEditorSupport':False,
                                  'attributes':{'soundFontName':MISSING_SF,'playbackSetupData':'generic'}}),
            ('missing-vst', {'id':MISSING_VST,'vendor':'Cadence QA','type':'vst_plugin','hasNativeEditorSupport':False,
                            'attributes':{}}),
        ]
        for name, meta in metas:
            source = output/f'{name}.mscz'
            settings = make_case(base, source, meta)
            source_before = sha(source)
            case = {'name':name,'requested_resource':meta,'input_sha256':source_before,
                    'actual_input_audio_settings':settings,'save_only_identity_preserved':None,
                    'source_unchanged_after_each_operation':[], 'audio':None}
            report['cases'].append(case)
            native = output/f'{name}-save-only.mscz'
            run(name+'-save-only', ['-o', native, source])
            saved = read_audio(native)
            case['save_only_audio_settings'] = saved
            case['save_only_identity_preserved'] = any(t.get('partId') == '1' and t.get('instrumentId') == 'piano'
                and t.get('in') == settings['tracks'][0]['in'] for t in saved.get('tracks',[]))
            if not case['save_only_identity_preserved']:
                report['identity_failures'].append(name)
            case['source_unchanged_after_each_operation'].append(sha(source) == source_before)
            wav = output/f'{name}.wav'
            delta = run(name+'-wav', ['-o', wav, source])
            case['audio'] = inspect_wav(wav)
            case['wav_sha256'] = sha(wav)
            case['resource_id_present_in_export_log_delta'] = meta['id'] in delta
            case['fluid_not_found_diagnostic_seen'] = ('Not found: '+meta['id']) in delta
            case['vst_missing_module_diagnostic_seen'] = ('Unable to find vst plugin module, resourceId: '+meta['id']) in delta
            case['vst_resolver_execution_confirmed'] = None if name != 'missing-vst' else case['vst_missing_module_diagnostic_seen']
            case['runtime_observation'] = ('missing-SF resolver diagnostic plus WAV numerical result' if name == 'missing-soundfont'
                else 'WAV from synthetic VST-request score; VST resolver path unconfirmed unless explicit module diagnostic present' if name == 'missing-vst'
                else 'MS Basic control WAV')
            case['source_unchanged_after_each_operation'].append(sha(source) == source_before)
            if not case['audio']['passed']:
                raise RuntimeError('Missing-resource WAV is silent, nonfinite or saturated')
            if name == 'missing-soundfont' and not case['fluid_not_found_diagnostic_seen']:
                raise RuntimeError('The missing SF identity was not observed at the actual resolver; no fallback claim')
            if not all(case['source_unchanged_after_each_operation']):
                raise RuntimeError('A source copy changed during read/export')
        report['source_fixture_unchanged'] = sha(fixture) == FIXTURE_HASH and sha(copied_fixture) == FIXTURE_HASH
        report['executable_unchanged'] = sha(executable) == EXE_HASH
        report['included_ms_basic_unchanged'] = sha(basic) == BASIC_HASH
        if not all(report[k] for k in ('source_fixture_unchanged','executable_unchanged','included_ms_basic_unchanged')):
            raise RuntimeError('A retained source fixture/executable/MS Basic changed')
        if report['identity_failures']:
            raise RuntimeError('Resource identity/configuration changed during save-only roundtrip: '+', '.join(report['identity_failures']))
        report['status'] = 'passed_cli_missing_sf_checks_and_vst_export_observation'
    except Exception as error:
        report['status'] = 'failed_or_blocked'
        report['error'] = str(error)
    finally:
        (output/'missing-audio-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print('CADENCE_MISSING_AUDIO_REPORT_BEGIN')
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print('CADENCE_MISSING_AUDIO_REPORT_END')
    return 0 if report['status'] == 'passed_cli_missing_sf_checks_and_vst_export_observation' else 1


if __name__ == '__main__':
    raise SystemExit(main())
