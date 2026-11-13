#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Check configuration-only regeneration against authenticated producer receipts."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

CI='95cebb22fe6cbde22919c94f2b480bd14c3eb8de'
TREE='c5452043983a048ef0aeef085615af903de3f5b0'
EXE='13cd4e6d2f408d2e64b187d4c3bff1188ff4192ac7b670d3a12373bbeb37f6cd'

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def require(value,message):
    if not value: raise ValueError(message)

def unique_suffix(root,suffix):
    found=[p for p in root.rglob(Path(suffix).name) if p.is_file() and p.as_posix().endswith('/'+suffix)]
    require(len(found)==1,'One authenticated original report required: '+suffix)
    return found[0]

def runtime_check(root,expected):
    files={p.relative_to(root).as_posix():p for p in root.rglob('*') if p.is_file()}
    require(set(files)==set(expected),'Runtime file extent changed')
    for name,p in files.items():
        require(not p.is_symlink() and p.stat().st_size==expected[name]['bytes'] and sha(p)==expected[name]['sha256'],'Original runtime changed: '+name)
    return len(files)

def git(root,*args):
    return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()

def check(temp,source):
    restoration=read(temp/'retained-restoration.json')
    original=read(temp/'cadence-stage-delivery/cadence-build.json')
    state=read(temp/'build-cadence/cadence-build.json')
    result=temp/'build-cadence/cadence-build-result.json'
    original_result=temp/'cadence-stage-delivery/cadence-build-result.json'
    macro=unique_suffix(temp/'retained-data-originals/originals/logs','macro-profile-prebuild.json')
    header=temp/'build-cadence/muse_framework_config.h'
    require(git(source,'rev-parse','HEAD')==CI and git(source,'rev-parse','HEAD^{tree}')==TREE and not git(source,'status','--porcelain','--untracked-files=all'),'Exact original clean CI source required')
    require(state['source_commit']==original['source_commit']==CI and state['variant']=='Cadence' and state['build_number']==2008 and state['configuration']=='Release' and state['windows_system_aac'] is True and state['source_dirty_at_configure'] is False,'Original configuration identity differs')
    require(Path(state['source_path']).resolve()==source.resolve() and Path(state['install_path']).resolve()==(temp/'stage-cadence').resolve(),'Fresh configuration paths differ')
    for key in ('qt_version','open_source_zlib','corresponding_sources'):
        require(state[key]==original[key],'Regenerated dependency profile differs: '+key)
    require(sha(header)==read(macro)['config_header_sha256'],'Regenerated framework header differs from original compiled header')
    require(result.read_bytes()==original_result.read_bytes(),'Original build-result was rewritten')
    require(read(result)['source_commit']==CI and read(result)['executable_sha256']==EXE,'Original build-result identity differs')
    count=runtime_check(temp/'stage-cadence',restoration['runtime_files'])
    require(count==2712,'Original runtime count differs')
    return {'schema_version':1,'passed':True,'status':'configuration-only-matches-original-built-stage','source_ci_commit':CI,'source_tree':TREE,'executable_sha256':EXE,'build_number':2008,'config_header_sha256':sha(header),'original_macro_report_sha256':sha(macro),'runtime_files_unchanged':count,'application_recompiled':False,'application_install_target_executed':False,'original_build_result_not_modified':True}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--temporary-root',type=Path,required=True);p.add_argument('--source-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); require(not a.output.exists(),'New report required')
    report=check(a.temporary_root,a.source_root)
    a.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))

if __name__=='__main__':main()
