#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Create one new native score using the byte-pinned actual2007 CLI."""
import argparse,hashlib,json,os,subprocess,zipfile
from pathlib import Path
EXE='dcfbf9155c6c972c37966a4b2b0dcd212133c8e31fb397c644dda800ac7122be'
def plain(path):
    path=path.absolute()
    for p in (path,*path.parents):
        if p.is_symlink() or (p.exists() and getattr(p.stat(),'st_file_attributes',0)&0x400):raise ValueError('Links/reparse refused')
    temp=Path(os.environ['RUNNER_TEMP']).resolve()
    if temp not in path.resolve().parents:raise ValueError('Runtime path must remain below RUNNER_TEMP')
    return path

def main():
    p=argparse.ArgumentParser();p.add_argument('--stage',type=Path,required=True);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--record',type=Path,required=True);a=p.parse_args()
    if os.name!='nt' or any(os.environ.get(k)!=v for k,v in {'CI':'true','GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted'}.items()):raise ValueError('Disposable Windows hosted CI only')
    exe=plain(a.stage/'bin/CadenceStudio4.exe');source=plain(a.input);target=plain(a.output);record=plain(a.record)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    if sha(exe)!=EXE or target.exists() or record.exists() or target.suffix!='.mscz' or not target.parent.is_dir():raise ValueError('Exact executable and new native output required')
    original=sha(source);environment=os.environ.copy();environment['PATH']=str(exe.parent)+';'+str(Path(os.environ['SystemRoot'])/'System32')
    for key in list(environment):
        if key.startswith(('QT','QML','CMAKE_','VSCMD_','VCPKG_')) or key in ('GH_TOKEN','GITHUB_TOKEN'):environment.pop(key,None)
    clock=target.parent/'conversion-clock-stats';clock.mkdir();environment['CADENCE_QA_CLOCK_STATS_DIR']=str(clock)
    command=[str(exe),'-o',str(target),str(source)]
    run=subprocess.run(command,cwd=exe.parent,env=environment,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
    target.with_suffix('.conversion.stdout.log').write_bytes(run.stdout);target.with_suffix('.conversion.stderr.log').write_bytes(run.stderr)
    if run.returncode or not target.is_file() or target.stat().st_size>16*1024**2 or sha(source)!=original:raise ValueError('Actual native conversion failed or source changed')
    with zipfile.ZipFile(target) as z:
        members=[n for n in z.namelist() if n.endswith('.mscx')]
        if len(members)!=1 or b'<museScore' not in z.read(members[0]):raise ValueError('Actual native score member missing')
    record.write_text(json.dumps({'status':'actual2007-own-native-copy-created','command':command,'exit_code':run.returncode,'input_sha256':original,'output_sha256':sha(target),'GUI_open_tested':False},indent=2)+'\n')
if __name__=='__main__':main()
