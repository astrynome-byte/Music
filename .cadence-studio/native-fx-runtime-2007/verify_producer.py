#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Read-only fixed producer/artifact metadata. Never download or run an installer."""
import argparse,datetime,hashlib,json,os
from pathlib import Path
import urllib.request
RUN=43266732201
ARTIFACT=13970570430
DRIVER='c3421a217c76a1b2cc5d4fab74305d209491d82f'
SOURCE_SHA='e0e36a40d2bee76337d8117016d0ca064e24fb2be2b9713b69855d6182a61fa9'
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):raise ValueError('Metadata GET must not redirect credentials')
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--source-selection',type=Path,required=True);a=p.parse_args()
 if os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('GITHUB_REPOSITORY')!='astrynome-byte/Music' or not os.environ.get('GH_TOKEN'):raise ValueError('Only the exact hosted repository read context is supported')
 if a.output.exists() or not a.output.absolute().is_relative_to(Path(os.environ['RUNNER_TEMP']).resolve()):raise ValueError('New output strictly below RUNNER_TEMP required')
 source=a.source_selection.read_bytes()
 if hashlib.sha256(source).hexdigest()!=SOURCE_SHA:raise ValueError('Frozen original2007 source.json differs')
 def get(endpoint):
  request=urllib.request.Request('https://api.github.com/repos/astrynome-byte/Music/'+endpoint,headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'Cadence-retained2007-SF2-QA'})
  with urllib.request.build_opener(NoRedirect).open(request,timeout=30) as response:
   body=response.read(2*1024**2+1)
   if response.status!=200 or len(body)>2*1024**2:raise ValueError('Bounded metadata HTTP200 required')
   return json.loads(body)
 run=get('actions/runs/'+str(RUN));artifact=get('actions/artifacts/'+str(ARTIFACT))
 if run.get('id')!=RUN or run.get('status')!='completed' or run.get('conclusion')!='success' or run.get('head_sha')!=DRIVER or run.get('run_attempt')!=1 or run.get('run_number')!=7 or run.get('repository',{}).get('full_name')!='astrynome-byte/Music':raise ValueError('Exact original full2007 successful producer required')
 if artifact.get('id')!=ARTIFACT or artifact.get('name')!='cadence-combined-system-aac-stage-experimental-7-1' or artifact.get('size_in_bytes')!=306532246 or artifact.get('digest')!='sha256:88a07b09b34b828ac1581338dc2b1d4ffc6d8ad5c3de7d7b38399d0431db3250' or artifact.get('workflow_run',{}).get('id')!=RUN or artifact.get('workflow_run',{}).get('head_sha')!=DRIVER or artifact.get('expired') is not False:raise ValueError('Original stage artifact metadata differs')
 expiry=datetime.datetime.fromisoformat(artifact['expires_at'].replace('Z','+00:00'))
 if expiry<=datetime.datetime.now(datetime.timezone.utc):raise ValueError('Original stage artifact expired; no substitution is allowed')
 result={'schema_version':1,'status':'fixed-full2007-producer-and-artifact-metadata-verified','producer_run_id':RUN,'artifact_id':ARTIFACT,'driver_commit':DRIVER,'source_selection_sha256':SOURCE_SHA,'producer':run,'artifact':artifact,'outer_digest_scope':'GitHub metadata; inner original archive separately recomputed against byte-pinned3776B stage-manifest, not a claimed local outer ZIP recomputation','application_executed':False,'installer_executed':False,'github_write':False}
 a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k] for k in ['status','producer_run_id','artifact_id','driver_commit','source_selection_sha256']}))
if __name__=='__main__':main()
