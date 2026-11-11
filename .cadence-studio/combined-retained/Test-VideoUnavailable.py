#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Recheck the retained Windows app's unavailable video encoder error.

Release console mode logs to AppLocalDataLocation, not stdout. Read only logs
created/changed by this invocation in the two known independent Cadence profiles.
No provider, settings, registry entry, application byte or original score changes.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import time

EXPECTED_EXE_SHA = '35d8b076cacddb8b37a4f23aeea9899e6ab4ac9214e9a5b1125bbeccf26cf39e'
MARKER = b'video_export_ffmpeg_unavailable'
MAX_RUNTIME_LOG = 2_000_000


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(65536), b''):
            digest.update(block)
    return digest.hexdigest()


def log_roots():
    parent = os.environ.get('LOCALAPPDATA')
    if not parent:
        raise ValueError('LOCALAPPDATA is required to locate the independent Cadence runtime logs')
    root = Path(parent) / 'CadenceStudio'
    return [root / name / 'logs' for name in ('CadenceStudio4', 'CadenceStudio4Development')]


def snapshot(roots):
    result = {}
    for root in roots:
        if not root.is_dir():
            continue
        if root.is_symlink() or getattr(root, 'is_junction', lambda: False)():
            raise ValueError('Linked runtime log directory is unsupported')
        for path in root.glob('*.log'):
            if path.is_file() and not path.is_symlink():
                stat = path.stat()
                result[path] = (stat.st_size, stat.st_mtime_ns)
    return result


def capture_new_logs(roots, before, output):
    records = []
    marker = False
    for path, state in snapshot(roots).items():
        if before.get(path) == state:
            continue
        if state[0] > MAX_RUNTIME_LOG:
            raise ValueError('New runtime log exceeds the bounded capture size: ' + str(path))
        raw = path.read_bytes()
        destination = output / ('missing-video-runtime-' + str(len(records)) + '.log')
        destination.write_bytes(raw)
        found = MARKER in raw
        marker = marker or found
        records.append({'original_path': str(path), 'retained_path': str(destination),
                        'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'guard_marker_seen': found})
    return records, marker


def qualify(executable, score, output, roots=None):
    roots = log_roots() if roots is None else roots
    before = snapshot(roots)
    copied = output / 'Été piano – négatif.musicxml'
    shutil.copyfile(score, copied)
    video = output / 'sans fournisseur FFmpeg.mp4'
    command = [str(executable), '--test-mode', '--score-video', '--resolution', '360p',
               '--fps', '24', '--ls', '0', '--ts', '0', '-o', str(video), str(copied)]
    environment = dict(os.environ)
    removed = []
    for name in list(environment):
        if re.match(r'^(QT|QML|CMAKE_|VCPKG_|VSCMD_|VSINSTALLDIR$|VCINSTALLDIR$|VCTools|INCLUDE$|LIB$|LIBPATH$|WindowsSdk|WindowsSDK|UniversalCRTSdkDir$|UCRTVersion$|DevEnvDir$|ExtensionSdkDir$|FrameworkDir|FrameworkVersion)', name, re.I):
            removed.append(name)
            del environment[name]
    if os.name == 'nt':
        environment['PATH'] = str(executable.parent) + ';' + str(Path(os.environ['SystemRoot']) / 'System32')
    process = {'command': command, 'timed_out': False, 'exit_code': None}
    started = time.monotonic()
    stdout = stderr = b''
    try:
        result = subprocess.run(command, cwd=executable.parent, env=environment,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, check=False)
        process['exit_code'] = result.returncode
        stdout, stderr = result.stdout, result.stderr
    except subprocess.TimeoutExpired as error:
        process['timed_out'] = True
        stdout, stderr = error.stdout or b'', error.stderr or b''
    process['elapsed_seconds'] = time.monotonic() - started
    (output / 'missing-video.stdout.log').write_bytes(stdout)
    (output / 'missing-video.stderr.log').write_bytes(stderr)
    logs, file_marker = capture_new_logs(roots, before, output)
    standard_marker = MARKER in stdout + stderr
    output_bytes = video.stat().st_size if video.is_file() else 0
    passed = (not process['timed_out'] and process['exit_code'] == 1331
              and (file_marker or standard_marker) and output_bytes == 0)
    return {'passed': passed, 'expected_exit_code': 1331, 'writer_ret_code': 4, 'process': process,
            'guard_marker_in_standard_streams': standard_marker, 'guard_marker_in_new_runtime_log': file_marker,
            'runtime_logs': logs, 'output_bytes': output_bytes, 'score_copy_sha256': sha(copied),
            'child_sdk_environment_removed_names': removed, 'child_path': environment.get('PATH'),
            'source_logging_rule': 'globalmodule.cpp: console destination only GuiApp or runtime debug; Release console uses profile/logs',
            'provider_or_registry_modified_by_probe': False, 'application_may_write_own_cadence_profile': True, 'mp4_format_validated': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', type=Path, required=True)
    parser.add_argument('--score', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_relative_to(args.executable.resolve().parent) or output.is_relative_to(args.score.resolve().parent):
        parser.error('Output must be outside the stage binary and original fixture directories')
    output.mkdir(parents=True, exist_ok=False)
    report = {'schema_version': 1, 'passed': False, 'status': 'failed', 'application_recompiled': False,
              'executable': str(args.executable), 'expected_executable_sha256': EXPECTED_EXE_SHA,
              'human_listening': False, 'mp4_format_validated': False, 'errors': []}
    try:
        if os.name != 'nt' or struct.calcsize('P') != 8:
            raise ValueError('Native Windows x64 is required; this host cannot validate the retained application')
        executable = args.executable.resolve(strict=True)
        if sha(executable) != EXPECTED_EXE_SHA:
            raise ValueError('Executable differs from the original full-build2002 SHA; nothing was launched')
        report['executable_sha256'] = sha(executable)
        report['negative_video'] = qualify(executable, args.score.resolve(strict=True), output)
        report['passed'] = report['negative_video']['passed']
        report['status'] = 'passed_explicit_missing_encoder_error' if report['passed'] else 'failed'
    except (OSError, ValueError, KeyError) as error:
        report['errors'].append(str(error))
    (output / 'video-unavailable-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('CADENCE_VIDEO_NEGATIVE_REPORT_BEGIN')
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    print('CADENCE_VIDEO_NEGATIVE_REPORT_END')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
