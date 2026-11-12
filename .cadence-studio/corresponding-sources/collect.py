#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Collect immutable source archives and original notices without running them."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request
import zipfile

MAX_NOTICE = 2 * 1024 * 1024
MAX_NOTICES_TOTAL = 64 * 1024 * 1024
LEGAL_NAME = re.compile(r'^(?:licen[cs]e|copying|copyright|notice|authors|ofl)(?:[._-].*)?$', re.I)


def sha(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def safe_relative(value: str) -> str:
    value = value.replace('\\', '/')
    if not value or value.startswith('/') or ':' in value or any(ord(c) < 32 for c in value):
        raise ValueError('Unsafe source member path')
    parts = PurePosixPath(value).parts
    if '..' in parts or any(not part or part == '.' for part in parts):
        raise ValueError('Unsafe source path component')
    return '/'.join(parts)


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')


class Archive:
    def __init__(self, path: Path, spec: dict, cmake: str):
        self.path, self.spec, self.cmake = path, spec, cmake
        self.tar = self.zip = None
        if spec['format'] == 'tar':
            self.tar = tarfile.open(path, 'r:*')
            self.members = {m.name.rstrip('/'): m for m in self.tar.getmembers() if m.isfile()}
        elif spec['format'] == 'zip':
            self.zip = zipfile.ZipFile(path)
            self.members = {m.filename.rstrip('/'): m for m in self.zip.infolist() if not m.is_dir()}
        elif spec['format'] == '7z':
            result = subprocess.run([cmake, '-E', 'tar', 'tf', str(path)], check=True,
                                    capture_output=True, text=True, timeout=60)
            if len(result.stdout) > 8 * 1024 * 1024:
                raise ValueError('Oversized original source archive listing')
            self.members = {line.rstrip('/'): None for line in result.stdout.splitlines() if not line.endswith('/')}
        else:
            raise ValueError('Unsupported source archive format')
        if not self.members or len(self.members) > 150000:
            raise ValueError('Missing or oversized source member list')
        for name in self.members:
            safe_relative(name)
            if spec['root'] and not name.startswith(spec['root'] + '/'):
                raise ValueError('Source archive root differs from the pinned archive')

    def close(self):
        if self.tar:
            self.tar.close()
        if self.zip:
            self.zip.close()

    def relative(self, name):
        return name[len(self.spec['root']) + 1:] if self.spec['root'] else name

    def read(self, name: str) -> bytes:
        if name not in self.members:
            raise ValueError('Declared source notice missing: ' + name)
        if self.tar:
            member = self.members[name]
            if member.size > MAX_NOTICE:
                raise ValueError('Notice exceeds the source text bound: ' + name)
            data = self.tar.extractfile(member).read(MAX_NOTICE + 1)
        elif self.zip:
            member = self.members[name]
            if member.file_size > MAX_NOTICE or ((member.external_attr >> 16) & 0o170000) == 0o120000:
                raise ValueError('Oversized or linked source notice: ' + name)
            data = self.zip.read(member)
        else:
            # Only hash-authenticated original SDK archives reach this path.
            # Extract a single explicitly selected relative notice into a new
            # private directory; never execute or extract the SDK as a whole.
            with tempfile.TemporaryDirectory(prefix='cadence-sdk-notice-') as tmp:
                subprocess.run([self.cmake, '-E', 'tar', 'xf', str(self.path), name], cwd=tmp,
                               check=True, capture_output=True, timeout=60)
                source = Path(tmp) / name
                for candidate in (source, *source.parents):
                    if candidate.is_symlink():
                        raise ValueError('Linked SDK notice refused')
                    if candidate == Path(tmp):
                        break
                if source.stat().st_size > MAX_NOTICE:
                    raise ValueError('Oversized SDK notice')
                data = source.read_bytes()
        if len(data) > MAX_NOTICE:
            raise ValueError('Notice exceeded the byte bound')
        return data


def fetch(spec: dict, destination: Path, caches: list[Path], offline: bool) -> dict:
    for cache in caches:
        candidate = cache / spec['archive']
        if candidate.is_file() and not candidate.is_symlink():
            if candidate.stat().st_size != spec['archive_bytes'] or sha(candidate) != spec['sha256']:
                raise ValueError('Cached archive failed the immutable byte/SHA pin: ' + spec['id'])
            shutil.copyfile(candidate, destination)
            return {'transport': 'verified local source archive', 'network_used': False}
    if offline:
        raise ValueError('Pinned source archive absent from offline caches: ' + spec['id'])
    parsed = urllib.parse.urlparse(spec['url'])
    if parsed.scheme != 'https' or parsed.hostname not in {'codeload.github.com', 'github.com', 'raw.githubusercontent.com'}:
        raise ValueError('Source URL is outside the explicit original-host set')
    request = urllib.request.Request(spec['url'], headers={'User-Agent': 'Cadence-corresponding-source-collector/1'})
    size = 0
    with urllib.request.urlopen(request, timeout=60) as response, destination.open('xb') as stream:
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if size > spec['archive_bytes']:
                raise ValueError('Source download exceeds its measured immutable length')
            stream.write(chunk)
    if size != spec['archive_bytes'] or sha(destination) != spec['sha256']:
        raise ValueError('Source download failed the measured immutable byte/SHA pin: ' + spec['id'])
    return {'transport': 'HTTPS original pinned URL', 'network_used': True}


def collect_notices(archive: Archive, output: Path) -> dict:
    selected = set()
    attribution_records = []
    nonstandard_json = []
    missing_references = []
    for name in archive.members:
        relative = archive.relative(name)
        if LEGAL_NAME.fullmatch(PurePosixPath(relative).name) or 'LICENSES' in PurePosixPath(relative).parts:
            selected.add(name)
        if PurePosixPath(relative).name != 'qt_attribution.json':
            continue
        selected.add(name)
        raw = archive.read(name)
        try:
            values = json.loads(raw)
        except json.JSONDecodeError:
            # Some upstream files contain literal control whitespace within
            # JSON strings. Preserve their original bytes and disclose this
            # parse mode; never edit the original attribution file.
            values = json.loads(raw, strict=False)
            nonstandard_json.append(relative)
        for item in values if isinstance(values, list) else [values]:
            references = item.get('LicenseFiles', [])
            if isinstance(references, str):
                references = [references]
            if item.get('LicenseFile'):
                references = [*references, item['LicenseFile']]
            record = {'source': relative, 'id': item.get('Id'), 'name': item.get('Name'),
                      'license_id': item.get('LicenseId'), 'license_description': item.get('License'),
                      'qt_parts': item.get('QtParts', []), 'qt_usage': item.get('QtUsage'),
                      'notice_members': []}
            for reference in references:
                resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), reference))
                safe_relative(resolved)
                if resolved not in archive.members:
                    missing_references.append({'source': relative, 'reference': reference, 'resolved': resolved})
                else:
                    selected.add(resolved)
                    record['notice_members'].append(archive.relative(resolved))
            attribution_records.append(record)
    files = []
    total = 0
    # TAR order avoids repeatedly decompressing the large archive backwards.
    ordered = sorted(selected, key=lambda name: archive.members[name].offset_data if archive.tar else name)
    for name in ordered:
        data = archive.read(name)
        total += len(data)
        if total > MAX_NOTICES_TOTAL:
            raise ValueError('Notice collection exceeds its explicit text budget')
        relative = safe_relative(archive.relative(name))
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        files.append({'file': relative, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    return {'files': files, 'bytes': total, 'attributions': attribution_records,
            'upstream_attributions_parsed_with_literal_controls': nonstandard_json,
            'missing_declared_license_files': missing_references,
            'scope': 'All original source notices/attributions found; metadata alone does not prove each third party is selected in the Windows binaries.'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lock', type=Path, default=Path(__file__).with_name('sources.lock.json'))
    parser.add_argument('--inventory', type=Path, default=Path(__file__).with_name('stage-inventory-2002.json'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cache', action='append', type=Path, default=[])
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--cmake', default=shutil.which('cmake'))
    parser.add_argument('--require-complete-distribution', action='store_true')
    args = parser.parse_args()
    if args.output.exists() or not args.cmake:
        parser.error('A new output directory and CMake (SDK archive reader) are required')
    lock = json.loads(args.lock.read_text())
    if lock.get('schema_version') != 1 or len(lock.get('archives', [])) != 11:
        raise ValueError('Expected the reviewed candidate profile with eleven immutable archives')
    if sha(args.inventory) != lock['binary_inventory_source']['inventory_sha256']:
        raise ValueError('Original binary inventory differs from the reviewed source-lock anchor')
    if args.require_complete_distribution and lock['remaining_binary_provenance']:
        parser.error('Final distribution refused: unresolved binary source/build provenance in this candidate profile')
    ids, filenames = set(), set()
    for item in [*lock['archives'], *lock.get('supplementary_notices', [])]:
        if not re.fullmatch(r'[a-z0-9-]+', item['id']) or item['id'] in ids or item['archive'] in filenames or \
            '/' in item['archive'] or '\\' in item['archive'] or not re.fullmatch(r'[a-f0-9]{64}', item['sha256']) or \
            not isinstance(item['archive_bytes'], int) or not 0 < item['archive_bytes'] <= 140 * 1024 * 1024:
            raise ValueError('Invalid or duplicate immutable archive entry')
        ids.add(item['id']); filenames.add(item['archive'])
    if sum(x['archive_bytes'] for x in lock['archives']) > 350 * 1024 * 1024:
        raise ValueError('The complete source collection exceeds its reviewed byte budget')
    args.output.mkdir(parents=True)
    archives = args.output / 'archives'; archives.mkdir()
    notices = args.output / 'notices'; notices.mkdir()
    report = {'schema_version': 1, 'profile': lock['profile'], 'source_lock_sha256': sha(args.lock),
              'source_program_or_library_executed': False, 'developer_archive_tool_executed': True,
              'python_version': sys.version, 'cmake_archive_reader': args.cmake,
              'source_archives_verified': False,
              'complete_distribution_ready': False, 'components': [], 'errors': [],
              'remaining_binary_provenance': lock['remaining_binary_provenance']}
    try:
        for item in lock['archives']:
            target = archives / item['archive']
            transport = fetch(item, target, args.cache, args.offline)
            reader = Archive(target, item, args.cmake)
            try:
                original_notices = collect_notices(reader, notices / item['id'])
            finally:
                reader.close()
            result = {'id': item['id'], 'archive': item['archive'], 'bytes': target.stat().st_size,
                      'sha256': sha(target), **transport, 'notices': original_notices}
            report['components'].append(result)
            print(json.dumps({'id': item['id'], 'sha256': result['sha256'],
                              'original_notice_files': len(original_notices['files']),
                              'attribution_entries': len(original_notices['attributions']),
                              'missing_notice_references': len(original_notices['missing_declared_license_files'])}), flush=True)
            if original_notices['missing_declared_license_files']:
                raise ValueError('An original Qt attribution declares missing notice files; collection is not complete: ' + item['id'])
        supplementary = []
        for item in lock.get('supplementary_notices', []):
            folder = notices / item['component']; folder.mkdir(exist_ok=True)
            target = folder / safe_relative(item['notice_file'])
            transport = fetch(item, target, args.cache, args.offline)
            supplementary.append({'file': item['notice_file'], 'bytes': target.stat().st_size,
                                  'sha256': sha(target), 'original_bytes': True, **transport})
        if supplementary:
            data = lock['vendored_w3c_mnx']
            target = notices / 'w3c-mnx' / data['generated_attribution_file']
            target.write_text(data['generated_attribution'], encoding='utf-8')
            supplementary.append({'file': target.name, 'bytes': target.stat().st_size,
                                  'sha256': sha(target), 'original_bytes': False,
                                  'scope': 'New attribution naming exact specification/version as required by W3C CLA2.2'})
            report['components'].append({'id': 'w3c-mnx', 'source_kind': 'Specification data already vendored in mnxdom',
                'notices': {'files': supplementary, 'bytes': sum(x['bytes'] for x in supplementary),
                            'attributions': [], 'missing_declared_license_files': [],
                            'scope': 'Original specification footer and CLA, with explicit name/version attribution; no MIT relicensing of W3C material'}})
        shutil.copyfile(args.lock, args.output / 'sources.lock.json')
        shutil.copyfile(args.inventory, args.output / 'original-stage-inventory.json')
        report['source_archives_verified'] = True
        if args.require_complete_distribution and report['remaining_binary_provenance']:
            raise ValueError('The final distribution gate refuses unresolved binary source/build provenance')
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        report['errors'].append(str(error))
    write_json(args.output / 'collection-report.json', report)
    sums = []
    for file in sorted(args.output.rglob('*')):
        if file.is_file():
            sums.append(sha(file) + '  ' + file.relative_to(args.output).as_posix())
    (args.output / 'SHA256SUMS.txt').write_text('\n'.join(sums) + '\n', encoding='ascii')
    print('CADENCE_CORRESPONDING_SOURCES_REPORT_BEGIN')
    print(json.dumps({k: v for k, v in report.items() if k != 'components'}, ensure_ascii=False))
    print('CADENCE_CORRESPONDING_SOURCES_REPORT_END')
    return 0 if report['source_archives_verified'] and not report['errors'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
