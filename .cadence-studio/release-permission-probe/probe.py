#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Disposable tag + private draft permission probe; never publishes a release."""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import quote

REPO='astrynome-byte/Music'
MAIN='a6c90b63344b3fd60567fd9f001ac9ecba4b2081'
ANDROID='ad0539f630eb11556f33f487e145d97558a629ff'
WF='.github/workflows/android.yml'
INDEPENDENT={'pull_request','pull_request_target','workflow_dispatch','workflow_call','schedule'}
MAX_WORKFLOWS=128
MAX_WORKFLOW=262144
MAX_OUTPUT=4_194_304


class Blocked(ValueError):pass


def ensure(condition,message):
    if not condition:raise Blocked(message)


def command(args,input_bytes=None,timeout=30):
    env=os.environ.copy()
    env.pop('GH_DEBUG',None)
    run=subprocess.run(args,input=input_bytes,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout,env=env,check=False)
    ensure(len(run.stdout)<=MAX_OUTPUT and len(run.stderr)<=32768,'subprocess output exceeds bound')
    return run


def audit_events(events):
    if isinstance(events,str):rules={events:None}
    elif isinstance(events,list):
        ensure(events and all(isinstance(x,str) for x in events) and len(set(events))==len(events),'invalid/duplicate event list')
        rules={name:None for name in events}
    else:
        ensure(isinstance(events,dict) and events,'missing or invalid trigger map')
        rules=events
    for name,config in rules.items():
        ensure(isinstance(name,str),'event name is not a string')
        if name in INDEPENDENT:continue
        ensure(name=='push','release/create/delete/workflow_run or unknown event refused')
        ensure(isinstance(config,dict),'unfiltered tag-capable push refused')
        ensure(not ({'tags','tags-ignore','branches-ignore'} & set(config)),'tag or implicit branch push filter refused')
        ensure(set(config)<= {'branches','paths','paths-ignore'},'unknown push filter refused')
        branches=config.get('branches')
        ensure(isinstance(branches,list) and branches and all(isinstance(x,str) and x and '\x00' not in x for x in branches),'push requires an explicit nonempty branch-only list')
    return sorted(rules)


def parse_workflow(raw,ruby,parser):
    ensure(len(raw)<=MAX_WORKFLOW,'workflow exceeds size bound')
    run=command([ruby,str(parser)],raw,timeout=12)
    ensure(run.returncode==0,'Ruby/Psych rejected workflow data')
    document=json.loads(run.stdout)
    return audit_events(document.get('events'))


def sha1_blob(raw):return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()


def api(gh,method,endpoint,payload=None,expected=(200,)):
    args=[gh,'api','--hostname','github.com','--include','--method',method,endpoint]
    if payload is not None:args+=['--input','-']
    run=command(args,None if payload is None else json.dumps(payload,separators=(',',':')).encode())
    # gh --include returns one HTTP status/header block and then the JSON body.
    # Never record raw headers, stderr, token, request environment or body errors.
    match=re.match(rb'HTTP/\S+\s+(\d{3})[^\r\n]*\r?\n',run.stdout)
    status=int(match.group(1)) if match else None
    if status is None:
        error=re.search(rb'\bHTTP\s+(\d{3})\b',run.stderr)
        status=int(error.group(1)) if error else None
    body=run.stdout
    if match:
        split=re.split(rb'\r?\n\r?\n',body,maxsplit=1)
        body=split[1] if len(split)==2 else b''
    doc=None
    if run.returncode==0 and status in expected and body.strip():
        doc=json.loads(body)
    accepted=run.returncode==0 or (method=='GET' and status==404 and 404 in expected and run.returncode==1)
    return {'gh_exit_code':run.returncode,'http_status':status,'succeeded':accepted and status in expected},doc


def get(gh,endpoint,expected=(200,)):
    receipt,doc=api(gh,'GET',endpoint,expected=expected)
    ensure(receipt['succeeded'],'read-only GitHub request failed (status '+str(receipt['http_status'])+')')
    return doc


def verify_main(gh):
    doc=get(gh,'repos/'+REPO+'/commits/main')
    ensure(isinstance(doc,dict) and doc.get('sha')==MAIN,'main changed; no new probe mutation permitted')


def audit_workflows(gh,git,ruby,parser,head):
    verify_main(gh)
    listing=get(gh,'repos/'+REPO+'/contents/.github/workflows?ref='+MAIN)
    ensure(isinstance(listing,list) and len(listing)==1 and listing[0].get('path')==WF and listing[0].get('sha')==ANDROID and listing[0].get('type')=='file','main workflow directory differs from exact Android audit')
    run=command([git,'ls-tree','-r','-z',head,'--','.github/workflows'],timeout=15)
    ensure(run.returncode==0,'cannot read HEAD workflow tree')
    rows=run.stdout.split(b'\0');inventory=[];total=0
    for row in rows:
        if not row:continue
        metadata,path=row.split(b'\t',1);mode,kind,blob=metadata.decode('ascii').split();name=path.decode('utf-8')
        ensure(re.fullmatch(r'\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml',name) is not None and mode in ('100644','100755') and kind=='blob' and re.fullmatch(r'[a-f0-9]{40}',blob),'unknown/linked/nested workflow file refused')
        ensure(len(inventory)<MAX_WORKFLOWS,'workflow count exceeds bound')
        size=command([git,'cat-file','-s',blob],timeout=10)
        ensure(size.returncode==0 and int(size.stdout)<=MAX_WORKFLOW,'workflow blob is too large or missing')
        content=command([git,'cat-file','blob',blob],timeout=10)
        raw=content.stdout;total+=len(raw)
        ensure(content.returncode==0 and total<=8_388_608 and sha1_blob(raw)==blob,'workflow bytes differ from Git object identity')
        events=parse_workflow(raw,ruby,parser)
        inventory.append({'path':name,'blob_sha1':blob,'bytes':len(raw),'events':events,'tag_release_cleanup_events_refused':True})
    ensure(any(x['path']==WF and x['blob_sha1']==ANDROID for x in inventory),'HEAD Android workflow is not the immutable audited file')
    return {'main_commit':MAIN,'main_workflows':[{'path':WF,'blob_sha1':ANDROID}], 'head_commit':head,'head_workflows':inventory}


def cleanup(gh,tag,head,created_id,tag_attempted):
    result={'release_deleted':None,'release_absence_verified':None,'tag_deleted':None,'tag_absence_verified':None,'errors':[]}
    if created_id is not None:
        try:
            endpoint='repos/'+REPO+'/releases/'+str(created_id)
            rec,doc=api(gh,'GET',endpoint,expected=(200,404))
            ensure(rec['succeeded'],'owned draft state cannot be read for cleanup')
            if rec['http_status']==404:
                result['release_absence_verified']=True
            else:
                ensure(isinstance(doc,dict) and doc.get('id')==created_id and doc.get('tag_name')==tag and doc.get('draft') is True and doc.get('prerelease') is True and not doc.get('assets'),'owned draft identity changed; refuse deleting')
                verify_main(gh)
                rec,_=api(gh,'DELETE',endpoint,expected=(204,));result['release_deleted']=rec
                ensure(rec['succeeded'],'owned draft deletion failed')
                rec,_=api(gh,'GET',endpoint,expected=(404,));result['release_absence_verified']=rec['succeeded']
                ensure(rec['succeeded'],'owned release absence not verified')
        except (Blocked,OSError,ValueError,subprocess.TimeoutExpired) as error:result['errors'].append(str(error))
    if tag_attempted:
        endpoint='repos/'+REPO+'/git/ref/tags/'+quote(tag,safe='')
        try:
            rec,doc=api(gh,'GET',endpoint,expected=(200,404))
            ensure(rec['succeeded'],'owned tag state cannot be read for cleanup')
            if rec['http_status']==404:
                result['tag_absence_verified']=True
                return result
            ensure(isinstance(doc,dict) and doc.get('ref')=='refs/tags/'+tag and doc.get('object',{}).get('type')=='commit' and doc['object'].get('sha')==head,'owned tag no longer points to the exact probe HEAD; refuse deleting')
            verify_main(gh)
            rec,_=api(gh,'DELETE','repos/'+REPO+'/git/refs/tags/'+quote(tag,safe=''),expected=(204,));result['tag_deleted']=rec
            ensure(rec['succeeded'],'owned tag deletion failed')
            rec,_=api(gh,'GET',endpoint,expected=(404,));result['tag_absence_verified']=rec['succeeded']
            ensure(rec['succeeded'],'owned tag absence not verified')
        except (Blocked,OSError,ValueError,subprocess.TimeoutExpired) as error:result['errors'].append(str(error))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    ensure(sys.platform=='linux' and os.environ.get('RUNNER_OS')=='Linux' and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted' and os.environ.get('CI')=='true' and os.environ.get('GITHUB_ACTIONS')=='true','only disposable hosted Ubuntu CI permitted')
    ensure(os.environ.get('GITHUB_REPOSITORY')==REPO and os.environ.get('GITHUB_REF')=='refs/heads/cadence-studio/windows-build' and os.environ.get('GITHUB_EVENT_NAME')=='push','only the scoped branch push permitted')
    head=os.environ.get('GITHUB_SHA','');run_id=os.environ.get('GITHUB_RUN_ID','');attempt=os.environ.get('GITHUB_RUN_ATTEMPT','')
    ensure(re.fullmatch(r'[0-9a-f]{40}',head) and re.fullmatch(r'[1-9][0-9]*',run_id) and re.fullmatch(r'[1-9][0-9]*',attempt),'actual HEAD/run/attempt required')
    ensure(os.environ.get('GH_TOKEN'),'ephemeral repository token required')
    gh,git,ruby=(shutil.which(name) for name in ('gh','git','ruby'))
    output=args.output.resolve();temporary=Path(os.environ['RUNNER_TEMP']).resolve()
    ensure(not output.exists() and output.is_relative_to(temporary) and output!=temporary,'new output below RUNNER_TEMP required')
    output.mkdir(parents=True)
    tag='cadence-studio/qa-permission-'+run_id+'-'+attempt
    report={'schema_version':1,'status':'blocked_before_mutation','repository':REPO,'head_commit':head,'tag':tag,'assets_created':False,'public_release_created':False,'main_modified':False,'tag_create':None,'draft_create':None,'draft_id':None,'cleanup':None,'error':None}
    tag_attempted=False;draft_attempted=False;created_id=None
    try:
        ensure(gh and git and ruby,'gh/git/Ruby required; no installation or mutation attempted')
        actual=command([git,'rev-parse','HEAD'],timeout=10)
        ensure(actual.returncode==0 and actual.stdout.decode().strip()==head,'checkout differs from triggering commit')
        report['workflow_audit']=audit_workflows(gh,git,ruby,Path(__file__).with_name('parse_workflow.rb'),head)
        endpoint='repos/'+REPO+'/git/ref/tags/'+quote(tag,safe='')
        prior,_=api(gh,'GET',endpoint,expected=(404,))
        ensure(prior['succeeded'],'temporary tag already exists or absence cannot be verified')
        verify_main(gh)
        tag_attempted=True
        receipt,doc=api(gh,'POST','repos/'+REPO+'/git/refs',{'ref':'refs/tags/'+tag,'sha':head},expected=(201,))
        report['tag_create']=receipt
        if not receipt['succeeded']:report['status']='tag_creation_denied_or_failed';return 1
        ensure(isinstance(doc,dict) and doc.get('ref')=='refs/tags/'+tag and doc.get('object',{}).get('sha')==head,'created temporary tag response mismatched')
        verify_main(gh)
        payload={'tag_name':tag,'target_commitish':head,'name':'Cadence private permission QA '+run_id+'-'+attempt,'body':'Temporary permission probe. No installer or asset. This draft must never be published.','draft':True,'prerelease':True,'generate_release_notes':False}
        draft_attempted=True
        receipt,doc=api(gh,'POST','repos/'+REPO+'/releases',payload,expected=(201,));report['draft_create']=receipt
        if not receipt['succeeded']:report['status']='draft_creation_denied_or_failed';return 1
        ensure(isinstance(doc,dict) and type(doc.get('id')) is int and doc['id']>0,'create draft did not return an owned id')
        created_id=doc['id'];report['draft_id']=created_id;report['public_release_created']=doc.get('draft') is False
        ensure(doc.get('tag_name')==tag and doc.get('draft') is True and doc.get('prerelease') is True and doc.get('assets')==[],'created release is not the exact empty private prerelease draft')
        actual=get(gh,'repos/'+REPO+'/releases/'+str(created_id))
        ensure(isinstance(actual,dict) and actual.get('id')==created_id and actual.get('tag_name')==tag and actual.get('draft') is True and actual.get('prerelease') is True and actual.get('assets')==[],'actual private draft did not match creation response')
        report['status']='tag_and_private_draft_created_pending_cleanup'
    except (Blocked,OSError,ValueError,KeyError,TypeError,subprocess.TimeoutExpired) as error:
        report['error']=str(error) if isinstance(error,Blocked) else type(error).__name__
    finally:
        report['cleanup']=cleanup(gh,tag,head,created_id,tag_attempted)
        if draft_attempted and created_id is None and (report['draft_create'] is None or report['draft_create']['http_status'] in (None,201)):
            report['cleanup']['errors'].append('Draft creation outcome unknown without an owned returned id; no release was deleted by name')
        if report['cleanup']['errors']:report['status']='cleanup_failed'
        elif report['status']=='tag_and_private_draft_created_pending_cleanup':report['status']='tag_and_private_draft_capability_confirmed_and_removed'
        (output/'permission-probe-report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print('CADENCE_RELEASE_PERMISSION_PROBE_BEGIN');print(json.dumps(report,sort_keys=True));print('CADENCE_RELEASE_PERMISSION_PROBE_END')
    return 0 if report['status']=='tag_and_private_draft_capability_confirmed_and_removed' else 1


if __name__=='__main__':raise SystemExit(main())
