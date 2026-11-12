#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Read three exact pre-existing logs; do not run Cadence or dump environment."""
import argparse
import hashlib
import json
from pathlib import Path
import re

RUN=43200417277
ARTIFACT=13933979236
DRIVER='936bfd88cafdb29138ec3c1119e5c059341a5e4a'
ZIP_SHA='9147c47614d82426b33120b32ac4a9ce67a68b47c107135f94bf1dbc77f0192f'
ZIP_BYTES=99979
SOURCE='0e05d04acbeee32f1b561f24493d7ef41c322081'
EXE='35d8b076cacddb8b37a4f23aeea9899e6ab4ac9214e9a5b1125bbeccf26cf39e'
MAX_FILE=2_000_000
MAX_PRINT=40_000
LOG_NAMES=('basic-control-gui.cadence-log-delta.txt','basic-control-gui.stderr.txt','basic-control-gui.stdout.txt')
SCRIPT_PINS={'manifest.json':'4066ff04f1f1b3fc57d0e96e64d4e0d91f99ea292a8bd1f2b65d0281cfd516df',
 'render.js':'e070da169e076714a4156eb8e4d49d13a6d25c7195b88f78e5440ef85c319987',
 'saved.js':'2614cb3513aa4089bea6cfb262424e3a5acd23af59f739b053ae5c1651a20763'}


def emit(value):
    print('CADENCE_RETENTION_READBACK_BEGIN')
    print(json.dumps(value,ensure_ascii=True,sort_keys=True))
    print('CADENCE_RETENTION_READBACK_END')


def sha(raw):return hashlib.sha256(raw).hexdigest()


def regular(root,relative,maximum):
    current=root
    for component in Path(relative).parts:
        current=current/component
        if current.is_symlink():raise ValueError('Symlink member refused')
    if not current.is_file() or not current.resolve().is_relative_to(root) or current.stat().st_size>maximum:
        raise ValueError('Missing, non-regular, outside-root or oversized source member')
    raw=current.read_bytes()
    if len(raw)>maximum:raise ValueError('Source member grew beyond bound')
    return raw


# Sanitisation follows our existing ci-evidence-reader and library-ui reader.
# Drop entire lines which could describe environment or credentials; hash the
# original file first, and distinguish the redacted excerpt from raw evidence.
ENV_LINE=re.compile(r'(?i)(?:\b(?:environment|environ|PATH|LOCALAPPDATA|APPDATA|USERPROFILE|GH_TOKEN|GITHUB_TOKEN|password|secret|authorization)\b|\b(?:RUNNER_|GITHUB_)[A-Z_]+)')


def sanitize(value):
    value=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','',value)
    lines=[]
    for line in value.splitlines():
        if ENV_LINE.search(line):lines.append('[environment/credential line excluded]');continue
        line=re.sub(r'(?:github_pat_[A-Za-z0-9_]+|gh[pousr]_[A-Za-z0-9_]+)','[REDACTED]',line)
        line=re.sub(r'(https?://[^\s?]+)\?[^\s]+',r'\1?[REDACTED]',line)
        lines.append(''.join(c for c in line if c.isprintable() or c=='\t'))
    return '\n'.join(lines)


def read(root,metadata):
    # This metadata is retrieved read-only from GitHub, not manufactured from
    # downloaded file names. Fix the producer run, commit, ZIP size and digest.
    if (metadata.get('id')!=ARTIFACT or metadata.get('size_in_bytes')!=ZIP_BYTES
        or metadata.get('digest')!='sha256:'+ZIP_SHA or metadata.get('expired') is not False
        or metadata.get('workflow_run',{}).get('id')!=RUN
        or metadata.get('workflow_run',{}).get('head_sha')!=DRIVER):
        raise ValueError('Source artifact metadata differs from the authenticated run-2 manifest')
    report=json.loads(regular(root,'retention-results/retention-report.json',256_000).decode('utf-8-sig'))
    if (report.get('source_commit')!=SOURCE or report.get('executable_sha256')!=EXE
        or report.get('build_number')!=2002 or report.get('status')!='failed_or_blocked'
        or report.get('diagnostic_extension_uri')!='action://extensions/cadence/resource-retention-qa'
        or report.get('cases',[{}])[0].get('token')!='76309f97-7f4a-4d0c-a8ca-1f6e09553c5b'
        or report['cases'][0].get('diagnostic_extension_hashes')!=SCRIPT_PINS):
        raise ValueError('Source report differs from the actual run-2 job-log manifest')
    for name,pin in SCRIPT_PINS.items():
        if sha(regular(root,'retention-results/basic-control-diagnostic-extension/'+name,64_000))!=pin:
            raise ValueError('Retained diagnostic extension does not match source report digest')
    result={'schema_version':1,'reader_only':True,'application_executed':False,'source_run_id':RUN,
        'source_artifact_id':ARTIFACT,'producer_driver_commit':DRIVER,'source_commit':SOURCE,
        'artifact_metadata_size_and_digest_verified':True,'artifact_zip_sha256_from_GitHub_API':ZIP_SHA,
        'artifact_ZIP_bytes_downloaded_and_independently_rehashed_by_this_reader':False,
        'source_report_and_all_three_diagnostic_scripts_match_pins':True,
        'scope':'Three exact existing application log files only; no environment dump or new GUI operation',
        'max_raw_file_bytes':MAX_FILE,'max_excerpt_bytes_per_file':MAX_PRINT,'files':[]}
    for name in LOG_NAMES:
        relative='retention-results/'+name
        raw=regular(root,relative,MAX_FILE)
        # UTF8 strict decoding makes byte provenance explicit; replacement only
        # for a tail cut into a multibyte sequence in an oversized excerpt.
        raw.decode('utf-8')
        excerpt=raw if len(raw)<=MAX_PRINT else raw[:MAX_PRINT//2]+b'\n[... bounded middle omitted ...]\n'+raw[-MAX_PRINT//2:]
        value=sanitize(excerpt.decode('utf-8',errors='replace'))
        # Sanitisation may add marker text: retain a final byte bound as well.
        encoded=value.encode('utf-8')
        if len(encoded)>MAX_PRINT:value=encoded[:MAX_PRINT].decode('utf-8',errors='ignore')
        result['files'].append({'path':relative,'bytes':len(raw),'sha256_original_file':sha(raw),
            'original_file_SHA256_was_not_previously_available':True,
            'truncated':len(raw)>MAX_PRINT,'excerpt_redacted':True,'text':value})
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True,type=Path)
    parser.add_argument('--artifact-metadata',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    # A separate output is the only thing this diagnostic writes. Never open or
    # mutate scores, installed files or application profiles.
    root=args.root.resolve();output=args.output.resolve()
    if not root.is_dir() or output.exists() or output==root or output.is_relative_to(root) or root.is_relative_to(output):
        raise ValueError('Require an existing input and new independent output directory')
    if args.artifact_metadata.is_symlink() or args.artifact_metadata.stat().st_size>64_000:
        raise ValueError('Unsafe artifact metadata file')
    metadata=json.loads(args.artifact_metadata.read_text(encoding='utf-8-sig'))
    result=read(root,metadata)
    output.mkdir(parents=True)
    (output/'readback.json').write_text(json.dumps(result,ensure_ascii=True,indent=2)+'\n',encoding='utf-8')
    emit(result)


if __name__=='__main__':main()
