#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Check stopped exact-schema reports from the new GUI-only clock folder."""
import argparse,hashlib,json,math
from pathlib import Path

def validate(directory):
    if directory.is_symlink() or not directory.is_dir():raise ValueError('Plain app-only stats folder required')
    files=list(directory.iterdir())
    if not 1<=len(files)<=8:raise ValueError('One to eight actual stopped GUI reports required')
    results=[]
    for path in files:
        if path.is_symlink() or not path.is_file() or not path.name.startswith('clock-') or path.suffix!='.json' or path.stat().st_size>4096:raise ValueError('Unexpected GUI stats file')
        raw=path.read_bytes();r=json.loads(raw)
        if r.get('schema_version')!=1 or r.get('endpoint')!='Cadence QA Clock (silent sink)' or r.get('physical_audio_output') is not False or r.get('qualified_hardware') is not False:raise ValueError('Exact silent endpoint scope differs')
        for key in ['callbacks','frames','finite_samples','nonzero_samples','nonfinite_samples','clipped_samples','late_blocks','callback_errors','active_channels']:
            if type(r.get(key)) is not int or r[key]<0:raise ValueError('Invalid counter '+key)
        if r['callbacks']<1 or r['frames']!=r['callbacks']*256 or r['finite_samples']!=r['frames']*r['active_channels'] or r['active_channels']!=2 or r['sample_rate'] not in (44100,48000) or r['nonzero_samples']>r['finite_samples'] or any(r[k] for k in ['nonfinite_samples','clipped_samples','callback_errors']):raise ValueError('No valid actual GUI callbacks or sample counters')
        if any(type(r.get(k)) not in (float,int) or not math.isfinite(r[k]) or not 0<=r[k]<=1 for k in ('peak','rms')):raise ValueError('Invalid finite metrics')
        results.append({'file':path.name,'sha256':hashlib.sha256(raw).hexdigest(),'report':r})
    return {'schema_version':1,'status':'new-app-only-stopped-clock-reports-verified','app_only_folder':str(directory),'reports':results,'pid_field_in_original_schema':False,'physical_audio_output':False,'human_listening':False,'musical_nonmute_required':False,'limits':'Reports prove engine callbacks only. Folder was supplied only to the owned GUI; exact endpoint schema has no PID. No Play or musical output is asserted.'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists() or a.output.is_symlink():raise ValueError('New report required')
    a.output.write_text(json.dumps(validate(a.directory),indent=2)+'\n')
if __name__=='__main__':main()
