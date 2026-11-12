#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Exercise the real source collection, corruption guards and final gate."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parent


def module(name):
    spec = importlib.util.spec_from_file_location('cadence_' + name, ROOT / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--network', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cmake', default=shutil.which('cmake'))
    parser.add_argument('--bundle', type=Path, default=ROOT / 'local-source-bundle')
    parser.add_argument('--cache', type=Path)
    args = parser.parse_args()
    args.cache = args.cache or args.bundle / 'archives'
    collector = module('collect')
    verifier = module('verify_bundle')
    lock_path = ROOT / 'sources.lock.json'
    lock = json.loads(lock_path.read_text())
    results = []
    actual = verifier.verify(args.bundle, lock_path)
    assert actual['verified'] and actual['source_archives'] == 11 and actual['notice_files'] == 265 and actual['original_notice_files'] == 264
    results.append({'case': 'real_complete_existing_material_and_all_original_notice_bytes', 'passed': True, 'result': actual})
    for path in ('../escape', '/absolute', 'C:/drive', 'bad\x00name'):
        try:
            collector.safe_relative(path)
        except ValueError:
            continue
        raise AssertionError('Unsafe source path accepted')
    results.append({'case': 'unsafe_notice_paths_refused', 'passed': True})
    mnx = next(x for x in lock['archives'] if x['id'] == 'mnxdom')
    with tempfile.TemporaryDirectory(prefix='cadence-source-guards-') as temporary:
        temporary = Path(temporary)
        cache = temporary / 'cache'; cache.mkdir()
        altered = bytearray((args.cache / mnx['archive']).read_bytes()); altered[-1] ^= 1
        (cache / mnx['archive']).write_bytes(altered)
        target = temporary / 'should-not-exist.tar.gz'
        try:
            collector.fetch(mnx, target, [cache], True)
        except ValueError as error:
            assert 'SHA pin' in str(error)
        else:
            raise AssertionError('Corrupt original archive was accepted')
        assert not target.exists()
        results.append({'case': 'real_mnx_archive_one_byte_corruption_refused_before_output', 'passed': True})
        try:
            collector.fetch(mnx, target, [], True)
        except ValueError as error:
            assert 'absent' in str(error)
        else:
            raise AssertionError('Offline collector silently fetched a missing archive')
        assert not target.exists()
        results.append({'case': 'offline_missing_source_refused_without_network_or_output', 'passed': True})
        output = temporary / 'final-forbidden'
        assert args.cmake, 'Supply the real CMake archive reader to exercise the final gate'
        gate = subprocess.run([sys.executable, '-I', str(ROOT / 'collect.py'), '--output', str(output),
                               '--cmake', args.cmake, '--require-complete-distribution'], capture_output=True, text=True)
        assert gate.returncode == 2 and 'Final distribution refused' in gate.stderr and not output.exists()
        results.append({'case': 'actual_final_distribution_cli_gate_refuses_unresolved_origins_before_writes', 'passed': True})
        if args.network:
            schema = next(x for x in lock['archives'] if x['id'] == 'json-schema-validator')
            target = temporary / schema['archive']
            transport = collector.fetch(schema, target, [], False)
            assert target.stat().st_size == schema['archive_bytes'] and collector.sha(target) == schema['sha256']
            results.append({'case': 'real_https_original_source_download_with_length_and_sha_pins', 'passed': True, **transport})
    report = {'schema_version': 1, 'status': 'passed', 'cases': results,
              'application_built_or_run': False, 'dll_loaded': False,
              'listening_or_windows_runtime_validation_claimed': False,
              'network_test_requested': args.network,
              'collector_sha256': collector.sha(ROOT / 'collect.py'),
              'verifier_sha256': collector.sha(ROOT / 'verify_bundle.py')}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': 'passed', 'checks': len(results), 'network_tested': args.network}))


if __name__ == '__main__':
    main()
