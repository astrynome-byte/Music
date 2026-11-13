#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Authenticate one completed Windows QA artifact and relocate only raw JSON.

This reader never executes any downloaded payload. Aggregate/report bytes are
preserved; an explicit index records their locations on the new runner.
"""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PureWindowsPath
import re
import time
import urllib.request
import zipfile

REPOSITORY = 'astrynome-byte/Music'
READER_SHA256 = '9bdcbc4732057fc50f8ba5387578d68d292682864a21938b717d29df662875ae'
GATES = {'native_practice', 'native_omr', 'native_transcription', 'audio_transcription_import',
         'cli57', 'reference35', 'aac5', 'stage_notices', 'stage_GUI', 'musical_roundtrip'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def selected(path):
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    require(value.get('schema_version') == 1 and value.get('ready') is True,
            'QA artifact selection remains inactive until actual measured pins are reviewed')
    require(value.get('repository') == REPOSITORY and value.get('run_id') == 43421094979
            and value.get('job_id') == 131870989277
            and value.get('head_sha') == 'cc88a26de1fd0966c311aae5a8e5e25b130b6629',
            'Exact original2008 resumed QA producer required')
    for row in (value.get('artifact', {}),):
        require(isinstance(row.get('bytes'), int) and 0 < row['bytes'] <= 2 * 1024**3
                and isinstance(row.get('sha256'), str) and re.fullmatch('[a-f0-9]{64}', row['sha256']),
                'Actual measured outer artifact byte pins required')
    require(value.get('qualification') == {'mode': 'measure-raw-member-after-authenticated-outer', 'bytes': None, 'sha256': None},
            'Unmeasured raw aggregate must be explicit; outer ZIP is the authentication anchor')
    require(isinstance(value['artifact'].get('id'), int) and value['artifact']['id'] > 0
            and isinstance(value['artifact'].get('name'), str) and value['artifact']['name']
            and value.get('source_temp_root') == 'D:\\a\\_temp', 'Exact artifact ID/name and original runner path required')
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selection', type=Path, required=True)
    parser.add_argument('--reader-root', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--bindings-template', type=Path, required=True)
    parser.add_argument('--bindings-output', type=Path, required=True)
    args = parser.parse_args()
    plan = selected(args.selection)
    require(os.name == 'nt' and os.environ.get('GITHUB_ACTIONS') == 'true'
            and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
            and os.environ.get('GITHUB_REPOSITORY') == REPOSITORY, 'Disposable Windows repository Actions context required')
    temp = Path(os.environ['RUNNER_TEMP']).resolve(strict=True)
    for path in (args.work, args.output):
        require(path.is_absolute() and not path.exists() and path.resolve().is_relative_to(temp)
                and not any(p.is_symlink() or (p.exists() and getattr(p.stat(), 'st_file_attributes', 0) & 0x400)
                            for p in (path, *path.parents)), 'New plain owned paths beneath RUNNER_TEMP required')
    require(args.bindings_output.is_absolute() and not args.bindings_output.exists()
            and args.bindings_output.resolve().is_relative_to(temp)
            and args.bindings_output.parent.is_dir(), 'New measured bindings beneath RUNNER_TEMP required')
    template_raw = args.bindings_template.read_bytes()
    binding = json.loads(template_raw.decode('utf-8-sig'))
    require(binding.get('ready') is False and binding.get('qualification_sha256') is None
            and binding.get('source_ci_commit') == '95cebb22fe6cbde22919c94f2b480bd14c3eb8de',
            'Inactive exact package bindings must await actual raw QA measurement')
    require(args.work != args.output and not args.work.is_relative_to(args.output)
            and not args.output.is_relative_to(args.work), 'Separate data acquisition/output paths required')
    original_reader = args.reader_root / 'read_existing_stage.py'
    require(sha(original_reader) == READER_SHA256, 'Reviewed original DATAONLY reader changed')
    spec = importlib.util.spec_from_file_location('cadence_original_data_reader', original_reader)
    reader = importlib.util.module_from_spec(spec); spec.loader.exec_module(reader)
    args.work.mkdir(); args.output.mkdir()
    token = os.environ['GH_TOKEN']

    def request(endpoint, redirect=False):
        require(re.fullmatch(r'actions/(?:runs|jobs|artifacts)/[0-9]+(?:/zip)?', endpoint), 'Pinned read-only Actions endpoint required')
        req = urllib.request.Request('https://api.github.com/repos/' + REPOSITORY + '/' + endpoint,
            headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
                     'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'Cadence-QA-DataReader/1.0'}, method='GET')
        return urllib.request.build_opener(reader.PublicRedirectOnly() if redirect else reader.NoRedirect()).open(req, timeout=120)

    def metadata(endpoint, label):
        with request(endpoint) as response:
            raw = response.read(4 * 1024**2 + 1)
            require(response.status == 200 and len(raw) <= 4 * 1024**2, 'Bounded API metadata HTTP200 required')
        (args.output / label).write_bytes(raw)
        return json.loads(raw.decode('utf-8-sig'))

    run = metadata('actions/runs/' + str(plan['run_id']), 'qa-run.original.json')
    require(run.get('id') == plan['run_id'] and run.get('head_sha') == plan['head_sha']
            and run.get('status') == 'completed' and run.get('conclusion') == 'success'
            and run.get('head_branch') == 'cadence-studio/windows-build'
            and run.get('repository', {}).get('full_name') == REPOSITORY, 'Actual completed successful resumed QA run required')
    job = metadata('actions/jobs/' + str(plan['job_id']), 'qa-job.original.json')
    require(job.get('id') == plan['job_id'] and job.get('run_id') == plan['run_id']
            and job.get('status') == 'completed' and job.get('conclusion') == 'success'
            and 'windows-2022' in job.get('labels', []), 'Actual successful Windows QA job required')
    pin = plan['artifact']
    artifact = metadata('actions/artifacts/' + str(pin['id']), 'qa-artifact.original.json')
    require(artifact.get('id') == pin['id'] and artifact.get('name') == pin['name']
            and artifact.get('size_in_bytes') == pin['bytes'] and artifact.get('digest') == 'sha256:' + pin['sha256']
            and artifact.get('expired') is False and artifact.get('workflow_run', {}).get('id') == plan['run_id']
            and artifact['workflow_run'].get('head_sha') == plan['head_sha']
            and datetime.datetime.fromisoformat(artifact['expires_at'].replace('Z', '+00:00')) > datetime.datetime.now(datetime.timezone.utc),
            'Exact unexpired resumed QA artifact required')
    archive_path = args.work / 'qa-original.zip'
    count = 0; measured = hashlib.sha256(); deadline = time.monotonic() + 600
    with request('actions/artifacts/' + str(pin['id']) + '/zip', True) as response, archive_path.open('xb') as target:
        require(response.status == 200, 'Artifact HTTP200 required')
        while True:
            require(time.monotonic() < deadline, 'QA acquisition deadline exceeded')
            chunk = response.read(1024**2)
            if not chunk:
                break
            count += len(chunk); require(count <= pin['bytes'], 'Artifact exceeds pinned bytes')
            measured.update(chunk); target.write(chunk)
    require(count == pin['bytes'] and measured.hexdigest() == pin['sha256'], 'QA outer ZIP bytes/SHA256 differ')
    files = {}
    with zipfile.ZipFile(archive_path) as archive:
        rows = reader.zip_rows(archive)
        def original(suffix, expected=None):
            found = [name for name in rows if name == suffix or name.endswith('/' + suffix)]
            require(len(found) == 1, 'One exact QA JSON member required: ' + suffix)
            info = rows[found[0]]
            require(0 < info.file_size <= 8 * 1024**2 and (expected is None or info.file_size == expected['bytes']), 'Bounded pinned QA JSON required')
            raw = archive.read(info)
            require(expected is None or hashlib.sha256(raw).hexdigest() == expected['sha256'], 'Original QA JSON bytes differ')
            return raw
        raw = original('_temp/retained-qualification.json')
        actual_qualification = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                                'measurement_basis': 'raw member of independently hashed authenticated outer QA artifact'}
        aggregate = json.loads(raw.decode('utf-8-sig'))
        require(aggregate.get('ready') is True and aggregate.get('passed') is True
                and aggregate.get('application_recompiled') is False and set(aggregate.get('gates', {})) == GATES
                and aggregate.get('source_original_commit') == binding['source_original_commit']
                and aggregate.get('source_ci_commit') == binding['source_ci_commit']
                and aggregate.get('source_tree') == binding['source_tree']
                and aggregate.get('executable_sha256') == binding['executable_sha256']
                and aggregate.get('build_number') == 2008 and aggregate.get('product_version') == '4.7.6.2008'
                and aggregate.get('counts') == {'cli_checks': 57, 'reference_outputs': 35, 'music_aac_cases': 5},
                'Completed actual ten-gate QA aggregate required')
        (args.output / 'retained-qualification.json').write_bytes(raw)
        for row in aggregate['gates'].values():
            require(row.get('passed') is True, 'An actual gate has not passed')
            relative = PureWindowsPath(row['path']).relative_to(PureWindowsPath(plan['source_temp_root'])).as_posix()
            reader.member(relative)
            raw = original('_temp/' + relative, row)
            target = args.output.joinpath(*relative.split('/'))
            if target.exists():
                require(target.read_bytes() == raw, 'Two gates map to different bytes')
            else:
                target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
            files[row['path']] = {'relative_path': relative, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    receipt = {'schema_version': 1, 'status': 'authenticated-resumed-QA-raw-JSON-relocated-no-execution',
               'source_run_id': plan['run_id'], 'source_job_id': plan['job_id'], 'source_driver_commit': plan['head_sha'],
               'outer_artifact': pin, 'qualification': actual_qualification, 'reports': files,
               'raw_reports_preserved': True, 'original_source_temp_root': plan['source_temp_root'],
               'new_evidence_root': str(args.output), 'application_executed': False,
               'application_or_test_recompiled': False, 'GitHub_write_performed': False,
               'redirect_authorization_forwarded': False}
    (args.output / 'evidence-index.json').write_bytes((json.dumps(receipt, indent=2) + '\n').encode())
    require(args.bindings_template.read_bytes() == template_raw, 'Original inactive package bindings changed')
    binding.update(ready=True, qualification_sha256=actual_qualification['sha256'],
                   actual_qualification_measurement=actual_qualification, actual_qa_artifact=pin,
                   note='NEW measured bindings from authenticated successful QA ZIP; original template and reports unchanged')
    args.bindings_output.write_bytes((json.dumps(binding, indent=2) + '\n').encode())
    print(json.dumps({k: v for k, v in receipt.items() if k != 'reports'}))


if __name__ == '__main__':
    main()
