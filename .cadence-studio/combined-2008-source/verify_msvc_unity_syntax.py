#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compile the actual configured project Unity units with MSVC /Zs, without PCH binaries.

This is a native syntax gate, not an application build or test. Compiler, source
and forced-include headers come from the reviewed build's compile database.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import struct
import subprocess
import sys
import time


def windows_split(command):
    """Microsoft argv quoting, independently round-tripped in the parser tests."""
    result, current, quoted, i, active = [], [], False, 0, False
    while i < len(command):
        char = command[i]
        if char in ' \t' and not quoted:
            if active:
                result.append(''.join(current)); current = []; active = False
            i += 1; continue
        active = True
        if char == '\\':
            end = i
            while end < len(command) and command[end] == '\\': end += 1
            count = end - i
            if end < len(command) and command[end] == '"':
                current.extend('\\' * (count // 2))
                if count % 2: current.append('"')
                else: quoted = not quoted
                i = end + 1; continue
            current.extend('\\' * count); i = end; continue
        if char == '"': quoted = not quoted
        else: current.append(char)
        i += 1
    if quoted: raise ValueError('Unterminated quote in compiler command')
    if active: result.append(''.join(current))
    return result


def tokens(entry):
    if isinstance(entry.get('arguments'), list) and all(isinstance(x, str) for x in entry['arguments']):
        result = entry['arguments'][:]
    elif isinstance(entry.get('command'), str):
        command = entry['command']
        result = windows_split(command)
        if os.name == 'nt':
            # Check our inspection tokenization against Windows itself before
            # reserializing any command for execution by subprocess.
            shell = ctypes.WinDLL('shell32', use_last_error=True)
            function = shell.CommandLineToArgvW
            function.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
            function.restype = ctypes.POINTER(ctypes.c_wchar_p)
            count = ctypes.c_int()
            pointer = function(command, ctypes.byref(count))
            if not pointer: raise ctypes.WinError(ctypes.get_last_error())
            try: native = [pointer[i] for i in range(count.value)]
            finally:
                local_free = ctypes.WinDLL('kernel32', use_last_error=True).LocalFree
                local_free.argtypes = [ctypes.c_void_p]; local_free.restype = ctypes.c_void_p
                local_free(pointer)
            if result != native: raise ValueError('Compiler tokenization differs from CommandLineToArgvW')
    else: raise ValueError('Compiler entry needs command or arguments')
    if not result or any('\0' in x or '\r' in x or '\n' in x for x in result):
        raise ValueError('Invalid compiler arguments')
    return result


def normalized(value):
    return str(value).replace('\\', '/').lower()


def selected_target(entry, include_qml=False):
    source = normalized(entry.get('file', ''))
    match = re.search(r'/cmakefiles/(project(?:_qml)?)\.dir/unity/unity_[^/]+\.cxx$', source)
    if not match: return None
    target = match.group(1)
    return target if target == 'project' or include_qml else None


def included_sources(raw):
    if len(raw) > 1024**2: raise ValueError('Configured Unity source exceeds1MiB')
    text = raw.decode('utf-8-sig')
    return {PureWindowsPath(name).name.lower() for name in re.findall(r'^\s*#\s*include\s+"([^"\r\n]+\.(?:cpp|cxx))"', text, re.M)}


def relevant_unit(target, included):
    required = {'localscorelibrarystore.cpp', 'mdlmigrator.cpp'} if target == 'project' else {'localaudiotranscriptionmodel.cpp', 'authorizedwavedownload.cpp'}
    return bool(included & required)


def transform(entry):
    original = tokens(entry)
    if PureWindowsPath(original[0]).name.lower() != 'cl.exe':
        raise ValueError('Direct MSVC cl.exe compile entry required')
    result, forced, macros, removed = [original[0]], [], [], []
    i = 1
    while i < len(original):
        token = original[i]
        if token.startswith('@') or token.lower() == '/link':
            raise ValueError('Opaque response files and linker modes are unsupported')
        if token[:2] in ('-D', '/D', '-U', '/U'):
            definition = token[2:]
            if not definition:
                if i + 1 == len(original): raise ValueError('Missing macro value')
                definition = original[i + 1]
            name, separator, value = definition.partition('=')
            if name == 'CADENCE_BUILD': macros.append((token[1], value if separator else None))
        if token in ('/c', '-c', '/showIncludes', '-showIncludes', '/Zi', '/Z7', '/FS', '/Zs', '/Y-'):
            removed.append(token); i += 1; continue
        # /FI is a forced *input* header and must remain. /Fi is a generated
        # preprocessor output. MSVC's option capitalization is significant.
        if token.startswith(('/FI', '-FI')):
            value = token[3:]
            if not value:
                if i + 1 == len(original): raise ValueError('Missing forced include')
                value = original[i + 1]; result.extend([token, value]); i += 2
            else: result.append(token); i += 1
            forced.append(value); continue
        consumed = False
        for prefix in ('/Fo', '-Fo', '/Fd', '-Fd', '/Fp', '-Fp', '/Fi', '-Fi', '/Fa', '-Fa', '/Fe', '-Fe', '/FR', '/Fr'):
            if token.startswith(prefix):
                removed.append(token)
                if len(token) == len(prefix):
                    if i + 1 == len(original): raise ValueError('Missing removed output path')
                    removed.append(original[i + 1]); i += 1
                i += 1; consumed = True; break
        if consumed: continue
        if token.startswith(('/Yu', '-Yu', '/Yc', '-Yc')):
            removed.append(token)
            if len(token) == 3 and i + 1 < len(original) and re.search(r'\.(?:h|hpp|hxx)$', original[i + 1], re.I):
                removed.append(original[i + 1]); i += 1
            i += 1; continue
        if token.startswith(('/sourceDependencies', '-sourceDependencies', '/scanDependencies')):
            removed.append(token)
            if i + 1 == len(original): raise ValueError('Missing dependency output path')
            removed.append(original[i + 1]); i += 2; continue
        if token.startswith(('/FA', '-FA', '/P', '/EP')):
            raise ValueError('Unsupported output/preprocessing mode in syntax command')
        result.append(token); i += 1
    if not macros or any(x != ('D', '1') for x in macros):
        raise ValueError('The real compiler command must define CADENCE_BUILD=1 consistently')
    source = normalized(entry.get('file', ''))
    if not source or not any(normalized(x) == source for x in result[1:]):
        raise ValueError('Actual Unity source is absent from compiler arguments')
    if not any('cmake_pch.' in normalized(x) for x in forced):
        raise ValueError('Actual textual PCH forced include is required')
    return result + ['/Zs', '/Y-'], forced, removed


def plain_file(path):
    if not path.is_file() or path.is_symlink(): raise ValueError('Required compiler input is absent or linked: ' + str(path))
    if getattr(path.stat(), 'st_file_attributes', 0) & 0x400:
        raise ValueError('Reparse compiler input refused: ' + str(path))


def run_unit(arguments, directory, log_path, seconds):
    start = time.monotonic(); limit = 2 * 1024**2
    with log_path.open('xb') as log:
        child = subprocess.Popen(arguments, cwd=directory, stdout=log, stderr=subprocess.STDOUT, shell=False)
        reason = None
        try:
            while child.poll() is None:
                if time.monotonic() - start > seconds: reason = 'compiler-timeout'; break
                if log_path.stat().st_size > limit: reason = 'compiler-log-bound'; break
                time.sleep(0.1)
            if reason:
                child.kill(); child.wait(timeout=5)
            code = child.wait(timeout=5)
        finally:
            if child.poll() is None: child.kill(); child.wait(timeout=5)
    size = log_path.stat().st_size
    if size > limit:
        with log_path.open('r+b') as log: log.truncate(limit)
        reason = reason or 'compiler-log-bound'
    raw = log_path.read_bytes()
    missing_generated = b'C1083' in raw and (b'_autogen' in raw or b'cmake_pch' in raw or b'ui_' in raw)
    return {'exit_code': code, 'seconds': round(time.monotonic() - start, 3),
            'failure': reason, 'missing_generated_header_suspected': missing_generated,
            'log': str(log_path), 'log_bytes': len(raw), 'log_sha256': hashlib.sha256(raw).hexdigest(),
            'passed': code == 0 and reason is None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--include-qml', action='store_true')
    parser.add_argument('--timeout-seconds', type=int, default=120)
    args = parser.parse_args()
    if args.output_dir.exists(): raise ValueError('New syntax-gate output directory required')
    args.output_dir.mkdir(parents=True)
    report = {'schema_version': 1, 'status': 'FAIL', 'application_built': False,
              'application_executed': False, 'syntax_only': True, 'units': [], 'errors': []}
    try:
        if os.name != 'nt' or struct.calcsize('P') != 8:
            raise ValueError('Actual Windows x64 MSVC required; parser tests are not native validation')
        if not 10 <= args.timeout_seconds <= 180: raise ValueError('Compiler timeout must be10..180seconds')
        build = args.build_dir.resolve(strict=True)
        database, config = build / 'compile_commands.json', build / 'muse_framework_config.h'
        plain_file(database); plain_file(config)
        raw, config_raw = database.read_bytes(), config.read_bytes()
        if len(raw) > 64 * 1024**2: raise ValueError('Compile database exceeds64MiB')
        defines = re.findall(rb'^\s*#\s*define\s+CADENCE_BUILD\b([^\r\n]*)', config_raw, re.M)
        if [value.strip() for value in defines] != [b'1'] or re.search(rb'^\s*#\s*undef\s+CADENCE_BUILD\b', config_raw, re.M):
            raise ValueError('Generated config must define CADENCE_BUILD=1')
        entries = json.loads(raw)
        if not isinstance(entries, list) or any(not isinstance(e, dict) for e in entries):
            raise ValueError('Compile database must contain an array of objects')
        candidates = [(e, selected_target(e, args.include_qml)) for e in entries]
        candidates = [(e, t) for e, t in candidates if t]
        if not 1 <= len(candidates) <= 32: raise ValueError('Actual bounded project Unity selection required')
        selected, all_inputs = [], {'project': set(), 'project_qml': set()}
        for entry, target in candidates:
            source = Path(entry['file']).resolve(strict=True)
            if not source.is_relative_to(build): raise ValueError('Configured Unity source must stay in build root')
            plain_file(source)
            included = included_sources(source.read_bytes())
            if relevant_unit(target, included):
                selected.append((entry, target, included)); all_inputs[target].update(included)
        if not {'localscorelibrarystore.cpp', 'mdlmigrator.cpp'}.issubset(all_inputs['project']):
            raise ValueError('Configured project Unity units containing the actual library and MDL sources are required')
        targets = {t for _, t, _ in selected}
        if 'project' not in targets or (args.include_qml and 'localaudiotranscriptionmodel.cpp' not in all_inputs['project_qml']):
            raise ValueError('Actual project Unity units required; empty/oversized selection refused')
        report.update(compile_commands_sha256=hashlib.sha256(raw).hexdigest(),
                      config_sha256=hashlib.sha256(config_raw).hexdigest(), selected_units=len(selected),
                      available_unity_units=len(candidates), selection='Actual library/MDL units plus optional audio-model QML units; no unrelated autogen targets')
        for index, (entry, target, included) in enumerate(selected):
            source = Path(entry['file']).resolve(strict=True)
            directory = Path(entry['directory']).resolve(strict=True)
            if not source.is_relative_to(build) or not directory.is_relative_to(build):
                raise ValueError('Actual configured Unity source/directory must stay in build root')
            plain_file(source)
            arguments, forced, removed = transform(entry)
            plain_file(Path(arguments[0]))
            for header in forced:
                path = Path(header) if Path(header).is_absolute() else directory / header
                plain_file(path)
            result = run_unit(arguments, directory, args.output_dir / f'{index:02d}-{target}.log', args.timeout_seconds)
            result.update(target=target, source=str(source), source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                          included_sources=sorted(included), command=arguments, removed_switches=removed, textual_forced_includes=forced)
            report['units'].append(result)
            print(json.dumps({k: result[k] for k in ('target', 'source', 'passed', 'exit_code', 'seconds', 'failure')}), flush=True)
            if not result['passed']: raise ValueError('Actual MSVC Unity syntax failed; see retained compiler log')
        report['status'] = 'PASS'
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as error:
        report['errors'].append(str(error)[:1200])
    (args.output_dir / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'checked_units': len(report['units']), 'errors': report['errors']}), flush=True)
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
