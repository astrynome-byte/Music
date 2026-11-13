#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Read-only compilation-profile gate; never builds or executes the application."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import sys

MACRO = 'CADENCE_BUILD'
def macro_switches(entry):
    if isinstance(entry.get('arguments'), list):
        tokens = [str(x) for x in entry['arguments']]
    elif isinstance(entry.get('command'), str):
        # Tokenization is used only to inspect switches, never to execute a
        # command. Preserve Windows backslashes in macro replacement values.
        # This preserves spaces inside other macros' quoted values, preventing
        # an embedded \" -DCADENCE_BUILD=1\" from masquerading as a switch.
        lexer = shlex.shlex(entry['command'], posix=True)
        lexer.whitespace_split = True
        lexer.commenters = ''
        lexer.escape = ''  # Windows backslashes belong to replacement values.
        tokens = list(lexer)
    else:
        raise ValueError('compile entry has neither command nor arguments')
    switches = []
    index = 0
    while index < len(tokens):
        token = tokens[index].strip('"')
        if token[:2] in ('-D', '/D', '-U', '/U'):
            operation = token[1]
            definition = token[2:].strip('"')
            if not definition and index + 1 < len(tokens):
                index += 1
                definition = tokens[index].strip('"')
            name, separator, value = definition.partition('=')
            if name == MACRO:
                switches.append((operation, value if separator else None))
        index += 1
    return switches


def normalized(value):
    return str(value).replace('\\', '/').lower()


def examine(build_dir, header=None, expected='ON', require_unity=False, require_pch=False):
    build = Path(build_dir)
    database = build / 'compile_commands.json'
    config = Path(header) if header else build / 'muse_framework_config.h'
    errors = []
    data = database.read_bytes()
    entries = json.loads(data)
    if not isinstance(entries, list):
        raise ValueError('compile_commands.json must contain an array')
    text = config.read_text(encoding='utf-8-sig')
    defines = re.findall(r'^\s*#\s*define\s+CADENCE_BUILD\b([^\r\n]*)', text, re.M)
    undefines = re.findall(r'^\s*#\s*undef\s+CADENCE_BUILD\b', text, re.M)
    config_valid = ([s.strip() for s in defines] == ['1'] and not undefines) if expected == 'ON' else not defines
    if not config_valid:
        errors.append('generated config does not match CADENCE_BUILD=' + expected)
    selected = []
    scene_count = unity_count = pch_count = 0
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError('compile entry is not an object')
        file = normalized(entry.get('file', ''))
        command = entry.get('command', '')
        if not command and isinstance(entry.get('arguments'), list):
            command = ' '.join(str(x) for x in entry['arguments'])
        # The object-output path identifies targets for generated moc sources.
        # Include paths alone must not cause unrelated units to be selected.
        target_path = normalized(entry.get('output', ''))
        scene = '/notationscene/' in '/' + file or bool(re.search(r'(?:^|[/\s\"])notationscene\.dir(?:[/\s\"]|$)', target_path))
        pch = 'cmake_pch' in file
        if not (scene or pch):
            continue
        scene_count += int(scene)
        unity = scene and '/unity/' in file
        unity_count += int(unity)
        pch_count += int(pch)
        switches = macro_switches(entry)
        valid = bool(switches) and all(switch == ('D', '1') for switch in switches) if expected == 'ON' else not switches
        selected.append({'entry': index, 'file': str(entry.get('file', ''))[:500],
                         'notationscene': scene, 'unity': unity, 'pch': pch,
                         'macro_switch_count': len(switches),
                         'macro_switches': [(op, value[:80] if value is not None else None) for op, value in switches[:8]], 'valid': valid})
        if not valid:
            errors.append('macro switches differ from expected profile on entry ' + str(index) + ': ' + str(entry.get('file', ''))[:300])
    if not scene_count:
        errors.append('no real notationscene compilation unit found')
    if require_unity and not unity_count:
        errors.append('no real notationscene Unity compilation unit found')
    if require_pch and not pch_count:
        errors.append('no PCH compilation unit found')
    return {'schema_version': 1, 'status': 'PASS' if not errors else 'FAIL',
            'expected_profile': expected, 'compile_commands': str(database),
            'compile_commands_sha256': hashlib.sha256(data).hexdigest(),
            'config_header': str(config), 'config_header_sha256': hashlib.sha256(config.read_bytes()).hexdigest(),
            'config_matches_profile': config_valid, 'total_compile_entries': len(entries),
            'notationscene_units': scene_count, 'notationscene_unity_units': unity_count,
            'pch_units': pch_count, 'checked_units': len(selected),
            'failed_units': sum(not x['valid'] for x in selected),
            'errors': errors[:20], 'error_count': len(errors),
            'samples': ([x for x in selected if not x['valid']] + [x for x in selected if x['valid']])[:12],
            'application_built': False, 'application_executed': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir', required=True)
    parser.add_argument('--config-header')
    parser.add_argument('--expected-profile', choices=['ON', 'OFF'], default='ON')
    parser.add_argument('--require-unity', action='store_true')
    parser.add_argument('--require-pch', action='store_true')
    parser.add_argument('--output', help='Optional bounded JSON receipt; the only file written')
    args = parser.parse_args(argv)
    try:
        report = examine(args.build_dir, args.config_header, args.expected_profile, args.require_unity, args.require_pch)
    except (OSError, ValueError, TypeError, KeyError) as error:
        report = {'schema_version': 1, 'status': 'FAIL', 'errors': [str(error)[:1000]],
                  'application_built': False, 'application_executed': False}
    result = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        Path(args.output).write_text(result, encoding='utf-8')
    print(result, end='')
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
