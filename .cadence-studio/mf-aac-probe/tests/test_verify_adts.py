# SPDX-License-Identifier: GPL-3.0-only
"""Check the ADTS validator; synthetic headers do not test an AAC codec."""
from array import array
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import wave

from verify_adts import inspect_decoded_pcm, parse_adts, verify_file


def synthetic_adts_frame(payload=b"\x01\x02\x03", rate_index=4, channels=2, crc=False):
    """Structurally plausible ADTS; its payload deliberately is not AAC audio."""
    size = 7 + (2 if crc else 0) + len(payload)
    header = bytes((0xFF, 0xF0 if crc else 0xF1,
                    (1 << 6) | (rate_index << 2) | (channels >> 2),
                    ((channels & 3) << 6) | (size >> 11),
                    (size >> 3) & 0xFF, ((size & 7) << 5) | 0x1F, 0xFC))
    return header + (b"\0\0" if crc else b"") + payload


class AdtsStructureTests(unittest.TestCase):
    def stream(self, count=45, **kwargs):
        return synthetic_adts_frame(**kwargs) * count

    def test_accepts_lc_stereo_and_counts_duration(self):
        report = parse_adts(self.stream(), 44100, 44100)
        self.assertEqual(report["frame_count"], 45)
        self.assertEqual(report["encoded_pcm_frames"], 45 * 1024)
        self.assertAlmostEqual(report["adts_duration_seconds"], 45 * 1024 / 44100)
        self.assertEqual(report["payload_validation"], "requires_decode")

    def test_crc_header_is_counted_but_not_claimed_verified(self):
        report = parse_adts(self.stream(crc=True), 44100, 44100)
        self.assertEqual(report["crc_present_frames"], 45)
        self.assertFalse(report["crc_verified"])

    def test_accepts_48000(self):
        self.assertEqual(parse_adts(self.stream(count=48, rate_index=3), 48000, 48000)["sample_rate"], 48000)

    def test_rejects_truncated_frame_and_trailing_bytes(self):
        for raw in (self.stream()[:-1], self.stream() + b"x"):
            with self.subTest(length=len(raw)), self.assertRaises(ValueError):
                parse_adts(raw, 44100, 44100)

    def test_rejects_sync_loss_inside_stream(self):
        raw = bytearray(self.stream())
        raw[len(synthetic_adts_frame()) * 3] = 0
        with self.assertRaisesRegex(ValueError, "sync"):
            parse_adts(bytes(raw), 44100, 44100)

    def test_rejects_layer_profile_rate_channel_and_raw_blocks(self):
        cases = ((1, 0xF3, "layer"), (2, 0x10, "profile"),
                 (2, 0x4C, "sample rate"), (2, 0x7C, "sample-rate index"),
                 (3, 0x40, "stereo"), (6, 0xFD, "raw data blocks"))
        for byte_index, value, message in cases:
            raw = bytearray(self.stream())
            raw[byte_index] = value
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                parse_adts(bytes(raw), 44100, 44100)

    def test_rejects_impossible_length_or_empty_payload(self):
        for size in (0, 6, 7, 8191):
            raw = bytearray(self.stream())
            raw[3] = (raw[3] & 0xFC) | (size >> 11)
            raw[4] = (size >> 3) & 255
            raw[5] = (raw[5] & 31) | ((size & 7) << 5)
            with self.subTest(size=size), self.assertRaises(ValueError):
                parse_adts(bytes(raw), 44100, 44100)

    def test_rejects_missing_frames_and_excess_padding(self):
        for count in (0, 43, 49):
            with self.subTest(count=count), self.assertRaises(ValueError):
                parse_adts(self.stream(count=count), 44100, 44100)

    def test_zero_pcm_expectation_is_not_accepted(self):
        with self.assertRaises(ValueError):
            parse_adts(self.stream(), 44100, 0)

    def test_missing_decoder_is_explicit_structure_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.aac"
            path.write_bytes(self.stream())
            with mock.patch("verify_adts.shutil.which", return_value=None):
                report = verify_file(path, 44100, 44100, True)
            self.assertTrue(report["passed"])
            self.assertEqual(report["status"], "passed_structure_only")
            self.assertEqual(report["decode"]["status"], "skipped")
            self.assertEqual(len(report["sha256"]), 64)

    def test_cli_failure_writes_report_and_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.aac"
            path.write_bytes(self.stream()[:-1])
            report = Path(directory) / "report.json"
            run = subprocess.run([sys.executable, str(Path(__file__).with_name("verify_adts.py")),
                                  "--input", str(path), "--sample-rate", "44100", "--pcm-frames", "44100",
                                  "--report", str(report)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 1, run.stderr)
            self.assertFalse(json.loads(report.read_text())["passed"])

    def test_cli_report_cannot_overwrite_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "keep.aac"
            original = self.stream()
            path.write_bytes(original)
            run = subprocess.run([sys.executable, str(Path(__file__).with_name("verify_adts.py")),
                                  "--input", str(path), "--sample-rate", "44100", "--pcm-frames", "44100",
                                  "--report", str(path)], capture_output=True, text=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertEqual(path.read_bytes(), original)


class DecodedSignalTests(unittest.TestCase):
    def pcm(self, left, right, frames=48000):
        samples = array("f")
        for frame in range(frames):
            samples.extend((left(frame), right(frame)))
        if sys.byteorder != "little":
            samples.byteswap()
        return samples.tobytes()

    def test_rejects_silence_nonfinite_and_high_level(self):
        for value in (0.0, float("nan"), 1.0):
            raw = self.pcm(lambda i: value, lambda i: value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                inspect_decoded_pcm(raw, 48000, 48000, 48000)

    def test_rejects_wrong_channel_tones(self):
        raw = self.pcm(lambda i: .2 * math.sin(2 * math.pi * 660 * i / 48000),
                       lambda i: .2 * math.sin(2 * math.pi * 440 * i / 48000))
        with self.assertRaisesRegex(ValueError, "expected"):
            inspect_decoded_pcm(raw, 48000, 48000, 48000)


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg unavailable; actual AAC decode checker not exercised")
class ActualAacValidatorTests(unittest.TestCase):
    def encoded_fixture(self, directory, silence=False, rate=48000, pcm_frames=None):
        pcm_frames = rate if pcm_frames is None else pcm_frames
        path = Path(directory) / "input.wav"
        samples = array("h")
        for frame in range(pcm_frames):
            for frequency in (440, 660):
                samples.append(0 if silence else round(.2 * 32767 * math.sin(2 * math.pi * frequency * frame / rate)))
        if sys.byteorder != "little":
            samples.byteswap()
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(2)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            wav.writeframes(samples.tobytes())
        encoded = Path(directory) / "ffmpeg-fixture.aac"
        run = subprocess.run([shutil.which("ffmpeg"), "-nostdin", "-v", "error", "-i", str(path),
                              "-c:a", "aac", "-profile:a", "aac_low", "-b:a", "128k", "-f", "adts", str(encoded)],
                             capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        return encoded

    def test_real_aac_decodes_to_expected_tones(self):
        # FFmpeg supplies a real fixture solely to test this validator. This
        # does not exercise the Windows Media Foundation encoder prototype.
        for rate, pcm_frames in ((44100, 55125), (48000, 60000)):
            with self.subTest(rate=rate), tempfile.TemporaryDirectory() as directory:
                encoded = self.encoded_fixture(directory, rate=rate, pcm_frames=pcm_frames)
                report = verify_file(encoded, rate, pcm_frames, True)
                self.assertTrue(report["passed"], report["errors"])
                self.assertEqual(report["status"], "passed_with_decode")
                self.assertEqual(report["decode"]["status"], "passed")

    def test_structurally_valid_silent_aac_fails_signal_check(self):
        with tempfile.TemporaryDirectory() as directory:
            report = verify_file(self.encoded_fixture(directory, silence=True), 48000, 48000, True)
            self.assertTrue(report["structure"]["passed"])
            self.assertFalse(report["passed"])
            self.assertIn("silent", report["errors"][0])


if __name__ == "__main__":
    unittest.main()
