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
import struct
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


# Data-only PE dependency reader: never LoadLibrary, execute, or extract a PE.
PE_TARGET_DLLS = ('icuuc.dll', 'dxcompiler.dll', 'dxil.dll', 'd3dcompiler_47.dll')
PE_MAX_SECTIONS = 96
PE_MAX_DESCRIPTORS = 4096
PE_MAX_THUNKS = 65536
PE_MAX_EXPORTS = 65536
PE_MAX_NAME = 4096
PE_MAX_DIRECTORY_BYTES = 16 * 1024 * 1024
PE_READ_CHUNK = 1024 * 1024
PE_MAX_TEXT_BYTES = 4 * 1024 * 1024
PE_MAX_REPORT_BYTES = 16 * 1024 * 1024


class PeData:
    def __init__(self, data):
        self.data = data
        self.sections = []
        self.thunks_read = 0
        self.text_bytes = 0
        require(len(data) >= 64 and data[:2] == b'MZ', 'PE DOS header missing/truncated')
        pe = self.unpack('<I', 60)[0]
        require(64 <= pe <= 1024 * 1024 and pe + 24 <= len(data), 'PE header offset outside bound')
        require(data[pe:pe + 4] == b'PE\0\0', 'PE signature missing')
        self.machine, count, _, _, _, optional_size, _ = self.unpack('<HHIIIHH', pe + 4)
        require(0 < count <= PE_MAX_SECTIONS, 'PE section count outside bound')
        optional = pe + 24
        require(optional_size <= 4096 and optional + optional_size + count * 40 <= len(data), 'PE optional/section headers truncated')
        magic = self.unpack('<H', optional)[0]
        require(magic in (0x10b, 0x20b), 'Unsupported PE optional-header format')
        self.bits = 64 if magic == 0x20b else 32
        directory_offset = 112 if self.bits == 64 else 96
        require(optional_size >= directory_offset, 'PE optional header too short')
        self.image_base = self.unpack('<Q' if self.bits == 64 else '<I', optional + (24 if self.bits == 64 else 28))[0]
        self.image_size, self.header_size = self.unpack('<II', optional + 56)
        require(optional + optional_size + count * 40 <= self.header_size <= len(data), 'PE header size outside file')
        directories = self.unpack('<I', optional + directory_offset - 4)[0]
        require(directories <= 16 and directory_offset + directories * 8 <= optional_size, 'PE data-directory count/size outside bound')
        self.directories = [self.unpack('<II', optional + directory_offset + i * 8) for i in range(directories)]
        raw_ranges = []
        virtual_ranges = []
        for i in range(count):
            section = optional + optional_size + i * 40
            virtual_size, rva, raw_size, raw = self.unpack('<IIII', section + 8)
            span = max(virtual_size, raw_size)
            require(rva + span <= 0x100000000, 'PE section RVA overflow')
            if raw_size:
                require(self.header_size <= raw and raw + raw_size <= len(data), 'PE section raw bytes outside file')
                require(not any(raw < end and start < raw + raw_size for start, end in raw_ranges), 'PE overlapping raw sections')
                raw_ranges.append((raw, raw + raw_size))
            if span:
                require(rva >= self.header_size and not any(rva < end and start < rva + span for start, end in virtual_ranges), 'PE overlapping/header-aliasing virtual sections')
                virtual_ranges.append((rva, rva + span))
            self.sections.append((rva, raw_size, raw))

    def unpack(self, fmt, offset):
        size = struct.calcsize(fmt)
        require(0 <= offset and offset + size <= len(self.data), 'PE structure outside file')
        return struct.unpack_from(fmt, self.data, offset)

    def locate(self, rva, size):
        require(0 <= rva < 0x100000000 and 0 < size and rva + size <= 0x100000000, 'PE RVA/size outside 32-bit range')
        if rva < self.header_size:
            require(rva + size <= self.header_size, 'PE RVA crosses header boundary')
            return rva, self.header_size - rva
        for start, raw_size, raw in self.sections:
            if start <= rva and rva + size <= start + raw_size:
                return raw + rva - start, start + raw_size - rva
        raise RuntimeError('PE RVA has no bounded file-backed section')

    def at(self, fmt, rva):
        offset, _ = self.locate(rva, struct.calcsize(fmt))
        return self.unpack(fmt, offset)

    def text(self, rva, maximum=PE_MAX_NAME):
        offset, available = self.locate(rva, 1)
        end = self.data.find(b'\0', offset, offset + min(available, maximum + 1))
        require(end >= offset and end - offset <= maximum, 'PE ASCII name is unterminated/over bound')
        self.text_bytes += end - offset + 1
        require(self.text_bytes <= PE_MAX_TEXT_BYTES, 'PE cumulative decoded-text budget exceeded')
        value = self.data[offset:end]
        require(value and all(32 <= byte < 127 for byte in value), 'PE name is empty/non-printable ASCII')
        return value.decode('ascii')

    def directory(self, index):
        if index >= len(self.directories):
            return None
        rva, size = self.directories[index]
        if rva == 0 and size == 0:
            return None
        require(rva > 0 and 0 < size <= PE_MAX_DIRECTORY_BYTES, 'PE data directory outside bound')
        self.locate(rva, size)
        return rva, size

    def pointer_rva(self, value, rva_based=True):
        value = value if rva_based else value - self.image_base
        require(0 < value < 0x100000000, 'PE VA/RVA conversion outside bound')
        return value

    def symbols(self, table_rva, rva_based=True):
        width = self.bits // 8
        ordinal_mask = 1 << (self.bits - 1)
        result = []
        for i in range(PE_MAX_THUNKS + 1):
            value = self.at('<Q' if width == 8 else '<I', table_rva + i * width)[0]
            if value == 0:
                return result
            self.thunks_read += 1
            require(self.thunks_read <= PE_MAX_THUNKS, 'PE cumulative thunk count outside bound')
            if value & ordinal_mask:
                require(value & ~(ordinal_mask | 0xffff) == 0, 'PE ordinal thunk has reserved bits')
                result.append({'ordinal': value & 0xffff})
            else:
                rva = self.pointer_rva(value, rva_based)
                hint = self.at('<H', rva)[0]
                result.append({'name': self.text(rva + 2), 'hint': hint})
        raise RuntimeError('PE import thunk table missing terminator')

    def imports(self, delay=False):
        directory = self.directory(13 if delay else 1)
        if directory is None:
            return []
        rva, size = directory
        width = 32 if delay else 20
        require(size >= width, 'PE import directory too short')
        result = []
        for index in range(min(size // width, PE_MAX_DESCRIPTORS + 1)):
            values = self.at('<8I' if delay else '<5I', rva + index * width)
            if not any(values):
                return result
            require(index < PE_MAX_DESCRIPTORS, 'PE import descriptor count outside bound')
            if delay:
                attributes, name, _, iat, table, _, _, _ = values
                require(attributes in (0, 1), 'Unsupported PE delay-import attributes')
                rva_based = bool(attributes & 1)
                name = self.pointer_rva(name, rva_based)
                table = self.pointer_rva(table or iat, rva_based)
            else:
                table, _, _, name, iat = values
                rva_based = True
                name = self.pointer_rva(name)
                table = self.pointer_rva(table or iat)
            result.append({'library': self.text(name, 1024), 'symbols': self.symbols(table, rva_based)})
        raise RuntimeError('PE import descriptors missing bounded null terminator')

    def export_forwarders(self):
        directory = self.directory(0)
        if directory is None:
            return {'function_slots': 0, 'named_exports': 0, 'forwarders': []}
        rva, size = directory
        require(size >= 40, 'PE export directory too short')
        _, _, _, _, _, base, function_count, name_count, functions, names, ordinals = self.at('<IIHHIIIIIII', rva)
        require(function_count <= PE_MAX_EXPORTS and name_count <= PE_MAX_EXPORTS and base + function_count <= 0x100000000, 'PE export count outside bound')
        if function_count:
            self.locate(functions, function_count * 4)
        if name_count:
            self.locate(names, name_count * 4)
            self.locate(ordinals, name_count * 2)
        by_index = {}
        for i in range(name_count):
            index = self.at('<H', ordinals + i * 2)[0]
            require(index < function_count, 'PE export name ordinal outside table')
            by_index.setdefault(index, []).append(self.text(self.at('<I', names + i * 4)[0]))
        forwarders = []
        for i in range(function_count):
            address = self.at('<I', functions + i * 4)[0]
            if rva <= address < rva + size:
                target = self.text(address, min(PE_MAX_NAME, rva + size - address - 1))
                require('.' in target and all(target.rsplit('.', 1)), 'PE forwarder lacks module/symbol separator')
                forwarders.append({'ordinal': base + i, 'names': by_index.get(i, []), 'forwarder': target})
        return {'function_slots': function_count, 'named_exports': name_count, 'forwarders': forwarders}


def dependency_name_string_hints(data):
    """Optional literal-name hints only; not imports, linking, execution or use."""
    result = []
    for library in PE_TARGET_DLLS:
        for encoding in ('ascii', 'utf-16le', 'utf-16be'):
            needle = library.encode(encoding)
            offsets = set()
            for start in range(0, len(data), PE_READ_CHUNK):
                block = data[start:start + PE_READ_CHUNK + len(needle) - 1].lower()
                position = block.find(needle)
                while position >= 0 and len(offsets) < 21:
                    offsets.add(start + position)
                    position = block.find(needle, position + 1)
                if len(offsets) >= 21:
                    break
            if offsets:
                result.append({'library': library, 'encoding': encoding, 'offsets': sorted(offsets)[:20], 'more_than_20_matches': len(offsets) > 20})
    return result


def inventory_pe_dependencies(archive, binary_inventory, scan_strings=False):
    expected = {row['path']: row for row in binary_inventory['files'] if PurePosixPath(row['path']).suffix.casefold() in ('.dll', '.exe')}
    selected = []
    for item in archive.infolist():
        name = safe_stage_member(item)
        if not item.is_dir() and PurePosixPath(name).suffix.casefold() in ('.dll', '.exe'):
            require(name in expected and item.file_size == expected[name]['bytes'], 'PE member missing/different from already-hashed inventory')
            selected.append((name, item))
    require(len(selected) == len(expected) and len({name for name, _ in selected}) == len(selected), 'PE inventory member set differs')
    require(sum(item.file_size for _, item in selected) <= MAX_STAGE_BINARY_BYTES, 'PE scan byte total outside bound')
    files = []
    target_importers = {library: [] for library in PE_TARGET_DLLS}
    icu_forwarders = []
    errors = []
    for name, item in sorted(selected):
        data = bytearray()
        measured = hashlib.sha256()
        with archive.open(item) as stream:
            for block in iter(lambda: stream.read(PE_READ_CHUNK), b''):
                require(len(data) + len(block) <= item.file_size <= MAX_STAGE_MEMBER_BYTES, 'PE stream outside declared/member bound')
                data.extend(block)
                measured.update(block)
        require(len(data) == expected[name]['bytes'] and measured.hexdigest() == expected[name]['sha256'], 'PE bytes differ from already-hashed inventory')
        row = {'path': name, 'bytes': len(data), 'sha256': measured.hexdigest()}
        if scan_strings:
            row['literal_dependency_name_hints'] = dependency_name_string_hints(data)
        try:
            pe = PeData(data)
            direct = pe.imports()
            delayed = pe.imports(delay=True)
            row.update({'status': 'parsed', 'pe_bits': pe.bits, 'machine': pe.machine,
                        'import_library_names': [entry['library'] for entry in direct],
                        'delay_import_library_names': [entry['library'] for entry in delayed],
                        'import_symbols_read': pe.thunks_read})
            for kind, entries in (('import', direct), ('delay-import', delayed)):
                for entry in entries:
                    library = entry['library'].replace('\\', '/').rsplit('/', 1)[-1].casefold()
                    if library in target_importers:
                        target_importers[library].append({'importer': name, 'importer_sha256': row['sha256'],
                                                          'kind': kind, 'declared_library': entry['library'], 'symbols': entry['symbols']})
            if PurePosixPath(name).name.casefold() == 'icuuc.dll':
                icu_forwarders.append({'path': name, 'sha256': row['sha256'], **pe.export_forwarders()})
        except RuntimeError as error:
            row.update({'status': 'unsupported-or-malformed', 'error': str(error)[:512]})
            errors.append({'path': name, 'error': str(error)[:512]})
        files.append(row)
    complete = not errors
    report = {'schema_version': 1, 'status': 'complete' if complete else 'incomplete-do-not-infer-absence',
            'scope': 'File-backed PE32/PE32+ import and delay-import tables; ICUuc.dll export forwarders only',
            'limits': {'read_chunk_bytes': PE_READ_CHUNK, 'sections_per_file': PE_MAX_SECTIONS,
                       'descriptors_per_table': PE_MAX_DESCRIPTORS, 'thunks_per_file': PE_MAX_THUNKS,
                       'exports_per_file': PE_MAX_EXPORTS, 'name_bytes': PE_MAX_NAME,
                       'decoded_text_bytes_per_file': PE_MAX_TEXT_BYTES, 'report_bytes': PE_MAX_REPORT_BYTES},
            'unsupported_format_scope': 'Non-PE32/PE32+ formats, malformed/oversized tables, and bound IAT-only imports with no recoverable name table cause an explicit incomplete result; no Windows loader emulation',
            'all_dll_exe_members_parsed': complete, 'dll_exe_count': len(files), 'files': files,
            'target_importers': target_importers, 'icuuc_export_forwarders': icu_forwarders,
            'target_stage_files': {library: [row['path'] for row in files if PurePosixPath(row['path']).name.casefold() == library] for library in PE_TARGET_DLLS},
            'errors': errors, 'literal_name_scan_enabled': scan_strings,
            'literal_name_scan_scope': 'Case-insensitive literal ASCII/UTF-16LE/UTF-16BE DLL names; hints only, at most 20 offsets per name/encoding/file',
            'negative_evidence_scope': 'No listed PE imports is not proof of no dependency: LoadLibrary/GetProcAddress, generated or assembled names, plugins and runtime-selected D3D12/DXC/DXIL paths can be absent from import tables',
            'license_or_redistribution_decision_made': False, 'code_or_dll_executed': False,
            'registry_accessed': False, 'archive_extracted': False}
    require(len(json.dumps(report, separators=(',', ':'))) <= PE_MAX_REPORT_BYTES, 'PE dependency report exceeds explicit byte bound')
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--source-selection', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scan-dependency-name-strings', action='store_true', help='Optional literal-name hints only; not evidence of loading/use')
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
        receipt['pe_dependencies'] = inventory_pe_dependencies(archive, receipt['stage_binary_inventory'], args.scan_dependency_name_strings)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + '\n')
    print('CADENCE_2005_STAGE_RECEIPT_BEGIN')
    print(json.dumps(receipt, separators=(',', ':')))
    print('CADENCE_2005_STAGE_RECEIPT_END')

if __name__ == '__main__':
    main()
