# SPDX-License-Identifier: GPL-3.0-only
"""Linux preparation checks only. Never starts Cadence, UIA, or a Windows GUI."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import yaml

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--pwsh', type=Path, required=True)
parser.add_argument('--source-selection', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
checks = []

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def require(name, passed, **detail):
    checks.append(dict(check=name, passed=bool(passed), **detail))
    if not passed:
        raise RuntimeError(name)

try:
    manifest = json.loads((root / 'gui-manifest.json').read_text())
    failures = [e['path'] for e in manifest['files'] if
                (root / e['path']).stat().st_size != e['bytes'] or digest(root / e['path']) != e['sha256']]
    require('runtime-helper-manifest-integrity', not failures, entries=len(manifest['files']), mismatches=failures)
    payload = json.loads((root / 'payload-utf8.json').read_text())
    failures = [p for p, text in payload['files'].items() if (root / p).read_text() != text]
    require('UTF8-payload-round-trip', not failures, entries=len(payload['files']), mismatches=failures)
    target = json.loads((root / 'target.template.json').read_text())
    require('pending-target-has-no-produced-identities',
            target['status'] == 'pending-actual-build-2008' and
            all(target[k] is None for k in ('producer_run_id', 'artifact_id', 'run_attempt')) and
            all(v is None for section in ('source', 'stage') for v in target[section].values()) and
            all(target[k] is None for k in ('producer_driver_commit', 'run_number', 'artifact_name', 'artifact_digest_from_github_metadata', 'artifact_expires_utc')) and
            all(v is None for record in target['artifact_files'].values() for v in record.values()) and
            not (root / 'target.json').exists())
    producer = json.loads((root / 'producer-context.json').read_text())
    require('failed-producer-excluded-replacement-known-stage-pending',
            producer['status'] == 'reviewed-launched-producer' and
            producer['producer_run_id'] == 43322336613 and
            producer['producer_job_id'] == 131545929459 and
            producer['producer_driver_commit'] == 'd685753476a30b8dc29e1fab979bb355263a4fd6' and
            producer['producer_run_number'] == 10 and producer['producer_run_attempt'] == 1 and
            producer['expected_build_number'] == 2008 and
            all(producer[k] is None for k in ('actual_artifact_id', 'actual_archive_sha256', 'actual_executable_sha256')) and
            producer['previous_failed_producer']['run_id'] == 43319506534 and
            producer['previous_failed_producer']['conclusion'] == 'failure' and
            producer['previous_failed_producer']['stage_produced'] is False and
            producer['previous_failed_producer']['eligible_for_GUI'] is False and
            {p['run_id'] for p in producer['rejected_prior_producers']} == {43319506534, 43321209033} and
            all(p['conclusion'] == 'failure' and p['eligible_for_GUI'] is False for p in producer['rejected_prior_producers']))
    require('Git-bytes-preserved-on-Windows', (root / '.gitattributes').read_bytes() == b'* -text\n')
    selection = json.loads((args.source_selection / 'source.json').read_text())
    require('known-final-source-selection', selection['source'] == {
        'commit': '49272b75a4107c97130b8a46727af6a8c95d1c9a',
        'tree': 'fae79e265b3a21431388cd432a853228ffd7676b'} and
        selection['patch']['sha256'] == 'c7654d9a8fa18adf9bcce0b6198c1ef907a2e5886a19339a08ed8ccb80f7b70d',
        source_json_sha256=digest(args.source_selection / 'source.json'))
    require('actual-frozen-patch-hash', digest(args.source_selection / selection['patch']['file']) == selection['patch']['sha256'])
    for p in sorted(root.glob('*.py')):
        ast.parse(p.read_text(), filename=str(p))
        require('Python-AST', True, file=p.name)
    steps = yaml.safe_load((root / 'workflow-fragment.yml').read_text())
    retain = [s for s in steps if s.get('uses') == 'actions/upload-artifact@v4']
    require('workflow-fragment-retains-evidence-always', len(steps) == 5 and len(retain) == 1 and retain[0].get('if') == 'always()', steps=len(steps), Actions_run=False)
    workflow = yaml.safe_load((root / 'cadence-import-dialogs-gui-2008.yml').read_text())
    events = workflow.get('on', workflow.get(True))
    full_steps = workflow['jobs']['actual2008-import-dialogs']['steps']
    downloads = [s for s in full_steps if s.get('uses') == 'actions/download-artifact@v4']
    require('complete-private-target-only-push-workflow', set(events) == {'workflow_dispatch', 'push'} and
            events['push'] == {'branches': ['cadence-studio/windows-build'], 'paths': ['.cadence-studio/import-dialogs-gui-2008/target.json']} and
            workflow['jobs']['actual2008-import-dialogs']['runs-on'] == 'windows-2022' and
            len(downloads) == 1 and downloads[0]['with']['repository'] == 'astrynome-byte/Music' and
            sum(s.get('uses') == 'actions/upload-artifact@v4' and s.get('if') == 'always()' for s in full_steps) == 1 and
            not any('install-qt' in s.get('uses', '') for s in full_steps),
            steps=len(full_steps), Actions_run=False)
    require('initial-payload-does-not-match-push-activation-path', 'target.json' not in payload['files'] and
            all('.cadence-studio/import-dialogs-gui-2008/' + name not in events['push']['paths'] for name in payload['files']))
    with tempfile.TemporaryDirectory(prefix='cadence-import-gui-check-', dir='/tmp') as directory:
        scratch = Path(directory)
        converted = scratch / 'tree-elements.json'
        converted_result = subprocess.run(['python3', '-I', str(root / 'prepare-tree-elements.py'), '--payload', str(root / 'payload-utf8.json'), '--output', str(converted)], text=True, capture_output=True, timeout=20)
        require('actual-files-dict-to-tree-elements-conversion', converted_result.returncode == 0, exit_code=converted_result.returncode, stdout=converted_result.stdout, stderr=converted_result.stderr)
        elements = json.loads(converted.read_text())['tree_elements']
        require('tree-elements-preserve-all-bytes-and-map-workflow',
                len(elements) == len(payload['files']) and all(
                    e['mode'] == '100644' and e['type'] == 'blob' and
                    e['content'] == payload['files'][e['path'].removeprefix('.github/workflows/').removeprefix('.cadence-studio/import-dialogs-gui-2008/')]
                    for e in elements) and
                sum(e['path'] == '.github/workflows/cadence-import-dialogs-gui-2008.yml' for e in elements) == 1)
        for number, step in enumerate(full_steps):
            if 'run' in step:
                (scratch / f'workflow-step-{number}.ps1').write_text(step['run'])
        env = dict(os.environ, XDG_CACHE_HOME=str(scratch / 'cache'), XDG_CONFIG_HOME=str(scratch / 'config'), XDG_DATA_HOME=str(scratch / 'data'), CADENCE_GUI_HELPER=str(root), CADENCE_GUI_CHECK_TEMP=str(scratch))
        program = r'''
$ErrorActionPreference='Stop'
$root=$env:CADENCE_GUI_HELPER
$files=@(Get-ChildItem -LiteralPath $root -File | Where-Object { $_.Extension -in @('.ps1','.psm1') })+@(Get-ChildItem -LiteralPath $env:CADENCE_GUI_CHECK_TEMP -File -Filter '*.ps1')
foreach($file in $files){
 $tokens=$null;$errors=$null
 [void][System.Management.Automation.Language.Parser]::ParseFile($file.FullName,[ref]$tokens,[ref]$errors)
 if($errors.Count){throw ($errors|Out-String)}
}
. "$root/Read-ActualImportTarget.ps1"
$missing=Join-Path $env:CADENCE_GUI_CHECK_TEMP 'must-stay-absent'
$expected='Only a reviewed, actually produced stage2008 target is accepted; the pending template cannot run.'
$readerRejected=$false
try{[void](Read-ActualImportTarget "$root/target.template.json" $missing)}catch{if($_.Exception.Message-cne$expected){throw};$readerRejected=$true}
if(-not$readerRejected){throw 'Pending reader was accepted.'}
$launcherRejected=$false
try{& "$root/Run-ImportDialogsGui.ps1" -TargetPath "$root/target.template.json" -SourceSelectionDirectory $missing -StagePath $missing -RestorationPath $missing -ProbePath $missing -OutputDirectory $missing}catch{if($_.Exception.Message-cne$expected){throw};$launcherRejected=$true}
if(-not$launcherRejected-or(Test-Path -LiteralPath $missing)){throw 'Pending launcher did not stop before native/profile access.'}
@{PowerShell_AST_files=$files.Count;pending_reader_rejected=$readerRejected;pending_launcher_rejected=$launcherRejected;native_or_profile_calls=$false}|ConvertTo-Json -Compress
'''
        result = subprocess.run([str(args.pwsh), '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', program], env=env, text=True, capture_output=True, timeout=40)
        require('PowerShell-AST-and-actual-pending-rejection', result.returncode == 0, exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)
        wave = scratch / 'original-three-notes.wav'
        result = subprocess.run(['python3', '-I', str(root / 'Prepare-OriginalWave.py'), '--output', str(wave)], text=True, capture_output=True, timeout=20)
        require('actual-original-WAV-decoding-format-and-SHA', result.returncode == 0, exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)
    checks.append(dict(check='Windows-native-probe-and-GUI', status='not-compiled-or-executed', GUI_executed=False, produced_stage2008=None))
    status = 'passed-local-preparation-only'
except Exception as exc:
    checks.append(dict(check='exception', passed=False, error=str(exc)))
    status = 'failed-local-preparation'
report = dict(schema_version=1, status=status, GUI_executed=False, Windows_CPP_compiled=False, actual_build_or_stage_identity=None, checks=checks)
args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(dict(status=status, checks=len(checks), GUI_executed=False, report=str(args.output))))
raise SystemExit(0 if status == 'passed-local-preparation-only' else 1)
