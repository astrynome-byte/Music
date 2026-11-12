#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Verify every file of the retained source collection against original pins."""
from pathlib import Path
import argparse
import importlib.util
import json
import re
spec = importlib.util.spec_from_file_location('cadence_source_collector', Path(__file__).with_name('collect.py'))
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)
safe_relative, sha = collector.safe_relative, collector.sha


def verify(root: Path, lock_path: Path) -> dict:
    root = root.resolve(strict=True)
    expected_lock = sha(lock_path)
    if sha(root / 'sources.lock.json') != expected_lock:
        raise ValueError('Bundle source lock differs from the original reviewed lock')
    lock = json.loads(lock_path.read_text())
    expected = {}
    for line in (root / 'SHA256SUMS.txt').read_text(encoding='ascii').splitlines():
        match = re.fullmatch(r'([a-f0-9]{64})  (.+)', line)
        if not match:
            raise ValueError('Invalid checksum line')
        name = safe_relative(match[2])
        file = root / name
        if name in expected or name == 'SHA256SUMS.txt' or not file.resolve().is_relative_to(root):
            raise ValueError('Duplicate or escaping checksum path')
        current = file
        while current != root:
            if current.is_symlink():
                raise ValueError('Linked source collection member')
            current = current.parent
        if sha(file) != match[1]:
            raise ValueError('Source collection hash differs: ' + name)
        expected[name] = match[1]
    members = list(root.rglob('*'))
    if any(x.is_symlink() for x in members):
        raise ValueError('Linked file or directory in source collection')
    actual = {x.relative_to(root).as_posix() for x in members if x.is_file() and x != root / 'SHA256SUMS.txt'}
    if expected.keys() != actual:
        raise ValueError('The retained source collection has unhashed or missing files')
    report = json.loads((root / 'collection-report.json').read_text())
    if report['source_lock_sha256'] != expected_lock or not report['source_archives_verified'] or report['errors']:
        raise ValueError('Original source collection did not pass')
    for spec in lock['archives']:
        archive = root / 'archives' / spec['archive']
        if archive.stat().st_size != spec['archive_bytes'] or sha(archive) != spec['sha256']:
            raise ValueError('Original immutable source archive differs: ' + spec['id'])
    for spec in lock.get('supplementary_notices', []):
        file = root / 'notices' / spec['component'] / spec['notice_file']
        if file.stat().st_size != spec['archive_bytes'] or sha(file) != spec['sha256']:
            raise ValueError('Original supplementary specification notice differs')
    if lock.get('vendored_w3c_mnx'):
        data = lock['vendored_w3c_mnx']
        expected_attribution = data['generated_attribution'].encode('utf-8')
        actual_attribution = (root / 'notices/w3c-mnx' / data['generated_attribution_file']).read_bytes()
        if actual_attribution != expected_attribution:
            raise ValueError('The specification name/version attribution changed or is absent')
    notices = 0
    original_notices = 0
    for component in report['components']:
        if component['notices']['missing_declared_license_files']:
            raise ValueError('A declared license reference was omitted')
        for record in component['notices']['files']:
            name = 'notices/' + component['id'] + '/' + safe_relative(record['file'])
            if name not in expected or expected[name] != record['sha256']:
                raise ValueError('Original notice bytes are absent or changed')
            notices += 1
            original_notices += int(record.get('original_bytes', True))
    return {'verified': True, 'files': len(expected), 'source_archives': len(lock['archives']),
            'notice_files': notices, 'original_notice_files': original_notices, 'source_lock_sha256': expected_lock,
            'final_distribution_ready': report['complete_distribution_ready'],
            'source_or_application_program_executed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--lock', type=Path, default=Path(__file__).with_name('sources.lock.json'))
    args = parser.parse_args()
    print(json.dumps(verify(args.bundle, args.lock), ensure_ascii=False, sort_keys=True))
