# SPDX-License-Identifier: GPL-3.0-only
"""Data/real-archive checks only. These never call GitHub or execute Cadence."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import validate_sounds_publication as validator

SUPPORT = Path(__file__).parent
ROOT = Path(os.environ.get("CADENCE_SOUNDS_ASSET_ROOT", str(SUPPORT.parent / "dist")))
TEMPLATE = json.loads((SUPPORT / "target.json.template").read_text(encoding="utf-8"))

class SoundsReleaseChecks(unittest.TestCase):
    def changed_native(self, mutate, expected):
        with tempfile.TemporaryDirectory() as temporary:
            support=Path(temporary); (support/'evidence').mkdir()
            for name in ('assessment.json','native-report.console-capture.json','owned-job.console-capture.json'):
                (support/'evidence'/name).write_bytes((SUPPORT/'evidence'/name).read_bytes())
            native=json.loads((support/'evidence/native-report.console-capture.json').read_text())
            mutate(native)
            (support/'evidence/native-report.console-capture.json').write_text(json.dumps(native))
            with self.assertRaisesRegex(ValueError,expected):
                validator.actual_qualification(support)

    def test_missing_actual_fallback_control_is_refused(self):
        self.changed_native(lambda n:n['native_load_gain_and_fallback_controls'].update(missing_cello_PCM_matches_MSBasic=False),'gain/fallback')

    def test_auxiliary_send_default_is_refused(self):
        self.changed_native(lambda n:n['cases'][0]['requested_track']['out'].update(auxSends=[]),'disabled auxiliary')

    def test_real_post_release_failure_is_refused(self):
        self.changed_native(lambda n:n['cases'][1]['audio']['envelope_observations'].update(post_release_is_quiet=False),'envelope')

    def test_timeout_in_one_native_command_is_refused(self):
        self.changed_native(lambda n:n['commands'][0].update(timed_out=True),'completion')

    def target(self):
        target = copy.deepcopy(TEMPLATE)
        target["ready"] = True
        target["audit"] = {"approved": True, "reviewed_by": "SYNTHETIC DATA TEST, NO APPROVAL"}
        target["android"].update(audit_status="reviewed-no-android-release-or-tag-trigger", reviewed_by="SYNTHETIC DATA TEST, NO APPROVAL",
                                 tag_workflows=[{"path": ".github/workflows/data-only.yml", "blob_sha1": "0" * 40}])
        return target

    def test_false_template_cannot_approve_before_file_reads(self):
        with patch.object(validator.assets, "plain", side_effect=AssertionError("No input read allowed")):
            with self.assertRaisesRegex(ValueError, "ready=true"):
                validator.validate(TEMPLATE, ROOT, SUPPORT)

    def test_string_true_is_refused(self):
        target = self.target(); target["ready"] = "true"
        with self.assertRaisesRegex(ValueError, "boolean"):
            validator.validate(target, ROOT, SUPPORT)

    def test_missing_root_approval_is_refused(self):
        target = self.target(); target["audit"]["approved"] = False
        with self.assertRaisesRegex(ValueError, "review"):
            validator.validate(target, ROOT, SUPPORT)

    def test_unreviewed_workflows_are_refused(self):
        target = self.target(); target["android"]["tag_workflows"] = []
        with self.assertRaisesRegex(ValueError, "workflow"):
            validator.validate(target, ROOT, SUPPORT)

    def test_wrong_repository_is_refused(self):
        target = self.target(); target["repository"] = "someone/else"
        with self.assertRaises(ValueError): validator.validate(target, ROOT, SUPPORT)

    def test_installer_scope_is_refused(self):
        target = self.target(); target["source"]["application_included"] = True
        with self.assertRaisesRegex(ValueError, "Only CC0"):
            validator.validate(target, ROOT, SUPPORT)

    def test_mutable_alternate_release_target_is_refused(self):
        target = self.target(); target["release"]["target_commit"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "workflow HEAD"):
            validator.validate(target, ROOT, SUPPORT)

    def test_msi_asset_injection_is_refused(self):
        target = self.target(); target["assets"].append({"kind": "msi"})
        with self.assertRaisesRegex(ValueError, "eight"):
            validator.validate(target, ROOT, SUPPORT)

    def test_wrong_actual_archive_hash_is_refused(self):
        target = self.target(); target["assets"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "actual asset differs"):
            validator.validate(target, ROOT, SUPPORT)

    def test_raw_sf2_cannot_declare_an_unqualified_hash(self):
        target = self.target()
        next(x for x in target["assets"] if x["kind"] == "cello_sf2")["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "actual qualified bank"):
            validator.validate(target, ROOT, SUPPORT)

    def test_inspect_actual_archives_cannot_authorize_publication(self):
        result = validator.validate(TEMPLATE, ROOT, SUPPORT, inspect_only=True)
        self.assertFalse(result["allowed"])
        self.assertFalse(result["ready"])
        self.assertEqual(len(result["asset_receipts"]), 8)

    def test_actual_qualification_string_flag_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            support = Path(temporary); (support / "evidence").mkdir()
            proof = json.loads((SUPPORT / "evidence/assessment.json").read_text())
            proof["banks_unchanged"] = "true"
            (support / "evidence/assessment.json").write_text(json.dumps(proof))
            (support / "evidence/native-report.console-capture.json").write_bytes((SUPPORT / "evidence/native-report.console-capture.json").read_bytes())
            (support / "evidence/owned-job.console-capture.json").write_bytes((SUPPORT / "evidence/owned-job.console-capture.json").read_bytes())
            with self.assertRaisesRegex(ValueError, "sound proof"):
                validator.actual_qualification(support)

if __name__ == "__main__":
    unittest.main(verbosity=2)
