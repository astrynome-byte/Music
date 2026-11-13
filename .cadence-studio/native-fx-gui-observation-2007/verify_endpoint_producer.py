#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Read-only current availability of the exact original QA endpoint artifact."""
import argparse,datetime,json,os,urllib.request
from pathlib import Path
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*a,**k):raise ValueError('Metadata credentials cannot redirect')
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if os.environ.get('GITHUB_REPOSITORY')!='astrynome-byte/Music' or os.environ.get('GITHUB_ACTIONS')!='true' or not os.environ.get('GH_TOKEN'):raise ValueError('Exact repository read context required')
    if a.output.exists() or a.output.is_symlink() or not a.output.absolute().is_relative_to(Path(os.environ['RUNNER_TEMP']).resolve()):raise ValueError('New owned metadata report required')
    def get(endpoint):
        r=urllib.request.Request('https://api.github.com/repos/astrynome-byte/Music/'+endpoint,headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'Cadence-owned-mixer-observation'})
        with urllib.request.build_opener(NoRedirect).open(r,timeout=30) as s:
            b=s.read(2*1024**2+1)
            if s.status!=200 or len(b)>2*1024**2:raise ValueError('Bounded metadata HTTP200 required')
            return json.loads(b)
    run=get('actions/runs/43212261044');artifact=get('actions/artifacts/13941567509')
    if run.get('id')!=43212261044 or run.get('status')!='completed' or run.get('conclusion')!='success' or run.get('head_sha')!='be392cc7fa98ff8b18c9d679eb55f42f49030f8c' or run.get('run_attempt')!=1:raise ValueError('Exact successful endpoint producer required')
    if artifact.get('id')!=13941567509 or artifact.get('size_in_bytes')!=173154 or artifact.get('digest')!='sha256:96657947191133d0d213aa684ddd549c228866cd7ddd098386c1b6279e0919e0' or artifact.get('expired') is not False or artifact.get('workflow_run',{}).get('id')!=43212261044:raise ValueError('Exact original endpoint artifact metadata differs')
    if datetime.datetime.fromisoformat(artifact['expires_at'].replace('Z','+00:00'))<=datetime.datetime.now(datetime.timezone.utc):raise ValueError('Original endpoint expired; no substitute permitted')
    a.output.write_text(json.dumps({'status':'original-endpoint-producer-current-metadata-verified','run':run,'artifact':artifact,'binary_download_or_execution':False,'github_write':False},indent=2)+'\n')
if __name__=='__main__':main()
