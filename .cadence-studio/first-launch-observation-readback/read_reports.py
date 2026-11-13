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

RUN = 43421688966
JOB = 131872965961
ARTIFACT = 14035045365
DRIVER = 'f11080d9cabb2f500e8f282ff91f546f38201cca'
DIGEST = 'sha256:66a8535c2bc69380a74888056fef33f210e233e58b768246b4eb987948582087'
ARCHIVE_BYTES = 412971
PNG_SHA256 = {
    'firstlaunch-gui-results/first-start-without-INI.png': '24389dd79c72de688c2b80a123b50887c7a69ee82f7349b4464f0a82d9fca175',
}
MANDATORY = {
    'firstlaunch-gui-results/first-launch-observation.json',
    'firstlaunch-gui-results/profile.json',
    'firstlaunch-gui-results/seed-removal.json',
    'firstlaunch-gui-results/readiness/native-readiness.json',
    'firstlaunch-authentication.json',
    'firstlaunch-producer-guard.json',
    'firstlaunch-data-output/readback-receipt.json',
} | set(PNG_SHA256)
SELECTED = MANDATORY | {
    'firstlaunch-gui-results/verify-no-INI-before-start.stdout.log',
    'firstlaunch-gui-results/cleanup-owned-unseeded-profile.stdout.log',
    'firstlaunch-gui-results/application.stdout.log',
    'firstlaunch-gui-results/application.stderr.log',
    'firstlaunch-gui-results/probe.stdout.log',
    'firstlaunch-gui-results/probe.stderr.log',
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('Metadata authentication cannot redirect')


def verify_metadata(output):
    if os.environ.get('GITHUB_REPOSITORY') != 'astrynome-byte/Music':
        raise ValueError('Exact repository context required')
    token = os.environ['GH_TOKEN']
    opener = urllib.request.build_opener(NoRedirect)
    values = {}
    for endpoint in (f'actions/runs/{RUN}', f'actions/jobs/{JOB}', f'actions/artifacts/{ARTIFACT}'):
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
    job = values[f'actions/jobs/{JOB}']
    artifact = values[f'actions/artifacts/{ARTIFACT}']
    if run['id'] != RUN or run['repository']['full_name'] != 'astrynome-byte/Music' or run['head_branch'] != 'cadence-studio/windows-build' or run['head_sha'] != DRIVER or run['status'] != 'completed' or run['conclusion'] != 'success' or run['run_attempt'] != 1:
        raise ValueError('Exact successful original first-launch collection required')
    if job['id'] != JOB or job['run_id'] != RUN or job['head_sha'] != DRIVER or job['status'] != 'completed' or job['conclusion'] != 'success' or 'windows-2022' not in job['labels']:
        raise ValueError('Exact original successful Windows first-launch job required')
    if artifact['id'] != ARTIFACT or artifact['digest'] != DIGEST or artifact['size_in_bytes'] != ARCHIVE_BYTES or artifact['expired'] is not False or artifact['workflow_run']['id'] != RUN or artifact['workflow_run']['head_sha'] != DRIVER:
        raise ValueError('Original evidence artifact identity differs')
    Path(output).write_text(json.dumps(values, indent=2) + '\n')


def read_reports(root, output):
    root, output = Path(root), Path(output)
    if root.is_symlink() or not root.is_dir() or output.exists():
        raise ValueError('Plain input and new output required')
    files = list(root.rglob('*'))
    if len(files) > 256:
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
        if total > 8 * 1024**2 or len(selected) >= 64:
            raise ValueError('Selected evidence exceeds bound')
        row = {'path': relative_name, 'bytes': len(raw), 'sha256': digest,
               'base64_original_bytes': base64.b64encode(raw).decode('ascii')}
        selected.append((Path(relative_name), raw, row))

    for path in sorted(files):
        if path.is_dir():
            if path.is_symlink():
                raise ValueError('Linked evidence directory refused')
            continue
        rel = path.relative_to(root).as_posix()
        # Large already authenticated runtime inventory/restoration maps and
        # unrelated original companion ledgers are intentionally not read or printed.
        if rel not in SELECTED:
            continue
        select(path, rel)
    # No output until mandatory original report/profile/no-INI records, guards
    # and the one exact owned-window capture have all been authenticated as data.
    names = {row['path'] for _, _, row in selected}
    if not MANDATORY.issubset(names):
        raise ValueError('Mandatory first-launch records and exact original capture required')
    output.mkdir()
    for rel, raw, row in selected:
        destination = output / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        print('CADENCE_FIRST_LAUNCH_ORIGINAL_FILE_BEGIN')
        print(json.dumps(row, separators=(',', ':')))
        print('CADENCE_FIRST_LAUNCH_ORIGINAL_FILE_END')
    receipt = {'scope': 'Original first startup without INI of real2008 known-failed31 stage; data only, visual review pending',
               'run': RUN, 'job': JOB, 'artifact': ARTIFACT, 'driver': DRIVER,
               'expected_archive_bytes': ARCHIVE_BYTES, 'expected_archive_digest': DIGEST,
               'archive_digest_source': 'Pinned GitHub metadata before one actions/download-artifact request; see action download log for its computed archive digest',
               'application_or_SDK_executed_by_reader': False,
               'original_artifact_file_count_measured': sum(path.is_file() for path in files),
               'selected_file_count': len(selected),
               'large_runtime_inventory_and_restoration_maps_omitted': True,
               'visual_review_complete': False, 'setup_completion_qualified': False,
               'playback_qualified': False, 'full_qualification_complete': False, 'MSI_produced_or_tested': False,
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
