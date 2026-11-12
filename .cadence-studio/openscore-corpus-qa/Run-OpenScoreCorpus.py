#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Qualify ten unmodified CC0 editions through the retained native CLI.

The enclosing existing PowerShell owned Job owns and drains all descendants.
No source/timbre/gain changes, GUI control, DLL installation or application build.
"""
from __future__ import annotations
import argparse,base64,hashlib,importlib.util,io,json,os,platform,shutil,stat,subprocess,sys,time,zipfile
from collections import Counter
from pathlib import Path,PurePosixPath
import xml.etree.ElementTree as ET
EXE_SHA='c29d7c8c76b213b79d7390acd65cbabc6fb940f06e3e7f86c0ce60be7e9b9520'
ARCHIVE_SHA='b6b6bb9160250282879543b44e1ca8217494285e86c47fb2003f8b24dd93954c'
SOURCE='ac9a24933f78f22ea630570910848201baad3d3b';TREE='a94a09974229c47e7b90b593a7649c29d6a6d190'
SOURCE_JSON_SHA='0d6c5944374cfa2b58ee8f81a3912b36585ed263ed79ffb3ff1968f2bd07ca1b'
BASIC_SHA='5ea2375e8bd7d8e71def1036978c1621e85b66934169b6a2744b27b9b3c2d99c'
PACK_SHA='00906d5d4bc85eabb931e9afebb4c2b9c5a452ef2a6a6b28916dbaa867016d03';PACK_BYTES=622656
B64_SHA='881d24034aab1ec31707407bffdcfd5347743cee542e702245d7a31063fb0d73';RECEIPT_SHA='1dbb572a67f7a0075e48504ad694f41ca7fc02d8dff57c117deb5fa7b9668f7a'
PROFILE_SHA='60b6bb2353467cf338e2c671151af37d3fd36d76748e52cda6a1e3ab22c4c27c'
WAV_CHECKER_SHA='f701874e7a37b8d3148f0bb99477b60b96865e804ed238372d75c06598027d82'
MANIFEST_SHA='8a93136fb13c3910fbc287204eb83bcf42c5ba9e4b2a60799d80a14aa84ba697'

def sha(path):
 with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def no_links(path):
 for part in (path,*path.parents):
  try:info=part.lstat()
  except FileNotFoundError:continue
  if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:raise ValueError('Linked/reparse runtime path refused')
def owned(path):
 path=Path(path).absolute();no_links(path);path=path.resolve();temp=Path(os.environ['RUNNER_TEMP']).resolve()
 if temp not in path.parents:raise ValueError('Runtime path must be strictly below RUNNER_TEMP')
 return path
def member(name):
 p=PurePosixPath(name)
 if not name or p.is_absolute() or p.as_posix()!=name or '..' in p.parts or any(c in name for c in '\\:\0<>"|?*'):raise ValueError('Unsafe content member')
 for part in p.parts:
  if part.endswith(('.', ' ')) or part.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}:raise ValueError('Ambiguous Windows content member')
 return p
def load_module(name,path,expected):
 if sha(path)!=expected:raise ValueError('Reused helper differs from exact pin')
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module);return module

def restore_pack(here,target):
 if target.exists():raise ValueError('New pack destination required')
 encoded=here/'score-pack.zip.base64';receipt_path=here/'package-receipt.json'
 if sha(encoded)!=B64_SHA or sha(receipt_path)!=RECEIPT_SHA:raise ValueError('Reviewed content transport/receipt differs')
 raw=base64.b64decode(b''.join(encoded.read_bytes().split()),validate=True)
 if len(raw)!=PACK_BYTES or hashlib.sha256(raw).hexdigest()!=PACK_SHA:raise ValueError('Exact reviewed score ZIP differs')
 receipt=json.loads(receipt_path.read_text());expected={r['path']:r for r in receipt['files']}
 if len(expected)!=38 or receipt['score_count']!=10 or receipt['sha256']!=PACK_SHA or receipt['manifest_sha256']!=MANIFEST_SHA:raise ValueError('Content receipt identity/count differs')
 sums=''.join(r['sha256']+'  '+r['path']+'\n' for r in receipt['files']).encode()
 expected['SHA256SUMS.txt']={'bytes':len(sums),'sha256':hashlib.sha256(sums).hexdigest()}
 with zipfile.ZipFile(io.BytesIO(raw)) as archive:
  infos=archive.infolist()
  if len(infos)!=39 or len({i.filename.casefold() for i in infos})!=39 or {i.filename for i in infos}!=set(expected) or sum(i.file_size for i in infos)>16777216:raise ValueError('Content ZIP members differ/exceed bounds')
  for info in infos:
   member(info.filename)
   if info.is_dir() or stat.S_ISLNK(info.external_attr>>16) or info.file_size!=expected[info.filename]['bytes']:raise ValueError('Content ZIP kind/size differs')
   data=archive.read(info)
   if hashlib.sha256(data).hexdigest()!=expected[info.filename]['sha256']:raise ValueError('Content ZIP member differs')
  target.mkdir()
  for info in infos:
   p=target.joinpath(*member(info.filename).parts);p.parent.mkdir(parents=True,exist_ok=True)
   with p.open('xb') as output:output.write(archive.read(info))
 manifest=json.loads((target/'collection-manifest.json').read_text())
 if sha(target/'collection-manifest.json')!=MANIFEST_SHA or manifest['score_count']!=10 or len(manifest['scores'])!=10:raise ValueError('Exact collection manifest differs')
 for row in manifest['scores']:
  for key in ('original_path','working_path'):
   path=target.joinpath(*member(row[key]).parts);no_links(path)
   if sha(path)!=row['edition']['score_sha256']:raise ValueError('Score copies differ')
 return manifest,expected

def verify_pack(target,expected):
 actual=[p for p in target.rglob('*') if p.is_file()]
 if {p.relative_to(target).as_posix() for p in actual}!=set(expected):raise ValueError('Content pack inventory changed')
 for name,row in expected.items():
  p=target.joinpath(*member(name).parts);no_links(p)
  if p.stat().st_size!=row['bytes'] or sha(p)!=row['sha256']:raise ValueError('Original content pack changed: '+name)
 return True

def read_score(path):
 settings=None
 if path.suffix=='.mscz':
  with zipfile.ZipFile(path) as archive:
   infos=archive.infolist()
   if len(infos)>256 or len({i.filename.casefold() for i in infos})!=len(infos) or sum(i.file_size for i in infos)>16777216:raise ValueError('Native score ZIP exceeds bounds')
   for info in infos:
    member(info.filename.rstrip('/') if info.is_dir() else info.filename)
    if info.file_size>8388608 or stat.S_ISLNK(info.external_attr>>16):raise ValueError('Oversized/linked native member')
   container=ET.fromstring(archive.read('META-INF/container.xml'));roots=[r.get('full-path') for r in container.iter('rootfile') if r.get('full-path','').endswith('.mscx')]
   if len(roots)!=1:raise ValueError('Unique master MSCX required')
   data=archive.read(roots[0]);settings=json.loads(archive.read('audiosettings.json')) if 'audiosettings.json' in archive.namelist() else None
 else:data=path.read_bytes()
 if len(data)>8388608 or b'<!DOCTYPE' in data or b'<!ENTITY' in data:raise ValueError('Unexpected score XML')
 root=ET.fromstring(data);score=root.find('Score')
 if root.tag!='museScore' or score is None:raise ValueError('Native score expected')
 staves=score.findall('Staff');pitches=Counter(int(n.text) for staff in staves for n in staff.findall('./Measure//Note/pitch'))
 meta={m.get('name'):''.join(m.itertext()) for m in score.findall('metaTag')}
 summary=dict(version=root.get('version'),part_count=len(score.findall('Part')),staff_count=len(staves),measure_counts=[len(s.findall('Measure')) for s in staves],
  pitch_multiset=sorted(pitches.items()),note_count=sum(pitches.values()),lyric_fragment_count=sum(len(list(s.iter('Lyrics'))) for s in staves),metadata=meta,
  encoded_parts=[dict(track_name=p.findtext('trackName'),instruments=[dict(id=i.get('id'),long_name=i.findtext('longName'),programs=[r.attrib for r in i.findall('./Channel/program')]) for i in p.findall('Instrument')]) for p in score.findall('Part')])
 return summary,settings

def compare_structure(before,after):
 keys=('part_count','staff_count','measure_counts','pitch_multiset','note_count','lyric_fragment_count')
 differences={key:{'before':before[key],'after':after[key]} for key in keys if before[key]!=after[key]}
 if not before['note_count'] or not before['lyric_fragment_count']:raise ValueError('Selected song is empty or lacks lyrics')
 if differences:raise ValueError('Native save changed coarse score structure: '+json.dumps(differences,ensure_ascii=True))
 if 'CC0' not in after['metadata'].get('copyright','') or 'OpenScore' not in after['metadata'].get('copyright',''):raise ValueError('OpenScore CC0 credit was lost')
 return dict(passed=True,compared=list(keys),scope='Coarse native structure only, not rhythm/articulation/lyric syllable content or visual equivalence')

def pdf_info(path):
 if not path.is_file() or not 100<path.stat().st_size<16777216:raise ValueError('PDF missing or outside bounds')
 with path.open('rb') as stream:
  header=stream.read(8);stream.seek(max(0,path.stat().st_size-4096));tail=stream.read()
 if not header.startswith(b'%PDF-') or b'%%EOF' not in tail:raise ValueError('PDF lacks its header or completion marker')
 return dict(bytes=path.stat().st_size,sha256=sha(path),container_complete=True,visually_checked=False)

def inventory(root):
 rows=[]
 for p in sorted(root.rglob('*')):
  no_links(p)
  if p.is_file():rows.append(dict(path=p.relative_to(root).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
 if not 2000<len(rows)<4000:raise ValueError('Unexpected retained stage inventory size')
 return rows

def snapshot(logs):
 files=list(logs.rglob('*.log')) if logs.exists() else []
 if len(files)>48:raise ValueError('Unexpected fresh profile log count')
 result={}
 for path in files:
  no_links(path)
  if path.stat().st_size>16777216:raise ValueError('Application log exceeds bound')
  result[path.name]=path.read_bytes()
 return result

def main(argv=None):
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',type=Path,required=True);parser.add_argument('--restoration-record',type=Path,required=True);parser.add_argument('--profile-record',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args(argv)
 if os.name!='nt' or platform.machine().lower() not in ('amd64','x86_64') or any(os.environ.get(k)!=v for k,v in [('CI','true'),('GITHUB_ACTIONS','true'),('RUNNER_ENVIRONMENT','github-hosted')]):raise ValueError('Only disposable native Windows x64 GitHub-hosted CI may execute this qualification')
 if sys.version_info[:2]!=(3,12):raise ValueError('Actual Python 3.12 required')
 here=Path(__file__).resolve().parent;stage=owned(args.stage);output=owned(args.output);restoration=owned(args.restoration_record);profile_record=owned(args.profile_record)
 if output.exists() or stage in output.parents or output in stage.parents:raise ValueError('New disjoint output required')
 record=json.loads(restoration.read_text(encoding='utf-8-sig'));exe=stage/'bin/CadenceStudio4.exe'
 if record.get('status')!='retained-actual2006-stage-restored-and-sha256-verified' or record.get('build_number')!=2006 or record.get('original_source_commit')!=SOURCE or record.get('source_tree')!=TREE or record.get('stage_archive_sha256')!=ARCHIVE_SHA or record.get('source_json_sha256')!=SOURCE_JSON_SHA or record.get('executable_sha256')!=EXE_SHA or Path(record['executable_path']).resolve()!=exe or sha(exe)!=EXE_SHA:raise ValueError('Authenticated exact stage2006 required')
 basic=list(stage.rglob('MS Basic.sf3'))
 if len(basic)!=1 or sha(basic[0])!=BASIC_SHA:raise ValueError('Exact retained MS Basic required')
 profile_helper=load_module('openscore_profile',here/'CadenceProfileScope.py',PROFILE_SHA);profile=profile_helper.verify_record(profile_record)
 checker=load_module('openscore_wav',here/'corpus_run_exports.py',WAV_CHECKER_SHA)
 output.mkdir();pack=output/'immutable-pack';manifest,expected=restore_pack(here,pack)
 before_stage=inventory(stage);(output/'stage-files-before.json').write_text(json.dumps(before_stage,indent=2)+'\n')
 report=dict(schema_version=1,status='running',source_commit=SOURCE,source_tree=TREE,build_number=2006,executable_sha256=EXE_SHA,stage_archive_sha256=ARCHIVE_SHA,source_json_sha256=SOURCE_JSON_SHA,
  content_pack_sha256=PACK_SHA,collection_manifest_sha256=MANIFEST_SHA,profile_owner=profile['owner'],commands=[],cases=[],errors=[],originals_unchanged=False,stage_unchanged=False,
  application_recompiled=False,application_executed=False,GUI_tested=False,library_GUI_import_tested=False,notes_edited=False,human_listening=False,physical_audio_playback_tested=False,
  source_timbres_or_gains_modified=False,missing_resource_warning_tested=False,save_after_same_live_audio_session_tested=False,
  scope='Real CLI opening/import, PDF, native MSCZ save, re-open PDF and nonmute finite unsaturated WAV for ten exact editions; copies only')
 ini=Path(profile['settings_file']);no_links(ini);ini.write_text('[application]\nhasCompletedFirstLaunchSetup=true\n\n[io]\naudioApi=WASAPI\noutputDevice=\nbufferSize=256\nsampleRate=48000\n',encoding='utf-8');report['owned_settings_sha256']=sha(ini)
 env={k:v for k,v in os.environ.items() if not k.startswith(('QT_','QML_','CADENCE_QA_CLOCK')) and k not in ('GITHUB_TOKEN','GH_TOKEN')};env['PATH']=str(exe.parent)+';'+str(Path(os.environ['SystemRoot'])/'System32')
 logs=Path(profile['log_root'])
 def run(name,args,timeout=120):
  first=snapshot(logs);row=dict(name=name,arguments=[str(exe),*map(str,args)],pid=None,exit_code=None,timed_out=False);report['commands'].append(row);started=time.monotonic()
  with (output/(name+'.stdout.log')).open('xb') as out,(output/(name+'.stderr.log')).open('xb') as err:
   process=subprocess.Popen(row['arguments'],cwd=output,env=env,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW);row['pid']=process.pid;report['application_executed']=True
   try:row['exit_code']=process.wait(timeout=timeout)
   except subprocess.TimeoutExpired:row['timed_out']=True;process.kill();row['exit_code']=process.wait(timeout=10)
   finally:
    if process.poll() is None:process.kill();process.wait(timeout=10)
  row['seconds']=round(time.monotonic()-started,3);last=snapshot(logs);delta=b'\n'.join(data[len(first.get(key,b'')):] if data.startswith(first.get(key,b'')) else data for key,data in last.items())
  (output/(name+'.cadence-log-delta.log')).write_bytes(delta)
  text=delta.decode('utf8',errors='replace')
  for suffix in ('stdout','stderr'):
   path=output/(name+'.'+suffix+'.log')
   if path.stat().st_size>16777216:raise ValueError('Application transcript exceeds bound')
   text+='\n'+path.read_text(encoding='utf8',errors='replace')
  row['resource_warning_lines']=[line[:1024] for line in text.splitlines() if any(word in line.lower() for word in ('not found','not available','fallback','failed to resolve','failed parse soundfont'))][-20:]
  if row['timed_out'] or row['exit_code']!=0:raise RuntimeError('Native CLI failed or timed out: '+name)
  return row
 try:
  for entry in manifest['scores']:
   case=dict(id=entry['id'],title=entry['title'],status='running',errors=[],source_sha256=entry['edition']['score_sha256'],source_format_version=entry['native_format_version'],known_source_timbres=entry['encoded_playback']['encoded_parts'],profile_was_owned=True)
   report['cases'].append(case);folder=output/entry['id'];folder.mkdir();original=pack/entry['original_path'];copy=folder/('input'+original.suffix);shutil.copyfile(original,copy)
   try:
    before,source_audio=read_score(copy);case['before_structure']=before;case['source_audio_settings']=source_audio
    prefix=entry['id'];pdf=folder/'opened.pdf';run(prefix+'-open-pdf',['-o',pdf,copy]);case['opened_pdf']=pdf_info(pdf)
    saved=folder/'saved.mscz';run(prefix+'-save-native',['-o',saved,copy]);after,audio=read_score(saved);case['saved_structure']=after;case['saved_audio_settings']=audio;case['saved_sha256']=sha(saved)
    try:case['coarse_roundtrip']=compare_structure(before,after)
    except ValueError as structure_error:case['coarse_roundtrip']={'passed':False,'error':str(structure_error)};case['errors'].append(str(structure_error))
    reopened=folder/'reopened.pdf';run(prefix+'-reopen-pdf',['-o',reopened,saved]);case['reopened_pdf']=pdf_info(reopened)
    wav=folder/'rendered.wav';run(prefix+'-render-wav',['-o',wav,saved],180)
    if not wav.is_file() or wav.stat().st_size>134217728:raise ValueError('WAV missing or exceeds 128 MiB')
    case['audio']=checker.inspect_wav(wav);case['wav_sha256']=sha(wav);case['wav_bytes']=wav.stat().st_size
    if not case['audio']['passed']:raise RuntimeError('WAV is silent, nonfinite or digitally saturated')
    case['saved_file_unchanged_by_reopen_and_render']=sha(saved)==case['saved_sha256']
    if not case['saved_file_unchanged_by_reopen_and_render']:raise RuntimeError('Saved source was modified by read-only export')
    case['status']='passed-native-file-and-audio-container-checks' if not case['errors'] else 'failed-or-blocked'
   except Exception as error:case['status']='failed-or-blocked';case['errors'].append(str(error))
   finally:
    case['input_copy_unchanged']=sha(copy)==entry['edition']['score_sha256'];case['original_unchanged']=sha(original)==entry['edition']['score_sha256']
    if not case['input_copy_unchanged'] or not case['original_unchanged']:case['status']='failed-or-blocked';case['errors'].append('Immutable score/input copy changed')
    (folder/'case-report.json').write_text(json.dumps(case,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:case[k] for k in ('id','title','status','errors')},ensure_ascii=True),flush=True)
  report['cases_passed']=sum(c['status']=='passed-native-file-and-audio-container-checks' for c in report['cases'])
  report['status']='passed-ten-native-score-cases' if len(report['cases'])==report['cases_passed']==10 else 'failed-or-blocked'
 except Exception as error:report['errors'].append(str(error));report['status']='failed-or-blocked'
 finally:
  try:report['originals_unchanged']=verify_pack(pack,expected)
  except Exception as error:report['errors'].append(str(error));report['status']='failed-or-blocked'
  try:
   after_stage=inventory(stage);(output/'stage-files-after.json').write_text(json.dumps(after_stage,indent=2)+'\n');report['stage_unchanged']=before_stage==after_stage
   if not report['stage_unchanged']:raise ValueError('Authenticated stage inventory changed')
  except Exception as error:report['errors'].append(str(error));report['status']='failed-or-blocked'
  report['finished_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime());(output/'openscore-native-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
  print('CADENCE_OPENSCORE_NATIVE_REPORT_BEGIN');print(json.dumps(report,ensure_ascii=True,separators=(',',':')));print('CADENCE_OPENSCORE_NATIVE_REPORT_END',flush=True)
 return 0 if report['status']=='passed-ten-native-score-cases' and not report['errors'] else 1
if __name__=='__main__':raise SystemExit(main())
