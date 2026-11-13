#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Prepare reviewed tree data only. Never publish, dispatch or execute a payload."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parent
PREFIX = '.cadence-studio/retained-2008-msi/'
WORKFLOW = '.github/workflows/cadence-retained2008-msi.yml'
GENERATED = {'helpers.manifest.json', 'HANDOFF.json', 'tree-elements.prepared.json',
             'target.prepared.json', 'package-bindings.prepared.json', 'qa-artifact.selection.prepared.json'}


def checksum(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode()


def main():
    files = {}
    for path in sorted(ROOT.rglob('*')):
        relative = path.relative_to(ROOT).as_posix()
        if not path.is_file() or '__pycache__' in path.parts or relative in GENERATED:
            continue
        raw = path.read_bytes(); raw.decode('utf-8')
        files[relative] = raw
    manifest = {'schema_version': 1,
                'scope': 'Retained original2008 runtime packaging/real MSI QA recipe; no app build or public release assertion',
                'files': [{'name': name, 'bytes': len(raw), 'sha256': checksum(raw)} for name, raw in files.items()]}
    manifest_raw = encode(manifest)
    (ROOT / 'helpers.manifest.json').write_bytes(manifest_raw)
    binding = json.loads(files['package-bindings.template.json'])
    assert binding['ready'] is False and binding['qualification_sha256'] is None
    binding_raw = encode(binding)
    selection = json.loads(files['qa-artifact.selection.template.json'])
    selection['ready'] = True
    selection['note'] = 'Root-reviewed acquisition: authenticate real successful QA outer ZIP, then measure raw aggregate. This is not an MSI success assertion.'
    selection_raw = encode(selection)
    target = json.loads(files['target.template.json'])
    target.update(ready=True, helpers_manifest_sha256=checksum(manifest_raw),
                  bindings_sha256=checksum(binding_raw), qa_selection_sha256=checksum(selection_raw),
                  note='Prepared activation data only; root alone publishes. Activate acquisition/packaging/real MSI test; no MSI or gift success is asserted.')
    target_raw = encode(target)
    for name, raw in [('package-bindings.prepared.json', binding_raw), ('qa-artifact.selection.prepared.json', selection_raw), ('target.prepared.json', target_raw)]:
        (ROOT / name).write_bytes(raw)
    tree_files = dict(files)
    tree_files.update({'helpers.manifest.json': manifest_raw, 'package-bindings.json': binding_raw,
                       'qa-artifact.selection.json': selection_raw, 'target.json': target_raw})
    elements = [{'path': PREFIX + name, 'mode': '100644', 'type': 'blob', 'content': raw.decode('utf-8')}
                for name, raw in tree_files.items()]
    elements.append({'path': WORKFLOW, 'mode': '100644', 'type': 'blob',
                     'content': files['cadence-retained2008-msi.prepared.yml'].decode()})
    payload = {'scope': 'Prepared Git tree entries only; no remote operation performed', 'tree': elements}
    payload_raw = encode(payload)
    (ROOT / 'tree-elements.prepared.json').write_bytes(payload_raw)
    handoff = {'schema_version': 1, 'status': 'reviewed-private-preparation-ready-for-root-controlled-publication',
               'root_or_remote_modified': False, 'application_recompiled': False, 'MSI_produced_or_executed_locally': False,
               'final_gift_qualified': False, 'manifest_sha256': checksum(manifest_raw),
               'payload_sha256': checksum(payload_raw), 'payload_bytes': len(payload_raw), 'tree_elements': len(elements),
               'namespace': PREFIX.rstrip('/'), 'workflow_path': WORKFLOW,
               'target_prepared_sha256': checksum(target_raw), 'qa_outer_artifact': selection['artifact'],
               'raw_qualification_bytes_and_sha256': None,
               'raw_qualification_measurement_plan': 'After outer ZIP/API authentication only; emit separate measured bindings, preserve original raw JSON',
               'runtime_files_unchanged': 2712,
               'source_original': binding['source_original_commit'], 'source_CI': binding['source_ci_commit'],
               'source_tree': binding['source_tree'], 'executable_sha256': binding['executable_sha256'],
               'product_version': '4.7.6.2008',
               'delivery_artifact_name_pattern': 'cadence-retained2008-msi-delivery-{run_number}-{run_attempt}',
               'logs_artifact_name_pattern': 'cadence-retained2008-msi-logs-{run_number}-{run_attempt}',
               'actual_verification': json.loads((ROOT / 'checks/preparation.json').read_text()),
               'next_action': 'Root reviews prepared tree and publishes once; hosted Windows authenticates retained inputs, packages only, performs RequireGui MSI qualification. No public link is created by this workflow.'}
    (ROOT / 'HANDOFF.json').write_bytes(encode(handoff))
    print(json.dumps({k: handoff[k] for k in ('status', 'manifest_sha256', 'payload_sha256', 'payload_bytes', 'tree_elements')}))


if __name__ == '__main__':
    main()
