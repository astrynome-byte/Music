# SPDX-License-Identifier: GPL-3.0-only
"""Check source pins and preparation guards; never builds an MSI or runs Windows."""
from pathlib import Path
import argparse
import ast
import hashlib
import importlib.util
import json
import os
import subprocess
import tempfile
import uuid
import yaml

root = Path(__file__).resolve().parents[1]
application = Path('/workspace/cadence')
for path in root.glob('*.py'):
    ast.parse(path.read_text())
spec = importlib.util.spec_from_file_location('retained2008_packaging_checks', root / 'prepare_retained_package.py')
data = importlib.util.module_from_spec(spec)
spec.loader.exec_module(data)
template = root / 'package-bindings.template.json'
assert json.loads(template.read_text())['ready'] is False
try:
    data.bindings(template)
except ValueError as error:
    assert 'inactive' in str(error)
else:
    raise AssertionError('Inactive bindings were accepted')
asset_lock = json.loads((root / 'packaging-assets.lock.json').read_text())
for row in asset_lock['files']:
    raw = subprocess.check_output(['git', '-C', str(application), 'show', data.ORIGINAL + ':' + row['path']])
    assert len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256']
assert str(uuid.uuid5(uuid.UUID('2e899094-116c-4518-8f13-94847281ff71'), 'CadenceStudio-4.7.6.2008')).upper() == 'CA4AC56B-9ED9-568F-9F5A-0D9475D4CC26'
project = (root / 'PackagingOnly.CMakeLists.txt').read_text()
assert 'LANGUAGES NONE' in project and not any(line.lstrip().startswith(('add_library(', 'add_executable(', 'install(', 'execute_process(')) for line in project.splitlines())
assert 'CPACK_INSTALL_CMAKE_PROJECTS' in project and 'MUE_PACK_INSTALL_DIR ON' in project
pwsh = '/workspace/toolchains/cadence-pwsh/pwsh'
records = []
with tempfile.TemporaryDirectory(prefix='cadence-retained2008-package-preparation-') as folder:
    folder = Path(folder)
    env = dict(os.environ, XDG_CACHE_HOME='/tmp/cadence-qa-xdg/cache', XDG_CONFIG_HOME='/tmp/cadence-qa-xdg/config', XDG_DATA_HOME='/tmp/cadence-qa-xdg/data')
    scripts = [root / 'Package-Retained2008.ps1', root / 'Test-PackageActivation.ps1', root / 'OwnProcessJob.psm1', root / 'installer-test/Test-Retained2008Installer.ps1', root / 'installer-test/upstream/Test-MsiInstall.ps1']
    workflow = yaml.safe_load((root / 'cadence-retained2008-msi.prepared.yml').read_text())
    steps = workflow['jobs']['package-and-install-retained']['steps']
    for index, step in enumerate(steps):
        if 'run' in step:
            block = folder / ('workflow-step-' + str(index) + '.ps1')
            block.write_text(step['run'])
            scripts.append(block)
    assert not any('install-qt' in row.get('uses', '') for row in steps)
    assert not any('cmake --build' in row.get('run', '') or 'Build.ps1' in row.get('run', '') or 'Configure.ps1' in row.get('run', '') for row in steps)
    script = folder / 'parse.ps1'
    script.write_text("$ErrorActionPreference='Stop'\n" + '\n'.join("$t=$null;$e=$null;[void][Management.Automation.Language.Parser]::ParseFile('" + str(path).replace("'", "''") + "',[ref]$t,[ref]$e);if($e.Count){throw ($e|Out-String)}" for path in scripts))
    result = subprocess.run([pwsh, '-NoLogo', '-NoProfile', '-NonInteractive', '-File', str(script)], env=env, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    # Exercise the actual native-OS guard before it can access metadata or COM.
    output = folder / 'must-not-exist'
    args = [pwsh, '-NoLogo', '-NoProfile', '-NonInteractive', '-File', str(root / 'Package-Retained2008.ps1')]
    for name in ('StagePath', 'ApplicationSource', 'SourceProfilePath', 'ArtifactDirectory', 'RuntimeInventoryPath', 'ReadbackReceiptPath', 'PackageBindingsPath', 'QualificationReportPath', 'CorrespondingSourceBundle', 'BuildRecipeDirectory'):
        args.extend(['-' + name, str(folder / ('absent-' + name))])
    args.extend(['-OutputDirectory', str(output)])
    refused = subprocess.run(args, env=env, text=True, capture_output=True, timeout=30)
    assert refused.returncode != 0 and 'disposable native Windows x64' in refused.stderr and not output.exists()
    # Isolated-mode imports must work before the real Windows invocation.
    for name in ('prepare_retained_package.py', 'bundle_delivery.py', 'verify_package_immutability.py', 'Restore-QualifiedQaEvidence.py'):
        result = subprocess.run(['python', '-I', '-B', str(root / name), '--help'], text=True, capture_output=True, timeout=30)
        assert result.returncode == 0, result.stderr
        records.append({'case': 'isolated-help-' + name, 'passed': True})
    # CMake must fail on this native Linux host before assets/stage access; it
    # is never permitted to cross-claim a Windows package in this preparation.
    tiny = folder / 'cmake-guard'; tiny.mkdir()
    (tiny / 'CMakeLists.txt').write_text(project)
    cmake = '/workspace/toolchains/cadence-python/lib/python3.12/site-packages/cmake/data/bin/cmake'
    result = subprocess.run([cmake, '-S', str(tiny), '-B', str(folder / 'cmake-build')], text=True, capture_output=True, timeout=30)
    assert result.returncode != 0 and 'requires native Windows' in result.stderr
    records.append({'case': 'CMake-native-Windows-guard', 'passed': True})
    # Resolve cross-job paths without rewriting authentic aggregate bytes.
    evidence = folder / 'cross-job-evidence'; evidence.mkdir()
    original = folder / 'original-aggregate.json'
    raw = b'{"ready":true,"original":"must stay byte-identical"}\r\n'
    original.write_bytes(raw)
    destination = evidence / 'qa/report.json'; destination.parent.mkdir()
    destination.write_bytes(b'{"passed":true}\r\n')
    row = {'path': r'D:\a\_temp\qa\report.json', 'bytes': destination.stat().st_size, 'sha256': data.sha(destination)}
    index = {'schema_version': 1, 'raw_reports_preserved': True, 'reports': {row['path']: {'relative_path': 'qa/report.json', 'bytes': row['bytes'], 'sha256': row['sha256']}}}
    (evidence / 'evidence-index.json').write_text(json.dumps(index))
    assert data.qualification_file(row, evidence) == destination
    assert original.read_bytes() == raw
    index['reports'][row['path']]['relative_path'] = '../escape.json'
    (evidence / 'evidence-index.json').write_text(json.dumps(index))
    try:
        data.qualification_file(row, evidence)
    except ValueError:
        pass
    else:
        raise AssertionError('Escaping cross-job report accepted')
    records.append({'case': 'cross-job-raw-byte-preservation-and-path-escape-rejection', 'passed': True})
    spec = importlib.util.spec_from_file_location('retained2008_qa_selection_checks', root / 'Restore-QualifiedQaEvidence.py')
    reader = importlib.util.module_from_spec(spec); spec.loader.exec_module(reader)
    try:
        reader.selected(root / 'qa-artifact.selection.template.json')
    except ValueError as error:
        assert 'inactive' in str(error)
    else:
        raise AssertionError('Inactive QA artifact selection accepted')
    records.append({'case': 'inactive-QA-artifact-selection-refused-before-network', 'passed': True})
report = {'schema_version': 1, 'scope': 'Local source-pin/AST and native/isolated-mode preparation guards only',
          'packaging_assets_Git_blobs_verified': len(asset_lock['files']), 'PowerShell_AST_files': len(scripts),
          'inactive_template_refused': True, 'actual_Linux_PS_invocation_refused_before_metadata_output': True,
          'GUID2008_derived_from_original_namespace': True, 'no_language_or_application_target_in_packaging_project': True,
          'workflow_without_Qt_SDK_application_configure_build_or_repeated_QA': True,
          'additional_guards': records, 'Windows_or_MSI_executed': False, 'root_or_refs_modified': False}
(root / 'checks/preparation.json').write_text(json.dumps(report, indent=2) + '\n')
print('PASS retained2008 preparation:9Git blobs,PS files and workflow AST,templates/OS/CMake/isolated imports/relocation; no MSI or Windows execution')
