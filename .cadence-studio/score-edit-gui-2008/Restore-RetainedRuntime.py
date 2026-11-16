#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Extract only the authenticated original2008 bundle and runtime into new paths.

Call the original DATAONLY reader first. Rehash its pinned outer archives and
inner archive before extracting. No payload, DLL or installer is executed.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import zipfile

SOURCE = 'a2b7abaf045a8f3cb84ec2953d9e0e51b9e78903'
TREE = 'c5452043983a048ef0aeef085615af903de3f5b0'
CI = '95cebb22fe6cbde22919c94f2b480bd14c3eb8de'
EXE = '13cd4e6d2f408d2e64b187d4c3bff1188ff4192ac7b670d3a12373bbeb37f6cd'
OUTER = {'stage-original.zip': (306891538, '8cd00d5df8670837c3b15d3e3bd6e406df290222e404ef88599e4383de048178'),
         'logs-original.zip': (6546788, '12f746febc7ca371fb00dcc33aa4a8151031e63ca03c5a8eaa24add50e3dfc8c')}
READER = '9bdcbc4732057fc50f8ba5387578d68d292682864a21938b717d29df662875ae'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def plain(value):
    path = value.absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or (part.exists() and getattr(part.stat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('Runtime reparse/link paths are forbidden')
    return path


def extract(reader, archive_path, destination, expected=None):
    destination.mkdir()
    measured = {}
    with zipfile.ZipFile(archive_path) as archive:
        entries = reader.zip_rows(archive)
        if expected is not None and set(entries) != set(expected):
            raise ValueError('Original runtime inventory extent differs')
        for name, info in sorted(entries.items()):
            if info.external_attr & 0x400:
                raise ValueError('Windows reparse ZIP members are forbidden')
            target = destination.joinpath(*name.split('/'))
            target.parent.mkdir(parents=True, exist_ok=True)
            row = reader.stream_entry(archive, info, target)
            if expected is not None and row != expected[name]:
                raise ValueError('Runtime bytes differ from authenticated original inventory: ' + name)
            measured[name] = row
    return measured


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reader-root', type=Path, required=True)
    parser.add_argument('--data-work', type=Path, required=True)
    parser.add_argument('--data-output', type=Path, required=True)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if os.name != 'nt' or struct.calcsize('P') != 8 or os.environ.get('GITHUB_ACTIONS') != 'true' \
            or os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted' or os.environ.get('GITHUB_REPOSITORY') != 'astrynome-byte/Music':
        raise ValueError('Disposable native Windows repository context required')
    temp = Path(os.environ['RUNNER_TEMP']).resolve()
    work, data, bundle, stage, report_path = map(plain, (args.data_work, args.data_output, args.bundle, args.stage, args.report))
    for path in (work, data, bundle, stage, report_path):
        if not path.is_relative_to(temp) or path == temp:
            raise ValueError('All runtime paths must remain beneath RUNNER_TEMP')
    for path in (bundle, stage, report_path):
        if path.exists() or not path.parent.is_dir():
            raise ValueError('New restoration paths with existing plain parents required')
    roots = (work, data, bundle, stage)
    if len(set(roots)) != 4 or any(a != b and (a.is_relative_to(b) or b.is_relative_to(a)) for a in roots for b in roots):
        raise ValueError('Separate input and restoration roots required')
    reader_path = args.reader_root / 'read_existing_stage.py'
    if sha(reader_path) != READER:
        raise ValueError('Reviewed original DATAONLY reader changed')
    spec = importlib.util.spec_from_file_location('original2008_reader', reader_path)
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    for name, (size, checksum) in OUTER.items():
        original = plain(work / name)
        if not original.is_file() or original.stat().st_size != size or sha(original) != checksum:
            raise ValueError('Actual retained outer ZIP differs: ' + name)
    receipt = json.loads((data / 'readback-receipt.json').read_text())
    inventory = json.loads((data / 'runtime-inventory.MEASURED.json').read_text())
    if receipt['producer_run_id'] != 43408309742 or receipt['producer_job_id'] != 131828068954 \
            or receipt['overall_producer_conclusion'] != 'failure' or receipt['expected_failed_step'] != 31 \
            or receipt['source_ci_commit_observed'] != CI or receipt['source']['original_commit'] != SOURCE \
            or receipt['source']['tree'] != TREE or receipt['executable_sha256'] != EXE \
            or receipt['runtime_inventory_MEASURED_sha256'] != sha(data / 'runtime-inventory.MEASURED.json'):
        raise ValueError('Authenticated original partial-build receipt differs')
    inner = plain(work / 'original-inner-stage.zip')
    if inner.stat().st_size != inventory['inner_archive_receipt']['bytes'] or sha(inner) != inventory['inner_archive_receipt']['sha256']:
        raise ValueError('Original inner runtime ZIP differs')
    bundle_rows = extract(reader, work / 'stage-original.zip', bundle)
    expected_bundle = inventory['stage_bundle_file_receipts_measured']
    if set(bundle_rows) != set(expected_bundle) | {'SHA256SUMS.txt'} or any(bundle_rows[name] != row for name, row in expected_bundle.items()):
        raise ValueError('Extracted original companion bytes differ from the authenticated measurements')
    runtime_rows = extract(reader, inner, stage, inventory['runtime_files'])
    if len(runtime_rows) != 2712 or runtime_rows['bin/CadenceStudio4.exe']['sha256'] != EXE or any(n.casefold() == 'bin/icuuc.dll' for n in runtime_rows):
        raise ValueError('Actual retained application identity or ICU policy differs')
    original_manifest = json.loads((bundle / 'stage-manifest.json').read_text(encoding='utf-8-sig'))
    if original_manifest['source_commit'] != CI or original_manifest['source_tree'] != TREE \
            or original_manifest['original_source_commit'] != SOURCE:
        raise ValueError('Original extracted companion provenance differs')
    zlib_archive = bundle / 'Cadence-zlib-1.3.2-corresponding-source.zip'
    if zlib_archive.stat().st_size != 4163182 or sha(zlib_archive) != '6dbe70f5e11b389877109f21b8b999f2371a880b68d66572bfd895c6e6da2696':
        raise ValueError('Actual original zlib prepared-source ZIP differs')
    zlib_destination = plain(temp / 'cadence-zlib-prepared')
    if zlib_destination.exists():
        raise ValueError('New zlib prepared directory required')
    zlib_rows = extract(reader, zlib_archive, zlib_destination)
    report = {'schema_version': 1, 'status': 'original2008-stage-and-companions-restored-no-execution',
              'origin_build_run': 43408309742, 'origin_build_job': 131828068954,
              'origin_overall_conclusion': 'failure', 'origin_failure': 'standalone MIDI harness include, step31',
              'original_source_commit': SOURCE, 'original_source_tree': TREE, 'original_ci_commit': CI,
              'executable_sha256': EXE, 'stage_path': str(stage), 'bundle_path': str(bundle),
              'runtime_files': runtime_rows, 'runtime_file_count': len(runtime_rows),
              'original_zlib_prepared_files': zlib_rows,
              'bundle_original_files': bundle_rows,
              'source_or_application_recompiled': False, 'original_companions_rewritten': False,
              'application_or_installer_executed': False, 'original_data_receipt_sha256': sha(data / 'readback-receipt.json')}
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('runtime_files', 'bundle_original_files')}))


if __name__ == '__main__':
    main()
