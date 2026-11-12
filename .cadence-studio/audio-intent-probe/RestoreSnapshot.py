# SPDX-License-Identifier: GPL-3.0-only
"""Restore only reviewed source bytes into new directories, without executing.

The Windows wrapper authenticates the outer QA manifest before invoking this.
This helper separately pins the archive and its exact source-member manifest.
"""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import zipfile

SOURCE_COMMIT = '0f1b61397d7b00714f135ecc737c48cdc380c930'
SOURCE_TREE = '34bd415cc77469c6439e6274c8c8c556391ae7e1'
CONTROL_COMMIT = 'b02b41f4cbb31f43df073d6cdf5249a18d425a7e'
MANIFEST_SHA = '842c8b2e4b62ffde1032d840830f024f9e31aa1ea86fc2a4edfc9b81ba490c62'
ARCHIVE_SHA = '9c9dc097241dcbdc3a00bb903b1ec916683df576604d37440b2139fc334139e7'
BASE64_SHA = '00a7718bdfe47c845f982d504232da11d9f826c96d5ca7a82452b2b8c866eefc'
SUMS_SHA = '47398d2ef949b75ed1a92b7228c50cafb96179fd37c2b799110e33a1f9de8836'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def plain_file(path):
    path = Path(path)
    if not path.is_file() or path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
        raise ValueError('Expected an ordinary source file: ' + str(path))
    for parent in path.parents:
        if parent.is_symlink() or getattr(parent, 'is_junction', lambda: False)():
            raise ValueError('Linked source ancestor refused: ' + str(path))
    return path

def safe_name(name):
    p = PurePosixPath(name)
    if not name or p.is_absolute() or p.as_posix() != name or '..' in p.parts or any(c in name for c in '\\:\0'):
        raise ValueError('Invalid source member name: ' + name)
    return p

def load_manifest(data):
    if sha(data) != MANIFEST_SHA:
        raise ValueError('Pinned source manifest differs')
    obj = json.loads(data)
    if obj.get('source_commit') != SOURCE_COMMIT or obj.get('source_tree') != SOURCE_TREE or \
       obj.get('control_commit') != CONTROL_COMMIT or obj.get('candidate_files') != 180 or obj.get('control_files') != 6 or \
       len(obj.get('files', [])) != 186 or obj.get('translation_unit_count') != 39:
        raise ValueError('Source identity/count differs')
    seen = set()
    for row in obj['files']:
        p = safe_name(row['path'])
        if p.parts[0] not in ('candidate', 'control-before') or row['path'].casefold() in seen:
            raise ValueError('Unexpected/case-colliding source member')
        seen.add(row['path'].casefold())
        if type(row['bytes']) is not int or not 0 < row['bytes'] <= 1048576 or len(row['sha256']) != 64:
            raise ValueError('Source size/hash metadata differs')
    return obj

def exact_files(root, expected):
    actual = {}
    if root.is_symlink() or getattr(root, 'is_junction', lambda: False)():
        raise ValueError('Linked snapshot root refused')
    for file in root.rglob('*'):
        if file.is_symlink() or getattr(file, 'is_junction', lambda: False)():
            raise ValueError('Linked snapshot member refused')
        if file.is_file():
            actual[file.relative_to(root).as_posix()] = file
    if set(actual) != set(expected):
        raise ValueError('Snapshot has missing or unexpected files')
    checked = []
    for name, row in sorted(expected.items()):
        data = plain_file(actual[name]).read_bytes()
        if len(data) != row['bytes'] or sha(data) != row['sha256']:
            raise ValueError('Source bytes differ: ' + name)
        if row.get('git_blob_sha') and hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() != row['git_blob_sha']:
            raise ValueError('Git object identity differs: ' + name)
        checked.append(dict(path=name, bytes=len(data), sha256=sha(data)))
    return checked

def verify(snapshot, old_tree):
    manifest_path = plain_file(snapshot / 'source-manifest.json')
    manifest_bytes = manifest_path.read_bytes()
    manifest = load_manifest(manifest_bytes)
    expected = {row['path']: row for row in manifest['files']}
    # The unchanged internal manifest and checksum text are source metadata too.
    sums = plain_file(snapshot / 'SHA256SUMS.txt').read_bytes()
    if sha(sums) != SUMS_SHA:
        raise ValueError('Pinned internal checksum file differs')
    expected['source-manifest.json'] = dict(bytes=len(manifest_bytes), sha256=sha(manifest_bytes))
    expected['SHA256SUMS.txt'] = dict(bytes=len(sums), sha256=sha(sums))
    snapshot_checked = exact_files(snapshot, expected)
    checksum_records = {}
    for line in sums.decode().splitlines():
        digest, name = line.split('  ', 1)
        safe_name(name)
        if name in checksum_records or name not in expected or digest != expected[name]['sha256']:
            raise ValueError('Internal source checksums differ')
        checksum_records[name] = digest
    old_expected = {row['path'].removeprefix('candidate/'): row for row in manifest['files'] if row['path'].startswith('candidate/')}
    for row in manifest['files']:
        if row['path'].startswith('control-before/'):
            old_expected[row['path'].removeprefix('control-before/')] = row
    old_checked = exact_files(old_tree, old_expected)
    return dict(schema_version=1, verified=True, source_commit=SOURCE_COMMIT, source_tree=SOURCE_TREE,
                old_engine_commit=CONTROL_COMMIT, source_manifest_sha256=MANIFEST_SHA,
                snapshot_files=snapshot_checked, old_source_tree_files=old_checked,
                candidate_file_count=180, old_engine_overlays=6, old_tree_file_count=180,
                old_tree_scope='Six exact frozen engine files plus unchanged candidate dependencies, current tests and constructor friend')

def restore(encoded_file, snapshot, old_tree):
    for directory in (snapshot, old_tree):
        if directory.exists() or directory.is_symlink() or directory.resolve().is_relative_to(encoded_file.resolve()):
            raise ValueError('New distinct owned output directories required')
    if snapshot.resolve().is_relative_to(old_tree.resolve()) or old_tree.resolve().is_relative_to(snapshot.resolve()):
        raise ValueError('Snapshot/control output directories must be disjoint')
    encoded = plain_file(encoded_file).read_bytes()
    if len(encoded) != 626891 or sha(encoded) != BASE64_SHA:
        raise ValueError('Reviewed source archive transport differs')
    raw = base64.b64decode(b''.join(encoded.split()), validate=True)
    if len(raw) != 465321 or sha(raw) != ARCHIVE_SHA:
        raise ValueError('Reviewed source archive differs')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        if len(infos) != 188 or len({x.filename.casefold() for x in infos}) != 188:
            raise ValueError('Unexpected/colliding archive member count')
        manifest_bytes = archive.read('source-manifest.json')
        manifest = load_manifest(manifest_bytes)
        expected = {row['path']: row for row in manifest['files']}
        expected['source-manifest.json'] = dict(bytes=len(manifest_bytes), sha256=MANIFEST_SHA)
        sums = archive.read('SHA256SUMS.txt')
        expected['SHA256SUMS.txt'] = dict(bytes=len(sums), sha256=sha(sums))
        if {x.filename for x in infos} != set(expected) or sum(x.file_size for x in infos) > 4194304:
            raise ValueError('Unexpected archive names/size')
        for info in infos:
            safe_name(info.filename)
            if info.is_dir() or stat.S_ISLNK(info.external_attr >> 16) or info.file_size != expected[info.filename]['bytes']:
                raise ValueError('Invalid archive member kind/size')
            data = archive.read(info)
            if sha(data) != expected[info.filename]['sha256']:
                raise ValueError('Archive member bytes differ')
        snapshot.mkdir(parents=True, exist_ok=False)
        for info in infos:
            target = snapshot.joinpath(*PurePosixPath(info.filename).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as output:
                output.write(archive.read(info))
    shutil.copytree(snapshot / 'candidate', old_tree)
    for row in manifest['files']:
        if row['path'].startswith('control-before/'):
            target = old_tree / row['path'].removeprefix('control-before/')
            if not target.is_file() or target.is_symlink():
                raise ValueError('Old overlay would not replace exactly one newly owned source copy')
            target.write_bytes((snapshot / row['path']).read_bytes())
    return verify(snapshot, old_tree)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['restore', 'verify'])
    parser.add_argument('--source', type=Path)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--old-tree', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if args.operation == 'restore':
        if args.source is None:
            parser.error('--source is required for restore')
        report = restore(args.source, args.snapshot, args.old_tree)
    else:
        report = verify(args.snapshot, args.old_tree)
    with args.report.open('x', encoding='utf8') as output:
        json.dump(report, output, indent=2)
        output.write('\n')
    print(json.dumps(dict(verified=True, candidate_files=180, frozen_engine_files=6,
                         source_manifest_sha256=MANIFEST_SHA)))

if __name__ == '__main__':
    main()
