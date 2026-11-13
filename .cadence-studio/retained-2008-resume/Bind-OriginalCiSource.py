#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Restore only verified original CI commit metadata in a new clean source clone.

No application or source bytes are changed. The exact commit object was recovered
from the original tree/parent/message/timestamp and matches its retained SHA1.
Keep the new Bootstrap receipt untouched and emit a separate binding receipt.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess

CI = '95cebb22fe6cbde22919c94f2b480bd14c3eb8de'
TREE = 'c5452043983a048ef0aeef085615af903de3f5b0'
ORIGINAL = 'a2b7abaf045a8f3cb84ec2953d9e0e51b9e78903'
OBJECT_SHA256 = 'ac72bad8089d200e6ac1f2f7e6eb2c4b65beab1af001d631f4780adcc5763c88'


def git(root, *args, data=None, check=True):
    result = subprocess.run(['git', '-C', str(root), *args], input=data,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check)
    return result.stdout.decode().strip() if check else result


def object_bytes(path):
    raw = path.read_bytes()
    if len(raw) != 317 or hashlib.sha256(raw).hexdigest() != OBJECT_SHA256:
        raise ValueError('Exact recovered original CI metadata object required')
    if hashlib.sha1(b'commit ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() != CI:
        raise ValueError('Recovered metadata does not match the actual original CI commit')
    if not raw.startswith(('tree ' + TREE + '\n').encode()):
        raise ValueError('Original source tree differs')
    return raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--object', type=Path, default=Path(__file__).with_name('original-ci-commit.object'))
    parser.add_argument('--source-root', type=Path)
    parser.add_argument('--bootstrap', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    raw = object_bytes(args.object)
    if args.verify_only:
        print(json.dumps({'scope': 'Exact original CI metadata bytes only; no source or Git mutation',
                          'commit': CI, 'tree': TREE, 'sha256': OBJECT_SHA256, 'passed': True}))
        return
    if os.name != 'nt' or struct.calcsize('P') != 8 or os.environ.get('GITHUB_ACTIONS') != 'true' \
            or os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted' or os.environ.get('GITHUB_REPOSITORY') != 'astrynome-byte/Music':
        raise ValueError('Only a new disposable hosted Windows source clone may be bound')
    if not all((args.source_root, args.bootstrap, args.output)):
        raise ValueError('Source, original new-bootstrap receipt and new output are required')
    root = args.source_root.resolve(strict=True)
    expected_root = (Path(os.environ['GITHUB_WORKSPACE']) / 'cadence-src').resolve()
    output = args.output.absolute()
    if root != expected_root or root.is_symlink() or not (root / '.git').is_dir():
        raise ValueError('Only the new cadence-src clone in this workflow is permitted')
    if output.exists() or output.is_symlink() or not output.parent.is_dir() \
            or not output.is_relative_to(Path(os.environ['RUNNER_TEMP']).resolve()):
        raise ValueError('New owned binding receipt required')
    bootstrap_raw = args.bootstrap.read_bytes()
    bootstrap = json.loads(bootstrap_raw.decode('utf-8-sig'))
    before = git(root, 'rev-parse', 'HEAD')
    if bootstrap['original_source_commit'] != ORIGINAL or bootstrap['source_tree'] != TREE \
            or bootstrap['ci_source_commit'] != before:
        raise ValueError('New Bootstrap source receipt does not identify the current exact clone')
    if git(root, 'rev-parse', 'HEAD^{tree}') != TREE or git(root, 'status', '--porcelain', '--untracked-files=all'):
        raise ValueError('Source must be clean and have the original exact tree')
    if git(root, 'symbolic-ref', '--quiet', 'HEAD', check=False).returncode != 1:
        raise ValueError('A detached new CI clone is required; no branch is changed')
    actual = git(root, 'hash-object', '-t', 'commit', '-w', '--stdin', data=raw)
    if actual != CI:
        raise ValueError('Git rejected the original metadata identity')
    # Both commits name the identical tree, so update only the detached HEAD.
    # No checkout/reset, source rewrite or original receipt rewriting occurs.
    git(root, 'update-ref', '--no-deref', 'HEAD', CI, before)
    if git(root, 'rev-parse', 'HEAD') != CI or git(root, 'rev-parse', 'HEAD^{tree}') != TREE \
            or git(root, 'status', '--porcelain', '--untracked-files=all'):
        raise ValueError('Original metadata binding did not preserve the clean source tree')
    if args.bootstrap.read_bytes() != bootstrap_raw:
        raise ValueError('Original new-Bootstrap receipt changed unexpectedly')
    receipt = {'scope': 'Original exact CI Git metadata rebound in new clone; no app compilation or source-byte changes',
               'source_root': str(root), 'original_source_commit': ORIGINAL, 'source_tree': TREE,
               'new_bootstrap_ci_commit_before': before, 'checked_out_original_ci_commit': CI,
               'original_commit_object_sha256': OBJECT_SHA256,
               'new_bootstrap_receipt_sha256': hashlib.sha256(bootstrap_raw).hexdigest(),
               'bootstrap_record_not_modified': True, 'source_clean_before_and_after': True,
               'source_or_application_bytes_modified': False, 'application_compiled': False}
    args.output.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
