#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Authenticate immutable 2008 inputs and prepare only the original WiX assets.

No application, DLL, compiler, installer or downloaded source is executed here.
The source checkout is queried only through git; runtime bytes are streamed.
"""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import re
import shutil
import stat
import struct
import subprocess

ROOT = Path(__file__).resolve().parent
ORIGINAL = 'a2b7abaf045a8f3cb84ec2953d9e0e51b9e78903'
CI = '95cebb22fe6cbde22919c94f2b480bd14c3eb8de'
TREE = 'c5452043983a048ef0aeef085615af903de3f5b0'
EXE = '13cd4e6d2f408d2e64b187d4c3bff1188ff4192ac7b670d3a12373bbeb37f6cd'
PRODUCT = '4.7.6.2008'
GATES = {'native_practice', 'native_omr', 'native_transcription', 'audio_transcription_import',
         'cli57', 'reference35', 'aac5', 'stage_notices', 'stage_GUI', 'musical_roundtrip'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def plain(path):
    path = Path(path).absolute()
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400,
                'Linked/reparse input refused: ' + str(part))
    return path


def sha(path):
    path = plain(path)
    require(path.is_file() and path.stat().st_size <= 2 * 1024**3, 'Bounded regular input required')
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_json(path, limit=8 * 1024**2):
    path = plain(path)
    require(path.is_file() and path.stat().st_size <= limit, 'Bounded JSON input required')
    return json.loads(path.read_text(encoding='utf-8-sig'))


def digest(value):
    require(isinstance(value, str) and re.fullmatch('[a-f0-9]{64}', value), 'A measured SHA256 pin is required')
    return value


def member(value):
    require(isinstance(value, str), 'Relative member must be text')
    p = PurePosixPath(value)
    require(value and p.as_posix() == value and not p.is_absolute() and '..' not in p.parts
            and '\\' not in value and ':' not in value, 'Safe canonical relative member required')
    return p


def inventory(directory):
    directory = plain(directory)
    require(directory.is_dir(), 'Plain directory required')
    rows, seen = {}, set()
    for path in sorted(directory.rglob('*')):
        plain(path)
        if path.is_dir():
            continue
        name = path.relative_to(directory).as_posix()
        member(name)
        require(path.is_file() and name.casefold() not in seen and len(rows) < 20000,
                'Duplicate or excessive runtime/source inventory')
        seen.add(name.casefold())
        rows[name] = {'bytes': path.stat().st_size, 'sha256': sha(path)}
    require(bool(rows), 'An empty inventory cannot pass')
    return rows


def git(source, *args, binary=False):
    result = subprocess.run(['git', '-C', str(source), *args], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=60)
    require(result.returncode == 0, 'Exact source Git verification failed')
    return result.stdout if binary else result.stdout.decode('utf-8').strip()


def source_identity(source):
    require(git(source, 'rev-parse', 'HEAD') == CI and git(source, 'rev-parse', 'HEAD^{tree}') == TREE,
            'Original compiled CI commit and source tree required')
    require(not git(source, 'status', '--porcelain', '--untracked-files=all'),
            'Application source must remain clean')


def bindings(path):
    value = read_json(path)
    require(value.get('schema_version') == 1 and value.get('ready') is True,
            'Actual measured package bindings must be reviewed and ready; template is inactive')
    require(value.get('source_original_commit') == ORIGINAL and value.get('source_ci_commit') == CI
            and value.get('source_tree') == TREE and value.get('executable_sha256') == EXE
            and value.get('product_version') == PRODUCT and value.get('build_number') == 2008
            and value.get('product_code') == '{CA4AC56B-9ED9-568F-9F5A-0D9475D4CC26}'
            and value.get('upgrade_code') == '{319B992F-470A-465B-9A79-6B0CBFC7D6C7}',
            'Exact retained 2008 package identity required')
    require(set(value.get('required_gates', [])) == GATES, 'The complete retained-stage gate inventory is required')
    for name in ('source_profile_sha256', 'runtime_inventory_sha256', 'readback_receipt_sha256', 'qualification_sha256',
                 'corresponding_source_report_sha256', 'corresponding_source_lock_sha256', 'packaging_assets_lock_sha256'):
        digest(value.get(name))
    require(set(value.get('stage_metadata_files', {})) == {'stage-manifest.json', 'cadence-build.json',
                                                         'cadence-build-result.json', 'SHA256SUMS.txt'},
            'Four original stage metadata pins required')
    for value_sha in value['stage_metadata_files'].values():
        digest(value_sha)
    return value


def qualification_file(row, evidence_root=None):
    if evidence_root is None:
        return plain(row.get('path', ''))
    root = plain(evidence_root)
    index = read_json(root / 'evidence-index.json')
    require(index.get('schema_version') == 1 and index.get('raw_reports_preserved') is True,
            'Authenticated cross-job QA evidence index required')
    target = index.get('reports', {}).get(row.get('path', ''))
    require(isinstance(target, dict) and target.get('bytes') == row.get('bytes')
            and target.get('sha256') == row.get('sha256'), 'Actual gate relocation differs')
    return plain(root.joinpath(*member(target['relative_path']).parts))


def qualify(path, stage, evidence_root=None):
    report = read_json(path)
    require(report.get('schema_version') == 1 and report.get('ready') is True and report.get('passed') is True
            and report.get('application_recompiled') is False and report.get('build_number') == 2008
            and report.get('source_ci_commit') == CI and report.get('source_tree') == TREE
            and report.get('executable_sha256') == EXE, 'Real completed retained-stage qualification required')
    gates = report.get('gates')
    require(isinstance(gates, dict) and set(gates) == GATES, 'All ten actual qualification gates are required')
    for name, row in gates.items():
        require(isinstance(row, dict) and row.get('passed') is True, 'Gate has not passed: ' + name)
        file = qualification_file(row, evidence_root)
        require(sha(file) == digest(row.get('sha256')) and file.stat().st_size == row.get('bytes'),
                'Actual qualification report bytes differ: ' + name)
    counts = report.get('counts', {})
    require(counts.get('cli_checks') == 57 and counts.get('reference_outputs') == 35
            and counts.get('music_aac_cases') == 5, 'Actual 57/35/5 counts required')
    notices = read_json(qualification_file(gates['stage_notices'], evidence_root))
    require(notices.get('passed') is True and notices.get('application_executed') is False
            and notices.get('executable_sha256') == EXE and len(notices.get('notices', [])) > 0
            and len(notices['notices']) == notices.get('notice_files_verified'), 'Completed read-only stage notice report required')
    for row in notices['notices']:
        file = stage.joinpath(*member(row['stage_path']).parts)
        require(file.stat().st_size == row['bytes'] and sha(file) == digest(row['sha256']), 'Runtime notice bytes changed')
    return report


def validate(args, pin):
    source, stage = plain(args.application_source), plain(args.stage)
    source_identity(source)
    require(sha(args.source_profile) == pin['source_profile_sha256'], 'Original source profile differs')
    profile = read_json(args.source_profile)
    require(profile.get('source') == {'commit': ORIGINAL, 'tree': TREE} and profile.get('build_number') == 2008,
            'Source profile does not describe the retained source')
    require(sha(args.runtime_inventory) == pin['runtime_inventory_sha256']
            and sha(args.readback_receipt) == pin['readback_receipt_sha256'], 'Measured readback receipt pins differ')
    measured, readback = read_json(args.runtime_inventory), read_json(args.readback_receipt)
    require(measured.get('source_original_commit') == ORIGINAL and measured.get('source_ci_commit') == CI
            and measured.get('source_tree') == TREE and measured.get('all_original_stage_ledger_members_verified') is True
            and measured.get('application_or_DLL_executed') is False, 'Actual DATAONLY stage inventory required')
    require(readback.get('producer_run_id') == 43408309742 and readback.get('producer_job_id') == 131828068954
            and readback.get('runtime_inventory_MEASURED_sha256') == pin['runtime_inventory_sha256']
            and readback.get('source_ci_commit_observed') == CI and readback.get('application_executed') is False
            and readback.get('MSI_produced_or_tested') is False, 'The stage measurement must be bound to the real producer')
    downloads = [row for row in readback.get('downloads', []) if row.get('role') == 'stage']
    require(len(downloads) == 1 and downloads[0].get('outer_ZIP_independently_hashed') is True
            and downloads[0].get('bytes') == 306891538
            and downloads[0].get('sha256') == '8cd00d5df8670837c3b15d3e3bd6e406df290222e404ef88599e4383de048178',
            'Original outer artifact bytes must be independently authenticated')
    stage_metadata = plain(args.artifact_directory)
    for name, expected in pin['stage_metadata_files'].items():
        require(sha(stage_metadata / name) == expected, 'Original producer metadata changed: ' + name)
    for name in ('dependencies.lock.json', 'zlib-source-profile.lock.json', 'Cadence-zlib-1.3.2-corresponding-source.zip'):
        expected = measured.get('stage_bundle_file_receipts_measured', {}).get(name)
        require(isinstance(expected, dict) and sha(stage_metadata / name) == expected.get('sha256')
                and (stage_metadata / name).stat().st_size == expected.get('bytes'), 'Original build dependency/source companion differs: ' + name)
    manifest = read_json(stage_metadata / 'stage-manifest.json')
    state = read_json(stage_metadata / 'cadence-build.json')
    built = read_json(stage_metadata / 'cadence-build-result.json')
    require(manifest.get('source_commit') == CI and manifest.get('source_tree') == TREE
            and manifest.get('original_source_commit') == ORIGINAL and manifest.get('build_number') == 2008
            and manifest.get('executable_sha256') == EXE and manifest.get('run_number') == 12
            and manifest.get('run_attempt') == 1 and manifest.get('windows_system_aac') is True
            and manifest.get('variant') == 'Cadence' and manifest.get('configuration') == 'Release',
            'Original stage manifest identity differs')
    require(state.get('source_commit') == CI and state.get('variant') == 'Cadence'
            and state.get('source_dirty_at_configure') is False and state.get('build_number') == 2008
            and state.get('configuration') == 'Release'
            and built.get('source_commit') == CI and built.get('source_dirty_at_build') is False
            and built.get('executable_sha256') == EXE, 'Original clean build identity differs')
    require(state.get('corresponding_sources', {}).get('report_sha256') == pin['corresponding_source_report_sha256'],
            'The component bundle must be the one bound to the actual compiled stage')
    require(measured.get('inner_archive') == manifest.get('stage_archive')
            and measured.get('inner_archive_receipt', {}).get('sha256') == manifest.get('stage_archive_sha256'),
            'Measured runtime inventory and original archive must agree')
    actual = inventory(stage)
    require(actual == measured.get('runtime_files') and len(actual) == measured.get('count'),
            'Every restored runtime byte must match the authenticated inner ZIP inventory')
    require(actual.get('bin/CadenceStudio4.exe', {}).get('sha256') == EXE
            and not any(name.casefold() == 'bin/icuuc.dll' for name in actual), 'Retained EXE/system ICU differs')
    with (stage / 'bin/CadenceStudio4.exe').open('rb') as stream:
        require(stream.read(2) == b'MZ', 'Actual PE executable required')
        stream.seek(60); offset = struct.unpack('<I', stream.read(4))[0]
        require(0 < offset < actual['bin/CadenceStudio4.exe']['bytes'] - 24, 'Invalid PE offset')
        stream.seek(offset); require(stream.read(6) == b'PE\0\0\x64\x86', 'Actual Windows AMD64 PE required')
    components = plain(args.corresponding_sources)
    require(sha(components / 'collection-report.json') == pin['corresponding_source_report_sha256']
            and sha(components / 'sources.lock.json') == pin['corresponding_source_lock_sha256'], 'Original component sources differ')
    require(sha(components / 'SHA256SUMS.txt') == state.get('corresponding_sources', {}).get('checksum_file_sha256')
            and state.get('corresponding_sources', {}).get('source_lock_sha256') == pin['corresponding_source_lock_sha256'],
            'Original build must authenticate the component ledger and source lock')
    collector, lock = read_json(components / 'collection-report.json'), read_json(components / 'sources.lock.json')
    require(collector.get('source_archives_verified') is True and not collector.get('errors')
            and collector.get('source_lock_sha256') == pin['corresponding_source_lock_sha256'], 'Original source collection must be verified')
    rows = inventory(components)
    archives = [name for name in rows if name.startswith('archives/')]
    notices = [name for name in rows if name.startswith('notices/')]
    require(len(archives) == pin.get('expected_source_archives') == 11
            and len(notices) == pin.get('expected_source_notices') == 265
            and len(lock.get('archives', [])) == 11, 'Eleven original source archives and265 notice texts are required')
    for row in lock['archives']:
        name = 'archives/' + str(member(row['archive']))
        require(rows.get(name) == {'bytes': row['archive_bytes'], 'sha256': digest(row['sha256'])}, 'Original component archive bytes differ')
        require(not any(Path(name).name.casefold() == Path(file).name.casefold() for file in actual), 'Development/source archive leaked into runtime')
    original_ledger = {}
    for line in (components / 'SHA256SUMS.txt').read_text(encoding='ascii').splitlines():
        match = re.fullmatch(r'([a-f0-9]{64})  (.+)', line)
        require(match is not None, 'Malformed original source collector ledger')
        name = str(member(match[2])); require(name not in original_ledger, 'Duplicate source collector ledger member')
        original_ledger[name] = match[1]
    require(set(rows) == set(original_ledger) | {'SHA256SUMS.txt'}, 'Original source collector ledger must cover its exact files')
    require(all(rows[name]['sha256'] == value for name, value in original_ledger.items()), 'Original source collector bytes changed')
    require(sha(args.qualification) == pin['qualification_sha256'], 'The authenticated actual QA aggregate differs')
    qualification = qualify(args.qualification, stage, args.qualification_evidence_root)
    return {'stage': actual, 'components': rows, 'qualification': qualification,
            'source_ci_commit': CI, 'source_tree': TREE, 'executable_sha256': EXE}


def prepare(args):
    pin = bindings(args.bindings)
    verified = validate(args, pin)
    project, output = plain(args.project_output), plain(args.report)
    require(not project.exists() and not output.exists(), 'New packaging source and report required')
    lock_path = ROOT / 'packaging-assets.lock.json'
    require(sha(lock_path) == pin['packaging_assets_lock_sha256'], 'Reviewed packaging asset lock changed')
    asset_lock = read_json(lock_path)
    assets = {}
    for row in asset_lock['files']:
        name = str(member(row['path']))
        raw = git(args.application_source, 'show', CI + ':' + name, binary=True)
        require(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'], 'Original packaging Git blob differs: ' + name)
        assets[name] = raw
    # No output directory exists until every original source/runtime/report check passed.
    project.mkdir(parents=True)
    for name, raw in assets.items():
        destination = project.joinpath(*member(name).parts)
        destination.parent.mkdir(parents=True, exist_ok=True); destination.write_bytes(raw)
    shutil.copyfile(ROOT / 'PackagingOnly.CMakeLists.txt', project / 'CMakeLists.txt')
    report = {'schema_version': 1, 'status': 'authenticated-retained2008-inputs-and-packaging-only-assets',
              'source_original_commit': ORIGINAL, 'source_ci_commit': CI, 'source_tree': TREE,
              'product_version': PRODUCT, 'executable_sha256': EXE, 'application_recompiled': False,
              'MSI_produced': False, 'bindings_sha256': sha(args.bindings),
              'qualification_sha256': sha(args.qualification), 'runtime_inventory_sha256': sha(args.runtime_inventory),
              'qualification_files': {name: {'path': str(qualification_file(row, args.qualification_evidence_root)),
                                            'original_report_path': row['path'], 'bytes': row['bytes'], 'sha256': row['sha256']}
                                      for name, row in verified['qualification']['gates'].items()},
              'stage_files': verified['stage'], 'component_files': verified['components'],
              'input_files': {name: {'path': str(path), 'bytes': Path(path).stat().st_size, 'sha256': sha(path)}
                              for name, path in [('stage-manifest.json', args.artifact_directory / 'stage-manifest.json'),
                                                 ('cadence-build.json', args.artifact_directory / 'cadence-build.json'),
                                                 ('cadence-build-result.json', args.artifact_directory / 'cadence-build-result.json'),
                                                 ('original-SHA256SUMS.txt', args.artifact_directory / 'SHA256SUMS.txt'),
                                                 ('dependencies.lock.json', args.artifact_directory / 'dependencies.lock.json'),
                                                 ('zlib-source-profile.lock.json', args.artifact_directory / 'zlib-source-profile.lock.json'),
                                                 ('Cadence-zlib-1.3.2-corresponding-source.zip', args.artifact_directory / 'Cadence-zlib-1.3.2-corresponding-source.zip'),
                                                 ('runtime-inventory.MEASURED.json', args.runtime_inventory),
                                                 ('readback-receipt.json', args.readback_receipt)]},
              'packaging_assets': asset_lock['files']}
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ('status', 'source_ci_commit', 'source_tree', 'executable_sha256', 'application_recompiled', 'MSI_produced')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('stage', 'application-source', 'source-profile', 'artifact-directory', 'runtime-inventory',
                 'readback-receipt', 'bindings', 'qualification', 'corresponding-sources', 'project-output', 'report'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--qualification-evidence-root', type=Path)
    args = parser.parse_args()
    prepare(args)
