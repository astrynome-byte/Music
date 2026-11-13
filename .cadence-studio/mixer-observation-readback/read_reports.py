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

RUN = 43415198550
ARTIFACT = 14031158386
DRIVER = '5aed1488550adda6c68240a9651d28e20f9139c6'
DIGEST = 'sha256:de0099fff63f934cca223d0f2e5de460eb9a93120e5d60ffc6d0e282d89a7ebf'
PNG_SHA256 = {
    'app-observation/before-observation.png': '13b9fee974bf5ff8c24721cc3e0dde2d5083dde5c3f3385bacd369f5d2078337',
    'app-observation/after-observation.png': '6647b55b50a4895dd028db99646843181c0d8d3378da894ecfdae7ec1e827581',
}
EXTRA_JSON = (
    'mixer-observer-build/observer-source-ledger.json',
    'mixer-observer-build/observation-plan.original.json',
    'mixer-observer-build/activation-target.original.json',
)


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
    if run['head_sha'] != DRIVER or run['status'] != 'completed' or run['conclusion'] != 'success' or run['run_attempt'] != 1:
        raise ValueError('Exact successful original F10 collection required')
    if artifact['id'] != ARTIFACT or artifact['digest'] != DIGEST or artifact['size_in_bytes'] != 226669 or artifact['expired'] is not False or artifact['workflow_run']['id'] != RUN:
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

    def select(path, relative_name):
        nonlocal total
        if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != root.parent):
            raise ValueError('Linked evidence refused')
        info = path.stat(follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 2 * 1024**2:
            raise ValueError('Evidence must be a bounded regular file')
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if relative_name in PNG_SHA256:
            if digest != PNG_SHA256[relative_name] or not raw.startswith(b'\x89PNG\r\n\x1a\n'):
                raise ValueError('Original expected capture digest or PNG header differs')
        elif path.suffix == '.json':
            json.loads(raw.decode('utf-8-sig'))
        total += len(raw)
        if total > 8 * 1024**2 or len(selected) >= 48:
            raise ValueError('Selected evidence exceeds bound')
        row = {'path': relative_name, 'bytes': len(raw), 'sha256': digest,
               'base64_original_bytes': base64.b64encode(raw).decode('ascii')}
        selected.append((Path(relative_name), raw, row))

    for path in sorted(files):
        rel = path.relative_to(own)
        if any(part in ('stage', 'profile', 'runtime') for part in rel.parts):
            continue
        name = path.name
        if not (name in ('result.json', 'observation-result.json', 'observation-report.json', 'app-clock-validation.json')
                or (len(rel.parts) > 1 and rel.parts[-2] in ('uia', 'clock-stats', 'registered-harness-stats') and path.suffix == '.json')
                or rel.as_posix() in PNG_SHA256):
            continue
        select(path, rel.as_posix())
    for relative_name in EXTRA_JSON:
        path = root / relative_name
        if path.exists() or path.is_symlink():
            select(path, relative_name)
    # Nothing is emitted or written until both original capture identities have
    # been proved. A missing or changed PNG cannot produce a partial success.
    names = {row['path'] for _, _, row in selected}
    if not set(PNG_SHA256).issubset(names):
        raise ValueError('Both exact original before/after captures are required')
    output.mkdir()
    for rel, raw, row in selected:
        destination = output / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        print('CADENCE_MIXER_ORIGINAL_FILE_BEGIN')
        print(json.dumps(row, separators=(',', ':')))
        print('CADENCE_MIXER_ORIGINAL_FILE_END')
    receipt = {'scope': 'Original single native F10 collection with partial UIA; data only, visual review pending',
               'run': RUN, 'artifact': ARTIFACT, 'driver': DRIVER,
               'expected_archive_bytes': 226669, 'expected_archive_digest': DIGEST,
               'archive_digest_source': 'Pinned GitHub metadata before one actions/download-artifact request; see action download log for its computed archive digest',
               'application_or_SDK_executed_by_reader': False,
               'UIA_complete': False, 'Mixer_visual_review_complete': False,
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
