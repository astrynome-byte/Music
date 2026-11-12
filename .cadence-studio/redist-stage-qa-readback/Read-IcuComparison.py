# SPDX-License-Identifier: GPL-3.0-only
"""Read only retained ICU experiment JSON/log/MXL data. Never run Cadence."""
import argparse
import collections
import hashlib
import io
import json
from pathlib import Path, PureWindowsPath
import re
import struct
import zipfile

EXE = 'd957ffc99497cb01b1f00f82ba1d6e89ef84547708506c6c51423675805e140a'
FIXTURES = {'piano', 'voice', 'guitar', 'percussion', 'ensemble'}
STABLE = {'export-mxl', 'export-svg', 'export-png', 'export-mid', 'export-wav', 'export-flac', 'export-mp3'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def plain_read(path, maximum):
    for node in (path, *path.parents):
        if node.is_symlink():
            raise ValueError('Symlink/reparse path refused')
    with path.open('rb') as stream:
        data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError('Data file exceeds bound: ' + path.name)
    return data


def read_json(path):
    raw = plain_read(path, 4 * 1024 * 1024)
    return json.loads(raw), {'file': path.name, 'bytes': len(raw), 'sha256': sha(raw)}


def report_map(path):
    report, receipt = read_json(path)
    checks = report.get('checks')
    if (report.get('executable_sha256') != EXE or type(report.get('version_exit_code')) is not int
            or report['version_exit_code'] != 0 or not isinstance(checks, list) or len(checks) != 57
            or any(type(row.get('passed')) is not bool or not row['passed'] for row in checks)):
        raise ValueError('The real 57-check report is incomplete or failed')
    result = {}
    stage_counts = collections.Counter()
    for row in checks:
        stage_counts[row['stage']] += 1
        if row['stage'] not in STABLE:
            continue
        if row['fixture'] not in FIXTURES:
            raise ValueError('Unknown fixture')
        for output in row['outputs']:
            filename = PureWindowsPath(output['path']).name
            if not re.fullmatch(r'[A-Za-z0-9_.-]{1,120}', filename) or filename in {'.', '..'}:
                raise ValueError('Unsafe output basename')
            key = (row['fixture'], row['stage'], filename)
            if key in result or not re.fullmatch(r'[a-f0-9]{64}', output.get('sha256', '')):
                raise ValueError('Duplicate or malformed retained output')
            if row['stage'] == 'export-wav' and output.get('audio', {}).get('passed') is not True:
                raise ValueError('Real existing numeric WAV gate failed')
            result[key] = output
    pair_counts = collections.Counter((key[0], key[1]) for key in result)
    expected_pairs = {(fixture, stage) for fixture in FIXTURES for stage in STABLE}
    contract = len(result) == 35 and pair_counts.keys() == expected_pairs and all(n == 1 for n in pair_counts.values())
    return result, {'receipt': receipt, 'checks_passed': 57, 'stable_outputs': len(result),
                    'expected_35_output_contract_satisfied': contract,
                    'stable_output_counts': [{'fixture': fixture, 'stage': stage, 'outputs': count} for (fixture, stage), count in sorted(pair_counts.items())],
                    'stages': dict(sorted(stage_counts.items()))}


def mxl_data(path, expected):
    raw = plain_read(path, 16 * 1024 * 1024)
    if sha(raw) != expected:
        raise ValueError('Retained MXL does not match its original report hash')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        if not 1 <= len(infos) <= 32 or sum(x.file_size for x in infos) > 16 * 1024 * 1024:
            raise ValueError('MXL member bounds exceeded')
        rows = []
        names = set()
        for entry in infos:
            if entry.filename in names or entry.flag_bits & 1 or not re.fullmatch(r'[A-Za-z0-9_./ -]{1,200}', entry.filename):
                raise ValueError('Unsafe or encrypted MXL member')
            names.add(entry.filename)
            values = struct.unpack_from('<4s5H3I2H', raw, entry.header_offset)
            if values[0] != b'PK\x03\x04':
                raise ValueError('Invalid local ZIP header')
            start = entry.header_offset + 30 + values[-2] + values[-1]
            finish = start + entry.compress_size
            if finish > len(raw):
                raise ValueError('Compressed member outside MXL')
            data = archive.read(entry)
            rows.append({'name': entry.filename, 'content_sha256': sha(data), 'bytes': len(data),
                         'compressed_payload_sha256': sha(raw[start:finish]), 'compressed_bytes': entry.compress_size,
                         'date_time': list(entry.date_time), 'CRC': entry.CRC, 'compression': entry.compress_type,
                         'extra_sha256': sha(entry.extra), 'comment_sha256': sha(entry.comment),
                         'flags': entry.flag_bits, 'internal_attr': entry.internal_attr, 'external_attr': entry.external_attr,
                         'create_system': entry.create_system, 'create_version': entry.create_version,
                         'extract_version': entry.extract_version})
        return {'archive_sha256': sha(raw), 'archive_comment_sha256': sha(archive.comment), 'members': rows}


def analyze(root):
    experiment, receipt = read_json(root / 'icu-omission-result.json')
    if (experiment.get('producer_run_id') != 43207550870 or experiment.get('producer_build') != 2005
            or experiment.get('status') != 'failed-or-blocked'
            or experiment.get('error') != 'Owned QA command failed: compare-existing-corpus'):
        raise ValueError('Unexpected experiment provenance or failure point')
    stderr = plain_read(root / 'compare-existing-corpus.stderr.log', 65536).decode('utf-8')
    maps = {}; reports = {}
    for side in ('baseline', 'without-local-icu'):
        maps[side], reports[side] = report_map(root / side / 'report.json')
    first, second = maps['baseline'], maps['without-local-icu']
    if first.keys() != second.keys():
        raise ValueError('The two retained report output identities differ')
    differences = []
    for key in sorted(first):
        if first[key]['sha256'] == second[key]['sha256']:
            continue
        fixture, stage, filename = key
        row = {'fixture': fixture, 'stage': stage, 'file': filename,
               'baseline_sha256': first[key]['sha256'], 'candidate_sha256': second[key]['sha256']}
        if stage == 'export-mxl':
            before = mxl_data(root / 'baseline' / fixture / filename, first[key]['sha256'])
            after = mxl_data(root / 'without-local-icu' / fixture / filename, second[key]['sha256'])
            row['MXL'] = {'baseline': before, 'candidate': after,
                          'same_member_names_and_content': [(x['name'], x['content_sha256']) for x in before['members']] == [(x['name'], x['content_sha256']) for x in after['members']],
                          'same_compressed_payloads': [(x['name'], x['compressed_payload_sha256']) for x in before['members']] == [(x['name'], x['compressed_payload_sha256']) for x in after['members']]}
        if stage == 'export-wav':
            row['numeric_WAV_baseline'] = first[key]['audio']
            row['numeric_WAV_candidate'] = second[key]['audio']
        differences.append(row)
    return {'schema_version': 1, 'status': 'completed-read-only-postmortem-of-the-sole-run',
            'source_run_id': 43242767502, 'artifact_id': 13954689320, 'experiment_receipt': receipt,
            'actual_comparison_stderr': stderr, 'reports': reports, 'stable_hashes_identical': len(first) - len(differences),
            'stable_hashes_differ': len(differences), 'differences': differences,
            'positive_actual_checks': {name: experiment[name] for name in ('system_icu_export_gate_passed', 'candidate_exact_omission_verified', 'own_process_System32_ICU_observed', 'profile_cleanup_verified', 'owned_job_closed_cleanly', 'forced_descendants')},
            'post_run_hash_proofs_not_reached': {'original_stage_modified': experiment['original_stage_modified'], 'system_files_modified': experiment['system_files_modified']},
            'original_experiment_reclassified_as_PASS': False, 'application_DLL_or_audio_executed_by_reader': False,
            'new_omission_variant_created': False, 'human_listening_or_other_Windows_qualified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    report = analyze(args.root)
    print('CADENCE_ICU_COMPARISON_POSTMORTEM_BEGIN')
    print(json.dumps(report, separators=(',', ':')))
    print('CADENCE_ICU_COMPARISON_POSTMORTEM_END')
