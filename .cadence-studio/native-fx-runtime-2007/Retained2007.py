#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Unchanged selected functions from the exact retained2007 stage QA recipe."""
import hashlib, importlib.util, json, math, os, re, shutil, stat, struct, sys
from pathlib import Path, PurePosixPath
import xml.etree.ElementTree as ET
import zipfile
SOURCE='5058d29dad67e6131ee46ee617258ccfed8ba4b0'

TREE='58d06a1c89e99173b0473587245187df5bc3b3cf'

CI_SOURCE='4bfd68815efcd3410419d47678792426e20e543b'

EXE_SHA='dcfbf9155c6c972c37966a4b2b0dcd212133c8e31fb397c644dda800ac7122be'

ARCHIVE='CadenceStudio-v4.7.6-combined-system-aac-stage-build-2007-attempt-1-x64.zip'

STAGE_MANIFEST_SHA='ba985694173769bded900789a57952eef564026626e8be68e3484c583541ad05'

STAGE_MANIFEST_BYTES=3776

BUILD_RESULT_SHA='8d77e9c7554fd1779abafa293350d51696b320f7247802f6efe892857c909e60'

SOURCE_JSON_SHA='e0e36a40d2bee76337d8117016d0ca064e24fb2be2b9713b69855d6182a61fa9'

PROFILE_SHA='60b6bb2353467cf338e2c671151af37d3fd36d76748e52cda6a1e3ab22c4c27c'

BASIC_SHA='5ea2375e8bd7d8e71def1036978c1621e85b66934169b6a2744b27b9b3c2d99c'

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def no_links(path):
    for current in (path, *path.parents):
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Runtime paths cannot traverse links or reparse points')

def owned(path):
    path = path.absolute()
    no_links(path)
    path = path.resolve()
    temporary = Path(os.environ['RUNNER_TEMP']).resolve()
    if temporary not in path.parents:
        raise ValueError('Runtime paths must be strictly below RUNNER_TEMP')
    return path

def relative_member(name):
    if name.startswith('./'):
        name = name[2:]
    path = PurePosixPath(name.rstrip('/'))
    if (not name or '\\' in name or ':' in name or path.is_absolute()
            or any(part in ('.', '..') for part in path.parts)
            or any(ord(char) < 32 for char in name)):
        raise ValueError('Unsafe archive member')
    for part in path.parts:
        if part.endswith(('.', ' ')):
            raise ValueError('Ambiguous archive member')
    return path

def load_profile_helper():
    path = Path(__file__).with_name('CadenceProfileScope.py')
    if sha(path) != PROFILE_SHA:
        raise ValueError('Pinned profile-scope helper differs')
    spec = importlib.util.spec_from_file_location('cadence_vsco_profile_scope', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

def native_data(path):
    with zipfile.ZipFile(path) as archive:
        if len(archive.infolist()) > 256 or len(set(archive.namelist())) != len(archive.namelist()):
            raise ValueError('Unexpected native project ZIP')
        for row in archive.infolist():
            relative_member(row.filename)
            if row.file_size > 16 * 1024**2:
                raise ValueError('Oversized native project member')
        masters = [name for name in archive.namelist() if name.endswith('.mscx') and '/' not in name]
        if len(masters) != 1:
            raise ValueError('A unique native master is required')
        return json.loads(archive.read('audiosettings.json')), ET.fromstring(archive.read(masters[0]))

def snapshot(logs):
    result = {}
    paths = list(logs.rglob('*.log')) if logs.is_dir() else []
    if len(paths) > 32:
        raise ValueError('Unexpected fresh profile log count')
    for path in paths:
        no_links(path)
        if path.stat().st_size > 16 * 1024**2:
            raise ValueError('Profile log exceeds 16 MiB')
        result[str(path)] = path.read_bytes()
    return result

def require(ok, message):
    if not ok: raise ValueError(message)

def ledger(root):
    """Validate the producer's existing bounded companion ledger, never make one."""
    path=root/'SHA256SUMS.txt'; no_links(path)
    raw=path.read_text(encoding='ascii'); result={}
    for line in raw.splitlines():
        m=re.fullmatch(r'([a-f0-9]{64})  (.+)',line)
        require(m is not None,'Malformed original companion ledger')
        rel=relative_member(m[2]); key=rel.as_posix()
        require(key not in result and len(result)<1024,'Duplicate or oversized companion ledger')
        target=root.joinpath(*rel.parts);no_links(target)
        require(target.is_file() and target.stat().st_size<=512*1024**2 and sha(target)==m[1], 'Original companion changed: '+key)
        result[key]=m[1]
    require(ARCHIVE in result and 'stage-manifest.json' in result,'Original archive/manifest absent from ledger')
    return result

def validate_stage_metadata(artifact):
    manifest=artifact/'stage-manifest.json'; no_links(manifest)
    require(manifest.is_file() and manifest.stat().st_size==STAGE_MANIFEST_BYTES and sha(manifest)==STAGE_MANIFEST_SHA,
            'The byte-exact actual2007 stage manifest is required; no guessed archive hash')
    doc=json.loads(manifest.read_text(encoding='utf-8-sig'))
    require(doc.get('schema_version')==1 and doc.get('status')=='experimental-stage-before-qa'
            and doc.get('variant')=='Cadence' and doc.get('build_number')==2007
            and doc.get('original_source_commit')==SOURCE and doc.get('source_commit')==CI_SOURCE
            and doc.get('source_tree')==TREE and doc.get('executable_sha256')==EXE_SHA
            and doc.get('stage_archive')==ARCHIVE and doc.get('windows_system_aac') is True
            and isinstance(doc.get('stage_archive_sha256'),str)
            and re.fullmatch('[a-f0-9]{64}',doc['stage_archive_sha256']), 'The actual2007 stage provenance differs')
    result=artifact/'cadence-build-result.json';no_links(result)
    require(result.is_file() and sha(result)==BUILD_RESULT_SHA,'Original build-result report changed')
    built=json.loads(result.read_text(encoding='utf-8-sig'))
    require(built.get('source_commit')==CI_SOURCE and built.get('executable_sha256')==EXE_SHA,'Original build/executable provenance differs')
    hashes=ledger(artifact)
    require(hashes['stage-manifest.json']==STAGE_MANIFEST_SHA and hashes[ARCHIVE]==doc['stage_archive_sha256'],
            'Original ledger and pinned manifest do not agree')
    return doc

def restore_stage(artifact,stage):
    doc=validate_stage_metadata(artifact)
    archive=artifact/ARCHIVE;no_links(archive)
    require(archive.is_file() and sha(archive)==doc['stage_archive_sha256'] and not stage.exists(),
            'Original actual2007 inner archive hash/new stage required')
    with zipfile.ZipFile(archive) as source:
        rows=source.infolist()
        require(len(rows)<=10000 and sum(r.file_size for r in rows)<=2*1024**3,'Stage extraction bound exceeded')
        seen=set(); planned=[]
        for row in rows:
            rel=relative_member(row.filename); key=rel.as_posix().casefold()
            require(key not in seen and row.file_size<=512*1024**2
                    and ((row.external_attr>>16)&0o170000)!=0o120000,'Duplicate, linked or oversized stage entry')
            seen.add(key);planned.append((row,stage.joinpath(*rel.parts)))
        stage.mkdir()
        for row,target in planned:
            no_links(target)
            if row.is_dir():target.mkdir(parents=True,exist_ok=True);continue
            target.parent.mkdir(parents=True,exist_ok=True)
            with source.open(row) as incoming,target.open('xb') as outgoing:shutil.copyfileobj(incoming,outgoing,1<<20)
    exe=stage/'bin/CadenceStudio4.exe'
    require(sha(exe)==EXE_SHA and not (stage/'bin/icuuc.dll').exists(),'Actual executable or no-local-system-ICU policy differs')
    return exe,doc

def inventory(root):
    result={}
    for path in sorted(root.rglob('*')):
        no_links(path)
        if path.is_file():
            require(len(result)<20000 and path.stat().st_size<=512*1024**2,'Input inventory exceeds bound')
            result[path.relative_to(root).as_posix()]={'bytes':path.stat().st_size,'sha256':sha(path)}
    return result

def read_wav(path):
    require(path.stat().st_size<=128*1024**2,'WAV exceeds128MiB')
    with path.open('rb') as stream:
        header=stream.read(12);require(header[:4]==b'RIFF' and header[8:]==b'WAVE','RIFF/WAVE required')
        fmt=data=None
        while header:=stream.read(8):
            require(len(header)==8,'Truncated WAV chunk')
            tag,size=struct.unpack('<4sI',header);offset=stream.tell()
            require(offset+size<=path.stat().st_size,'WAV chunk exceeds file')
            if tag==b'fmt ':
                require(16<=size<=1024,'WAV format bound');fmt=struct.unpack('<HHIIHH',stream.read(16))
            elif tag==b'data':require(data is None,'Multiple WAV data chunks');data=(offset,size)
            stream.seek(offset+size+(size&1))
        require(fmt is not None and data is not None,'WAV format/data missing')
        encoding,channels,rate,byte_rate,align,bits=fmt;width=bits//8
        require((encoding,bits) in {(1,16),(1,24),(1,32),(3,32),(3,64)} and channels==2 and rate>=8000
                and align==channels*width and byte_rate==rate*align and data[1]>0 and data[1]%align==0,'Unsupported WAV encoding/shape')
        stream.seek(data[0]);raw=stream.read(data[1]);require(len(raw)==data[1],'Truncated PCM')
    scalars=([r[0] for r in struct.iter_unpack('<f' if bits==32 else '<d',raw)] if encoding==3 else
             [int.from_bytes(raw[i:i+width],'little',signed=True)/2**(bits-1) for i in range(0,len(raw),width)])
    return scalars,rate,{'encoding':encoding,'bits':bits,'channels':channels,'sample_rate':rate,'duration_seconds':data[1]/byte_rate,'pcm_sha256':hashlib.sha256(raw).hexdigest()}

def window_rms(values,rate,start,end):
    lo=round(start*rate)*2;hi=round(end*rate)*2
    require(0<=lo<hi<=len(values),'Musical analysis window is outside the actual WAV')
    return math.sqrt(sum(v*v for v in values[lo:hi])/(hi-lo))
