#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare existing57-check reports and35 stable exports; no application run."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path, PureWindowsPath

EXE = 'd957ffc99497cb01b1f00f82ba1d6e89ef84547708506c6c51423675805e140a'
STABLE = {'export-mxl', 'export-svg', 'export-png', 'export-mid', 'export-wav', 'export-flac', 'export-mp3'}


def checked_report(path):
    with path.open('rb') as stream:
        raw = stream.read(4 * 1024 * 1024 + 1)
    if len(raw) > 4 * 1024 * 1024:
        raise ValueError('Corpus report exceeds bound')
    report = json.loads(raw)
    checks = report.get('checks')
    if (report.get('executable_sha256') != EXE or type(report.get('version_exit_code')) is not int or report['version_exit_code'] != 0
            or not isinstance(checks, list) or len(checks) != 57
            or any(type(row.get('passed')) is not bool or not row['passed'] for row in checks)):
        raise ValueError('All57 existing checks must pass for the exact retained executable')
    stable = {}
    for row in checks:
        if row['stage'] not in STABLE:
            continue
        for output in row['outputs']:
            key = (row['fixture'], row['stage'], PureWindowsPath(output['path']).name)
            checksum = output.get('sha256')
            if key in stable or not isinstance(checksum, str) or len(checksum) != 64 or any(c not in '0123456789abcdef' for c in checksum):
                raise ValueError('Duplicate or malformed stable-output identity')
            if row['stage'] == 'export-wav' and output.get('audio', {}).get('passed') is not True:
                raise ValueError('Existing numeric WAV gate did not pass')
            stable[key] = checksum
    if len(stable) != 35:
        raise ValueError('Exactly35 stable output hashes required')
    return {'checks_passed': 57, 'report_sha256': hashlib.sha256(raw).hexdigest(), 'stable': stable}


def compare_reports(baseline, candidate):
    first, second = checked_report(baseline), checked_report(candidate)
    if first['stable'] != second['stable']:
        raise ValueError('Removing the local ICU forwarder changed a stable export')
    return {'schema_version': 1, 'status': 'passed-existing57-checks-and35-identical-stable-exports',
            'baseline_checks_passed': 57, 'candidate_checks_passed': 57, 'stable_hashes_identical': 35,
            'baseline_report_sha256': first['report_sha256'], 'candidate_report_sha256': second['report_sha256'],
            'executable_sha256': EXE, 'GUI_editing_or_listening_qualified': False,
            'comparison_scope': 'Existing converter imports/native reopen/exports/linked parts;35 deterministic formats, PDF metadata and native serialization not hash-compared'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(compare_reports(args.baseline, args.candidate), indent=2))


if __name__ == '__main__':
    main()
