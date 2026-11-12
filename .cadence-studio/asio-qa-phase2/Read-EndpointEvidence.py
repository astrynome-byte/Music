#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Read the exact successful QA endpoint artifact as data; execute no binaries."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import zipfile

DLL='08f570d7df0dfb5f2cafe899c6b6679e48d4e1fa132656e58f4b0113a8709fd2'
HARNESS='adeea91ef5207b7425dfa90b8c412c23ca0d0e4ad9e99138b6dfe4778bcc9665'
MANIFEST='061c8801a4de0bb0546091226844fa999b81b02a47fdaeab63088c98bdfc98f3'
SOURCES='5b9204779f64706191eba6428bb7eff1dc37885aa43e488178f38974a80442aa'
COMMIT='be392cc7fa98ff8b18c9d679eb55f42f49030f8c'

def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def read(root:Path):
    root=root.resolve(strict=True)
    files=list(root.rglob('*'))
    if len(files)>128 or any(p.is_symlink() for p in files) or sum(p.stat().st_size for p in files if p.is_file())>16*1024**2:
        raise ValueError('Unexpected artifact bounds or links')
    result=json.loads((root/'result.json').read_text(encoding='utf-8-sig'))
    if result.get('status')!='native-qa-endpoint-direct-factory-harness-passed' or result.get('native_scenarios')!=4 or result.get('commit')!=COMMIT or result.get('run_id')!='43212261044':
        raise ValueError('Producer result differs from the successful direct run')
    for field in ('physical_audio_output','listening_validated','application_Cadence_executed','registry_modified','kernel_driver_installed'):
        if result.get(field) is not False:raise ValueError('Producer scope flag differs: '+field)
    identities={}
    for name,expected in [('CadenceQaClock.dll',DLL),('CadenceQaClockHarness.exe',HARNESS),('Cadence-QA-Clock-corresponding-source.zip',SOURCES)]:
        path=root/name;actual=sha(path)
        if actual!=expected:raise ValueError('Actual retained file SHA differs: '+name)
        identities[name]={'bytes':path.stat().st_size,'sha256':actual}
    for key,expected in [('dll_sha256',DLL),('harness_sha256',HARNESS),('source_manifest_sha256',MANIFEST),('corresponding_source_zip_sha256',SOURCES)]:
        if result.get(key)!=expected:raise ValueError('Producer identity differs: '+key)
    text=(root/'harness.stdout.log').read_text(encoding='utf-8-sig')
    if len(text)>32768 or (root/'harness.stderr.log').read_text(encoding='utf-8-sig').strip():raise ValueError('Unexpected harness transcript')
    pattern=re.compile(r'^PASS rate=(44100|48000) time_info=(true|false) silence=(true|false) self_stop=(true|false) callbacks=(\d+) frames=(\d+) peak=([\deE+.-]+) rms=([\deE+.-]+)$')
    scenarios=[]
    for line in text.splitlines():
        match=pattern.fullmatch(line)
        if not match:continue
        rate,time_info,silence,self_stop,callbacks,frames,peak,rms=match.groups()
        row={'rate':int(rate),'time_info':time_info=='true','silence':silence=='true','self_stop':self_stop=='true','callbacks':int(callbacks),'frames':int(frames),'peak':float(peak),'rms':float(rms)}
        if row['callbacks']<1 or row['frames']!=row['callbacks']*256 or not math.isfinite(row['peak']) or not math.isfinite(row['rms']):raise ValueError('Inconsistent original scenario counters')
        if row['silence']:
            if row['peak'] or row['rms']:raise ValueError('Original silence control is not silent')
        elif row['peak']!=.5 or not math.isclose(row['rms'],math.sqrt(.15625),abs_tol=1e-8):raise ValueError('Original known PCM metrics differ')
        scenarios.append(row)
    expected={(44100,False,False,False),(48000,True,False,False),(48000,False,True,False),(44100,True,False,True)}
    if len(scenarios)!=4 or {(r['rate'],r['time_info'],r['silence'],r['self_stop']) for r in scenarios}!=expected or 'PASS 4 native ASIO ABI scenarios through direct DllGetClassObject; no physical output or listening.' not in text:
        raise ValueError('Four original scenario kinds and summary not present')
    reports=[];unmatched=list(scenarios)
    paths=list((root/'stats').glob('clock-*.json'))
    if len(paths)!=4:raise ValueError('Four original stopped-run reports required')
    for path in sorted(paths):
        if path.stat().st_size>4096:raise ValueError('Oversized original stopped report')
        row=json.loads(path.read_text(encoding='utf-8'))
        if row.get('schema_version')!=1 or row.get('endpoint')!='Cadence QA Clock (silent sink)' or row.get('physical_audio_output') is not False or row.get('qualified_hardware') is not False:
            raise ValueError('Original endpoint report scope differs')
        for field in ('callbacks','frames','finite_samples','nonzero_samples','nonfinite_samples','clipped_samples','late_blocks','callback_errors','active_channels'):
            if type(row.get(field)) is not int or row[field]<0:raise ValueError('Invalid original report counter: '+field)
        if row['callbacks']<1 or row['frames']!=row['callbacks']*256 or row['finite_samples']!=row['frames']*2 or row['active_channels']!=2 or any(row[k] for k in ('nonfinite_samples','clipped_samples','callback_errors')):
            raise ValueError('Inconsistent original stopped report')
        matches=[r for r in unmatched if row['sample_rate']==r['rate'] and row['callbacks']==r['callbacks'] and row['frames']==r['frames'] and row['peak']==r['peak'] and math.isclose(row['rms'],r['rms'],abs_tol=1e-8)]
        if not matches:raise ValueError('Stopped report does not match an original harness row')
        scenario=matches[0];unmatched.remove(scenario)
        if row['nonzero_samples']!=(0 if scenario['silence'] else row['finite_samples']):raise ValueError('Original output sample counts differ')
        reports.append({'path':path.relative_to(root).as_posix(),'sha256':sha(path),'report':row})
    with zipfile.ZipFile(root/'Cadence-QA-Clock-corresponding-source.zip') as archive:
        entries={};total=0
        for info in archive.infolist():
            name=info.filename.replace('\\','/')
            if info.is_dir():continue
            parts=PurePosixPath(name).parts
            if name.startswith('/') or ':' in name or any(p in ('.','..') for p in parts) or name in entries or ((info.external_attr>>16)&0o170000)==0o120000:
                raise ValueError('Unsafe or duplicate source ZIP entry')
            entries[name]=info;total+=info.file_size
        if len(entries)>64 or total>2*1024**2:raise ValueError('Source ZIP bounds differ')
        prefix='corresponding-source/'
        data=archive.read(entries[prefix+'source-manifest.json'])
        if hashlib.sha256(data).hexdigest()!=MANIFEST:raise ValueError('Actual source ZIP manifest SHA differs')
        manifest=json.loads(data)
        if manifest.get('status')!='source-prepared-not-Windows-qualified' or len(manifest.get('files',[]))!=19:raise ValueError('Original source profile differs')
        for member in manifest['files']:
            payload=archive.read(entries[prefix+member['path']])
            if len(payload)!=member['bytes'] or hashlib.sha256(payload).hexdigest()!=member['sha256']:raise ValueError('Actual original source member differs')
    return {'schema_version':1,'status':'original-direct-endpoint-evidence-verified','producer_run_id':43212261044,'artifact_id':13941567509,'producer_commit':COMMIT,
            'reader_executed_DLL_or_harness':False,'reader_modified_registry':False,'physical_audio_or_listening_validated':False,
            'identities':identities,'original_scenarios':scenarios,'original_stopped_reports':reports,'original_source_manifest_sha256':MANIFEST,'source_members_verified':19}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    root=a.root.resolve(strict=True);output=a.output.resolve()
    if output.exists() or output.is_relative_to(root):raise ValueError('New output outside original artifact required')
    report=read(root);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('CADENCE_QA_CLOCK_ORIGINAL_EVIDENCE_BEGIN');print(json.dumps(report,indent=2));print('CADENCE_QA_CLOCK_ORIGINAL_EVIDENCE_END')
    return 0
if __name__=='__main__':raise SystemExit(main())
