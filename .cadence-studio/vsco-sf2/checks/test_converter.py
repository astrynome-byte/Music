# SPDX-License-Identifier: GPL-3.0-only
"""Synthetic format/guard fixtures; real bank render evidence is separate."""
import importlib.util
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("vsco_sf2_converter_checks", HERE / "build_vsco_sf2.py")
builder = importlib.util.module_from_spec(SPEC);sys.modules[SPEC.name] = builder;SPEC.loader.exec_module(builder)


def synthetic_wave(bits=16, loop=True):
    frames = 512
    data = bytearray()
    for index in range(frames):
        for channel in (0, 1):
            value = round(math.sin(index * 2 * math.pi / 64 + channel * 0.2) * (1 << (bits - 3)))
            data += value.to_bytes(bits // 8, "little", signed=True)
    fmt = struct.pack("<HHIIHH", 1, 2, 44100, 44100 * 2 * bits // 8, 2 * bits // 8, bits)
    payload = b"WAVE" + builder.chunk(b"fmt ", fmt) + builder.chunk(b"data", data)
    if loop:
        smpl = struct.pack("<9I", 0, 0, 0, 60, 0, 0, 0, 1, 0) + struct.pack("<6I", 0, 0, 64, 447, 0, 0)
        payload += builder.chunk(b"smpl", smpl)
    return builder.chunk(b"RIFF", payload)


class ConverterChecks(unittest.TestCase):
    def test_exact_two_mapping_coverage_and_tuning(self):
        manifest = json.loads((HERE / "asset-source-manifest.json").read_text())
        pins = {row["path"]: row for row in manifest["files"]}
        for name, count in (("FluteSusVib.sfz", 13), ("SViolinVib.sfz", 30)):
            raw = (HERE / "mappings" / name).read_bytes();builder.verify_source(raw, pins[name])
            regions, attack, release = builder.parse_mapping(raw)
            self.assertEqual(len(regions), count);self.assertEqual(attack, 0.001)
            self.assertIn(release, (0.7, 0.8))
            if name.startswith("SViolin"):
                tuned = [r for r in regions if r.fine_tune]
                self.assertEqual(len(tuned), 1);self.assertEqual(tuned[0].fine_tune, -20)

    def test_unknown_opcode_gap_and_overlap_refused(self):
        original = (HERE / "mappings/FluteSusVib.sfz").read_bytes()
        for changed in (original + b"\nunsupported_opcode=1\n", original.replace(b"hikey=70", b"hikey=69"),
                        original.replace(b"hikey=70", b"hikey=71")):
            with self.subTest(changed=changed[-50:]), self.assertRaises(ValueError): builder.parse_mapping(changed)

    def test_pcm_and_loop_exclusive_end(self):
        for bits in (16, 24, 32):
            decoded = builder.decode_wav(synthetic_wave(bits))
            self.assertEqual(decoded["channels"], 2);self.assertEqual(decoded["source_bits"], bits)
            self.assertEqual(decoded["frames"], 512);self.assertEqual(decoded["loop"], (64, 448))
            self.assertEqual(len(decoded["pcm16"][0]), 1024)
        self.assertIsNone(builder.decode_wav(synthetic_wave(loop=False))["loop"])
        with self.assertRaises(ValueError): builder.decode_wav(synthetic_wave()[:-1])
        wrong = bytearray(synthetic_wave());smpl = wrong.index(b"smpl")
        struct.pack_into("<I", wrong, smpl + 8 + 36 + 4, 1)  # Alternating/backward loops unsupported.
        with self.assertRaises(ValueError): builder.decode_wav(wrong)

    def test_new_bank_stereo_links_guards_and_even_info(self):
        with tempfile.TemporaryDirectory(prefix="sf2-synthetic-") as folder:
            path = Path(folder) / "test.sf2"
            region = builder.Region("SYNTHETIC-NOT-VSCO.wav", 60, 64, 60, 0, 127, 0)
            receipt = builder.build_bank(path, [region], lambda _: (synthetic_wave(), {"fixture": "synthetic"}),
                                         title="Synthetic fixture", program=73, attack=0.001, release=0.7)
            self.assertEqual(receipt["zones"], 2);self.assertEqual(receipt["loops_enabled"], 1)
            chunks = builder.sf2_chunks(path)
            for (kind, tag), (_, length) in chunks.items():
                if kind == b"INFO": self.assertEqual(length % 2, 0, tag)
            start, size = chunks[b"pdta", b"shdr"]
            raw = path.read_bytes()[start:start + size]
            left = struct.unpack_from("<20sIIIIIBbHH", raw, 0)
            right = struct.unpack_from("<20sIIIIIBbHH", raw, 46)
            self.assertEqual((left[-2], left[-1], right[-2], right[-1]), (1, 4, 0, 2))
            self.assertEqual((left[3] - left[1], left[4] - left[1]), (64, 448))
            self.assertEqual(right[1] - left[2], 46)
            quiet = path.with_name("quiet.sf2");self.assertEqual(builder.attenuate_bank(path, quiet), 2)
            igen_start, igen_size = builder.sf2_chunks(quiet)[b"pdta", b"igen"]
            data = quiet.read_bytes()[igen_start:igen_start + igen_size]
            amounts = [amount for operator, amount in struct.iter_unpack("<HH", data) if operator == 48]
            self.assertEqual(amounts, [450, 450])  # Explicit retained FluidSynth EMU profile, not generic SF2 dB.
            with self.assertRaises(ValueError): builder.attenuate_bank(path, quiet)


if __name__ == "__main__": unittest.main()
