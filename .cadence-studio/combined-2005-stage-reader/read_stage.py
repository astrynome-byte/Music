# SPDX-License-Identifier: GPL-3.0-only
"""Read only the already retained full2005 stage; never execute staged files."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
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

# Only ZIP members with these extensions are hashed by the added inventory.
# A .lib can be a COFF archive; extensions do not establish PE format or ABI.
BINARY_SUFFIXES = ('.dll', '.exe', '.lib')
MAX_STAGE_MEMBER_BYTES = 500 * 1024 * 1024
MAX_STAGE_BINARY_BYTES = 1024 * 1024 * 1024
MAX_STAGE_MEMBERS = 100000


def safe_stage_member(item):
    """Return a canonical relative ZIP path; reject Windows/Unix aliases/links."""
    raw = item.filename
    require(getattr(item, 'orig_filename', raw) == raw, 'NUL-truncated stage ZIP name')
    require(raw and len(raw) <= 4096 and not raw.startswith('/') and
            not re.search(r'[\\:\x00-\x1f\x7f<>"|?*]', raw), 'Unsafe stage ZIP name')
    name = raw[2:] if raw.startswith('./') else raw
    directory = item.is_dir()
    name = name[:-1] if directory else name
    parts = name.split('/')
    require(all(part and part not in ('.', '..') and len(part) <= 255 and
                not part.endswith((' ', '.')) and
                re.fullmatch(r'(?:con|prn|aux|nul|com[1-9¹²³]|lpt[1-9¹²³])(?:\..*)?', part, re.IGNORECASE) is None
                for part in parts), 'Unsafe stage ZIP path component')
    mode = (item.external_attr >> 16) & 0xffff
    kind = stat.S_IFMT(mode)
    require(kind in (0, stat.S_IFDIR if directory else stat.S_IFREG) and
            not (item.external_attr & 0x400), 'Linked/special stage ZIP member')
    require(not (item.flag_bits & 1), 'Encrypted stage ZIP member')
    require(0 <= item.file_size <= MAX_STAGE_MEMBER_BYTES and
            (not directory or item.file_size == 0), 'Stage ZIP member exceeds 500 MiB bound')
    return name


def inventory_stage_zip(archive):
    """Read a bounded archive inventory, without extraction or staged execution."""
    items = archive.infolist()
    require(len(items) <= MAX_STAGE_MEMBERS, 'Stage ZIP member bound exceeded')
    members = []
    seen = {}
    binary_total = 0
    # Validate every entry before reading any added binary stream. Case-folding
    # deliberately rejects aliases that could collide on the Windows target.
    for item in items:
        name = safe_stage_member(item)
        key = name.casefold()
        require(key not in seen, 'Duplicate/case-colliding stage ZIP path: ' + name)
        seen[key] = item.is_dir()
        binary = not item.is_dir() and PurePosixPath(name).suffix.casefold() in BINARY_SUFFIXES
        if binary:
            binary_total += item.file_size
            require(binary_total <= MAX_STAGE_BINARY_BYTES, 'Stage ZIP binary total exceeds 1 GiB bound')
        members.append((name, item, binary))
    for name, item, binary in members:
        for parent in PurePosixPath(name).parents:
            if str(parent) != '.':
                require(seen.get(str(parent).casefold(), True), 'Stage ZIP file/directory collision: ' + name)
    files = []
    websocket_members = []
    qml_members = []
    nested_bin_members = []
    direct_qt6 = []
    for name, item, binary in sorted(members, key=lambda row: row[0]):
        parts = [part.casefold() for part in PurePosixPath(name).parts]
        qml_subtree = any(part in ('qml', 'qml6') for part in parts[:-1])
        nested_bin = len(parts) > 2 and parts[0] == 'bin'
        direct_qt6_dll = bool(re.fullmatch(r'bin/qt6[^/]*\.dll', name, re.IGNORECASE)) and binary
        if binary:
            sha = hashlib.sha256()
            count = 0
            with archive.open(item) as stream:
                for data in iter(lambda: stream.read(1024 * 1024), b''):
                    count += len(data)
                    require(count <= item.file_size and count <= MAX_STAGE_MEMBER_BYTES,
                            'Stage ZIP binary stream exceeds declared/bounded size')
                    sha.update(data)
            require(count == item.file_size, 'Stage ZIP binary stream size mismatch')
            row = {'path': name, 'zip_path': item.filename, 'bytes': count, 'sha256': sha.hexdigest(),
                   'location': ('direct-bin-qt6-dll' if direct_qt6_dll else
                                'qml-subtree' if qml_subtree else
                                'nested-bin-binary' if nested_bin else 'other-binary')}
            files.append(row)
            if direct_qt6_dll:
                direct_qt6.append(name)
            if nested_bin:
                nested_bin_members.append(name)
        if qml_subtree or (item.is_dir() and parts[-1] in ('qml', 'qml6')):
            qml_members.append(name)
        if 'websocket' in name.casefold():
            websocket_members.append({'path': name, 'zip_path': item.filename,
                                      'directory': item.is_dir(), 'bytes': item.file_size,
                                      'binary_sha256_recorded': binary, 'qml_subtree': qml_subtree})
    return {'schema_version': 1, 'scope': 'all stage ZIP names; SHA-256 of every .dll/.exe/.lib member',
            'member_count': len(items), 'binary_extensions': list(BINARY_SUFFIXES),
            'max_member_bytes': MAX_STAGE_MEMBER_BYTES, 'max_binary_bytes': MAX_STAGE_BINARY_BYTES,
            'binary_count': len(files), 'binary_bytes_hashed': binary_total, 'files': files,
            'direct_bin_qt6_dll_paths': direct_qt6, 'direct_bin_qt6_dll_count': len(direct_qt6),
            'direct_bin_qt6_dll_count_equals_35': len(direct_qt6) == 35,
            'qml_member_paths': qml_members, 'nested_bin_binary_paths': nested_bin_members,
            'location_classification_basis': 'ZIP path only; nested bin binaries can include plugins; no SDK inference',
            'websocket_name_match': 'case-insensitive substring websocket, all entries and extensions',
            'websocket_named_members': websocket_members,
            'qt6_websockets_dll_paths': [row['path'] for row in websocket_members if not row['directory'] and PurePosixPath(row['path']).name.casefold() == 'qt6websockets.dll'],
            'qml_websockets_paths': [row['path'] for row in websocket_members if row['qml_subtree'] or 'qmlwebsocket' in row['path'].casefold()],
            'sdk_inspected': False, 'file_format_or_abi_validated': False,
            'archive_extracted': False, 'staged_code_executed': False}


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
    # The frozen source, original root hashes and EXE checks above stay mandatory.
    with zipfile.ZipFile(root / ARCHIVE) as archive:
        receipt['stage_binary_inventory'] = inventory_stage_zip(archive)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + '\n')
    print('CADENCE_2005_STAGE_RECEIPT_BEGIN')
    print(json.dumps(receipt, separators=(',', ':')))
    print('CADENCE_2005_STAGE_RECEIPT_END')

if __name__ == '__main__':
    main()
