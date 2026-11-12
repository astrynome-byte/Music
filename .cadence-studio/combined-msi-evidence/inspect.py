#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Verify retained delivery files, inventory its stage and relay original PNGs.

Read-only data: no MSI installation, executable loading, codec or source build.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import zipfile

EXPECTED_MSI = '2d0d4b82ced312b22fea36470aec4c2677060135dd6cf8fb43bb25777953673e'
EXPECTED_STAGE = '18bdda165ddcdef884949bf84ae398e6ee11619439161d4a1b84404edf307b46'
PNG_HASHES = {'e4ef009a7adc9f532366b5b85cd704068e6e956f90b6462baf30e2a0e42c43a0',
              '214eb2d63a5e8127a3cb93572ca5c31273b3794923f68ab73c8496b96a9dcc70'}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def emit(kind, data):
    print('CADENCE_MSI2002_' + kind + '_BEGIN', flush=True)
    print(json.dumps(data, ensure_ascii=False, sort_keys=True), flush=True)
    print('CADENCE_MSI2002_' + kind + '_END', flush=True)


def normalized(name):
    name = name.replace('\\', '/')
    while name.startswith('./'):
        name = name[2:]
    name = name.rstrip('/')
    if name.startswith('/') or ':' in name or '..' in name.split('/'):
        raise ValueError('Unsafe relative path')
    return name


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--qa', type=Path, required=True)
    p.add_argument('--delivery', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    qa, downloaded, output = a.qa.resolve(strict=True), a.delivery.resolve(strict=True), a.output.resolve()
    if output == qa or output == downloaded or output.is_relative_to(qa) or output.is_relative_to(downloaded):
        p.error('Separate new output required')
    output.mkdir(parents=True, exist_ok=False)
    result = {'schema_version': 1, 'run_id': 43123411562, 'qa_artifact_id': 13902581012,
              'delivery_artifact_id': 13902536112, 'reader_only': True, 'program_executed': False,
              'audio_reencoded': False, 'images_modified': False, 'passed': False, 'errors': []}
    try:
        msis = list(downloaded.rglob('CadenceStudio-4.7.6-cadence.2002-x86_64.msi'))
        if len(msis) != 1 or digest(msis[0]) != EXPECTED_MSI:
            raise ValueError('Expected exactly the originally installed and tested MSI bytes')
        root = msis[0].parent
        result['installer'] = {'file': msis[0].name, 'bytes': msis[0].stat().st_size, 'sha256': EXPECTED_MSI,
                               'version_from_original_windows_installer_report': '4.7.6.2002'}
        sums = root / 'SHA256SUMS.txt'
        records = []
        for line in sums.read_text(encoding='utf-8-sig').splitlines():
            match = re.fullmatch(r'([a-f0-9]{64})  (.+)', line)
            if not match:
                raise ValueError('Invalid delivery checksum line')
            relative = normalized(match[2]); path = root / relative
            if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root) or digest(path) != match[1]:
                raise ValueError('Delivery checksum mismatch/missing file: ' + relative)
            records.append({'file': relative, 'bytes': path.stat().st_size, 'sha256': match[1]})
        names = {x['file'] for x in records}
        if len(names) != len(records):
            raise ValueError('Duplicate delivery checksum entry')
        extras = [path.relative_to(root).as_posix() for path in root.rglob('*') if path.is_file()
                  and path != sums and not path.relative_to(root).as_posix().startswith('_CPack_Packages/')
                  and path.relative_to(root).as_posix() not in names]
        if extras:
            raise ValueError('Unhashed delivered files: ' + repr(extras))
        result['checksums'] = {'sha256': digest(sums), 'verified_file_count': len(records), 'records': records}
        (output / 'SHA256SUMS.original.txt').write_bytes(sums.read_bytes())
        emit('DELIVERY', {'installer': result['installer'], 'checksum_file_sha256': digest(sums),
                          'verified_file_count': len(records), 'records': records})
        result['reports'] = []
        for path in sorted(root.glob('*.json')):
            if path.stat().st_size > 200000:
                continue
            raw = path.read_bytes()
            entry = {'file': path.name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                     'report': json.loads(raw.decode('utf-8-sig'))}
            result['reports'].append(entry); emit('REPORT', entry)
            (output / path.name).write_bytes(raw)
        stage_map = json.loads((root / 'stage-file-sha256.json').read_text(encoding='utf-8-sig'))
        stage_map = {normalized(name): value for name, value in stage_map.items()}
        archive_path = root / 'original-stage/CadenceStudio-v4.7.6-combined-system-aac-stage-build-2002-attempt-1-x64.zip'
        if digest(archive_path) != EXPECTED_STAGE:
            raise ValueError('Original stage archive changed')
        inventory = {'stage_archive_sha256': EXPECTED_STAGE, 'binaries': [], 'fonts': [], 'sounds': [], 'notices': []}
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue
                name = normalized(member.filename); lower = name.lower()
                entry = {'file': name, 'bytes': member.file_size, 'sha256': stage_map.get(name)}
                if name not in stage_map:
                    raise ValueError('Stage ZIP member absent from original pre/post packaging inventory: ' + name)
                if lower.endswith(('.dll', '.exe', '.lib')):
                    inventory['binaries'].append(entry)
                if lower.endswith(('.ttf', '.otf', '.woff', '.woff2')):
                    inventory['fonts'].append(entry)
                if 'sound' in PurePosixPath(lower).parts or lower.endswith(('.sf2', '.sf3')):
                    inventory['sounds'].append(entry)
                if any(word in lower for word in ('license', 'licence', 'copying', 'notice', 'ofl', 'attribution')):
                    if member.file_size <= 40000 and lower.endswith(('.txt', '.html', '.json', '.md', '.rtf')):
                        raw = archive.read(member)
                        if hashlib.sha256(raw).hexdigest() != entry['sha256']:
                            raise ValueError('Notice hash differs from original stage inventory')
                        entry['text'] = raw.decode('utf-8-sig', errors='replace')
                    inventory['notices'].append(entry)
        inventory['classification_note'] = 'DLL names identify external payload only; static code/resources require original build graph and source audit.'
        result['stage_inventory'] = inventory
        emit('INVENTORY', inventory)
        result['qa_reports'] = []
        for path in sorted(qa.rglob('*.json')):
            if path.name not in {'msi-install-report.json', 'gui-report.json', 'video-unavailable-report.json'} or path.stat().st_size > 200000:
                continue
            raw = path.read_bytes()
            entry = {'file': path.relative_to(qa).as_posix(), 'sha256': hashlib.sha256(raw).hexdigest(),
                     'report': json.loads(raw.decode('utf-8-sig'))}
            result['qa_reports'].append(entry); emit('REPORT', entry)
        images = []
        for path in sorted(qa.rglob('actual-home-or-intro.png')):
            raw = path.read_bytes(); checksum = hashlib.sha256(raw).hexdigest()
            if checksum not in PNG_HASHES or len(raw) > 750000 or not raw.startswith(b'\x89PNG\r\n\x1a\n'):
                raise ValueError('Unexpected or oversized original GUI screenshot')
            entry = {'file': path.relative_to(qa).as_posix(), 'bytes': len(raw), 'sha256': checksum}
            images.append(entry); emit('PNG_META', entry)
            encoded = base64.b64encode(raw).decode('ascii')
            print('CADENCE_MSI2002_PNG_BEGIN ' + checksum, flush=True)
            for index in range(0, len(encoded), 12000):
                print('CADENCE_MSI2002_PNG_CHUNK ' + checksum + ' ' + encoded[index:index + 12000], flush=True)
            print('CADENCE_MSI2002_PNG_END ' + checksum, flush=True)
            (output / (checksum + '.png')).write_bytes(raw)
        if len(images) != 2 or {x['sha256'] for x in images} != PNG_HASHES:
            raise ValueError('Both original stage and installed screenshots required')
        result['screenshots'] = images
        result['passed'] = True
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        result['errors'].append(str(error))
    (output / 'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    emit('SUMMARY', {k: v for k, v in result.items() if k not in {'reports', 'qa_reports', 'stage_inventory', 'checksums'}})
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
