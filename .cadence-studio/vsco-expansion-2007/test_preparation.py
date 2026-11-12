# SPDX-License-Identifier: GPL-3.0-only
"""Data and refusal checks only; no application or Windows qualification."""
import hashlib,importlib.util,json,math,os
from pathlib import Path
import struct,tempfile,unittest,xml.etree.ElementTree as ET,zipfile
P=Path(__file__).with_name('Test-VscoExpansion.py');s=importlib.util.spec_from_file_location('expansion_qa',P);q=importlib.util.module_from_spec(s);s.loader.exec_module(q)

def wav(path,gain=1,clipped=False,silent=False):
 rate=8000;pcm=bytearray()
 for i in range(rate*29):
  t=i/rate;amp=0.0
  for start,level in [(0,.03),(2,.06),(4,.12)]:
   phase=t-start
   if 0<=phase<.4:amp=level
   elif .4<=phase<1.2:amp=level*math.exp(-6*(phase-.4))
  if 6<=t<14:amp=.06
  v=0 if silent else amp*math.sin(2*math.pi*130.81278265*t)*gain
  if clipped and i==80:v=2.0
  pcm+=struct.pack('<ff',v,v)
 fmt=struct.pack('<HHIIHH',3,2,rate,rate*8,8,32)
 body=b'fmt '+struct.pack('<I',len(fmt))+fmt+b'data'+struct.pack('<I',len(pcm))+pcm
 path.write_bytes(b'RIFF'+struct.pack('<I',len(body)+4)+b'WAVE'+body)

class Preparation(unittest.TestCase):
 def test_scores_program_clef_dynamics_ties_and_duration(self):
  for instrument,program in [('cello',43),('trumpet',57),('contrabass',44)]:
   root=ET.fromstring(q.score_xml(instrument));self.assertEqual(root.findtext('part-list/score-part/midi-instrument/midi-program'),str(program))
   measures=root.findall('part/measure');self.assertEqual(len(measures),14)
   self.assertTrue(all(sum(int(n.findtext('duration')) for n in m.findall('note'))==16 for m in measures))
   self.assertEqual(sum(1 for t in root.findall('.//tie') if t.get('type')=='start'),9)
   self.assertEqual(sum(1 for t in root.findall('.//tie') if t.get('type')=='stop'),9)
   self.assertEqual(root.findtext('part/measure/attributes/clef/sign'),'G' if instrument=='trumpet' else 'F')
   self.assertEqual(root.findtext('part/measure/attributes/transpose/chromatic'),'-12' if instrument=='contrabass' else '0')
   self.assertIn('CC0-1.0',root.findtext('identification/rights'))
   self.assertEqual([x.get('dynamics') for x in root.findall('.//sound') if x.get('dynamics')],['25','63','90','63'])
 def test_actual_three_bank_metadata_lock(self):
  lock=json.loads(P.with_name('bank-lock.json').read_text());self.assertEqual(len(lock['banks']),3)
  self.assertEqual({b['program'] for b in lock['banks']},{42,56,43})
  self.assertEqual(sum(b['bytes'] for b in lock['banks']),117965908)
  for b in lock['banks']:self.assertEqual(b['resource_id'],b['soundfont_name']+'\\0\\'+str(b['program']))
 def test_exact_collection_ids_and_eight_case_plan(self):
  lock=json.loads(P.with_name('bank-lock.json').read_text());rows={b['collection_id']:b for b in lock['banks']}
  quiet={**rows['trumpet-vibrato'],'file':q.QUIET_FILE,'resource_id':q.QUIET_FILE[:-4]+'\\0\\56'}
  cases=q.planned_cases(rows,quiet);self.assertEqual(len(cases),8);self.assertEqual(3+len(cases)*3,27)
  self.assertEqual([x[0] for x in cases],['basic-cello','cello','basic-trumpet','trumpet','basic-contrabass','contrabass','trumpet-minus18','missing-cello'])
  self.assertEqual([x[2]['program'] for x in cases if x[2] is not None],[42,56,43,56,42])
  bad=dict(rows);bad['trumpet-vibrato']={**bad['trumpet-vibrato'],'program':55}
  with self.assertRaisesRegex(ValueError,'collection/family'):q.planned_cases(bad,quiet)
 def test_synthetic_native_assignment_rejects_wrong_family_or_program(self):
  with tempfile.TemporaryDirectory() as t:
   d=Path(t);base=d/'base.mscz'
   with zipfile.ZipFile(base,'x') as z:
    z.writestr('base.mscx','<museScore><Score><Part id="1"><Instrument id="violoncello"><Channel><program value="42"/></Channel></Instrument></Part></Score></museScore>');z.writestr('audiosettings.json','{}')
   bank={'soundfont_name':'Cadence-VSCO-Cello-Ensemble','resource_id':'Cadence-VSCO-Cello-Ensemble\\0\\42','program':42}
   track,meta=q.assign_soundfont(base,d/'assigned.mscz','cello',bank);self.assertTrue(q.input_preserved(d/'assigned.mscz',track));self.assertEqual(meta['imported_GM_programs_zero_based'],[42])
   with self.assertRaises(ValueError):q.assign_soundfont(base,d/'wrong.mscz','trumpet',bank)
 def test_data_windows_gain_and_no_false_silence_or_clipping_pass(self):
  with tempfile.TemporaryDirectory() as t:
   d=Path(t)
   for name,gain,clip,silence in [('normal',1,False,False),('quiet',10**(-18/20),False,False),('clip',1,True,False),('silent',0,False,True)]:wav(d/(name+'.wav'),gain,clip,silence)
   a=q.inspect_wav(d/'normal.wav','cello',True);b=q.inspect_wav(d/'quiet.wav','cello',True)
   self.assertTrue(a['passed']);self.assertTrue(b['passed']);self.assertAlmostEqual(b['rms']/a['rms'],10**(-18/20),delta=1e-6)
   self.assertFalse(a['spectral_diagnostic_only']['used_as_qualification_gate']);self.assertTrue(a['envelope_observations']['finite_unlooped_sample_ends_while_note_held'])
   self.assertFalse(q.inspect_wav(d/'clip.wav','cello',True)['passed']);self.assertFalse(q.inspect_wav(d/'silent.wav','cello',True)['passed'])
 def test_stage_manifest_tamper_refused_before_extraction(self):
  with tempfile.TemporaryDirectory() as t:
   d=Path(t);(d/'stage-manifest.json').write_text('{"schema_version":1}')
   with self.assertRaisesRegex(ValueError,'byte-exact actual2007'):q.restore_stage(d,d/'new-stage')
   self.assertFalse((d/'new-stage').exists())
 def test_archive_paths(self):
  for name in ['../outside','/absolute','C:stream','dir\\file','dir/trailing. ']:
   with self.assertRaises(ValueError):q.relative_member(name)
 @unittest.skipIf(os.name=='nt','Linux refusal check only')
 def test_native_entry_refuses_linux_without_writes(self):
  with tempfile.TemporaryDirectory() as t:
   d=Path(t)
   with self.assertRaises(ValueError):q.main(['--artifact',str(d/'a'),'--stage',str(d/'s'),'--banks',str(d/'b'),'--profile-record',str(d/'p'),'--output',str(d/'o')])
   self.assertEqual(list(d.iterdir()),[])
if __name__=='__main__':unittest.main()
