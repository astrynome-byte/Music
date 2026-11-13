#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Disable the existing promotions preference only in the fresh owned QA profile."""
import argparse,configparser,hashlib,importlib.util,json,os,sys
from contextlib import ExitStack
from pathlib import Path
HELPER_SHA='60b6bb2353467cf338e2c671151af37d3fd36d76748e52cda6a1e3ab22c4c27c'
ADDITION=b'\n[musesounds]\ncheckForUpdate=false\n'

def configured_seed(seed:bytes)->bytes:
    p=configparser.ConfigParser(interpolation=None,delimiters=('=',),strict=True);p.optionxform=str
    p.read_string(seed.decode('utf-8'))
    if p.has_section('musesounds') or any('checkForUpdate' in p.options(s) for s in p.sections()):raise ValueError('Only the exact untouched seed may be configured')
    return seed+ADDITION

def promotions_disabled(data:bytes)->bool:
    p=configparser.ConfigParser(interpolation=None,delimiters=('=',),strict=True);p.optionxform=str
    p.read_string(data.decode('utf-8-sig'))
    if p.defaults():raise ValueError('No inherited QSettings options')
    for group in p.sections():
        for key in p.options(group):
            effective=(('' if group.casefold()=='general' else group)+'/'+key).strip('/').casefold()
            if effective=='musesounds/checkforupdate' and (group!='musesounds' or key!='checkForUpdate'):raise ValueError('Ambiguous promotion preference spelling')
    return p.get('musesounds','checkForUpdate',fallback=None,raw=True)=='false'

def main():
    p=argparse.ArgumentParser();p.add_argument('--record',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--verify-only',action='store_true');a=p.parse_args()
    if os.name!='nt' or any(os.environ.get(k)!=v for k,v in {'CI':'true','GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted'}.items()):raise ValueError('Disposable hosted Windows only')
    helper=Path(__file__).with_name('runtime')/'CadenceProfileScope.py'
    if hashlib.sha256(helper.read_bytes()).hexdigest()!=HELPER_SHA:raise ValueError('Owned profile helper differs')
    spec=importlib.util.spec_from_file_location('cadence_mixer_profile',helper);m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
    record=m.verify_record(a.record);settings=Path(record['settings_file'])
    output=a.output.absolute();m._plain_ancestors(output)
    if output.exists() or Path(os.environ['RUNNER_TEMP']).resolve() not in output.resolve().parents:raise ValueError('New report below RUNNER_TEMP required')
    before=m._read_regular(settings,m.MAX_SETTINGS_BYTES)
    if a.verify_only:
        if not promotions_disabled(before):raise ValueError('Actual QA promotion preference was not retained false')
        output.write_text(json.dumps({'status':'actual-QA-promotions-preference-false-verified','settings_sha256':hashlib.sha256(before).hexdigest(),'ASIO_endpoint_unchanged':True})+'\n')
        return
    if before!=m.SEED_SETTINGS:raise ValueError('Only our exact freshly prepared seed may be changed; no user preference is overwritten')
    after=configured_seed(before);m.validate_audio_settings(after)
    with ExitStack() as stack:
        for key in m.ROOT_KEYS:
            stack.enter_context(m._hold_root(Path(record[key])));m._assert_marker(record,key)
        identity=m._identity(m._lstat_plain(settings,'file'))
        with settings.open('r+b') as stream:
            if m._identity(os.fstat(stream.fileno()))!=identity or stream.read(m.MAX_SETTINGS_BYTES+1)!=before:raise ValueError('Owned settings identity or bytes changed')
            stream.seek(0);stream.write(after);stream.truncate();stream.flush();os.fsync(stream.fileno())
        if m._identity(m._lstat_plain(settings,'file'))!=identity or m._read_regular(settings,m.MAX_SETTINGS_BYTES)!=after:raise ValueError('Owned QA preference did not persist exactly')
    m.verify_record(a.record)
    output.write_text(json.dumps({'status':'fresh-owned-QA-profile-promotions-disabled','scope':'QA profile only; no production default, user profile, remote service or application code changed','settings_file':str(settings),'preference':'musesounds/checkForUpdate','value':False,'settings_sha256_before':hashlib.sha256(before).hexdigest(),'settings_sha256_after':hashlib.sha256(after).hexdigest(),'ASIO_endpoint_unchanged':True,'existing_user_settings_overwritten':False},indent=2)+'\n')
if __name__=='__main__':main()
