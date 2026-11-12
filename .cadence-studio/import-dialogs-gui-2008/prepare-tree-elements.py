# SPDX-License-Identifier: GPL-3.0-only
"""Convert the private UTF-8 files dict to reviewable Git tree elements. No network."""
import argparse
import json
from pathlib import Path, PurePosixPath

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--payload', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
payload = json.loads(args.payload.read_text(encoding='utf-8'))
files = payload['files']
if not isinstance(files, dict) or not files or 'target.json' in files:
    raise ValueError('Expected a nonempty private files dict without target.json')
workflow = 'cadence-import-dialogs-gui-2008.yml'
if workflow not in files:
    raise ValueError('Complete workflow is missing from the payload')
elements = []
for name, content in sorted(files.items()):
    path = PurePosixPath(name)
    if (not isinstance(content, str) or path.is_absolute() or '\\' in name or
            str(path) != name or any(part in ('', '.', '..') for part in path.parts)):
        raise ValueError('Unsafe path or non-text payload member')
    destination = '.github/workflows/' + name if name == workflow else '.cadence-studio/import-dialogs-gui-2008/' + name
    elements.append(dict(path=destination, mode='100644', type='blob', content=content))
args.output.write_text(json.dumps(dict(tree_elements=elements), ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
print(json.dumps(dict(status='prepared-private-tree-elements-only', entries=len(elements), publication_performed=False, target_json_present=False)))
