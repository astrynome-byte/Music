#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Download and data-extract only pinned free reader/sample assets in a new CI folder."""
from __future__ import annotations
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import struct
import subprocess
import time
import urllib.parse
import urllib.request
import zipfile


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def require_native_ci():
    if os.name!='nt' or platform.machine().lower() not in ('amd64','x86_64') or os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('CI')!='true' or os.environ.get('RUNNER_ENVIRONMENT')!='github-hosted':
        raise ValueError('Only disposable native Windows x64 GitHub-hosted runners are allowed')


def require_new_temporary(path):
    root=Path(os.environ['RUNNER_TEMP']).resolve();path=path.absolute()
    for entry in [path,*path.parents]:
        if entry.is_symlink() or getattr(entry,'is_junction',lambda:False)():
            raise ValueError('Runtime paths must not traverse links')
    path=path.resolve()
    if root not in path.parents or path.exists():
        raise ValueError('New path strictly below RUNNER_TEMP required')
    return path


def download(url, target, expected_bytes, expected_sha256=None, expected_git_blob=None):
    if urllib.parse.urlsplit(url).scheme!='https' or not 0<expected_bytes<=100000000:
        raise ValueError('Bounded explicit HTTPS source required')
    target.parent.mkdir(parents=True,exist_ok=True)
    received=0;digest=hashlib.sha256();git=hashlib.sha1(b'blob '+str(expected_bytes).encode()+b'\0')
    with urllib.request.urlopen(url,timeout=90) as response, target.open('xb') as output:
        if response.status!=200:raise ValueError('Unexpected download response')
        while True:
            block=response.read(min(1048576,expected_bytes+1-received))
            if not block:break
            received+=len(block)
            if received>expected_bytes:raise ValueError('Download exceeds independently pinned size')
            output.write(block);digest.update(block);git.update(block)
    actual=digest.hexdigest()
    if received!=expected_bytes or (expected_sha256 is not None and actual!=expected_sha256) or (expected_git_blob is not None and git.hexdigest()!=expected_git_blob):
        raise ValueError('Downloaded bytes do not match their independent pinned identity: '+target.name)
    return {'bytes':received,'sha256':actual,'git_blob_sha1':git.hexdigest(),'url':url}


def reader(root, driver):
    lock=json.loads((driver/'sfizz-reader-lock.json').read_text())
    installer=root/'sfizz-1.2.3-win64.exe';extractor_zip=root/'innoextract-1.9-windows.zip'
    receipts={'installer':download(lock['installer_url'],installer,lock['installer_bytes'],lock['installer_sha256']),
              'extractor':download(lock['extractor_url'],extractor_zip,lock['extractor_bytes'],lock['extractor_sha256'])}
    tool=root/'extractor';tool.mkdir()
    with zipfile.ZipFile(extractor_zip) as archive:
        for info in archive.infolist():
            relative=PurePosixPath(info.filename)
            if relative.is_absolute() or '..' in relative.parts or '\\' in info.filename or ':' in info.filename or info.file_size>5000000 or ((info.external_attr>>16)&0o170000)==0o120000:
                raise ValueError('Unsafe official extractor ZIP member')
            target=tool.joinpath(*relative.parts)
            if info.is_dir():target.mkdir(parents=True,exist_ok=True);continue
            target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as output:output.write(archive.read(info))
    executable=tool/'innoextract.exe'
    if executable.stat().st_size!=lock['extractor_exe_bytes'] or sha(executable)!=lock['extractor_exe_sha256']:
        raise ValueError('Exact official extraction utility required before execution')
    extracted=root/'reader-unpacked'
    args=[str(executable),'--extract','--output-dir',str(extracted),str(installer)]
    with (root/'extractor.stdout.log').open('xb') as out,(root/'extractor.stderr.log').open('xb') as err:
        process=subprocess.Popen(args,stdout=out,stderr=err,cwd=root,creationflags=subprocess.CREATE_NO_WINDOW)
        try:code=process.wait(timeout=90)
        except subprocess.TimeoutExpired:
            process.kill();process.wait(timeout=10);raise RuntimeError('Owned data-extraction utility timed out')
    if code!=0:raise RuntimeError('Reader data extraction failed; no installer was executed')
    for item in extracted.rglob('*'):
        if item.is_symlink() or getattr(item,'is_junction',lambda:False)():raise ValueError('Extracted reader contains a link')
    bundle=extracted/'commoncf/VST3/sfizz.vst3'
    expected={item['path']:item for item in lock['plugin_bundle_files']}
    actual={item.relative_to(extracted).as_posix():item for item in bundle.rglob('*') if item.is_file()}
    if set(actual)!=set(expected):raise ValueError('Extracted VST3 bundle file set differs from inspected official package')
    for name,path in actual.items():
        pin=expected[name]
        if path.stat().st_size!=pin['bytes'] or sha(path)!=pin['sha256']:raise ValueError('Extracted VST3 member hash differs')
    binary=bundle/'Contents/x86_64-win/sfizz.vst3';raw=binary.read_bytes();pe=struct.unpack_from('<I',raw,0x3c)[0]
    if raw[:2]!=b'MZ' or raw[pe:pe+4]!=b'PE\0\0' or struct.unpack_from('<H',raw,pe+4)[0]!=0x8664:
        raise ValueError('The real reader DLL must be native x64 PE')
    receipts.update({'bundle':str(bundle),'binary':str(binary),'binary_sha256':sha(binary),'binary_bytes':binary.stat().st_size,
                     'bundle_files_verified':len(actual),'native_x64_pe_verified':True,'windows_installer_executed':False,
                     'global_plugin_directory_modified':False,'extraction_command_exit_code':code,
                     'source_archive_url':lock['source_url'],'source_archive_sha256':lock['source_archive_sha256'],
                     'source_archive_downloaded_by_this_job':False})
    return receipts


def samples(root,driver):
    manifest=json.loads((driver/'asset-source-manifest.json').read_text())
    if manifest['commit']!='28092772094b2d9f1148d84cea97f4545b8c687d' or len(manifest['files'])!=46:
        raise ValueError('Exact CC0 two-instrument source selection required')
    folder=root/'vsco-ce-mini';folder.mkdir()
    def one(pin):
        name=pin['path'];path=PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name:raise ValueError('Unsafe sample source path')
        url='https://raw.githubusercontent.com/sgossner/VSCO-2-CE/'+manifest['commit']+'/'+urllib.parse.quote(name,safe='/')
        record=download(url,folder.joinpath(*path.parts),pin['bytes'],expected_git_blob=pin['git_blob_sha1']);record['file']=name;return record
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        records=list(pool.map(one,manifest['files']))
    patches={}
    for instrument in manifest['instruments']:
        patch=folder/instrument['patch'];text=patch.read_text()
        default=re.search(r'^default_path=([^\r\n]+)',text,re.M).group(1).replace('\\','/')
        sample_names=re.findall(r'^sample=([^\r\n]+)',text,re.M)
        if len(sample_names)!=instrument['regions']:raise ValueError('Source SFZ region count differs')
        for sample in sample_names:
            if not folder.joinpath(*PurePosixPath(default+sample).parts).is_file():raise ValueError('Source SFZ refers to an absent sample')
        patches[instrument['patch']]=str(patch)
    # A controlled CC0 derivative changes each flute REGION gain by exactly -18dB.
    # This distinguishes real SFZ restoration from sfizz's default sine program.
    original=(folder/'FluteSusVib.sfz').read_text();header,separator,regions=original.partition('<region>')
    pattern=r'(?m)^(volume=)([-+0-9.]+)(\s*)$'
    count=len(re.findall(pattern,regions));assert count==13
    changed=re.sub(pattern,lambda m:m.group(1)+format(float(m.group(2))-18.0,'g')+m.group(3),regions)
    attenuated=folder/'Cadence-QA-Flute-minus18.sfz';attenuated.write_text(header+separator+changed,encoding='utf-8')
    patches['Cadence-QA-Flute-minus18.sfz']=str(attenuated)
    return {'root':str(folder),'source_commit':manifest['commit'],'downloaded_source_bytes':sum(x['bytes'] for x in records),
            'original_file_count':len(records),'original_records':records,'patches':patches,
            'qa_derivative':{'file':attenuated.name,'source':'FluteSusVib.sfz','region_gain_delta_db':-18.0,
                            'changed_region_volumes':count,'sha256':sha(attenuated),'license':'CC0-1.0'},
            'SFZ_loaded_by_preparation':False,'raw_SFZ_support_assumed':False}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--mode',choices=('reader','samples'),required=True)
    p.add_argument('--root',type=Path,required=True);args=p.parse_args();require_native_ci();driver=Path(__file__).resolve().parent
    if args.mode=='reader':
        root=require_new_temporary(args.root);root.mkdir();report={'schema_version':1,'mode':'reader','passed':False,'error':None}
    else:
        root=args.root.absolute();temporary=Path(os.environ['RUNNER_TEMP']).resolve()
        for entry in [root,*root.parents]:
            if entry.is_symlink() or getattr(entry,'is_junction',lambda:False)():raise ValueError('Runtime paths must not traverse links')
        root=root.resolve()
        if temporary not in root.parents or not root.is_dir() or (root/'vsco-ce-mini').exists():raise ValueError('Owned existing reader root and new sample folder required')
        owner=json.loads((root/'reader-assets.json').read_text());
        if owner.get('passed') is not True:raise ValueError('Successfully verified owned reader setup required first')
        report={'schema_version':1,'mode':'samples','passed':False,'error':None}
    try:
        report['assets']=reader(root,driver) if args.mode=='reader' else samples(root,driver);report['passed']=True
    except Exception as error:report['error']=str(error)
    name='reader-assets.json' if args.mode=='reader' else 'sample-assets.json'
    (root/name).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('CADENCE_SFZ_ASSETS_BEGIN');print(json.dumps(report,ensure_ascii=False));print('CADENCE_SFZ_ASSETS_END')
    return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
