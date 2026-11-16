#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare a Windows administrative MSI extraction with retained 2008 bytes."""
from pathlib import Path
import argparse
import hashlib
import json
import stat

INVENTORY_SHA = '7b3b721f01b0a57610b9dcc1cd72bd15e50747dcd751fcd5e31cfbb96a81a4a4'
EXE_SHA = '13cd4e6d2f408d2e64b187d4c3bff1188ff4192ac7b670d3a12373bbeb37f6cd'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def plain(path):
    path = path.absolute()
    for parent in (path, *path.parents):
        info = parent.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400,
                'Linked or reparse path refused')
    return path


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--extracted-root', required=True, type=Path)
    parser.add_argument('--measured-inventory', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    inventory = plain(args.measured_inventory)
    require(inventory.is_file() and inventory.stat().st_size == 530785
            and sha(inventory) == INVENTORY_SHA, 'Exact authenticated runtime inventory required')
    expected = json.loads(inventory.read_text(encoding='utf-8'))['runtime_files']
    require(len(expected) == 2712, 'Expected exactly 2712 runtime files')
    root = plain(args.extracted_root)
    require(root.is_dir() and not args.output.exists(), 'New report and existing extraction required')
    candidates = []
    # Walk without following links; reject all links before considering an EXE.
    inspected = 0
    for path in root.rglob('*'):
        inspected += 1
        require(inspected <= 20000, 'Bounded extraction tree required')
        plain(path)
        if path.is_file() and path.name == 'CadenceStudio4.exe' and path.parent.name == 'bin':
            candidates.append(path)
    require(len(candidates) == 1 and sha(candidates[0]) == EXE_SHA, 'One exact 2008 executable required')
    runtime = candidates[0].parent.parent
    actual, seen = {}, set()
    for path in sorted(runtime.rglob('*')):
        plain(path)
        if path.is_dir():
            continue
        require(path.is_file(), 'Regular runtime files required')
        name = path.relative_to(runtime).as_posix()
        require(name.casefold() not in seen and len(actual) < 10000, 'Duplicate or excessive runtime tree')
        seen.add(name.casefold())
        actual[name] = {'bytes': path.stat().st_size, 'sha256': sha(path)}
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    changed = sorted(name for name in set(expected) & set(actual) if expected[name] != actual[name])
    notice_names = [name for name in expected if name.startswith(('licenses/', 'doc/'))]
    require(len(notice_names) == 338, 'Expected338 original notice/document files')
    notices_verified = sum(actual.get(name) == expected[name] for name in notice_names)
    no_local_icu = not any(name.casefold() == 'bin/icuuc.dll' for name in actual)
    exact = actual == expected
    report = {'schema_version': 1, 'scope': 'Administrative MSI extraction versus exact retained runtime; no application execution',
              'source': 'public-MSI-2008', 'runtime_root': str(runtime),
              'expected_count': 2712, 'actual_count': len(actual), 'exact_runtime_match': exact,
              'missing': missing, 'extra': extra, 'changed': changed,
              'inventory_sha256': INVENTORY_SHA, 'executable_sha256': EXE_SHA,
              'notice_files_verified': notices_verified, 'expected_notice_files': 338,
              'local_icuuc_absent': no_local_icu,
              'source_original_commit': 'a2b7abaf045a8f3cb84ec2953d9e0e51b9e78903',
              'source_ci_commit': '95cebb22fe6cbde22919c94f2b480bd14c3eb8de',
              'application_executed': False, 'portable_profile_qualified': False}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    raise SystemExit(0 if exact else 1)


if __name__ == '__main__':
    main()
