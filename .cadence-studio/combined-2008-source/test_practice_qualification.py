#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Parser/metadata regression tests only; fixtures are not native runtime proof."""
import tempfile
from pathlib import Path
import struct
import unittest
import qualify_practice as q


def midi(variant="ON"):
    lines = ["PASS 14 musical/lifecycle groups, 12764 assertions"] if variant == "ON" else []
    lines += ["PASS: " + name for name in ((q.EVENTS if variant == "ON" else []) + q.ROUTES[variant])]
    return "\n".join("1: " + line for line in lines)


def history():
    lines = ["PASS " + name if name not in q.SKIPPED else "SKIP " + name + ": " + q.SKIPPED[name] for name in q.HISTORY]
    lines.append("PASSED 13 meaningful production-store scenarios; SKIPPED 2; Qt 6.10.2")
    return "\n".join("1: " + line for line in lines)


class QualificationParsers(unittest.TestCase):
    def test_exact_actual_output_forms_are_accepted(self):
        self.assertEqual(q.midi_observation(midi(), "ON")["matcher_assertions"], 12764)
        self.assertEqual(q.midi_observation(midi("OFF"), "OFF")["route_groups"], 4)
        self.assertEqual(len(q.history_observation(history())["skipped_scenarios"]), 2)

    def test_matcher_count_or_duplicate_summary_is_rejected(self):
        for text in (midi().replace("12764", "12763"), midi() + "\n1: PASS 14 musical/lifecycle groups, 12764 assertions"):
            with self.assertRaises(ValueError): q.midi_observation(text, "ON")

    def test_missing_event_or_router_scenario_is_rejected(self):
        for name in (q.EVENTS[0], q.ROUTES["ON"][2]):
            with self.assertRaises(ValueError): q.midi_observation(midi().replace("1: PASS: " + name, ""), "ON")

    def test_duplicate_pass_cannot_replace_a_missing_scenario(self):
        with self.assertRaises(ValueError):
            q.midi_observation(midi().replace(q.EVENTS[0], q.EVENTS[1]), "ON")

    def test_on_route_cannot_claim_reference_mode(self):
        with self.assertRaises(ValueError):
            q.midi_observation(midi("OFF").replace(q.ROUTES["OFF"][2], q.ROUTES["ON"][2]), "OFF")

    def test_unexpected_skips_or_failures_are_rejected(self):
        for text in (history().replace("PASS " + q.HISTORY[0], "SKIP " + q.HISTORY[0]), history() + "\n1: FAIL extra"):
            with self.assertRaises(ValueError): q.history_observation(text)

    def test_unix_skips_cannot_be_reported_as_windows_passes(self):
        text = history()
        for name, reason in q.SKIPPED.items(): text = text.replace("SKIP " + name + ": " + reason, "PASS " + name)
        text = text.replace("PASSED 13", "PASSED 15").replace("SKIPPED 2", "SKIPPED 0")
        with self.assertRaises(ValueError): q.history_observation(text)

    def test_qt_version_drift_is_rejected(self):
        with self.assertRaises(ValueError): q.history_observation(history().replace("6.10.2", "6.8.2"))

    def test_ctest_requires_execution_and_every_exact_target(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "results.xml"
            for content in ('<testsuite><testcase name="a" status="run"/></testsuite>',):
                path.write_text(content);self.assertEqual(q.ctest_xml(path, ["a"])["completed_targets"], ["a"])
            for content in ('<testsuite><testcase name="a"><failure/></testcase></testsuite>',
                            '<testsuite><testcase name="a" status="notrun"/></testsuite>',
                            '<testsuite><testcase name="a"><skipped/></testcase></testsuite>',
                            '<testsuite/>'):
                path.write_text(content)
                with self.assertRaises(ValueError): q.ctest_xml(path, ["a"])

    def test_reference_header_changes_only_the_reviewed_directive(self):
        for ending in (b"\n", b"\r\n"):
            raw=ending.join([b"/* real feature profile */", b"#define CADENCE_BUILD 1", b"#define MUSE_THREADS_SUPPORT 1", b""])
            self.assertEqual(q.reference_framework_header(raw), raw.replace(b"#define CADENCE_BUILD 1", b"/* #undef CADENCE_BUILD */"))
        for raw in (b"", b"#define CADENCE_BUILD 0\n", b"#define CADENCE_BUILD 1\n#define CADENCE_BUILD 1\n", b"#define CADENCE_BUILD 1 // unknown\n"):
            with self.assertRaises(ValueError):q.reference_framework_header(raw)

    def test_pe_header_check_rejects_wrong_machine_and_truncated_data(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "metadata.exe"
            data = bytearray(80);data[:2] = b"MZ";struct.pack_into("<I", data, 0x3c, 64);data[64:68] = b"PE\0\0";struct.pack_into("<H", data, 68, 0x8664)
            path.write_bytes(data);self.assertEqual(q.pe_x64(path)["pe_machine"], "0x8664")
            struct.pack_into("<H", data, 68, 0x14c);path.write_bytes(data)
            with self.assertRaises(ValueError): q.pe_x64(path)
            path.write_bytes(b"MZ")
            with self.assertRaises(ValueError): q.pe_x64(path)


if __name__ == "__main__": unittest.main()
