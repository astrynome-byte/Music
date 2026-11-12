#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Local QA harness checks: fresh logs, stale evidence rejection and real status.

These tests never execute Cadence or imply Windows validation. Subprocess results
are deliberately synthetic to exercise the diagnostic gate, not audio encoding.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


def load_video():
    path = Path(__file__).with_name("Test-VideoUnavailable.py")
    spec = importlib.util.spec_from_file_location("next_video_gate", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FreshDiagnosticEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.video = load_video()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.logs = self.root / "logs"
        self.logs.mkdir()
        self.output = self.root / "output"
        self.output.mkdir()
        binary_directory = self.root / "stage" / "bin"
        binary_directory.mkdir(parents=True)
        self.executable = binary_directory / "CadenceStudio4.exe"
        self.executable.write_bytes(b"synthetic test executable; never executed")
        source_directory = self.root / "source"
        source_directory.mkdir()
        self.score = source_directory / "source.musicxml"
        self.score.write_text("<score-partwise/>", encoding="utf-8")

    def qualify(self, exit_code=1331, create_log=True, video_bytes=b""):
        def native(command, **kwargs):
            if create_log:
                (self.logs / "new.log").write_bytes(self.video.MARKER + b"\n")
            if video_bytes:
                Path(command[command.index("-o") + 1]).write_bytes(video_bytes)
            return subprocess.CompletedProcess(command, exit_code, b"", b"")
        with patch.object(self.video.subprocess, "run", side_effect=native):
            return self.video.qualify(self.executable, self.score, self.output, [self.logs])

    def test_new_runtime_log_is_valid_evidence_without_stdout(self):
        result = self.qualify()
        self.assertTrue(result["passed"])
        self.assertTrue(result["guard_marker_in_new_runtime_log"])
        self.assertFalse(result["guard_marker_in_standard_streams"])
        retained = Path(result["runtime_logs"][0]["retained_path"])
        self.assertEqual(retained.read_bytes(), self.video.MARKER + b"\n")
        self.assertEqual(self.score.read_text(), "<score-partwise/>")

    def test_preexisting_stale_log_cannot_make_failure_pass(self):
        (self.logs / "old.log").write_bytes(self.video.MARKER)
        result = self.qualify(create_log=False)
        self.assertFalse(result["passed"])
        self.assertEqual(result["runtime_logs"], [])

    def test_old_marker_followed_by_unrelated_append_cannot_pass(self):
        old = self.logs / "old.log"
        old.write_bytes(self.video.MARKER + b"\n")
        before = self.video.snapshot([self.logs])
        old.write_bytes(old.read_bytes() + b"unrelated new diagnostic\n")
        records, marker = self.video.capture_new_logs([self.logs], before, self.output)
        self.assertFalse(marker)
        self.assertEqual(len(records), 1)
        self.assertFalse(records[0]["guard_marker_seen"])
        self.assertEqual(records[0]["evidence_scope"], "appended_bytes")
        self.assertEqual(records[0]["evidence_bytes"], len(b"unrelated new diagnostic\n"))

    def test_new_marker_appended_to_existing_log_is_valid_evidence(self):
        old = self.logs / "old.log"
        old.write_bytes(b"unrelated old diagnostic\n")
        before = self.video.snapshot([self.logs])
        old.write_bytes(old.read_bytes() + self.video.MARKER + b"\n")
        records, marker = self.video.capture_new_logs([self.logs], before, self.output)
        self.assertTrue(marker)
        self.assertTrue(records[0]["guard_marker_seen"])
        self.assertEqual(records[0]["evidence_scope"], "appended_bytes")

    def test_wrong_native_status_with_valid_diagnostic_still_fails(self):
        result = self.qualify(exit_code=1399)
        self.assertFalse(result["passed"])
        self.assertTrue(result["guard_marker_in_new_runtime_log"])

    def test_partial_video_with_valid_diagnostic_still_fails(self):
        result = self.qualify(video_bytes=b"partial MP4")
        self.assertFalse(result["passed"])
        self.assertEqual(result["output_bytes"], len(b"partial MP4"))

    def test_oversized_new_log_is_rejected_instead_of_read(self):
        before = self.video.snapshot([self.logs])
        (self.logs / "new.log").write_bytes(self.video.MARKER + b"a" * self.video.MAX_RUNTIME_LOG)
        with self.assertRaisesRegex(ValueError, "bounded capture"):
            self.video.capture_new_logs([self.logs], before, self.output)

    def test_executable_hash_mismatch_stops_before_process_launch(self):
        args = ["probe", "--executable", str(self.executable), "--score", str(self.score),
                "--expected-executable-sha256", "0" * 64,
                "--output", str(self.root / "mismatch")]
        # Only the platform gate is synthetic. No application invocation is allowed.
        with patch.object(self.video.sys, "argv", args), patch.object(self.video.os, "name", "nt"), \
                patch.object(self.video.subprocess, "run") as native:
            # pathlib uses os.name at Path construction; retain the actual host Path.
            with patch.object(self.video, "Path", type(self.root)):
                self.assertEqual(self.video.main(), 1)
        native.assert_not_called()
        report = json.loads((self.root / "mismatch/video-unavailable-report.json").read_text())
        self.assertFalse(report["passed"])
        self.assertTrue(any("differs" in item for item in report["errors"]))


if __name__ == "__main__":
    unittest.main()
