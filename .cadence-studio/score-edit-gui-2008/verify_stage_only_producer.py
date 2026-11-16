# SPDX-License-Identifier: GPL-3.0-only
"""GET-only eligibility for one real compiled stage after known failed MIDI test31.

This never validates an MSI or an overall successful build. Stage extraction and
all file hashing remain separate required operations before any app is launched.
"""
from pathlib import Path
import argparse,datetime,json,os,urllib.request

RUN=43408309742;JOB=131828068954;DRIVER='a8470ae087841875fd39284188d0e9d11d95e32b'
SOURCE='a2b7abaf045a8f3cb84ec2953d9e0e51b9e78903';TREE='c5452043983a048ef0aeef085615af903de3f5b0'
CI='95cebb22fe6cbde22919c94f2b480bd14c3eb8de'
EXE='13cd4e6d2f408d2e64b187d4c3bff1188ff4192ac7b670d3a12373bbeb37f6cd'
ARTIFACT=14031621703;OUTER_BYTES=306891538
OUTER_SHA='8cd00d5df8670837c3b15d3e3bd6e406df290222e404ef88599e4383de048178'
SCOPE='known-failed31-compiled-stage-GUI-only-fullQA-and-MSI-pending'
PASSED_STEP_NAMES={25:'Compile and stage the complete Cadence library and system AAC candidate',
26:'Authenticate the executable used by all following probes',
27:'Require omitted local ICU forwarder and the exact system export profile before archiving',
28:'Preserve the actual combined candidate stage before CLI, GUI and MSI testing',
29:'Retain the experimental Cadence stage (download before expiry)',
30:'Require the Windows OMR runner and its owned descendant cancellation'}

def require(ok,message):
    if not ok:raise ValueError(message)

def validate_plan(plan):
    p=plan.get('producer',{});s=plan.get('source',{});a=plan.get('artifacts',{}).get('stage',{});stage=plan.get('stage',{})
    require(plan.get('scope')==SCOPE and plan.get('full_qualification_complete')is False and plan.get('MSI')is None,
            'Only an explicit partial-stage GUI scope may be used')
    require(all(type(p.get(k))is int for k in ('run_id','job_id','run_number','run_attempt','failed_step'))
            and(p['run_id'],p['job_id'],p['run_number'],p['run_attempt'],p['failed_step'])==(RUN,JOB,12,1,31)
            and p.get('conclusion')=='failure' and p.get('driver_commit')==DRIVER
            and p.get('passed_steps')==list(range(25,31)),'Only the actual failed31 after compiled stage2008 is eligible')
    require(s.get('original_commit')==SOURCE and s.get('tree')==TREE and s.get('ci_commit')==CI
            and s.get('source_json_sha256')=='d8150851d20d6f9d631a7f93226753951eb1fb456e8a385a0ef8c834992bf354'
            and s.get('patch_sha256')=='ce7bc369062d6520785169c89d187bf8fa0c9e8dc069315a5e0d75e8f79247b9',
            'Exact source and original CI identity required')
    require(type(a.get('id'))is int and a['id']==ARTIFACT and type(a.get('size_in_bytes'))is int
            and a['size_in_bytes']==OUTER_BYTES and a.get('digest')=='sha256:'+OUTER_SHA,
            'Only the exact authenticated original outer stage archive is eligible')
    require(stage.get('executable_sha256')==EXE and type(stage.get('executable_bytes'))is int and stage['executable_bytes']==81236992
            and stage.get('archive_sha256')=='360ee31bcd6599af40b8d395aad16db732ec32ebabe76b777aed465c274ae830'
            and type(stage.get('archive_bytes'))is int and stage['archive_bytes']==148420143,
            'Exact measured original inner archive and EXE required')

def validate_metadata(plan,run,job,artifact,now=None):
    validate_plan(plan)
    require(run.get('id')==RUN and run.get('repository',{}).get('full_name')=='astrynome-byte/Music'
            and run.get('head_sha')==DRIVER and run.get('head_branch')=='cadence-studio/windows-build'
            and run.get('status')=='completed' and run.get('conclusion')=='failure'
            and type(run.get('run_number'))is int and run['run_number']==12
            and type(run.get('run_attempt'))is int and run['run_attempt']==1,
            'Actual original run must remain the known failure; no success or retry is substituted')
    require(type(job.get('id'))is int and job['id']==JOB and type(job.get('run_id'))is int and job['run_id']==RUN
            and job.get('head_sha')==DRIVER and job.get('head_branch')=='cadence-studio/windows-build'
            and type(job.get('run_attempt'))is int and job['run_attempt']==1 and job.get('status')=='completed'
            and job.get('conclusion')=='failure' and 'windows-2022'in job.get('labels',[]),
            'Actual failed Windows Server2022 job identity differs')
    rows=job.get('steps',[]);require(isinstance(rows,list) and all(type(r.get('number'))is int for r in rows),'Original job steps must be typed')
    steps={r['number']:r for r in rows};require(len(steps)==len(rows),'Duplicate original job steps refused')
    require(all(steps.get(n,{}).get('status')=='completed' and steps[n].get('conclusion')=='success'
                and steps[n].get('name')==PASSED_STEP_NAMES[n] for n in range(25,31))
            and steps.get(31,{}).get('status')=='completed' and steps[31].get('conclusion')=='failure'
            and steps[31].get('name')=='Compile and execute the actual MIDI practice and history components with MSVC x64'
            and all(steps.get(n,{}).get('status')=='completed' and steps[n].get('conclusion')=='skipped'for n in range(32,47))
            and not any(r.get('conclusion')=='failure'and r['number']!=31 for r in rows),
            'Only passes25–30, MIDI-harness failure31 and skipped downstream qualification are eligible')
    require(type(artifact.get('id'))is int and artifact['id']==ARTIFACT
            and artifact.get('name')=='cadence-combined-system-aac-stage-experimental-12-1'
            and type(artifact.get('size_in_bytes'))is int and artifact['size_in_bytes']==OUTER_BYTES
            and artifact.get('digest')=='sha256:'+OUTER_SHA and artifact.get('expired')is False
            and artifact.get('workflow_run',{}).get('id')==RUN and artifact['workflow_run'].get('head_sha')==DRIVER,
            'Actual exact stage artifact ID/origin/digest/size differs')
    expiry=datetime.datetime.fromisoformat(artifact['expires_at'].replace('Z','+00:00'))
    require(expiry.tzinfo is not None and expiry>(now or datetime.datetime.now(datetime.timezone.utc)),
            'The original stage artifact must still be available')
    return {'schema_version':1,'status':'eligible-actual-compiled-stage-known-failed31-GUI-only',
            'scope':SCOPE,'producer_run':RUN,'producer_job':JOB,'driver_commit':DRIVER,
            'producer_conclusion':'failure','passed_original_steps':list(range(25,31)),'failed_original_step':31,
            'source':plan['source'],'stage_artifact_id':ARTIFACT,'stage_outer_sha256':OUTER_SHA,
            'stage_executable_sha256':EXE,'stage_extraction_or_application_executed_by_guard':False,
            'GUI_validated':False,'full_qualification_complete':False,'MSI':None,'GitHub_write_performed':False}

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('Read-token metadata requests cannot redirect')

def main():
    p=argparse.ArgumentParser();p.add_argument('--selection',type=Path,default=Path(__file__).with_name('stage-only-provenance.json'));p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    require(os.environ.get('GITHUB_ACTIONS')=='true'and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted'
            and os.environ.get('GITHUB_REPOSITORY')=='astrynome-byte/Music','Disposable exact repository Actions context required')
    temp=Path(os.environ['RUNNER_TEMP']).resolve(strict=True)
    require(a.output.is_absolute()and a.output.resolve().is_relative_to(temp)and not a.output.exists()
            and not a.output.is_symlink()and a.output.parent.is_dir(),'New guard output beneath RUNNER_TEMP required')
    raw=a.selection.read_bytes();require(len(raw)<=1024**2,'Bounded frozen selection required');plan=json.loads(raw);validate_plan(plan)
    token=os.environ['GH_TOKEN'];opener=urllib.request.build_opener(NoRedirect)
    def get(endpoint):
        request=urllib.request.Request('https://api.github.com/repos/astrynome-byte/Music/'+endpoint,
            headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','User-Agent':'Cadence-StageOnly-GUI-Guard/1.0'})
        with opener.open(request,timeout=30)as response:
            data=response.read(4*1024**2+1);require(response.status==200 and len(data)<=4*1024**2,'Bounded original metadata HTTP200 required');return json.loads(data)
    result=validate_metadata(plan,get('actions/runs/'+str(RUN)),get('actions/jobs/'+str(JOB)),get('actions/artifacts/'+str(ARTIFACT)))
    a.output.write_bytes((json.dumps(result,indent=2)+'\n').encode('utf-8'));print(json.dumps(result,separators=(',',':')))

if __name__=='__main__':main()
