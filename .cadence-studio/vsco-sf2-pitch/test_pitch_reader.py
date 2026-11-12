# SPDX-License-Identifier: GPL-3.0-only
"""Synthetic signals only: these tests do not validate the real Windows WAVs."""
import importlib.util
import math
from pathlib import Path
import struct
import unittest

SPEC = importlib.util.spec_from_file_location('pitch_reader', Path(__file__).with_name('analyze_existing_wavs.py'))
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class SyntheticPitch(unittest.TestCase):
    def tone(self, frequency, vibrato=0, second=.3):
        phase = 0
        values = []
        for index in range(1800):
            instantaneous = frequency * 2 ** (vibrato * math.sin(2 * math.pi * 5 * index / 11025) / 1200)
            phase += 2 * math.pi * instantaneous / 11025
            values.append(.03 * (math.sin(phase) + second * math.sin(2 * phase)))
        return values

    def test_all_exercise_pitches_and_octaves_blind(self):
        for midi in sorted(set(M.SCORES['flute'][1] + M.SCORES['violin'][1] + [55, 84])):
            frequency = 440 * 2 ** ((midi - 69) / 12)
            found = M.estimate_pitch(self.tone(frequency))
            self.assertGreater(found['clarity'], M.CLARITY)
            self.assertLess(abs(1200 * math.log2(found['frequency_hz'] / frequency)), 12)

    def test_dominant_second_harmonic_is_not_forced_to_expected_octave(self):
        frequency = 440
        found = M.estimate_pitch(self.tone(frequency, second=2.5))
        self.assertLess(abs(1200 * math.log2(found['frequency_hz'] / frequency)), 12)

    def test_weak_lower_fundamental_cannot_pass_as_its_second_harmonic(self):
        frequency = 261.625565
        found = M.estimate_pitch(self.tone(frequency, second=10))
        self.assertTrue(found['subharmonic_ambiguity'])
        self.assertGreater(found['subharmonic_amplitude_ratio'], .05)

    def test_parent_traversal_refused(self):
        with self.assertRaises(ValueError):
            M.plain('/tmp/synthetic-runner-temp/../outside')

    def test_vibrato_within_tolerance(self):
        found = M.estimate_pitch(self.tone(659.255, vibrato=35))
        self.assertGreater(found['clarity'], M.CLARITY)
        self.assertLess(abs(1200 * math.log2(found['frequency_hz'] / 659.255)), 45)

    def test_silence_and_nonfinite_refused(self):
        self.assertIsNone(M.estimate_pitch([0.] * 1800)['frequency_hz'])
        with self.assertRaises(ValueError):
            M.estimate_pitch([float('nan')] * 1800)

    def test_full_sequence_and_antiphase_stereo(self):
        expected = M.SCORES['flute'][1]
        values = []
        for midi in expected:
            frequency = 440 * 2 ** ((midi - 69) / 12)
            values.extend(.02 * math.sin(2 * math.pi * frequency * i / 44100) for i in range(22050))
        values.extend([0.] * (3 * 44100))
        result = M.analyze_channels(values, [-value for value in values], expected)
        self.assertEqual(result['status'], 'pitch-and-octave-match')
        self.assertEqual([row['observed_midi'] for row in result['notes']], expected)
        wrong = M.analyze_channels(values, values, [note + 12 for note in expected])
        self.assertEqual(wrong['status'], 'mismatch-or-inconclusive')
        self.assertTrue(all(row['octave_displacement_semitones'] == -12 for row in wrong['notes']))

    def test_strict_wav_size_padding_duplicates_and_nan(self):
        def riff(chunks):
            body = b'WAVE' + b''.join(tag + struct.pack('<I', len(payload)) + payload + (b'\0' if len(payload) & 1 else b'') for tag, payload in chunks)
            return b'RIFF' + struct.pack('<I', len(body)) + body
        fmt = struct.pack('<HHIIHH', 3, 2, 44100, 352800, 8, 32)
        payload = b'\0' * (7 * 44100 * 8)
        good = riff([(b'JUNK', b'x'), (b'fmt ', fmt), (b'data', payload)])
        self.assertEqual(len(M.wav_channels(good)[0]), 7 * 44100)
        for bad in (good[:-1], good + b'x', riff([(b'fmt ', fmt), (b'fmt ', fmt), (b'data', payload)]),
                    riff([(b'fmt ', fmt), (b'data', payload), (b'data', payload)]),
                    riff([(b'fmt ', fmt), (b'data', struct.pack('<f', float('nan')) + payload[4:])])):
            with self.assertRaises(ValueError):
                M.wav_channels(bad)

    def test_metadata_pins_and_real_data_not_synthetically_claimed(self):
        run = {'id': M.RUN, 'head_sha': M.HEAD, 'status': 'completed', 'conclusion': 'success'}
        artifact = {'id': M.ARTIFACT, 'name': 'cadence-vsco-sf2-qa-43231480145-1', 'size_in_bytes': M.ARTIFACT_BYTES,
                    'digest': M.DIGEST, 'expired': False, 'workflow_run': {'id': M.RUN, 'head_sha': M.HEAD}}
        self.assertEqual(M.check_metadata(run, artifact)['artifact_id'], M.ARTIFACT)
        for key, value in (('id', M.ARTIFACT + 1), ('digest', 'sha256:' + '0' * 64), ('expired', True)):
            with self.assertRaises(ValueError):
                M.check_metadata(run, {**artifact, key: value})


if __name__ == '__main__':
    unittest.main()
