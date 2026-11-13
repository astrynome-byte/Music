#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Check original runtime/source inputs again, including after a packaging failure."""
from pathlib import Path
import argparse
import importlib.util
import json

spec = importlib.util.spec_from_file_location('cadence_retained_packaging_inputs', Path(__file__).with_name('prepare_retained_package.py'))
data = importlib.util.module_from_spec(spec)
spec.loader.exec_module(data)

parser = argparse.ArgumentParser()
for name in ('validated', 'stage', 'application-source', 'corresponding-sources', 'output'):
    parser.add_argument('--' + name, type=Path, required=True)
args = parser.parse_args()
data.require(not args.output.exists(), 'New immutability report required')
report = {'schema_version': 1, 'scope': 'Read-only input comparison after retained packaging; no application execution',
          'passed': False, 'stage_preserved': False, 'source_preserved': False,
          'component_sources_preserved': False, 'errors': []}
try:
    snapshot = data.read_json(args.validated)
    report['stage_preserved'] = data.inventory(args.stage) == snapshot['stage_files']
    report['component_sources_preserved'] = data.inventory(args.corresponding_sources) == snapshot['component_files']
    data.source_identity(args.application_source)
    report['source_preserved'] = True
    report['passed'] = all(report[key] for key in ('stage_preserved', 'source_preserved', 'component_sources_preserved'))
except (OSError, ValueError, KeyError) as error:
    report['errors'].append(str(error)[:1200])
args.output.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
raise SystemExit(0 if report['passed'] else 1)
