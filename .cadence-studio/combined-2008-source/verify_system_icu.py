#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Read only two caller-selected SystemDirectory ICU PE files; never load them."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys

PE_MAX_SECTIONS = 96
PE_MAX_DESCRIPTORS = 4096
PE_MAX_THUNKS = 65536
PE_MAX_EXPORTS = 65536
PE_MAX_NAME = 4096
PE_MAX_DIRECTORY_BYTES = 16 * 1024 * 1024
PE_MAX_TEXT_BYTES = 4 * 1024 * 1024
MAX_SYSTEM_FILE_BYTES = 64 * 1024 * 1024
READ_CHUNK = 1024 * 1024
MAX_FORWARD_STEPS = 16
SYSTEM_FILES = ('icuuc.dll', 'icu.dll')


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


FULL2005_PROFILE = {'schema_version': 1, 'scope': 'Exact full2005 Qt6Core named ICUuc imports measured in retained real-stage PE receipt', 'producer_run_id': 43207550870, 'artifact_id': 13943781621, 'pe_reader_run_id': 43233124238, 'receipt_sha256': '37640544ccbed69e8b224c6023cf7df28fc86211828a0fbfd42e4536389e04bf', 'importer': 'bin/Qt6Core.dll', 'importer_sha256': 'b98eea394a95563879b614dbd4432ce074b0fceeb154c3bae252f4e7a9376a40', 'required_names': ['ucnv_open', 'UCNV_TO_U_CALLBACK_SUBSTITUTE', 'UCNV_FROM_U_CALLBACK_SUBSTITUTE', 'ucnv_close', 'ucnv_reset', 'ucnv_getMaxCharSize', 'ucnv_getName', 'ucnv_getToUCallBack', 'ucnv_getFromUCallBack', 'ucnv_setToUCallBack', 'ucnv_setFromUCallBack', 'ucnv_fromUnicode', 'ucnv_toUnicode', 'ucnv_countAvailable', 'ucnv_getAvailableName', 'ucnv_cbToUWriteUChars', 'ucnv_cbFromUWriteUChars', 'ucnv_toUCountPending', 'ucnv_fromUCountPending', 'ucnv_getStandardName'], 'required_count': 20, 'build_number': 2005, 'stage_archive_sha256': '4707aea7e6f0f63361ced55edfff7c7cf591f15463f9219263bfac4de3f96f9b', 'executable_sha256': 'd957ffc99497cb01b1f00f82ba1d6e89ef84547708506c6c51423675805e140a', 'stage_icuuc_sha256': '6febd789ff616dd6398ae2453adc1e7ccd7bbb6aee8c623a2638c1c00d51e003'}


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


def plain_path_chain(path, file=False):
    """Reject symlinks/reparse entries before resolution; allow genuine hardlinks."""
    require(path.is_absolute() and '..' not in path.parts, 'Explicit absolute SystemDirectory path required')
    chain = [*reversed(path.parents), path]
    final = None
    for index, component in enumerate(chain):
        info = component.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not (getattr(info, 'st_file_attributes', 0) & 0x400), 'Symlink/reparse file or ancestor refused')
        if index == len(chain) - 1 and file:
            require(stat.S_ISREG(info.st_mode), 'Named system input is not a regular file')
        else:
            require(stat.S_ISDIR(info.st_mode), 'SystemDirectory ancestor is not a directory')
        final = info
    return final


def identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def read_system_file(directory, name):
    require(name in SYSTEM_FILES, 'Only the two named ICU files may be read')
    path = directory / name
    before = plain_path_chain(path, file=True)
    require(0 < before.st_size <= MAX_SYSTEM_FILE_BYTES, 'Named system ICU size outside bound')
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0))
    data = bytearray()
    measured = hashlib.sha256()
    with os.fdopen(descriptor, 'rb') as stream:
        opened = os.fstat(stream.fileno())
        require(identity(before) == identity(opened) and stat.S_ISREG(opened.st_mode), 'System ICU changed before read')
        require(not (getattr(opened, 'st_file_attributes', 0) & 0x400), 'Opened system ICU is a reparse entry')
        for chunk in iter(lambda: stream.read(READ_CHUNK), b''):
            require(len(data) + len(chunk) <= before.st_size <= MAX_SYSTEM_FILE_BYTES, 'System ICU stream outside size bound')
            data.extend(chunk)
            measured.update(chunk)
        require(identity(os.fstat(stream.fileno())) == identity(opened), 'System ICU changed during read')
    after = plain_path_chain(path, file=True)
    require(identity(after) == identity(before) and len(data) == before.st_size, 'System ICU changed after read')
    return data, {'file': name, 'path': str(path), 'bytes': len(data), 'sha256': measured.hexdigest(),
                  'hardlink_count': before.st_nlink, 'hardlinks_allowed_for_read_only_system_files': True,
                  'file_and_ancestors_checked_for_reparse': True, 'identity_stable_before_during_after_read': True}


class SystemPeData(PeData):
    def export_catalog(self):
        require(self.bits == 64 and self.machine == 0x8664, 'System ICU must be x64 PE32+')
        directory = self.directory(0)
        require(directory is not None, 'System ICU export directory missing')
        rva, size = directory
        require(size >= 40, 'System ICU export directory truncated')
        _, _, _, _, _, base, functions_count, names_count, functions, names, ordinals = self.at('<IIHHIIIIIII', rva)
        require(0 < functions_count <= PE_MAX_EXPORTS and names_count <= PE_MAX_EXPORTS and base + functions_count <= 0x100000000, 'System ICU export count outside bound')
        self.locate(functions, functions_count * 4)
        if names_count:
            self.locate(names, names_count * 4)
            self.locate(ordinals, names_count * 2)
        by_ordinal = {}
        by_name = {}
        for index in range(functions_count):
            address = self.at('<I', functions + index * 4)[0]
            if not address:
                continue
            entry = {'ordinal': base + index, 'rva': address, 'names': []}
            if rva <= address < rva + size:
                entry['forwarder'] = self.text(address, min(PE_MAX_NAME, rva + size - address - 1))
            by_ordinal[base + index] = entry
        for index in range(names_count):
            position = self.at('<H', ordinals + index * 2)[0]
            require(position < functions_count, 'System ICU named export ordinal outside table')
            ordinal = base + position
            require(ordinal in by_ordinal, 'System ICU name refers to an empty export slot')
            name = self.text(self.at('<I', names + index * 4)[0])
            require(name not in by_name, 'Duplicate system ICU export name')
            entry = by_ordinal[ordinal]
            entry['names'].append(name)
            by_name[name] = entry
        return {'by_name': by_name, 'by_ordinal': by_ordinal,
                'summary': {'function_slots': functions_count, 'nonempty_exports': len(by_ordinal), 'named_exports': names_count,
                            'forwarder_exports': sum('forwarder' in entry for entry in by_ordinal.values())}}

    def executable_export(self, rva):
        require(0 < rva < self.image_size, 'Terminal ICU export RVA outside SizeOfImage')
        self.locate(rva, 1)
        pe = self.unpack('<I', 60)[0]
        optional_size = self.unpack('<H', pe + 20)[0]
        table = pe + 24 + optional_size
        for index, (start, raw_size, _) in enumerate(self.sections):
            if start <= rva < start + raw_size:
                flags = self.unpack('<I', table + index * 40 + 36)[0]
                require(flags & 0x20000000, 'Terminal ICU export is not in a file-backed executable section')
                return flags
        raise RuntimeError('Terminal ICU export does not point into a raw executable section')


def resolve_icu_export(catalogs, images, name):
    module = 'icuuc.dll'
    symbol = name
    visited = set()
    chain = []
    for step in range(MAX_FORWARD_STEPS):
        key = (module, type(symbol).__name__, symbol)
        require(key not in visited, 'System ICU export-forwarder cycle')
        visited.add(key)
        catalog = catalogs[module]
        entry = catalog['by_ordinal'].get(symbol) if isinstance(symbol, int) else catalog['by_name'].get(symbol)
        require(entry is not None, 'Required ICU export missing: ' + module + '!' + str(symbol))
        row = {'module': module, 'requested': symbol, 'ordinal': entry['ordinal'], 'export_names': entry['names']}
        chain.append(row)
        if 'forwarder' not in entry:
            row['rva'] = entry['rva']
            row['section_characteristics'] = images[module].executable_export(entry['rva'])
            row['terminal_file_backed_executable_export'] = True
            return {'required_name': name, 'complete': True, 'chain': chain, 'terminal_module': module, 'terminal_ordinal': entry['ordinal']}
        forwarder = entry['forwarder']
        row['forwarder'] = forwarder
        require('.' in forwarder, 'Malformed ICU export forwarder')
        target_module, target_symbol = forwarder.rsplit('.', 1)
        target_module = target_module.casefold()
        if not target_module.endswith('.dll'):
            target_module += '.dll'
        require(target_module in SYSTEM_FILES and target_symbol, 'ICU forwarder leaves the two explicitly supplied system files')
        if target_symbol.startswith('#'):
            require(target_symbol[1:].isascii() and target_symbol[1:].isdigit() and 0 < int(target_symbol[1:]) <= 0xffff, 'Invalid ICU forwarded export ordinal')
            symbol = int(target_symbol[1:])
        else:
            symbol = target_symbol
        module = target_module
    raise RuntimeError('System ICU forwarder depth bound exceeded')


def verify_system_icu(path, required_names):
    """Return export availability evidence. This function never omits any file."""
    report = {'schema_version': 1, 'status': 'refused', 'complete': False,
              'scope': 'Read-only x64 PE export resolution for exact full2005 Qt6Core ICU imports; not ABI or runtime qualification',
              'system_directory': str(path), 'system_directory_provenance': 'Explicit caller value; caller must obtain it from Windows SystemDirectory API',
              'host_is_windows': sys.platform == 'win32', 'local_forwarder_omission_export_gate_passed': False,
              'source_receipt': FULL2005_PROFILE, 'system_files': [], 'resolutions': [], 'errors': [],
              'application_or_DLL_executed': False, 'registry_accessed': False, 'file_omission_performed': False,
              'license_or_redistribution_decision_made': False}
    try:
        require(isinstance(required_names, (list, tuple)) and all(isinstance(name, str) for name in required_names), 'Required names must be a list of exact symbol strings')
        require(len(required_names) == len(set(required_names)) == 20 and set(required_names) == set(FULL2005_PROFILE['required_names']), 'Required names differ from the exact20 measured full2005 ICU imports')
        directory = Path(path)
        plain_path_chain(directory)
        catalogs = {}
        images = {}
        for name in SYSTEM_FILES:
            data, record = read_system_file(directory, name)
            image = SystemPeData(data)
            catalog = image.export_catalog()
            record.update({'pe_bits': image.bits, 'machine': image.machine, 'export_table': catalog['summary']})
            report['system_files'].append(record)
            images[name] = image
            catalogs[name] = catalog
        for name in FULL2005_PROFILE['required_names']:
            try:
                report['resolutions'].append(resolve_icu_export(catalogs, images, name))
            except RuntimeError as error:
                report['errors'].append({'required_name': name, 'error': str(error)[:512]})
        report['complete'] = not report['errors'] and len(report['resolutions']) == 20
        report['status'] = 'complete-static-export-evidence' if report['complete'] else 'refused'
        report['local_forwarder_omission_export_gate_passed'] = report['complete'] and report['host_is_windows']
    except (RuntimeError, OSError, ValueError, TypeError, struct.error) as error:
        report['errors'].append({'error': str(error)[:512]})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system-directory', type=Path, required=True)
    parser.add_argument('--required-names-json', type=Path)
    args = parser.parse_args()
    names = FULL2005_PROFILE['required_names']
    input_error = None
    if args.required_names_json:
        try:
            require(args.required_names_json.stat().st_size <= 16384, 'Required names JSON exceeds bound')
            document = json.loads(args.required_names_json.read_text(encoding='utf-8-sig'))
            names = document.get('required_names') if isinstance(document, dict) else document
        except (RuntimeError, OSError, ValueError, UnicodeError) as error:
            names = None
            input_error = str(error)[:512]
    report = verify_system_icu(args.system_directory, names)
    if input_error:
        report['errors'].insert(0, {'required_names_json_error': input_error})
    text = json.dumps(report, indent=2) + '\n'
    print(text, end='')
    return 0 if report['local_forwarder_omission_export_gate_passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
