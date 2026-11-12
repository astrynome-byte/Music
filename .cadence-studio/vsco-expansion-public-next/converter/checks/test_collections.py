# SPDX-License-Identifier: GPL-3.0-only
"""Pinned musical zones and real SoundFont container regression checks.

These checks do not claim sample rendering, GUI, hardware or Windows testing.
The separate FluidSynth probe records the actual Linux bank renders.
"""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("_cadence_vsco_collections_tests", HERE / "build_collections.py")
collections = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = collections
SPEC.loader.exec_module(collections)
core = collections.core


def wave_fixture():
    data = bytearray()
    for index in range(512):
        for channel in (0, 1):
            value = round(math.sin(index * 2 * math.pi / 64 + channel * .2) * (1 << 13))
            data += value.to_bytes(2, "little", signed=True)
    fmt = struct.pack("<HHIIHH", 1, 2, 44100, 176400, 4, 16)
    smpl = struct.pack("<9I", 0, 0, 0, 60, 0, 0, 0, 1, 0) + struct.pack("<6I", 0, 0, 64, 447, 0, 0)
    return core.chunk(b"RIFF", b"WAVE" + core.chunk(b"fmt ", fmt) + core.chunk(b"data", data) + core.chunk(b"smpl", smpl))


class VscoCollectionsChecks(unittest.TestCase):
    def test_audited_zone_ranges_and_native_gm_identities(self):
        manifest = collections.load_manifest()
        ids = ["cello-ensemble", "trumpet-vibrato", "contrabass-vibrato"]
        plans, _ = collections.validate_profiles(manifest, ids)
        self.assertEqual([(p["program"], len(r), p["midi_range"], rel) for p, r, _, rel in plans],
                         [(42, 27, [36, 77], .8), (56, 22, [52, 84], .5), (43, 26, [24, 60], .8)])
        for profile, regions, attack, _ in plans:
            self.assertEqual(attack, .001)
            for note in range(profile["midi_range"][0], profile["midi_range"][1] + 1):
                for velocity in range(128):
                    self.assertEqual(sum(r.low <= note <= r.high and r.velocity_low <= velocity <= r.velocity_high
                                         for r in regions), 1)

    def test_unimplemented_round_robin_and_changed_envelope_are_refused(self):
        raw = (HERE / "mappings/TrumpetSusVib.sfz").read_bytes()
        expected = {"seq_length": "1", "seq_position": "1", "group_label": "gr_1"}
        for changed in (raw.replace(b"seq_length=1", b"seq_length=2"),
                        raw.replace(b"ampeg_release=0.5", b"ampeg_release=0.6"),
                        raw + b"\nloop_mode=loop_continuous\n"):
            with self.subTest(changed=changed[-40:]), self.assertRaises(ValueError):
                core.parse_mapping(changed, expected_releases=(.5,), expected_group=expected)

    def test_group_label_does_not_silently_admit_an_unknown_group(self):
        raw = (HERE / "mappings/ContrabassSusVB.sfz").read_bytes()
        with self.assertRaises(ValueError):
            core.parse_mapping(raw.replace(b"group_label=gr_1", b"group_label=gr_2"),
                               expected_releases=(.8,), expected_group={"group_label": "gr_1"})
        # Legacy callers still refuse nonempty groups rather than gaining new
        # musical behaviour as a side effect of this expansion.
        with self.assertRaises(ValueError):
            core.parse_mapping(raw)

    def test_manifest_changes_and_duplicate_or_unknown_selection_are_refused(self):
        with tempfile.TemporaryDirectory(prefix="cadence-vsco-manifest-") as temp:
            changed = Path(temp) / "manifest.json"
            changed.write_bytes((HERE / "expansion-source-manifest.json").read_bytes() + b" ")
            with self.assertRaises(ValueError):
                collections.load_manifest(changed)
        for selected in ([], ["cello-ensemble", "cello-ensemble"], ["unreviewed-piano"]):
            with self.subTest(selected=selected), self.assertRaises(ValueError):
                collections.validate_profiles(collections.load_manifest(), selected)

    def test_existing_default_writer_matches_the_previous_converter_golden_bytes(self):
        # This hash was calculated with the previously published converter,
        # before the optional profile/preset-name parameters were introduced.
        with tempfile.TemporaryDirectory(prefix="cadence-vsco-legacy-") as temp:
            path = Path(temp) / "legacy.sf2"
            core.build_bank(path, [core.Region("s.wav", 60, 64, 60, 0, 127, 0)],
                            lambda _: (wave_fixture(), {}), title="Legacy default",
                            program=73, attack=.001, release=.7)
            self.assertEqual(path.stat().st_size, 3052)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                             "d1fb7f72c62233177f9e5d40a6a25878fe53b6a45d0ad2005cbb29c52556be3b")

    def test_new_preset_label_program_and_release_are_written_to_real_sf2_chunks(self):
        with tempfile.TemporaryDirectory(prefix="cadence-vsco-format-") as temp:
            path = Path(temp) / "trumpet.sf2"
            core.build_bank(path, [core.Region("s.wav", 52, 84, 60, 0, 127, 0)],
                            lambda _: (wave_fixture(), {}), title="Cadence-VSCO-Trumpet",
                            preset_name="Trompette", program=56, attack=.001, release=.5)
            chunks = core.sf2_chunks(path)
            data = path.read_bytes()
            start, _ = chunks[b"pdta", b"phdr"]
            title, program, bank = struct.unpack_from("<20sHH", data, start)
            self.assertEqual((title.rstrip(b"\0"), program, bank), (b"Trompette", 56, 0))
            start, size = chunks[b"pdta", b"igen"]
            signed_release = [amount - 65536 if amount >= 32768 else amount
                              for operator, amount in struct.iter_unpack("<HH", data[start:start + size])
                              if operator == 38]
            self.assertEqual(signed_release, [-1200, -1200])

    def test_local_wave_identity_checked_before_conversion(self):
        raw = wave_fixture()
        pin = {"path": "sample.wav", "bytes": len(raw),
               "git_blob_sha1": hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()}
        with tempfile.TemporaryDirectory(prefix="cadence-vsco-source-") as temp:
            root = Path(temp)
            path = root / "sample.wav"
            path.write_bytes(raw)
            fetch = collections.make_provider({"sample.wav": pin}, root)
            self.assertEqual(fetch("sample.wav")[0], raw)
            changed = bytearray(raw)
            changed[-1] ^= 1
            path.write_bytes(changed)
            with self.assertRaises(ValueError):
                fetch("sample.wav")


if __name__ == "__main__":
    unittest.main()
