# SPDX-License-Identifier: GPL-3.0-only
"""Authenticate a known partial build; read/hash original ZIP data, execute none."""
from pathlib import Path, PurePosixPath
import argparse, base64, datetime, hashlib, json, os, re, shutil, stat, time
import urllib.parse, urllib.request, zipfile

HERE=Path(__file__).resolve().parent
PLAN=json.loads((HERE/'selection.json').read_text())
REPOSITORY='astrynome-byte/Music'
MAX=2*1024**3

def require(condition,message):
    if not condition: raise ValueError(message)

def digest(path):
    with Path(path).open('rb')as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def member(name):
    if name.startswith('./'):name=name[2:]
    require(isinstance(name,str)and 0<len(name)<=2048 and not name.startswith('/')
            and not re.search(r'[\\:\x00-\x1f]',name)
            and all(p not in ('','.','..')for p in name.rstrip('/').split('/')),'Unsafe ZIP/member path')
    return name.rstrip('/')

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('Metadata requests may not redirect')

class PublicRedirectOnly(urllib.request.HTTPRedirectHandler):
    # Same credential separation as the proven data-only acquisition helper:
    # create a NEW request with no Authorization/cookies on every CDN redirect.
    def redirect_request(self,request,fp,code,message,headers,new_url):
        parsed=urllib.parse.urlparse(new_url)
        require(parsed.scheme=='https'and not parsed.username and not parsed.password and parsed.hostname
                and parsed.port in (None,443) and(parsed.hostname in ('api.github.com','github.com')
                    or parsed.hostname.endswith('.githubusercontent.com')or parsed.hostname.endswith('.blob.core.windows.net')),
                'Unexpected artifact redirect destination')
        return urllib.request.Request(new_url,headers={'User-Agent':'Cadence-StageOnly-DataReader/1.0'},method='GET')

def json_bytes(raw):return json.loads(raw.decode('utf-8-sig'))

def emit_original(output,role,name,raw,rows):
    require(0<len(raw)<=4*1024**2,'Original small-file size bound')
    destination=output/'originals'/role/Path(name)
    destination.parent.mkdir(parents=True,exist_ok=True)
    with destination.open('xb')as stream:stream.write(raw)
    receipt={'role':role,'original_member_path':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
             'base64_original_bytes':base64.b64encode(raw).decode('ascii')}
    rows.append({k:v for k,v in receipt.items()if k!='base64_original_bytes'})
    print('CADENCE_RETAINED2008_ORIGINAL_FILE_BEGIN',flush=True)
    print(json.dumps(receipt,separators=(',',':')),flush=True)
    print('CADENCE_RETAINED2008_ORIGINAL_FILE_END',flush=True)

def zip_rows(archive,maximum=20000):
    rows={}; keys=set();total=0
    require(len(archive.infolist())<=maximum,'ZIP inventory count bound')
    for info in archive.infolist():
        if info.filename in ('.','./')and info.is_dir():continue
        name=member(info.filename)
        if info.is_dir():continue
        require(name.casefold()not in keys and not info.flag_bits&1
                and stat.S_IFMT(info.external_attr>>16)!=stat.S_IFLNK
                and info.compress_type in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED)
                and 0<=info.file_size<=512*1024**2,'Duplicate, linked, encrypted or oversized ZIP entry')
        keys.add(name.casefold());total+=info.file_size;require(total<=MAX,'ZIP total bound')
        rows[name]=info
    return rows

def stream_entry(archive,info,destination=None):
    measured=hashlib.sha256(); count=0
    with archive.open(info)as incoming:
        outgoing=Path(destination).open('xb')if destination else None
        try:
            while True:
                chunk=incoming.read(1024**2)
                if not chunk:break
                count+=len(chunk);require(count<=info.file_size,'ZIP entry exceeded its original size')
                measured.update(chunk)
                if outgoing:outgoing.write(chunk)
        finally:
            if outgoing:outgoing.close()
    require(count==info.file_size,'ZIP entry byte count differs')
    return {'bytes':count,'sha256':measured.hexdigest()}

def stage_data(path,work,output,originals):
    with zipfile.ZipFile(path)as archive:
        entries=zip_rows(archive)
        required=('stage-manifest.json','cadence-build.json','cadence-build-result.json','SHA256SUMS.txt')
        for name in required:require(name in entries,'Exact original stage companion absent: '+name)
        raw={name:archive.read(entries[name])for name in required}
        for name,data in raw.items():emit_original(output,'stage',name,data,originals)
        manifest=json_bytes(raw['stage-manifest.json']); build=json_bytes(raw['cadence-build-result.json'])
        require(manifest.get('schema_version')==1 and manifest.get('status')=='experimental-stage-before-qa'
                and manifest.get('variant')=='Cadence'and manifest.get('build_number')==2008
                and manifest.get('original_source_commit')==PLAN['source']['original_commit']
                and manifest.get('source_tree')==PLAN['source']['tree']
                and manifest.get('executable_sha256')==PLAN['executable_sha256']
                and manifest.get('run_number')==12 and manifest.get('run_attempt')==1
                and manifest.get('windows_system_aac')is True,'Original stage source/product/EXE provenance differs')
        require(isinstance(manifest.get('source_commit'),str)and re.fullmatch('[a-f0-9]{40}',manifest['source_commit'])
                and build.get('source_commit')==manifest['source_commit']
                and build.get('executable_sha256')==PLAN['executable_sha256'],'Original CI/build-result provenance differs')
        ledger={}
        for line in raw['SHA256SUMS.txt'].decode('ascii').splitlines():
            match=re.fullmatch(r'([a-f0-9]{64})  (.+)',line);require(match is not None,'Malformed original companion ledger')
            name=member(match[2]);require(name not in ledger and name in entries,'Duplicate/missing original ledger entry')
            ledger[name]=match[1]
        require(set(entries)==set(ledger)|{'SHA256SUMS.txt'},'Original ledger does not cover the exact stage bundle')
        inner=member(manifest.get('stage_archive',''))
        require(inner in ledger and ledger[inner]==manifest.get('stage_archive_sha256'),'Original inner archive digest differs from ledger/manifest')
        inner_path=work/'original-inner-stage.zip'; measured={}
        for name,expected in ledger.items():
            row=stream_entry(archive,entries[name],inner_path if name==inner else None)
            require(row['sha256']==expected,'Original stage companion bytes differ from producer ledger: '+name)
            measured[name]=row
        for name in ('stage-system-icu-policy.json','system-icu-exports.json','dependencies.lock.json',
                     'zlib-source-profile.lock.json','corresponding-sources/collection-report.json','corresponding-sources/sources.lock.json'):
            require(name in entries,'Original companion required for continuation: '+name)
            emit_original(output,'stage',name,archive.read(entries[name]),originals)
    runtime={}
    with zipfile.ZipFile(inner_path)as archive:
        for name,info in zip_rows(archive,10000).items():runtime[name]=stream_entry(archive,info)
    require(runtime.get('bin/CadenceStudio4.exe',{}).get('sha256')==PLAN['executable_sha256']
            and not any(name.casefold()=='bin/icuuc.dll'for name in runtime),'Actual inner EXE/no-local-ICU differs')
    inventory={'scope':'NEW measurement of every original inner-ZIP member; not a producer JSON file',
               'inner_archive':inner,'inner_archive_receipt':measured[inner],
               'source_original_commit':PLAN['source']['original_commit'],'source_tree':PLAN['source']['tree'],
               'source_ci_commit':manifest['source_commit'],'runtime_files':runtime,'count':len(runtime),
               'application_or_DLL_executed':False,'all_original_stage_ledger_members_verified':True,
               'stage_bundle_file_receipts_measured':measured}
    (output/'runtime-inventory.MEASURED.json').write_text(json.dumps(inventory,indent=2)+'\n')
    print('CADENCE_RETAINED2008_STAGE_MEASUREMENT_BEGIN',flush=True)
    print(json.dumps(inventory,separators=(',',':')),flush=True)
    print('CADENCE_RETAINED2008_STAGE_MEASUREMENT_END',flush=True)
    return inventory

LOG_REPORTS=('cadence-bootstrap.json','qa-authorized-wav-HTTPS/qualification-report.json',
 'macro-profile-prebuild.json','project-unity-prebuild/report.json','cadence-omr-runner-tests/runner-report.json',
 'qa-qualification-plan/native-additions-observation.json','qa-qualification-plan/store-observation.json',
 'qa-qualification-plan/preflight.json')

def logs_data(path,output,originals):
    with zipfile.ZipFile(path)as archive:
        entries=zip_rows(archive)
        for suffix in LOG_REPORTS:
            found=[name for name in entries if name==suffix or name.endswith('/'+suffix)]
            require(len(found)==1,'One exact original log report required: '+suffix)
            info=entries[found[0]];require(info.file_size<=4*1024**2,'Original log report size bound')
            emit_original(output,'logs',found[0],archive.read(info),originals)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--work',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    require(os.environ.get('GITHUB_ACTIONS')=='true'and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted'
            and os.environ.get('GITHUB_REPOSITORY')==REPOSITORY,'Exact disposable repository Actions context required')
    temp=Path(os.environ['RUNNER_TEMP']).resolve(strict=True)
    for path in (args.work,args.output):
        require(path.is_absolute()and path.resolve().is_relative_to(temp)and not path.exists(),'New owned data-only output paths beneath RUNNER_TEMP required')
    require(args.work!=args.output and not args.output.is_relative_to(args.work)and not args.work.is_relative_to(args.output),'Separate data-only work and output required')
    args.work.mkdir();args.output.mkdir();token=os.environ['GH_TOKEN']; originals=[]
    def request(endpoint,redirect=False):
        require(re.fullmatch(r'actions/(?:runs|jobs|artifacts)/[0-9]+(?:/zip)?',endpoint)is not None,'Only pinned Actions endpoints may be read')
        req=urllib.request.Request('https://api.github.com/repos/'+REPOSITORY+'/'+endpoint,
            headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'Cadence-StageOnly-DataReader/1.0'},method='GET')
        return urllib.request.build_opener(PublicRedirectOnly()if redirect else NoRedirect()).open(req,timeout=120)
    def metadata(endpoint,label):
        with request(endpoint)as response:raw=response.read(4*1024**2+1);require(response.status==200 and len(raw)<=4*1024**2,'Bounded metadata HTTP200 required')
        emit_original(args.output,'api',label,raw,originals);return json_bytes(raw)
    run=metadata('actions/runs/'+str(PLAN['run_id']),'run.original.json')
    require(run.get('id')==PLAN['run_id']and run.get('head_sha')==PLAN['driver_commit']and run.get('status')=='completed'
            and run.get('conclusion')=='failure'and run.get('run_number')==12 and run.get('run_attempt')==1
            and run.get('head_branch')=='cadence-studio/windows-build'
            and run.get('repository',{}).get('full_name')==REPOSITORY,'Exact known failed producer required; overall success is NOT asserted')
    job=metadata('actions/jobs/'+str(PLAN['job_id']),'job.original.json')
    require(job.get('id')==PLAN['job_id']and job.get('run_id')==PLAN['run_id']and job.get('status')=='completed'
            and job.get('conclusion')=='failure'and 'windows-2022'in job.get('labels',[]),'Exact original failed Windows job required')
    steps={row['number']:row for row in job.get('steps',[])}
    require(all(steps.get(n,{}).get('conclusion')=='success'for n in range(25,31))
            and steps.get(31,{}).get('conclusion')=='failure'
            and steps[31].get('name')=='Compile and execute the actual MIDI practice and history components with MSVC x64',
            'Known partial qualification differs: original25–30 PASS and MIDI-test31 FAIL required')
    downloads=[]
    for row in PLAN['artifacts']:
        item=metadata('actions/artifacts/'+str(row['id']),row['role']+'-artifact.original.json')
        require(item.get('id')==row['id']and item.get('size_in_bytes')==row['bytes']and item.get('digest')=='sha256:'+row['sha256']
                and item.get('name')==row['name']and item.get('expired')is False
                and item.get('workflow_run',{}).get('id')==PLAN['run_id']and item['workflow_run'].get('head_sha')==PLAN['driver_commit'],
                'Exact original artifact metadata differs')
        require(datetime.datetime.fromisoformat(item['expires_at'].replace('Z','+00:00'))>datetime.datetime.now(datetime.timezone.utc),'Original artifact expired')
        path=args.work/(row['role']+'-original.zip');measured=hashlib.sha256();count=0;deadline=time.monotonic()+600
        with request('actions/artifacts/'+str(row['id'])+'/zip',True)as response,path.open('xb')as target:
            require(response.status==200,'Artifact HTTP200 required')
            while True:
                require(time.monotonic()<deadline,'Artifact download deadline exceeded');data=response.read(1024**2)
                if not data:break
                count+=len(data);require(count<=row['bytes'],'Artifact size exceeded pinned bytes');measured.update(data);target.write(data)
        require(count==row['bytes']and measured.hexdigest()==row['sha256'],'Original outer artifact ZIP byte count/digest differs')
        downloads.append({'role':row['role'],'bytes':count,'sha256':measured.hexdigest(),'outer_ZIP_independently_hashed':True})
    stage=stage_data(args.work/'stage-original.zip',args.work,args.output,originals)
    logs_data(args.work/'logs-original.zip',args.output,originals)
    receipt={'schema_version':1,'scope':'DATAONLY original partial-build evidence; no app, DLL, SDK or installer executed',
        'producer_run_id':PLAN['run_id'],'producer_job_id':PLAN['job_id'],'producer_driver_commit':PLAN['driver_commit'],
        'overall_producer_conclusion':'failure','expected_failed_step':31,'passed_original_steps':list(range(25,31)),
        'source':PLAN['source'],'source_ci_commit_observed':stage['source_ci_commit'],'executable_sha256':PLAN['executable_sha256'],
        'downloads':downloads,'original_small_files':originals,'runtime_inventory_MEASURED_sha256':digest(args.output/'runtime-inventory.MEASURED.json'),
        'application_executed':False,'MSI_produced_or_tested':False,'full_application_qualification_complete':False,'GitHub_write_performed':False,
        'redirect_authorization_forwarded':False}
    (args.output/'readback-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print('CADENCE_RETAINED2008_DATAONLY_RECEIPT_BEGIN',flush=True);print(json.dumps(receipt,separators=(',',':')),flush=True);print('CADENCE_RETAINED2008_DATAONLY_RECEIPT_END',flush=True)

if __name__=='__main__':main()
