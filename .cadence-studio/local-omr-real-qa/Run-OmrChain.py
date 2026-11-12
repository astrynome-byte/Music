#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Real external Audiveris recognition, then native Cadence import, copies only.

This script is executed below a reviewed OwnedProcessJob wrapper on disposable
Windows CI. Its fixtures are original CC0. It performs no application rebuild,
user GUI, human listening or final product publication.
"""
from __future__ import annotations
import argparse,base64,ctypes,hashlib,json,os,platform,shutil,subprocess,sys,time,urllib.request,zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
PINS={
 'cadence':dict(name='CadenceStudio-4.7.6-cadence.2007-x86_64.msi',bytes=120701412,sha256='ca4e012a44c74935bdeb6f7ba07ad7d3ed688f79c48800202a366df147dc36f6',url='https://github.com/astrynome-byte/Music/releases/download/cadence-studio/v4.7.6-cadence.2007-experimental.1/CadenceStudio-4.7.6-cadence.2007-x86_64.msi'),
 'audiveris':dict(name='Audiveris-5.11.0-windowsConsole-x86_64.msi',bytes=85062430,sha256='5f1b4e96a12c53c7da426814b76e599363c4181e291855996e0a6878dda95f71',url='https://github.com/Audiveris/audiveris/releases/download/5.11.0/Audiveris-5.11.0-windowsConsole-x86_64.msi'),
 'english':dict(name='eng.traineddata',bytes=23466654,sha256='daa0c97d651c19fba3b25e81317cd697e9908c8208090c94c3905381c23fc047',url='https://raw.githubusercontent.com/tesseract-ocr/tessdata/ced78752cc61322fb554c280d13360b35b8684e4/eng.traineddata')}
EXE_SHA='dcfbf9155c6c972c37966a4b2b0dcd212133c8e31fb397c644dda800ac7122be'
EXPECTED=[64,65,67,69,71,72,74,76]

def sha(path):
 with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def require(ok,text):
 if not ok:raise RuntimeError(text)
def download(pin,folder):
 target=folder/pin['name'];require(not target.exists(),'download destination exists')
 req=urllib.request.Request(pin['url'],headers={'User-Agent':'Cadence-local-OMR-qualification'})
 with urllib.request.urlopen(req,timeout=120) as response,target.open('xb') as f:
  status=response.status;size=0
  while True:
   part=response.read(1024*1024)
   if not part:break
   size+=len(part);require(size<=pin['bytes'],'download too large');f.write(part)
 require(status==200 and target.stat().st_size==pin['bytes'] and sha(target)==pin['sha256'],'pinned anonymous download differs')
 return target

def msi_properties(path):
 dll=ctypes.WinDLL('msi',use_last_error=True);H=ctypes.c_uint
 dll.MsiOpenDatabaseW.argtypes=[ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.POINTER(H)]
 dll.MsiDatabaseOpenViewW.argtypes=[H,ctypes.c_wchar_p,ctypes.POINTER(H)]
 dll.MsiViewExecute.argtypes=[H,H];dll.MsiViewFetch.argtypes=[H,ctypes.POINTER(H)]
 dll.MsiRecordGetStringW.argtypes=[H,ctypes.c_uint,ctypes.c_wchar_p,ctypes.POINTER(ctypes.c_uint)]
 db=H();require(dll.MsiOpenDatabaseW(str(path),None,ctypes.byref(db))==0,'MSI READONLY open failed');values={}
 try:
  for key in ['ProductName','ProductVersion','ProductCode']:
   view=H();record=H();require(dll.MsiDatabaseOpenViewW(db,"SELECT `Value` FROM `Property` WHERE `Property`='"+key+"'",ctypes.byref(view))==0,'MSI property view failed')
   try:
    require(dll.MsiViewExecute(view,0)==0 and dll.MsiViewFetch(view,ctypes.byref(record))==0,'MSI property missing')
    size=ctypes.c_uint(4096);buf=ctypes.create_unicode_buffer(4096);require(dll.MsiRecordGetStringW(record,1,buf,ctypes.byref(size))==0,'MSI string read failed');values[key]=buf.value
   finally:
    if record.value:dll.MsiCloseHandle(record)
    if view.value:dll.MsiCloseHandle(view)
 finally:dll.MsiCloseHandle(db)
 return values

def parse_score(path):
 if path.suffix.lower()=='.mxl':
  with zipfile.ZipFile(path) as z:
   require(len(z.infolist())<=256 and sum(x.file_size for x in z.infolist())<=16*1024*1024,'MXL bounds exceeded')
   container=ET.fromstring(z.read('META-INF/container.xml'));roots=[x.attrib.get('full-path','') for x in container.iter() if x.tag.rsplit('}',1)[-1]=='rootfile']
   require(len(roots)==1 and not roots[0].startswith(('/','\\')) and '..' not in roots[0].split('/'),'MXL root invalid');raw=z.read(roots[0])
 else:raw=path.read_bytes()
 root=ET.fromstring(raw);require(root.tag=='score-partwise','partwise score expected for this canonical fixture')
 pitch=[];durations=[];voices=[];measure_counts=[];meters=[];divisions=1
 for measure in root.findall('./part/measure'):
  d=measure.findtext('./attributes/divisions')
  if d:divisions=int(d)
  measure_counts.append(sum(n.find('rest') is None for n in measure.findall('note')))
  time_sig=measure.find('./attributes/time')
  if time_sig is not None:meters.append([time_sig.findtext('beats'),time_sig.findtext('beat-type')])
  for note in measure.findall('note'):
   if note.find('rest') is not None:continue
   step=note.findtext('./pitch/step');octave=note.findtext('./pitch/octave');require(step is not None and step in 'CDEFGAB' and octave is not None,'pitched note expected')
   pitch.append(12*(int(octave)+1)+dict(C=0,D=2,E=4,F=5,G=7,A=9,B=11)[step]+int(note.findtext('./pitch/alter','0')))
   durations.append(float(note.findtext('duration','0'))/divisions);voices.append(note.findtext('voice','1'))
 return dict(pitches=pitch,quarter_units=durations,voices=voices,measure_note_counts=measure_counts,meters=meters,exact_measures=measure_counts==[4,4] and meters==[['4','4']],measure_count=len(root.findall('./part/measure')),xml_bytes=len(raw),xml_sha256=hashlib.sha256(raw).hexdigest(),xml_base64=base64.b64encode(raw).decode() if len(raw)<=262144 else None,
  expected_pitches=EXPECTED,exact_pitches=pitch==EXPECTED,exact_durations=durations==[1.0]*8)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);ap.add_argument('--profile-record',type=Path,required=True);a=ap.parse_args()
 require(os.name=='nt' and platform.machine().lower() in ('amd64','x86_64') and os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted','disposable Windows64 CI only')
 out=a.output.resolve();temp=Path(os.environ['RUNNER_TEMP']).resolve();require(out.is_relative_to(temp) and not out.exists(),'new owned output required');out.mkdir()
 here=Path(__file__).resolve().parent;profile=json.loads(a.profile_record.read_text(encoding='utf-8-sig'));require(profile.get('status')=='prepared','prepared owned profile required')
 ini=Path(profile['settings_file']);ini.write_text('[application]\nhasCompletedFirstLaunchSetup=true\n\n[io]\naudioApi=WASAPI\noutputDevice=\nbufferSize=256\nsampleRate=48000\n',encoding='utf8')
 report=dict(schema_version=1,status='running',producer='External Audiveris5.11.0 and published Cadence2007',commands=[],downloads=[],cases=[],errors=[],firewall_rules=[],first_launch_tested=False,GUI_tested=False,human_listening=False,application_recompiled=False,MSI_normal_installation_tested=False)
 env={k:v for k,v in os.environ.items() if not k.startswith(('QT_','QML_')) and k not in ('GH_TOKEN','GITHUB_TOKEN')}
 def run(name,argv,seconds=180,custom_env=None):
  row=dict(name=name,arguments=list(map(str,argv)),exit_code=None,timed_out=False);report['commands'].append(row);start=time.monotonic()
  with (out/(name+'.stdout.log')).open('xb') as stdout,(out/(name+'.stderr.log')).open('xb') as stderr:
   p=subprocess.Popen(row['arguments'],env=custom_env or env,cwd=out,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW);row['pid']=p.pid
   try:row['exit_code']=p.wait(timeout=seconds)
   except subprocess.TimeoutExpired:row['timed_out']=True;p.kill();row['exit_code']=p.wait(timeout=15)
  row['seconds']=round(time.monotonic()-start,3);require(row['exit_code']==0 and not row['timed_out'],'command failed: '+name)
 def ps(name,code):
  payload=base64.b64encode(code.encode('utf-16le')).decode();run(name,['pwsh','-NoProfile','-NonInteractive','-EncodedCommand',payload],90)
 try:
  downloads=out/'downloads';downloads.mkdir();runtime={}
  for key,pin in PINS.items():
   path=download(pin,downloads);runtime[key]=path;report['downloads'].append(dict(kind=key,**pin,anonymous_http_status=200))
  for key,version in [('cadence','4.7.6.2007'),('audiveris','5.11.0')]:
   props=msi_properties(runtime[key]);require(props['ProductVersion']==version,'MSI version differs');report[key+'_msi_properties_readonly']=props
   target=out/(key+'-image');run(key+'-admin-image',[str(Path(os.environ['SystemRoot'])/'System32/msiexec.exe'),'/a',str(runtime[key]),'/qn','/norestart','TARGETDIR='+str(target),'/L*v',str(out/(key+'-admin-image.log'))],300)
   candidates=list(target.rglob('CadenceStudio4.exe' if key=='cadence' else 'Audiveris.exe'));require(len(candidates)==1,'single native executable expected');runtime[key+'_exe']=candidates[0]
  require(sha(runtime['cadence_exe'])==EXE_SHA,'actual published Cadence EXE differs');report['cadence_exe_sha256']=EXE_SHA
  jarfiles=list((out/'audiveris-image').rglob('audiveris.jar'))+list((out/'audiveris-image').rglob('Audiveris.jar'));jarfiles=list(dict.fromkeys(jarfiles));require(len(jarfiles)==1,'Audiveris application JAR required')
  with zipfile.ZipFile(jarfiles[0]) as jar:
   names=[n for n in jar.namelist() if n.endswith('basic-classifier.zip')];require(len(names)==1,'packaged classifier missing');data=jar.read(names[0]);report['packaged_classifier']=dict(member=names[0],bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),git_blob_sha1=hashlib.sha1(('blob '+str(len(data))+'\0').encode()+data).hexdigest());require(report['packaged_classifier']['git_blob_sha1']=='2b7b9260e2c9b3ce939afb243bcd8fbd9fc00b62','packaged classifier differs from source tag')
  tessdata=out/'tessdata';tessdata.mkdir();shutil.copyfile(runtime['english'],tessdata/'eng.traineddata')
  programs=[runtime['cadence_exe'],runtime['audiveris_exe'],*list((out/'audiveris-image').rglob('java.exe'))];require(len(programs)<=16,'engine executables bound')
  rules=[]
  for i,program in enumerate(programs):
   name='CadenceOMR-QA-'+str(os.getpid())+'-'+str(i);rules.append(name);report['firewall_rules'].append(dict(name=name,program=str(program)))
   q=lambda s:"'"+str(s).replace("'","''")+"'"
   ps('firewall-add-'+str(i),"$ErrorActionPreference='Stop';$r=New-NetFirewallRule -Name "+q(name)+" -DisplayName "+q(name)+" -Direction Outbound -Program "+q(program)+" -Action Block -Enabled True -Profile Any;if($r.Enabled -ne 'True' -or $r.Action -ne 'Block'){throw 'Firewall block not observed'}")
  fixture=here/'omr-canonical.musicxml';before=sha(fixture);working=out/'canonical.musicxml';shutil.copyfile(fixture,working)
  cadence_env=dict(env,PATH=str(runtime['cadence_exe'].parent)+';'+str(Path(os.environ['SystemRoot'])/'System32'))
  run('render-canonical-png',[runtime['cadence_exe'],'--test-mode','--image-resolution','300','-o',out/'canonical.png',working],180,cadence_env)
  run('render-canonical-pdf',[runtime['cadence_exe'],'--test-mode','-o',out/'canonical.pdf',working],180,cadence_env)
  pngs=list(out.glob('canonical*.png'));require(len(pngs)==1 and (out/'canonical.pdf').is_file(),'one actual PNG page and PDF required')
  for kind,source in [('png',pngs[0]),('pdf',out/'canonical.pdf')]:
   case=out/kind;case.mkdir();copy=case/('document.'+kind);shutil.copyfile(source,copy);source_sha=sha(source);dest=case/'output';profile_dir=case/'tool-profile';profile_dir.mkdir()
   tool_env=dict(env,TESSDATA_PREFIX=str(tessdata),APPDATA=str(profile_dir),JAVA_TOOL_OPTIONS='-Duser.home="'+str(profile_dir)+'" -Dorg.bytedeco.javacpp.cachedir="'+str(case/'native-cache')+'"');argv=[runtime['audiveris_exe'],'-batch','-transcribe','-export','-output',dest,'--',copy]
   run('recognize-'+kind,argv,600,tool_env)
   produced=sorted(dest.rglob('*.mxl'));require(produced,'no actual MXL result');require(len(produced)<=8,'too many scores for canonical fixture')
   facts=parse_score(produced[0]);row=dict(kind=kind,recognized=str(produced[0]),recognized_sha256=sha(produced[0]),source_sha256=source_sha,source_unchanged=sha(source)==source_sha,working_copy_unchanged=sha(copy)==source_sha,facts=facts);report['cases'].append(row)
   run('native-import-'+kind,[runtime['cadence_exe'],'--test-mode','-o',case/'recognized.mscz',produced[0]],180,cadence_env)
   run('native-reopen-pdf-'+kind,[runtime['cadence_exe'],'--test-mode','-o',case/'reopened.pdf',case/'recognized.mscz'],180,cadence_env)
   run('native-reexport-'+kind,[runtime['cadence_exe'],'--test-mode','-o',case/'reexport.musicxml',case/'recognized.mscz'],180,cadence_env)
   row['reexport_facts']=parse_score(case/'reexport.musicxml');row['native_MSCZ_and_reopened_PDF']=True
  report['fixture_unchanged']=sha(fixture)==before and sha(working)==before
  report['offline_rule_scope']='Actual Cadence and Audiveris native executables plus included java.exe blocked outbound while rendering and recognizing; downloads completed beforehand'
  report['pinned_downloads_unchanged']=all(sha(downloads/p['name'])==p['sha256'] for p in PINS.values())
  report['native_executable_unchanged']=sha(runtime['cadence_exe'])==EXE_SHA
  require(len(report['cases'])==2 and report['fixture_unchanged'] and report['pinned_downloads_unchanged'] and report['native_executable_unchanged'] and all(c['source_unchanged'] and c['working_copy_unchanged'] and c['facts']['exact_pitches'] and c['facts']['exact_durations'] and c['facts']['exact_measures'] and c['reexport_facts']['exact_pitches'] and c['reexport_facts']['exact_durations'] and c['reexport_facts']['exact_measures'] for c in report['cases']),'Canonical note/rhythm or preservation differs; keep actual results for correction')
  report['status']='passed-real-PNG-and-PDF-OMR-then-native-import-with-canonical-notes-and-rhythms'
 except Exception as e:report['status']='failed-or-blocked';report['errors'].append(str(e))
 finally:
  for i,row in enumerate(report['firewall_rules']):
   try:ps('firewall-remove-'+str(i),"$ErrorActionPreference='Stop';Remove-NetFirewallRule -Name '"+row['name']+"';if(Get-NetFirewallRule -Name '"+row['name']+"' -ErrorAction SilentlyContinue){throw 'Rule cleanup incomplete'}")
   except Exception as e:report['errors'].append(str(e))
  if report['errors']:report['status']='failed-or-blocked'
  (out/'omr-chain-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
  print('CADENCE_REAL_OMR_REPORT_BEGIN');print(json.dumps(report,ensure_ascii=False,separators=(',',':')));print('CADENCE_REAL_OMR_REPORT_END')
 return 0 if report['status'].startswith('passed-') else 1
if __name__=='__main__':raise SystemExit(main())
