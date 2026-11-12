# SPDX-License-Identifier: GPL-3.0-only
"""Pure Linux fixtures only; no Cadence, FluidSynth, sample or Windows qualification."""
import importlib.util
import json
import math
import os
from pathlib import Path
import struct
import tempfile
import unittest
import wave
import xml.etree.ElementTree as ET
import zipfile

SPEC = importlib.util.spec_from_file_location('vsco_sf2_native_source', Path(__file__).with_name('Test-VscoSf2.py'))
qa = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qa)


class SourceDataChecks(unittest.TestCase):
    def test_generated_original_exercises_have_correct_family_program_and_duration(self):
        for instrument, program in [('flute', '74'), ('violin', '41')]:
            root = ET.fromstring(qa.score_xml(instrument))
            self.assertEqual(root.findtext('part-list/score-part/midi-instrument/midi-program'), program)
            self.assertEqual(root.findtext('part-list/score-part/part-name').lower(), instrument)
            self.assertEqual(len(root.findall('part/measure/note')), 8)
            self.assertIn('CC0-1.0', root.findtext('identification/rights'))

    def test_archive_paths_and_parser(self):
        for name in ('../outside', '/absolute', 'C:stream', 'dir\\file', 'dir/trailing. '):
            with self.subTest(name=name), self.assertRaises(ValueError):
                qa.relative_member(name)
        args = qa.build_parser().parse_args(['--artifact','a','--stage','s','--banks','b','--profile-record','p','--output','o'])
        self.assertEqual(args.banks, Path('b'))

    def test_synthetic_native_resource_assignment_and_preservation(self):
        with tempfile.TemporaryDirectory(prefix='synthetic-vsco-native-') as temporary:
            root = Path(temporary)
            base, target = root/'base.mscz', root/'assigned.mscz'
            master = b'<museScore><Score><Part id="1"><Instrument id="flute"/></Part></Score></museScore>'
            with zipfile.ZipFile(base, 'x') as archive:
                archive.writestr('base.mscx', master)
                archive.writestr('audiosettings.json', '{}')
            bank = {'soundfont_name':'Cadence-VSCO-Flute','resource_id':r'Cadence-VSCO-Flute\0\73','program':73}
            track = qa.assign_soundfont(base, target, 'flute', bank)
            self.assertEqual(track['in']['resourceMeta']['id'], r'Cadence-VSCO-Flute\0\73')
            self.assertTrue(qa.input_preserved(target, track))
            settings, _ = qa.native_data(target)
            self.assertEqual(settings['master']['fxChain'], {})
            self.assertEqual(settings['aux'], [])
            with self.assertRaises(ValueError):
                qa.assign_soundfont(base, root/'wrong-family.mscz', 'violin', bank)

    def test_synthetic_pcm_gain_and_silence_detection(self):
        with tempfile.TemporaryDirectory(prefix='synthetic-vsco-wav-') as temporary:
            root = Path(temporary)
            metrics = []
            for label, gain in [('normal',1),('minus18',10**(-18/20)),('silent',0)]:
                path = root/(label+'.wav')
                with wave.open(str(path), 'wb') as writer:
                    writer.setparams((2,2,8000,0,'NONE','not compressed'))
                    writer.writeframes(b''.join(struct.pack('<hh', value, value) for value in
                        [round(5000*gain*math.sin(2*math.pi*440*i/8000)) for i in range(16000)]))
                metrics.append(qa.inspect_wav(path))
            self.assertTrue(metrics[0]['passed'])
            self.assertTrue(metrics[1]['passed'])
            self.assertFalse(metrics[2]['passed'])
            self.assertAlmostEqual(metrics[1]['rms']/metrics[0]['rms'],10**(-18/20),delta=.001)

    @unittest.skipIf(os.name == 'nt', 'Linux refusal check only')
    def test_windows_entrypoint_refuses_without_runtime_writes(self):
        with tempfile.TemporaryDirectory(prefix='synthetic-vsco-refusal-') as temporary:
            root = Path(temporary)
            with self.assertRaises(ValueError):
                qa.main(['--artifact',str(root/'a'),'--stage',str(root/'s'),'--banks',str(root/'b'),
                         '--profile-record',str(root/'p'),'--output',str(root/'o')])
            self.assertEqual(list(root.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
