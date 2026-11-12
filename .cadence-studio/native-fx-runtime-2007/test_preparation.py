# SPDX-License-Identifier: GPL-3.0-only
"""Preparation/data/refusal checks; never a native Windows application PASS."""
import base64
import copy
import importlib.util
import json
import math
import os
from pathlib import Path
import struct
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

SPEC=importlib.util.spec_from_file_location('native_fx_qa',Path(__file__).with_name('Test-NativeFxRuntime.py'))
q=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(q)


def wave(path,gain=1,defect=None):
    rate=8000;pcm=bytearray()
    for i in range(rate*9):
        t=i/rate
        level=(.01 if t<2 else .04 if t<4 else .08 if t<6 else .04) if t%2<1.5 else 0
        value=level*math.sin(2*math.pi*130.81278265*t)*gain
        if defect=='silent':value=0
        if defect=='nan' and i==400:value=float('nan')
        if defect=='clip' and i==400:value=1.1
        if defect=='shape':value=level*math.sin(2*math.pi*220*t)*gain
        pcm.extend(struct.pack('<ff',value,value))
    fmt=struct.pack('<HHIIHH',3,2,rate,rate*8,8,32)
    body=b'fmt '+struct.pack('<I',16)+fmt+b'data'+struct.pack('<I',len(pcm))+pcm
    path.write_bytes(b'RIFF'+struct.pack('<I',len(body)+4)+b'WAVE'+body)


def native(path,instrument='violoncello',program=42):
    with zipfile.ZipFile(path,'x') as z:
        z.writestr('base.mscx',f'<museScore><Score><Part id="1"><Instrument id="{instrument}"><Channel><program value="{program}"/></Channel></Instrument></Part></Score></museScore>')
        z.writestr('audiosettings.json','{}')


class Preparation(unittest.TestCase):
    def test_fixture_original_cc0_actual_gm_and_eight_second_duration(self):
        root=ET.parse(Path(__file__).parent/'fixtures/native-fx-cello.musicxml')
        self.assertIn('CC0-1.0',root.findtext('identification/rights'))
        self.assertEqual(root.findtext('part-list/score-part/midi-instrument/midi-program'),'43')
        self.assertEqual(root.find('.//sound[@tempo]').get('tempo'),'120')
        measures=root.findall('part/measure');self.assertEqual(len(measures),4)
        self.assertTrue(all(sum(int(n.findtext('duration')) for n in measure.findall('note'))==16 for measure in measures))
        self.assertEqual([s.get('dynamics') for s in root.findall('.//sound[@dynamics]')],['25','63','90','63'])

    def test_real_native_metadata_and_base64_values(self):
        for effect,category,parameters in ((q.EQ,'EQ',q.EQ_PARAMS),(q.COMP,'Dynamics',q.COMP_PARAMS)):
            item=q.fx(effect,True)
            self.assertEqual(item['resourceMeta'],{'id':effect,'type':'muse_plugin','vendor':'Cadence',
                'hasNativeEditorSupport':True,'attributes':{'categories':category}})
            self.assertEqual({k:base64.b64decode(v,validate=True).decode() for k,v in item['unitConfiguration'].items()},parameters)
            self.assertEqual(item['chainOrder'],0)
        with self.assertRaises(ValueError):q.fx('Fake VST',True)

    def test_eleven_case_34_command_plan_and_analytic_settings(self):
        plan=q.cases();self.assertEqual(len(plan),11);self.assertEqual(1+len(plan)*3,34)
        self.assertEqual(len({c['name'] for c in plan}),11)
        for location in ('track','master'):
            group=[c for c in plan if c['location']==location];self.assertEqual(len(group),5)
            self.assertEqual(sum(c['reduction'] for c in group),1)
        self.assertEqual(q.COMP_PARAMS['ratio'],'1');self.assertEqual(q.COMP_PARAMS['makeupDb'],'6')
        self.assertEqual(q.REDUCTION_PARAMS['thresholdDb'],'-60');self.assertEqual(q.REDUCTION_PARAMS['ratio'],'4')

    def test_exact_native_assignment_dry_two_aux_and_fx_roundtrip(self):
        with tempfile.TemporaryDirectory() as t:
            d=Path(t);base=d/'base.mscz';native(base)
            for case in q.cases():
                target=d/(case['name']+'.mscz');requested=q.assign(base,target,case)
                self.assertTrue(q.preserved(target,requested))
                self.assertEqual(requested['tracks'][0]['out']['auxSends'],q.DRY)
                for send in requested['tracks'][0]['out']['auxSends']:
                    self.assertIs(send['active'],False);self.assertIsInstance(send['signalAmount'],float)
                actual,_=q.r.native_data(target);self.assertEqual(actual,requested)
                self.assertEqual(set(actual['tracks'][0]['out']['fxChain']),{'0'} if case['location']=='track' else set())
                self.assertEqual(set(actual['master']['fxChain']),{'0'} if case['location']=='master' else set())

    def test_persistence_refuses_bypass_parameter_and_aux_loss(self):
        with tempfile.TemporaryDirectory() as t:
            d=Path(t);base=d/'base.mscz';native(base);assigned=d/'assigned.mscz';expected=q.assign(base,assigned,q.cases()[2])
            for mode in ('active','configuration','aux'):
                changed=copy.deepcopy(expected)
                if mode=='active':changed['tracks'][0]['out']['fxChain']['0']['active']=False
                elif mode=='configuration':changed['tracks'][0]['out']['fxChain']['0']['unitConfiguration']['outputGainDb']='MA=='
                else:changed['tracks'][0]['out']['auxSends']=[]
                path=d/(mode+'.mscz')
                with zipfile.ZipFile(assigned) as source,zipfile.ZipFile(path,'x') as dest:
                    for row in source.infolist():dest.writestr(row,json.dumps(changed).encode() if row.filename=='audiosettings.json' else source.read(row))
                with self.assertRaises(ValueError):q.preserved(path,expected)

    def test_native_instrument_or_gm_mismatch_refused(self):
        with tempfile.TemporaryDirectory() as t:
            d=Path(t)
            for n,instrument,program in ((1,'trumpet',56),(2,'violoncello',41)):
                source=d/f'{n}.mscz';native(source,instrument,program)
                with self.assertRaises(ValueError):q.assign(source,d/f'out{n}.mscz',q.cases()[0])

    def test_actual_pcm_gates_and_known_gain_controls(self):
        with tempfile.TemporaryDirectory() as t:
            d=Path(t);base=d/'base.wav';wave(base)
            self.assertTrue(q.inspect(base)['passed'])
            for db in (0,-6,6):
                path=d/(str(db)+'.wav');wave(path,10**(db/20))
                self.assertTrue(q.compare(base,path,db)['passed'])
            self.assertFalse(q.compare(base,base,6)['passed'])
            self.assertFalse(q.compare(base,base,-6)['passed'])
            for defect in ('silent','nan','clip'):
                path=d/(defect+'.wav');wave(path,defect=defect)
                self.assertFalse(q.inspect(path)['passed'])
            wrong=d/'wrong-shape.wav';wave(wrong,defect='shape')
            self.assertFalse(q.compare(base,wrong,0)['passed'])

    def test_actual_reduction_control_refuses_unchanged_or_amplified_pcm(self):
        with tempfile.TemporaryDirectory() as t:
            d=Path(t);base=d/'base.wav';quiet=d/'quiet.wav';loud=d/'loud.wav'
            wave(base);wave(quiet,.25);wave(loud,2)
            self.assertTrue(q.compare(base,quiet,reduction=True)['passed'])
            self.assertFalse(q.compare(base,base,reduction=True)['passed'])
            self.assertFalse(q.compare(base,loud,reduction=True)['passed'])

    def test_exact_stage_tamper_refused_before_extraction(self):
        with tempfile.TemporaryDirectory() as t:
            d=Path(t);(d/'stage-manifest.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'byte-exact actual2007'):q.r.restore_stage(d,d/'stage')
            self.assertFalse((d/'stage').exists())

    def test_archive_paths_refused(self):
        for path in ('../outside','/absolute','C:stream','dir\\file','trailing. '):
            with self.assertRaises(ValueError):q.r.relative_member(path)

    @unittest.skipIf(os.name=='nt','Linux refusal only')
    def test_native_entry_refuses_linux_without_writes(self):
        with tempfile.TemporaryDirectory() as t:
            d=Path(t)
            with self.assertRaises(ValueError):q.main(['--artifact',str(d/'a'),'--stage',str(d/'s'),'--profile-record',str(d/'p'),'--output',str(d/'o')])
            self.assertEqual(list(d.iterdir()),[])

if __name__=='__main__':unittest.main()
