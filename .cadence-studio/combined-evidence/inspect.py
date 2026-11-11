#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Read retained application reports and hash AAC bytes. Never execute a codec."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

MAX_JSON = 200_000
MAX_LOG = 24_000


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(65536), b''):
            digest.update(data)
    return digest.hexdigest()


def emit(kind, value):
    print('CADENCE_COMBINED_' + kind + '_BEGIN', flush=True)
    print(json.dumps(value, ensure_ascii=False, sort_keys=True), flush=True)
    print('CADENCE_COMBINED_' + kind + '_END', flush=True)


def stage_metadata(root):
    """Authenticate retained stage records and inspect ZIP entries without extraction."""
    expected_tree = 'f95b7097a55dddf9c7f697fc826b95721071231a'
    expected_source = '0e05d04acbeee32f1b561f24493d7ef41c322081'
    expected_ci = 'dbca5382bc029a2a6bb8c8eb761abb2c9294479c'
    expected_exe = '35d8b076cacddb8b37a4f23aeea9899e6ab4ac9214e9a5b1125bbeccf26cf39e'
    sums = {}
    for line in (root / 'SHA256SUMS.txt').read_text(encoding='utf-8-sig').splitlines():
        m = re.fullmatch(r'([a-f0-9]{64})  ([^/\\:]+)', line)
        if not m or m[2] in sums or m[2] in {'.', '..', 'SHA256SUMS.txt'}:
            raise ValueError('Invalid retained-stage checksum path/record')
        path = root / m[2]
        if path.is_symlink() or not path.is_file() or sha256(path) != m[1]:
            raise ValueError('Retained-stage checksum mismatch: ' + m[2])
        sums[m[2]] = m[1]
    for path in root.iterdir():
        if path.is_symlink() or not path.is_file() or (path.name != 'SHA256SUMS.txt' and path.name not in sums):
            raise ValueError('Unaccounted retained-stage entry: ' + path.name)
    records = {}
    for name in ['stage-manifest.json', 'cadence-build.json', 'cadence-build-result.json', 'dependencies.lock.json', 'zlib-source-profile.lock.json']:
        path = root / name
        if name not in sums or path.stat().st_size > MAX_JSON:
            raise ValueError('Missing/big retained-stage record: ' + name)
        records[name] = {'bytes': path.stat().st_size, 'sha256': sums[name], 'record': json.loads(path.read_text(encoding='utf-8-sig'))}
    manifest = records['stage-manifest.json']['record']
    state = records['cadence-build.json']['record']
    result = records['cadence-build-result.json']['record']
    if (manifest['source_tree'] != expected_tree or manifest['original_source_commit'] != expected_source
            or manifest['source_commit'] != expected_ci or state['source_commit'] != expected_ci or result['source_commit'] != expected_ci
            or manifest['build_number'] != 2002 or state['build_number'] != 2002 or manifest['run_number'] != 2 or manifest['run_attempt'] != 1
            or manifest['executable_sha256'] != expected_exe or result['executable_sha256'] != expected_exe
            or not state['windows_system_aac'] or not state['open_source_zlib']['pinned_ci_verified']
            or state['source_dirty_at_configure'] or result['source_dirty_at_build']):
        raise ValueError('Retained-stage identity does not match qualified source/build2002')
    archive_name = manifest['stage_archive']
    supplement = 'Cadence-zlib-1.3.2-corresponding-source.zip'
    if set(path.name for path in root.glob('*.zip')) != {archive_name, supplement}:
        raise ValueError('Expected exactly payload ZIP plus separately retained zlib source ZIP')
    if sums[archive_name] != manifest['stage_archive_sha256'] or sums[supplement] != manifest['zlib_sources_archive_sha256']:
        raise ValueError('ZIP identity mismatch in original stage manifest')
    with zipfile.ZipFile(root / archive_name) as archive:
        names = set(); exe = None; expanded = 0
        for member in archive.infolist():
            name = member.filename.replace('\\', '/')
            while name.startswith('./'): name = name[2:]
            name = name.rstrip('/')
            if not name or name == '.': continue
            if name.startswith('/') or ':' in name or '..' in name.split('/') or name.casefold() in names or ((member.external_attr >> 16) & 0o170000) == 0o120000:
                raise ValueError('Unsafe/duplicate payload ZIP entry')
            names.add(name.casefold()); expanded += member.file_size
            if expanded > 5 * 1024**3 or len(names) > 100000:
                raise ValueError('Payload ZIP exceeds original bounds')
            if name == 'bin/CadenceStudio4.exe': exe = member
        if exe is None or exe.file_size > 512 * 1024**2:
            raise ValueError('Missing/oversized executable ZIP entry')
        digest = hashlib.sha256()
        with archive.open(exe) as stream:
            for block in iter(lambda: stream.read(65536), b''): digest.update(block)
        if digest.hexdigest() != expected_exe:
            raise ValueError('Executable bytes do not match independently recorded full-build result')
        exe_record = {'name': exe.filename, 'bytes': exe.file_size, 'sha256': digest.hexdigest(),
                      'archive_entries': len(names), 'expanded_archive_bytes': expanded}
    with zipfile.ZipFile(root / supplement) as archive:
        entries = {item.filename.removeprefix('./').rstrip('/'): item for item in archive.infolist() if not item.is_dir()}
        hidden = 'sources/unmodified/zlib-1.3.2/.cmake-format.yaml'
        if hidden not in entries or hashlib.sha256(archive.read(entries[hidden])).hexdigest() != '986f0fdc53be34f931d66c1a6fa4935d84991da14f059c7df567ede7cd32b68f':
            raise ValueError('Corresponding zlib sources do not contain the repaired original hidden source')
    return {'reader_only': True, 'payload_extracted': False, 'application_executed': False,
            'source_tree': expected_tree, 'source_commit': expected_source, 'original_ci_commit': expected_ci,
            'records': records, 'checksum_file_sha256': sha256(root / 'SHA256SUMS.txt'),
            'all_root_file_sha256': sums, 'payload_zip': archive_name, 'payload_zip_sha256': sums[archive_name],
            'source_supplement_zip': supplement, 'source_supplement_sha256': sums[supplement],
            'hidden_zlib_original_source_present': True, 'executable_zip_entry': exe_record}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--run-id', type=int, required=True)
    parser.add_argument('--artifact-id', type=int, required=True)
    parser.add_argument('--artifact-name', required=True)
    parser.add_argument('--stage-root', type=Path)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    output = args.output.resolve()
    if not root.is_dir() or output == root or output.is_relative_to(root) or root.is_relative_to(output):
        parser.error('Use an existing artifact root and disjoint new summary directory')
    output.mkdir(parents=True, exist_ok=False)
    summary = {'schema_version': 1, 'source_run_id': args.run_id,
               'source_artifact_id': args.artifact_id, 'source_artifact_name': args.artifact_name,
               'reader_only': True, 'application_or_codec_executed_by_reader': False,
               'audio_reencoded_by_reader': False, 'audio_bytes_printed': False,
               'human_listening': False, 'reports': [], 'logs': [], 'aac_files': [],
               'errors': [], 'reader_passed': False}
    music = None
    selected_names = {'cadence-build.json', 'cadence-build-result.json', 'cadence-bootstrap.json'}
    compact_dirs = {'qa-cadence', 'qa-roundtrip-cadence', 'qa-combined-reference-bytes'}
    for path in sorted(root.rglob('*')):
        if path.is_symlink() or not path.is_file():
            continue
        if not path.resolve(strict=True).is_relative_to(root):
            summary['errors'].append('File outside artifact root')
            continue
        relative = path.relative_to(root).as_posix()
        if path.suffix.lower() == '.json':
            selected = (path.name in selected_names or (path.name == 'report.json' and
                        path.parent.name in compact_dirs | {'qa-system-aac-music', 'qa-system-aac-graph'}))
            if not selected:
                continue
            if path.stat().st_size > MAX_JSON:
                summary['errors'].append('Selected JSON exceeds bounded reader limit: ' + relative)
                continue
            try:
                report = json.loads(path.read_text(encoding='utf-8-sig'))
            except (UnicodeError, ValueError) as error:
                summary['errors'].append('Invalid report: ' + relative + ': ' + str(error))
                continue
            entry = {'path': relative, 'bytes': path.stat().st_size, 'sha256': sha256(path)}
            if path.parent.name in compact_dirs:
                entry['report_summary'] = {k: v for k, v in report.items()
                                           if k not in {'checks', 'conversions', 'comparisons', 'fixtures', 'limits'}}
                for key in ('checks', 'conversions', 'comparisons'):
                    rows = report.get(key)
                    if isinstance(rows, list):
                        entry['report_summary'][key + '_count'] = len(rows)
                        entry['report_summary'][key + '_failed'] = [row for row in rows if row.get('passed') is False]
            else:
                entry['report'] = report
            summary['reports'].append(entry)
            emit('REPORT', entry)
            if path.parent.name == 'qa-system-aac-music' and path.name == 'report.json':
                if music is not None:
                    summary['errors'].append('Duplicate musical application report')
                music = report
        elif path.suffix.lower() == '.log' and path.name.startswith(('missing-video-encoder', 'application-aac-batch')):
            raw = path.read_bytes()
            entry = {'path': relative, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                     'truncated_to_last_bytes': max(0, len(raw) - MAX_LOG),
                     'text': raw[-MAX_LOG:].decode('utf-8-sig', errors='replace')}
            summary['logs'].append(entry)
            emit('DIAGNOSTIC', entry)
        elif path.suffix.lower() == '.aac':
            entry = {'path': relative, 'bytes': path.stat().st_size, 'sha256': sha256(path)}
            summary['aac_files'].append(entry)
            emit('AAC', entry)
    if music is None:
        summary['errors'].append('Missing actual musical application report')
    else:
        summary['original_application_overall_passed'] = music.get('passed')
        cases = music.get('cases', [])
        summary['original_music_cases_passed'] = sum(case.get('passed') is True for case in cases)
        summary['original_missing_video_encoder'] = music.get('missing_video_encoder')
        if len(cases) != 5 or len(summary['aac_files']) != 5:
            summary['errors'].append('Expected five reported musical cases and five retained AAC files')
        for case in cases:
            matches = [entry for entry in summary['aac_files'] if case.get('fixture') in Path(entry['path']).parts]
            if len(matches) != 1 or matches[0]['sha256'] != case.get('adts', {}).get('sha256') or matches[0]['bytes'] != case.get('adts', {}).get('bytes'):
                summary['errors'].append('Retained AAC does not match unique recorded case hash/size: ' + str(case.get('fixture')))
    if args.stage_root:
        try:
            summary['retained_stage_metadata'] = stage_metadata(args.stage_root.resolve(strict=True))
            emit('STAGE', summary['retained_stage_metadata'])
        except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
            summary['errors'].append('Retained-stage metadata failed: ' + str(error))
    summary['reader_passed'] = not summary['errors']
    (output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    emit('SUMMARY', {k: v for k, v in summary.items() if k not in {'reports', 'logs'}})
    return 0 if summary['reader_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
