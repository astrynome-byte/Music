# SPDX-License-Identifier: GPL-3.0-only
"""Read only the already retained full2005 stage; never execute staged files."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import zipfile

RUN = 43207550870
ARTIFACT = 13943781621
ORIGINAL = '961c80b235d413dc9d123ea8f669ddb7f84ecd09'
TREE = 'c4780f1487559744fd4b2c2040b86ac37bb8c67b'
ARCHIVE = 'CadenceStudio-v4.7.6-combined-system-aac-stage-build-2005-attempt-1-x64.zip'
SOURCE_JSON_SHA = 'acd0aabb88bec95eb8f6803844e4f5cd32e7a67084d2a58d0dce3df3fba33e98'
PATCH_SHA = '1f9823f48ae63c69647bf5dbc3e05e096540f96d1dfd0ed5de568ed4ad7f464b'

def require(ok, message):
    if not ok:
        raise RuntimeError(message)

def digest(stream):
    sha = hashlib.sha256()
    for data in iter(lambda: stream.read(1024 * 1024), b''):
        sha.update(data)
    return sha.hexdigest()

def file_hash(path):
    with path.open('rb') as stream:
        return digest(stream)

def json_file(root, name):
    path = root / name
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 131072, 'Missing/large/linked JSON: ' + name)
    return json.loads(path.read_text(encoding='utf-8-sig'))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--source-selection', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted', 'Hosted disposable CI required')
    root = args.root.resolve(strict=True)
    require(root.is_dir() and not args.output.exists(), 'Original artifact and new report required')
    for name, expected in [('source.json', SOURCE_JSON_SHA), ('changes.patch.gz', PATCH_SHA)]:
        require(file_hash(args.source_selection / name) == expected, 'Frozen source-selection bytes changed')
    sums_path = root / 'SHA256SUMS.txt'
    require(sums_path.is_file() and sums_path.stat().st_size <= 262144, 'Missing/large checksum list')
    sums = {}
    total = 0
    for line in sums_path.read_text(encoding='ascii').splitlines():
        match = re.fullmatch(r'([a-f0-9]{64})  (.+)', line)
        require(match is not None, 'Malformed original checksum record')
        sha, name = match.groups()
        parts = PurePosixPath(name).parts
        require(name and not name.startswith('/') and not re.search(r'[\\:\x00-\x1f]', name) and all(x not in ('', '.', '..') for x in name.split('/')) and name != 'SHA256SUMS.txt' and name not in sums, 'Unsafe/duplicate original path')
        path = root.joinpath(*parts)
        require(path.is_file() and all(not parent.is_symlink() for parent in [path, *path.parents]) and path.resolve().is_relative_to(root), 'Linked/missing/escaped original member')
        size = path.stat().st_size
        require(size <= 838860800, 'Original member exceeds bound')
        total += size
        require(len(sums) < 1000 and total <= 2147483648, 'Original artifact exceeds count/byte bounds')
        require(file_hash(path) == sha, 'Original member SHA mismatch: ' + name)
        sums[name] = sha
    actual = [p for p in root.rglob('*') if p.is_file()]
    require(len(actual) == len(sums) + 1 and len(sums) >= 7, 'Original artifact inventory is incomplete')
    manifest = json_file(root, 'stage-manifest.json')
    result = json_file(root, 'cadence-build-result.json')
    state = json_file(root, 'cadence-build.json')
    require(manifest['original_source_commit'] == ORIGINAL and manifest['source_tree'] == TREE and manifest['build_number'] == 2005 and manifest['run_number'] == 5 and manifest['run_attempt'] == 1 and manifest['status'] == 'experimental-stage-before-qa' and manifest['stage_archive'] == ARCHIVE and manifest['qt_version'] == '6.10.2', 'Actual stage does not match reviewed full2005 provenance')
    ci = manifest['source_commit']
    require(re.fullmatch('[a-f0-9]{40}', ci) is not None and result['source_commit'] == ci and state['source_commit'] == ci and state['source_dirty_at_configure'] is False and result['source_dirty_at_build'] is False and state['build_number'] == 2005 and state['variant'] == 'Cadence', 'Build records or clean source disagree')
    require(sums[ARCHIVE] == manifest['stage_archive_sha256'], 'Measured stage ZIP differs from original manifest')
    with zipfile.ZipFile(root / ARCHIVE) as archive:
        require(len(archive.infolist()) <= 100000, 'Stage ZIP member bound exceeded')
        matches = [item for item in archive.infolist() if item.filename in ('bin/CadenceStudio4.exe', './bin/CadenceStudio4.exe')]
        require(len(matches) == 1 and 0 < matches[0].file_size <= 268435456, 'Exactly one bounded actual EXE required')
        with archive.open(matches[0]) as stream:
            exe_sha = digest(stream)
        exe_bytes = matches[0].file_size
    require(exe_sha == manifest['executable_sha256'] == result['executable_sha256'], 'Actual EXE bytes differ from build and stage records')
    receipt = {'schema_version': 1, 'status': 'actual-retained-stage-metadata-and-all-companion-hashes-read', 'producer_run_id': RUN, 'artifact_id': ARTIFACT, 'original_source_commit': ORIGINAL, 'source_commit': ci, 'source_tree': TREE, 'build_number': 2005, 'run_number': 5, 'run_attempt': 1, 'stage_archive': ARCHIVE, 'stage_archive_sha256': sums[ARCHIVE], 'executable_sha256': exe_sha, 'executable_bytes': exe_bytes, 'source_json_sha256': SOURCE_JSON_SHA, 'source_patch_sha256': PATCH_SHA, 'original_files_hashed': len(sums), 'original_bytes_hashed': total, 'source_record_receipts': {name: {'bytes': (root / name).stat().st_size, 'sha256': sums[name]} for name in ('stage-manifest.json', 'cadence-build-result.json', 'cadence-build.json')}, 'application_executed': False, 'application_rebuilt': False, 'gui_qualified': False, 'msi_qualified': False, 'raw_outer_artifact_digest_recomputed': False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + '\n')
    print('CADENCE_2005_STAGE_RECEIPT_BEGIN')
    print(json.dumps(receipt, separators=(',', ':')))
    print('CADENCE_2005_STAGE_RECEIPT_END')

if __name__ == '__main__':
    main()
