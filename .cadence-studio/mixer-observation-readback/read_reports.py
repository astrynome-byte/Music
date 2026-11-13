# SPDX-License-Identifier: GPL-3.0-only
"""Read bounded evidence only; never import or execute downloaded artifact files."""
import argparse
import base64
import hashlib
import json
import os
import stat
import urllib.request
from pathlib import Path

RUN = 43405873102
ARTIFACT = 14027790752
DRIVER = '04f5bea5632bdc2497815faa03787c1183ed36ae'
DIGEST = 'sha256:e609de8ee5b67191d9e7d8238e91be615af14ac9b6c334434c58c4523fa7834d'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('Metadata authentication cannot redirect')


def verify_metadata(output):
    if os.environ.get('GITHUB_REPOSITORY') != 'astrynome-byte/Music':
        raise ValueError('Exact repository context required')
    token = os.environ['GH_TOKEN']
    opener = urllib.request.build_opener(NoRedirect)
    values = {}
    for endpoint in (f'actions/runs/{RUN}', f'actions/artifacts/{ARTIFACT}'):
        request = urllib.request.Request('https://api.github.com/repos/astrynome-byte/Music/' + endpoint,
                                        headers={'Authorization': 'Bearer ' + token,
                                                 'Accept': 'application/vnd.github+json',
                                                 'User-Agent': 'Cadence-data-only-observation-reader'})
        with opener.open(request, timeout=30) as response:
            raw = response.read(2 * 1024**2 + 1)
            if response.status != 200 or len(raw) > 2 * 1024**2:
                raise ValueError('Bounded metadata HTTP200 required')
            values[endpoint] = json.loads(raw)
    run = values[f'actions/runs/{RUN}']
    artifact = values[f'actions/artifacts/{ARTIFACT}']
    if run['head_sha'] != DRIVER or run['status'] != 'completed' or run['conclusion'] != 'failure' or run['run_attempt'] != 1:
        raise ValueError('Exact failed original observation required')
    if artifact['id'] != ARTIFACT or artifact['digest'] != DIGEST or artifact['size_in_bytes'] != 150363436 or artifact['expired'] is not False or artifact['workflow_run']['id'] != RUN:
        raise ValueError('Original evidence artifact identity differs')
    Path(output).write_text(json.dumps(values, indent=2) + '\n')


def read_reports(root, output):
    root, output = Path(root), Path(output)
    if root.is_symlink() or not root.is_dir() or output.exists():
        raise ValueError('Plain input and new output required')
    own = root / 'mixer-owned-observation'
    if own.is_symlink() or not own.is_dir():
        raise ValueError('Exact owned observation directory required')
    files = list(own.rglob('*'))
    if len(files) > 5000:
        raise ValueError('Evidence inventory exceeds bound')
    selected = []
    total = 0
    for path in sorted(files):
        rel = path.relative_to(own)
        # Exclude the restored application, profiles, registry backup and all executable files.
        if any(part in ('stage', 'profile', 'runtime') for part in rel.parts):
            continue
        name = path.name
        if not (name in ('result.json', 'observation-result.json', 'observation-report.json', 'app-clock-validation.json')
                or name.endswith(('.stdout.log', '.stderr.log'))
                or (len(rel.parts) > 1 and rel.parts[-2] == 'uia' and path.suffix == '.json')
                or name in ('before-observation.png', 'after-observation.png')):
            continue
        if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != root.parent):
            raise ValueError('Linked evidence refused')
        info = path.stat(follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 2 * 1024**2:
            raise ValueError('Evidence must be a bounded regular file')
        raw = path.read_bytes()
        total += len(raw)
        if total > 8 * 1024**2 or len(selected) >= 48:
            raise ValueError('Selected evidence exceeds bound')
        row = {'path': rel.as_posix(), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
               'base64_original_bytes': base64.b64encode(raw).decode('ascii')}
        selected.append((rel, raw, row))
    if not selected:
        raise ValueError('No original observation reports found')
    output.mkdir()
    for rel, raw, row in selected:
        destination = output / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        print('CADENCE_MIXER_ORIGINAL_FILE_BEGIN')
        print(json.dumps(row, separators=(',', ':')))
        print('CADENCE_MIXER_ORIGINAL_FILE_END')
    receipt = {'scope': 'Original failed observation data only; no application or SDK execution',
               'run': RUN, 'artifact': ARTIFACT, 'driver': DRIVER,
               'files': [{k: v for k, v in row.items() if k != 'base64_original_bytes'} for _, _, row in selected]}
    (output / 'readback-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--metadata-output')
    parser.add_argument('--root')
    parser.add_argument('--output')
    args = parser.parse_args()
    if args.metadata_output:
        verify_metadata(args.metadata_output)
    else:
        read_reports(args.root, args.output)
