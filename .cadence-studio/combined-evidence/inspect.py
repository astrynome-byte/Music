#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Read retained application reports and hash AAC bytes. Never execute a codec."""
from __future__ import annotations
import argparse
import hashlib
import json
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--run-id', type=int, required=True)
    parser.add_argument('--artifact-id', type=int, required=True)
    parser.add_argument('--artifact-name', required=True)
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
    summary['reader_passed'] = not summary['errors']
    (output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    emit('SUMMARY', {k: v for k, v in summary.items() if k not in {'reports', 'logs'}})
    return 0 if summary['reader_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
