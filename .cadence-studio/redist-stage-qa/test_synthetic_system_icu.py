# SPDX-License-Identifier: GPL-3.0-only
"""Synthetic PE export files read on Linux only; no DLL or Windows code executed."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import stat
import struct
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('system_icu_data_reader', HERE / 'verify_system_icu.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
NAMES = r.FULL2005_PROFILE['required_names']
FIXTURES = HERE / 'synthetic-system-icu-fixtures'
FIXTURES.mkdir(exist_ok=True)
RESULTS = []


class MiniPe:
    def __init__(self, bits=64):
        self.bits = bits
        self.base = 0x180000000 if bits == 64 else 0x400000
        self.data = bytearray(0x2200)
        self.optional = 0x98
        self.dirs = self.optional + (112 if bits == 64 else 96)
        self.optional_size = 240 if bits == 64 else 224
        self.cursor = 0x1100
        self.put(0, b'MZ')
        self.pack('<I', 60, 0x80)
        self.put(0x80, b'PE\0\0')
        self.pack('<HHIIIHH', 0x84, 0x8664 if bits == 64 else 0x14c, 1, 0, 0, 0, self.optional_size, 0x2022)
        self.pack('<H', self.optional, 0x20b if bits == 64 else 0x10b)
        self.pack('<Q' if bits == 64 else '<I', self.optional + (24 if bits == 64 else 28), self.base)
        self.pack('<II', self.optional + 32, 0x1000, 0x200)
        self.pack('<II', self.optional + 56, 0x3000, 0x200)
        self.pack('<I', self.dirs - 4, 16)
        section = self.optional + self.optional_size
        self.put(section, b'.rdata\0\0')
        self.pack('<IIII', section + 8, 0x2000, 0x1000, 0x2000, 0x200)
        self.pack('<I', section + 36, 0x40000040)

    def put(self, offset, value):
        self.data[offset:offset + len(value)] = value

    def pack(self, fmt, offset, *values):
        struct.pack_into(fmt, self.data, offset, *values)

    def offset(self, rva):
        return 0x200 + rva - 0x1000

    def alloc(self, data, align=1):
        self.cursor = (self.cursor + align - 1) // align * align
        address = self.cursor
        self.put(self.offset(address), data)
        self.cursor += len(data)
        assert self.cursor < 0x3000
        return address

    def directory(self, index, rva, size):
        self.pack('<II', self.dirs + index * 8, rva, size)

    def imports(self, entries, delay=False, va=False, fallback=False):
        size = 32 if delay else 20
        descriptors = self.alloc(bytes(size * (len(entries) + 1)), 8)
        self.directory(13 if delay else 1, descriptors, size * (len(entries) + 1))
        for i, (library, symbols) in enumerate(entries):
            name = self.alloc(library.encode('ascii') + b'\0')
            values = []
            for symbol in symbols:
                if isinstance(symbol, int):
                    values.append((1 << (self.bits - 1)) | symbol)
                else:
                    pointer = self.alloc(struct.pack('<H', 7) + symbol.encode('ascii') + b'\0', 2)
                    values.append(pointer + (self.base if va else 0))
            values.append(0)
            table = self.alloc(struct.pack('<' + ('Q' if self.bits == 64 else 'I') * len(values), *values), self.bits // 8)
            if delay:
                adjust = self.base if va else 0
                self.pack('<8I', self.offset(descriptors) + i * size, 0 if va else 1, name + adjust, 0, table + adjust, 0 if fallback else table + adjust, 0, 0, 0)
            else:
                self.pack('<5I', self.offset(descriptors) + i * size, 0 if fallback else table, 0, 0, name, table)
        return descriptors

    def exports(self):
        self.cursor = 0x1800
        start = self.alloc(bytes(40), 4)
        functions = self.alloc(bytes(12), 4)
        names = self.alloc(bytes(8), 4)
        ordinals = self.alloc(struct.pack('<HH', 0, 1), 2)
        name0 = self.alloc(b'u_strToUpper\0')
        name1 = self.alloc(b'u_strlen\0')
        forward0 = self.alloc(b'icu.u_strToUpper\0')
        forward1 = self.alloc(b'icu.#123\0')
        forward2 = self.alloc(b'icu.#400\0')
        self.pack('<III', self.offset(functions), forward0, forward1, forward2)
        self.pack('<II', self.offset(names), name0, name1)
        self.pack('<IIHHIIIIIII', self.offset(start), 0, 0, 0, 0, 0, 10, 3, 2, functions, names, ordinals)
        self.directory(0, start, self.cursor - start)
        return start, forward0, ordinals


def image(exports, bits=64, executable=True, base=100):
    fixture = MiniPe(bits)
    fixture.data.extend(bytes(0x2000))
    fixture.pack('<IIII', fixture.optional + fixture.optional_size + 8, 0x4000, 0x1000, 0x4000, 0x200)
    fixture.pack('<I', fixture.optional + 56, 0x5000)
    fixture.pack('<I', fixture.optional + fixture.optional_size + 36, 0x60000020 if executable else 0x40000040)
    fixture.cursor = 0x1800
    start = fixture.alloc(bytes(40), 4)
    functions = fixture.alloc(bytes(len(exports) * 4), 4)
    named = [(index, name) for index, (name, target) in enumerate(exports) if name is not None]
    names = fixture.alloc(bytes(len(named) * 4), 4)
    ordinals = fixture.alloc(bytes(len(named) * 2), 2)
    for index, (name, target) in enumerate(exports):
        address = fixture.alloc(target.encode('ascii') + b'\0') if isinstance(target, str) else 0x1000 if target is None else target
        fixture.pack('<I', fixture.offset(functions) + index * 4, address)
    for i, (index, name) in enumerate(named):
        address = fixture.alloc(name.encode('ascii') + b'\0')
        fixture.pack('<I', fixture.offset(names) + i * 4, address)
        fixture.pack('<H', fixture.offset(ordinals) + i * 2, index)
    fixture.pack('<IIHHIIIIIII', fixture.offset(start), 0, 0, 0, 0, 0, base, len(exports), len(named), functions, names, ordinals)
    fixture.directory(0, start, fixture.cursor - start)
    return fixture


def write_pair(label, stubs=None, terminals=None, bits=64, executable=True):
    directory = FIXTURES / label
    directory.mkdir(exist_ok=True)
    stub = image(stubs if stubs is not None else [(name, 'icu.' + name) for name in NAMES], bits=bits)
    core = image(terminals if terminals is not None else [(name, None) for name in NAMES], executable=executable)
    (directory / 'icuuc.dll').write_bytes(stub.data)
    (directory / 'icu.dll').write_bytes(core.data)
    return directory


def passed(label):
    RESULTS.append({'case': label, 'passed': True, 'synthetic': True})


def refused(label, directory, substring, required=NAMES):
    report = r.verify_system_icu(directory, required)
    assert not report['complete'] and not report['local_forwarder_omission_export_gate_passed'], (label, report)
    assert substring in json.dumps(report['errors']), (label, report['errors'])
    passed(label)
    return report


valid = write_pair('valid20')
before = {name: hashlib.sha256((valid / name).read_bytes()).hexdigest() for name in r.SYSTEM_FILES}
report = r.verify_system_icu(valid, NAMES)
assert report['complete'] and len(report['resolutions']) == 20
assert all(len(row['chain']) == 2 and row['terminal_module'] == 'icu.dll' for row in report['resolutions'])
assert all(row['chain'][-1]['terminal_file_backed_executable_export'] for row in report['resolutions'])
assert not report['local_forwarder_omission_export_gate_passed'] and not report['host_is_windows']
assert before == {name: hashlib.sha256((valid / name).read_bytes()).hexdigest() for name in r.SYSTEM_FILES}
passed('all20-exact-named-forwarders-reach-real-x64-exports-read-only')
passed('Linux-synthetic-success-cannot-pass-Windows-omission-gate')
(HERE / 'synthetic-system-icu-report-example.json').write_text(json.dumps({'synthetic': True, 'actual_Windows_system_ICU_validated': False, 'report': report}, indent=2) + '\n', encoding='utf-8')

ordinal = write_pair('ordinal20', stubs=[(name, 'icu.#' + str(100 + i)) for i, name in enumerate(NAMES)])
report = r.verify_system_icu(ordinal, NAMES)
assert report['complete'] and report['resolutions'][0]['chain'][1]['requested'] == 100
passed('all20-forwarders-by-ordinal')
direct = write_pair('direct-system-icuuc', stubs=[(name, None) for name in NAMES])
report = r.verify_system_icu(direct, NAMES)
assert report['complete'] and all(len(row['chain']) == 1 for row in report['resolutions'])
passed('direct-system-icuuc-executable-exports')
missing = write_pair('missing-one', terminals=[(name, None) for name in NAMES[1:]])
refused('one-of20-missing-is-refused', missing, 'missing')
wrongcase = write_pair('wrong-case', terminals=[(name.lower(), None) for name in NAMES])
refused('export-symbol-names-remain-case-sensitive', wrongcase, 'missing')
pe32 = write_pair('PE32-system-stub', bits=32)
refused('PE32-is-not-x64-SystemICU', pe32, 'x64')
arm = write_pair('ARM64-system-stub')
p = arm / 'icuuc.dll'; data = bytearray(p.read_bytes()); struct.pack_into('<H', data, 0x84, 0xaa64); p.write_bytes(data)
refused('ARM64-is-not-x64-SystemICU', arm, 'x64')
nonexec = write_pair('non-executable-terminal', executable=False)
refused('terminal-export-in-data-section-is-refused', nonexec, 'executable section')
unbacked = write_pair('non-file-backed-terminal', terminals=[(name, 0x6000) for name in NAMES])
refused('non-file-backed-export-RVA-is-refused', unbacked, 'SizeOfImage')
imagebound = write_pair('outside-image-size', terminals=[(name, 0x1000) for name in NAMES])
p = imagebound / 'icu.dll'; data = bytearray(p.read_bytes()); struct.pack_into('<I', data, 0x98 + 56, 0x1000); p.write_bytes(data)
refused('raw-bytes-outside-SizeOfImage-are-refused', imagebound, 'SizeOfImage')
external = write_pair('external-forwarder', stubs=[(name, ('outside.' if i == 0 else 'icu.') + name) for i, name in enumerate(NAMES)])
refused('forwarder-to-third-DLL-is-refused', external, 'two explicitly')
cycle = write_pair('forwarder-cycle', terminals=[(name, 'icuuc.' + name) for name in NAMES])
refused('forwarder-cycle-is-refused', cycle, 'cycle')
missingordinal = write_pair('missing-ordinal', stubs=[(name, 'icu.#999') for name in NAMES])
refused('forwarded-missing-ordinal-is-refused', missingordinal, 'missing')
invalidordinal = write_pair('invalid-ordinal', stubs=[(name, 'icu.#65536') for name in NAMES])
refused('forwarded-ordinal-bound-is-enforced', invalidordinal, 'ordinal')
depthentries = [(name, 'icu.alias0') for name in NAMES]
depthentries += [('alias' + str(i), 'icu.alias' + str(i + 1)) for i in range(17)] + [('alias17', None)]
depth = write_pair('forwarder-depth', terminals=depthentries)
refused('forwarder-depth-bound-is-enforced', depth, 'depth bound')
duplicate = write_pair('duplicate-export-names', terminals=[(name, None) for name in NAMES] + [(NAMES[0], None)])
refused('duplicate-named-exports-are-refused', duplicate, 'Duplicate')
absent = write_pair('missing-core-file'); (absent / 'icu.dll').unlink()
refused('missing-system-icu-file-is-refused', absent, 'No such file')
refused('required-list-cannot-omit-one-of20', valid, 'exact20', NAMES[:-1])
refused('required-list-cannot-repeat-symbols', valid, 'exact20', [NAMES[0]] * 20)
refused('relative-SystemDirectory-is-refused', Path('synthetic-relative-directory'), 'absolute')

hardlinks = FIXTURES / 'legitimate-hardlinks'; hardlinks.mkdir(exist_ok=True)
for name in r.SYSTEM_FILES:
    destination = hardlinks / name
    if destination.exists(): destination.unlink()
    os.link(valid / name, destination)
report = r.verify_system_icu(hardlinks, NAMES)
assert report['complete'] and all(row['hardlink_count'] >= 2 for row in report['system_files'])
passed('legitimate-nlink-greater-than1-is-accepted-for-read-only-system-files')
linked = write_pair('leaf-symlink'); (linked / 'icu.dll').unlink(); (linked / 'icu.dll').symlink_to(valid / 'icu.dll')
refused('symlink-system-file-is-refused', linked, 'Symlink/reparse')
ancestor = FIXTURES / 'ancestor-link'
if ancestor.is_symlink(): ancestor.unlink()
ancestor.symlink_to(valid, target_is_directory=True)
refused('symlink-SystemDirectory-ancestor-is-refused', ancestor, 'Symlink/reparse')
with patch.object(Path, 'lstat', return_value=SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_file_attributes=0x400)):
    try:
        r.plain_path_chain(Path('/synthetic-reparse-attribute'))
    except RuntimeError as exc:
        assert 'reparse' in str(exc)
    else:
        raise AssertionError('Synthetic reparse attribute not rejected')
passed('synthetic-Windows-reparse-attribute-is-refused-without-Windows-execution')
with patch.object(r, 'MAX_SYSTEM_FILE_BYTES', 100):
    refused('system-file-read-bound-is-enforced-with-tiny-test-bound', valid, 'size outside bound')

cli = subprocess.run([sys.executable, '-I', str(HERE / 'verify_system_icu.py'), '--system-directory', str(valid)], capture_output=True, text=True, check=False)
assert cli.returncode == 2 and json.loads(cli.stdout)['complete'] is True
passed('CLI-emits-JSON-and-refuses-Windows-omission-gate-on-Linux')
assert '--output' not in subprocess.run([sys.executable, '-I', str(HERE / 'verify_system_icu.py'), '--help'], capture_output=True, text=True, check=True).stdout
passed('helper-CLI-has-no-file-writing-output-option')
summary = {'schema_version': 1, 'scope': 'Actual bounded export parser on synthetic mini-PE files and Linux filesystem fixtures only',
           'actual_Windows_system_ICU_validated': False, 'application_or_DLL_executed': False,
           'tests_passed': len(RESULTS), 'tests': RESULTS}
(HERE / 'synthetic-system-icu-test-results.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
print(json.dumps({key: value for key, value in summary.items() if key != 'tests'}))
