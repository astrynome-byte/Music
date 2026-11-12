# SPDX-License-Identifier: GPL-3.0-only
"""Synthetic data only; does not establish the retained WAV spectrum."""
import importlib.util
import math
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location('overlap_reader', Path(__file__).with_name('diagnose_pitch_overlap.py'))
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class SyntheticOverlap(unittest.TestCase):
    def wave(self, lower_amplitude=0):
        frequency = 261.6255653005986
        return [lower_amplitude * math.sin(2 * math.pi * frequency * i / 11025)
                + .02 * math.sin(2 * math.pi * frequency * 2 * i / 11025)
                + .01 * math.sin(2 * math.pi * frequency * 3 * i / 11025) for i in range(1749)]

    def test_virtual_period_without_low_spectral_component(self):
        result = M.spectral_window(self.wave(), 261.6255653005986)
        self.assertLess(result['lower_band_relative_amplitude'], .005)
        self.assertAlmostEqual(result['bands'][1]['peak_amplitude'], .02, delta=.0001)
        self.assertAlmostEqual(result['bands'][2]['peak_amplitude'], .01, delta=.0001)

    def test_physical_lower_component_is_visible(self):
        result = M.spectral_window(self.wave(.003), 261.6255653005986)
        self.assertAlmostEqual(result['lower_band_relative_amplitude'], .15, delta=.002)

    def test_Hann_normalization_and_published_helper_pin(self):
        self.assertAlmostEqual(M.goertzel_amplitude([.25 * math.sin(2 * math.pi * 440 * i / 11025)
                                                   for i in range(1749)], 440), .25, delta=.001)
        self.assertEqual(M.pinned_helper().RUN, 43231480145)
        original = M.HELPER_SHA
        try:
            M.HELPER_SHA = '0' * 64
            with self.assertRaises(ValueError):
                M.pinned_helper()
        finally:
            M.HELPER_SHA = original


if __name__ == '__main__':
    unittest.main()
