# SPDX-License-Identifier: GPL-3.0-only
"""Bounded data-only preparation of an experimental 2008 delivery; no MSI/app execution."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tarfile
import zipfile

# This inert selection must be completed and reviewed in the recipe commit,
# before a later activation commit adds only target.json. Action run_number
# and application build_number are independent identities.
EXPECTED = json.loads(Path(__file__).with_name("expected-inputs.json").read_text(encoding="utf-8"))
RUN = EXPECTED["producer"]["run_id"]
DRIVER = EXPECTED["producer"]["driver_commit"]
JOB = EXPECTED["producer"]["job_id"]
RUN_NUMBER = EXPECTED["producer"]["run_number"]
RUN_ATTEMPT = EXPECTED["producer"]["run_attempt"]
SOURCE = EXPECTED["source"]["original_commit"]
TREE = EXPECTED["source"]["tree"]
SOURCE_JSON_SHA = EXPECTED["source"]["source_json_sha256"]
PATCH_SHA = EXPECTED["source"]["patch_sha256"]
QTCORE_SHA = "b98eea394a95563879b614dbd4432ce074b0fceeb154c3bae252f4e7a9376a40"
PREFIX = "CadenceStudio-4.7.6-cadence.2008-x86_64"
ROLES = ("msi", "source_archive", "build_recipe", "component_sources", "notices", "guide", "checksums")
BASE = "CadenceStudio-4.7.6-cadence.2008"
ASSET_NAMES = dict(zip(ROLES, (BASE + "-x86_64.msi", BASE + "-source.tar.gz", BASE + "-build-recipe.zip", BASE + "-component-sources.zip", BASE + "-notices.zip", "LIRE-MOI-" + BASE + "-FR.txt", "SHA256SUMS.txt")))
ARTIFACT_ROLES = ("stage", "original_logs", "qa_logs", "delivery", "msi_logs")
REPORTS = ("bootstrap", "build", "stage_manifest", "release_manifest", "cli", "msi", "notices", "components", "icu_policy", "icu_exports", "native_additions", "practice", "audio_transcription", "omr_runner", "authorized_wav_https", "macro_profile", "unity_syntax", "retained_qualification", "retained_packaging", "retained_installer_wrapper")
REPORT_ARTIFACT_ROLES = {'bootstrap': 'original_logs',
 'build': 'stage',
 'stage_manifest': 'stage',
 'release_manifest': 'msi_logs',
 'cli': 'qa_logs',
 'msi': 'msi_logs',
 'notices': 'qa_logs',
 'components': 'stage',
 'icu_policy': 'stage',
 'icu_exports': 'stage',
 'native_additions': 'original_logs',
 'practice': 'qa_logs',
 'audio_transcription': 'qa_logs',
 'omr_runner': 'original_logs',
 'authorized_wav_https': 'original_logs',
 'macro_profile': 'original_logs',
 'unity_syntax': 'original_logs',
 'retained_qualification': 'qa_logs',
 'retained_packaging': 'msi_logs',
 'retained_installer_wrapper': 'msi_logs'}
SHA = re.compile(r"[a-f0-9]{64}")
GIT = re.compile(r"[a-f0-9]{40}")
MAX = 2_147_483_648

def require(ok, message):
    if not ok: raise ValueError(message)

def digest(path):
    with Path(path).open("rb") as stream: return hashlib.file_digest(stream, "sha256").hexdigest()

def relative(name):
    require(isinstance(name, str) and 0 < len(name) <= 2048 and not name.startswith("/")
            and not re.search(r"[\\:\x00-\x1f]", name)
            and all(part not in ("", ".", "..") for part in name.split("/")), "Unsafe relative member")
    return name

def plain(path):
    for part in (path, *path.parents):
        require(not part.is_symlink() and not getattr(part, "is_junction", lambda: False)(), "Linked path refused")

def receipt(root, entry, maximum=MAX):
    require(isinstance(entry, dict) and isinstance(entry.get("sha256"), str) and SHA.fullmatch(entry["sha256"])
            and type(entry.get("bytes")) is int and 0 < entry["bytes"] <= maximum, "Exact byte/SHA receipt required")
    path = root / relative(entry.get("member_path")); plain(path)
    require(path.is_file() and path.resolve().is_relative_to(root.resolve()) and path.stat().st_size == entry["bytes"]
            and digest(path) == entry["sha256"], "Missing or changed receipt member: " + entry["member_path"])
    return path

def producer_context(role):
    if role in ("stage", "original_logs"):
        return EXPECTED["stage_producer"]
    if role == "qa_logs":
        return EXPECTED["qualification_producer"]
    require(role in ("delivery", "msi_logs"), "Unknown retained artifact role")
    return EXPECTED["producer"]

def assert_selection():
    require(EXPECTED.get("schema_version") == 1 and EXPECTED.get("build_number") == 2008
            and EXPECTED.get("product_version") == "4.7.6.2008", "Reviewed product identity required")
    for role in ARTIFACT_ROLES:
        origin = producer_context(role)
        require(all(type(origin.get(k)) is int and origin[k] > 0 for k in ("run_id", "job_id", "run_number", "run_attempt"))
                and isinstance(origin.get("driver_commit"), str) and GIT.fullmatch(origin["driver_commit"]),
                "Retained producer selection is incomplete; actual successful MSI producer is required")
    require(all(isinstance(v, str) and GIT.fullmatch(v) for v in (SOURCE, TREE, EXPECTED["source"].get("ci_commit")))
            and all(isinstance(v, str) and SHA.fullmatch(v) for v in (SOURCE_JSON_SHA, PATCH_SHA, EXPECTED.get("executable_sha256"))),
            "Exact unchanged source/CI/EXE selection required")

def expected_artifact_names():
    assert_selection()
    suffix = lambda role: str(producer_context(role)["run_number"]) + "-" + str(producer_context(role)["run_attempt"])
    return {"stage": "cadence-combined-system-aac-stage-experimental-" + suffix("stage"),
            "original_logs": "cadence-combined-system-aac-logs-" + suffix("original_logs"),
            "qa_logs": "cadence-retained2008-resume-logs-" + suffix("qa_logs"),
            "delivery": "cadence-retained2008-msi-delivery-" + suffix("delivery"),
            "msi_logs": "cadence-retained2008-msi-logs-" + suffix("msi_logs")}

def validate_target(target, approval=True):
    assert_selection()
    require(type(target.get("schema_version")) is int and target["schema_version"] == 1, "Unsupported target schema")
    require(target.get("repository") == "astrynome-byte/Music" and target.get("version") == "4.7.6-cadence.2008"
            and type(target.get("build_number")) is int and target["build_number"] == 2008, "Only the frozen experimental2008 delivery is supported")
    require(type(target.get("ready")) is bool and (target["ready"] or not approval), "ready must be the reviewed boolean true")
    producer = target.get("producer", {})
    require(producer.get("run_id") == RUN and type(producer.get("run_id")) is int and producer.get("driver_commit") == DRIVER
            and all(type(producer.get(k)) is int for k in ("job_id", "run_number", "run_attempt"))
            and producer.get("job_id") == JOB and producer.get("run_number") == RUN_NUMBER
            and producer.get("run_attempt") == RUN_ATTEMPT, "Original producer changed")
    for key in ("stage_producer", "qualification_producer"):
        actual, expected = target.get(key, {}), EXPECTED[key]
        require(all(actual.get(k) == expected.get(k) and type(actual.get(k)) is type(expected.get(k))
                    for k in ("run_id", "job_id", "driver_commit", "run_number", "run_attempt")), "Retained source/QA producer differs")
    require(target["stage_producer"].get("conclusion") == "failure" and target["stage_producer"].get("passed_steps") == list(range(25,31))
            and target["stage_producer"].get("failed_step") == 31, "Original build remains failure31 after stages25-30")
    source = target.get("source", {})
    require(source.get("original_commit") == SOURCE and source.get("tree") == TREE and source.get("source_json_sha256") == SOURCE_JSON_SHA
            and source.get("patch_sha256") == PATCH_SHA and source.get("ci_commit") == EXPECTED["source"]["ci_commit"], "Actual frozen source/CI tree required")
    require(all(isinstance(target.get(k), str) and SHA.fullmatch(target[k]) for k in ("executable_sha256", "msi_sha256")), "Actual EXE/MSI hashes required; template deliberately refused")
    require(target["executable_sha256"] == EXPECTED["executable_sha256"], "Retained executable changed")
    limitations = target.get("limitations", {})
    require(limitations.get("tested_platform") == "Windows Server 2022 (GitHub Actions)"
            and all(limitations.get(k) is False for k in ("windows10_client_tested", "windows11_client_tested", "human_listening_completed", "paid_equivalence_complete", "final_gift", "physical_audio_midi_hardware_tested", "signed_installer")), "Experimental platform and incomplete-feature limits must remain explicit")
    artifacts = target.get("artifacts")
    require(isinstance(artifacts, list) and len(artifacts) == len(ARTIFACT_ROLES) and all(isinstance(a, dict) for a in artifacts)
            and {a.get("role") for a in artifacts} == set(ARTIFACT_ROLES), "Five exact retained artifact roles required")
    require(len({a.get("id") for a in artifacts}) == len(ARTIFACT_ROLES), "Duplicate artifact id")
    for row in artifacts:
        require(type(row.get("id")) is int and row["id"] > 0 and row.get("run_id") == producer_context(row["role"])["run_id"]
                and isinstance(row.get("name"), str) and row["name"] in expected_artifact_names().values()
                and isinstance(row.get("digest"), str) and re.fullmatch(r"sha256:[a-f0-9]{64}", row["digest"])
                and type(row.get("bytes")) is int and 0 < row["bytes"] <= MAX and isinstance(row.get("expires_at"), str)
                and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", row["expires_at"]), "Actual original artifact identity/digest/size/expiry required")
        if row["role"] in EXPECTED["original_artifacts"]:
            original = EXPECTED["original_artifacts"][row["role"]]
            require(row["id"] == original["id"] and row["digest"] == original["digest"] and row["bytes"] == original["size_in_bytes"], "Known original stage/log artifact changed")
        expected_name = expected_artifact_names()[row["role"]]
        require(row["name"] == expected_name, "Artifact role/name differs")
    require(isinstance(target.get("reports"), dict) and set(target["reports"]) == set(REPORTS), "Exact original report receipts required")
    for kind,row in target["reports"].items():
        require(row.get("artifact_role") == REPORT_ARTIFACT_ROLES[kind], "Report must belong to its exact pinned retained producer")
        relative(row.get("member_path"))
        require(isinstance(row.get("sha256"), str) and SHA.fullmatch(row["sha256"]) and type(row.get("bytes")) is int and 0 < row["bytes"] <= 4_000_000, "Actual report byte receipts required")
    if approval:
        review = target.get("review", {})
        require(review.get("approved") is True and isinstance(review.get("reviewed_by"), str) and review["reviewed_by"].strip()
                and isinstance(review.get("reviewed_utc"), str) and review["reviewed_utc"], "Root review of actual bytes/notices remains required")
        release = target.get("release", {})
        require(release.get("prerelease") is True and release.get("target_commit_mode") == "workflow_head" and "target_commit" not in release
                and isinstance(release.get("tag"), str) and re.fullmatch(r"cadence-studio/v?4\.7\.6-cadence\.2008-experimental\.[1-9][0-9]*", release["tag"])
                and isinstance(release.get("title"), str) and len(release["title"]) <= 140 and re.search(r"exp[eé]rimental", release["title"], re.I), "New explicitly experimental prerelease at the workflow HEAD required")
        require(not re.search(r"\b(?:finale?|cadeau|compl[eè]te?|complete)\b", release["title"], re.I), "Final/gift/complete claims are outside this experimental delivery")
        rows = target.get("assets")
        require(isinstance(rows, list) and len(rows) == 7 and {a.get("kind") for a in rows} == set(ROLES)
                and len({a.get("name") for a in rows}) == 7, "Exactly seven distinct approved assets required")
        for row in rows:
            require(isinstance(row.get("name"), str) and row["name"] == ASSET_NAMES[row["kind"]] and row.get("member_path") == row["name"] and isinstance(row.get("sha256"), str) and SHA.fullmatch(row["sha256"])
                    and type(row.get("bytes")) is int and 0 < row["bytes"] <= MAX, "Immutable reviewed asset receipt required")
    return target

def json_receipts(target, acquired):
    docs = {}
    for kind, row in target["reports"].items():
        docs[kind] = json.loads(receipt(acquired / row["artifact_role"], row, 4_000_000).read_text(encoding="utf-8-sig"))
    return docs

def check_reports(target, docs):
    ci = target["source"]["ci_commit"]; exe = target["executable_sha256"]; msi = target["msi_sha256"]
    boot, build, release = (docs[k] for k in ("bootstrap", "build", "release_manifest"))
    require(boot.get("original_source_commit") == SOURCE and boot.get("source_tree") == TREE and boot.get("ci_source_commit") == ci, "Bootstrap source mismatch")
    require(build.get("source_commit") == ci and build.get("source_dirty_at_build") is False and build.get("executable_sha256") == exe, "Build/executable mismatch")
    require(release.get("source_original_commit") == SOURCE and release.get("source_ci_commit") == ci
            and release.get("source_tree") == TREE and release.get("executable_sha256") == exe
            and release.get("status") == "packaged-sources-and-notices-verified; MSI-test-still-required"
            and all(release.get(k) is True for k in ("stage_unchanged", "component_sources_unchanged", "source_archive_CI_comment_verified"))
            and release.get("installer_executed") is False, "Authentic retained delivery bundle differs")
    stage_manifest = docs["stage_manifest"]
    require(stage_manifest.get("original_source_commit") == SOURCE and stage_manifest.get("source_commit") == ci
            and stage_manifest.get("source_tree") == TREE and stage_manifest.get("build_number") == 2008
            and stage_manifest.get("run_number") == EXPECTED["stage_producer"]["run_number"] and stage_manifest.get("run_attempt") == EXPECTED["stage_producer"]["run_attempt"]
            and stage_manifest.get("qt_version") == "6.10.2" and stage_manifest.get("executable_sha256") == exe, "Stage provenance differs")
    cli = docs["cli"]; rows = cli.get("checks")
    expected = {(f, s) for f in ("piano", "voice", "guitar", "percussion", "ensemble") for s in ("import-save-native", "reopen-native", "export-mxl", "export-pdf", "export-svg", "export-png", "export-mid", "export-wav", "export-flac", "export-mp3")}
    expected |= {("ensemble", "extract-native-parts")} | {("ensemble", f"part-{i:02d}-reopen-pdf") for i in range(1, 7)}
    require(cli.get("executable_sha256") == exe and type(cli.get("version_exit_code")) is int and cli["version_exit_code"] == 0
            and isinstance(rows, list) and len(rows) == 57 and {(r.get("fixture"), r.get("stage")) for r in rows} == expected, "Actual CLI57 coverage differs")
    for row in rows:
        require(row.get("passed") is True and not row.get("error") and "FAIL" not in str(row.get("stage", "")).upper()
                and type(row.get("exit_code")) is int and row["exit_code"] == 0 and row.get("outputs"), "CLI failure or missing outputs")
        for output in row["outputs"]:
            require(type(output.get("bytes")) is int and output["bytes"] > 0 and isinstance(output.get("sha256"), str) and SHA.fullmatch(output["sha256"]), "CLI output byte evidence missing")
            if row["stage"] == "export-wav": require(output.get("audio", {}).get("passed") is True, "CLI audio gate missing")
    check_native_reports(target, docs)
    install = docs["msi"]
    require(install.get("status") == "passed" and install.get("source_commit") == ci and install.get("msi_sha256") == msi
            and install.get("installed_executable_sha256") == exe and install.get("product_version") == "4.7.6.2008"
            and install.get("upgrade_code") == "{319B992F-470A-465B-9A79-6B0CBFC7D6C7}" and install.get("summary_template") == "x64;1033", "Actual MSI identity differs")
    require(all(type(install.get(k)) is int and install[k] in (0, 3010) for k in ("install_exit_code", "uninstall_exit_code"))
            and install.get("product_removed") is True and type(install.get("cli_exit_code")) is int and install["cli_exit_code"] == 0
            and install.get("cli_version_matched") is True and install.get("error") is None and install.get("cleanup_error") is None, "MSI install/CLI/uninstall did not pass")
    require(all(install.get(k) is True for k in ("gui_requested", "gui_tested", "gui_startup_observed", "clean_exit_observed", "require_system_icu", "installed_local_icuuc_absent"))
            and install.get("expected_product_version") == "4.7.6.2008" and install.get("gui_status") == "startup_observed_closed_cleanly"
            and type(install.get("gui_exit_status")) is int and install["gui_exit_status"] == 0, "MSI GUI/system ICU prerequisite missing")
    absence = install.get("installed_icu_absence_checks", [])
    require({r.get("phase") for r in absence} == {"before-installed-cli", "before-installed-gui"} and all(r.get("absent") is True for r in absence), "Installed ICU absence checks missing")
    notices = docs["notices"]; notes = notices.get("notices")
    require(notices.get("passed") is True and notices.get("status") == "passed_staged_notice_bytes_and_development_archive_exclusion"
            and notices.get("executable_sha256") == exe and notices.get("errors") == [] and isinstance(notes, list) and len(notes) > 0
            and type(notices.get("notice_files_verified")) is int and notices["notice_files_verified"] == len(notes), "Final stage notices not verified")
    expected_notes = [{"path": n["stage_path"], "bytes": n["bytes"], "sha256": n["sha256"]} for n in notes]
    require(install.get("notice_verification_requested") is True and type(install.get("installed_notices_verified")) is int and install["installed_notices_verified"] == len(notes)
            and install.get("installed_notices") == expected_notes and notices.get("mnxdom_development_archives_found") == []
            and notices.get("corresponding_source_archives_found_in_runtime") == [] and notices.get("corresponding_sources_remain_companion_files") is True, "Installed notice bytes/development archive exclusion differs")
    components = docs["components"]
    require(components.get("source_archives_verified") is True and components.get("errors") == []
            and notices.get("corresponding_source_report_sha256") == target["reports"]["components"]["sha256"], "Original component source collection/notices disagree")
    policy, exports = docs["icu_policy"], docs["icu_exports"]
    require(policy.get("status") == "local-forwarder-absent-and-system20exports-proved" and policy.get("local_forwarder_absent") is True
            and policy.get("qtcore_sha256") == QTCORE_SHA and policy.get("candidate_executable_sha256") == exe
            and policy.get("export_report_sha256") == target["reports"]["icu_exports"]["sha256"], "Stage ICU omission policy differs")
    require(exports.get("status") == "complete-static-export-evidence" and exports.get("complete") is True
            and exports.get("host_is_windows") is True and exports.get("local_forwarder_omission_export_gate_passed") is True
            and exports.get("errors") == [] and len(exports.get("resolutions", [])) == 20
            and all(r.get("complete") is True for r in exports["resolutions"]), "Actual system ICU20 export evidence incomplete")


def check_native_reports(target, docs):
    ci = target["source"]["ci_commit"]; exe = target["executable_sha256"]
    native = docs["native_additions"]
    require(native.get("observations_verified") is True and native.get("errors") == []
            and native.get("source_commit") == SOURCE and native.get("source_tree") == TREE
            and native.get("selection_sha256") == SOURCE_JSON_SHA, "Native metadata/QtNetwork source evidence differs")
    observations = native.get("observations", [])
    require(len(observations) == 2 and {r.get("kind") for r in observations} == {"metadata_and_focus_runtime", "optional_sync_runtime"}, "Native metadata/optional-sync observations missing")
    metadata = next(r for r in observations if r["kind"] == "metadata_and_focus_runtime")
    require(metadata.get("reported_metadata_groups") == 10 and metadata.get("executed_metadata_groups") == 9
            and metadata.get("focus_cases_passed") == 6 and metadata.get("focus_group_passed") is True
            and metadata.get("not_executed") == ["symlink export preserves unregistered scores"]
            and metadata.get("windows_reparse_point_runtime_validated") is False and metadata.get("gui_focus_validated") is False,
            "Actual Windows metadata/focus counts or declared reparse skip differs")
    sync = next(r for r in observations if r["kind"] == "optional_sync_runtime")
    require(sync.get("real_http_checks_passed") == 128 and sync.get("reentrancy_checks_passed") == 35
            and sync.get("pending_after_synchronous_cancel") == 0 and sync.get("server_hits_after_synchronous_cancel") == 0
            and sync.get("https_remote_validated") is False and sync.get("gui_validated") is False, "Native sync scope or cancellation evidence differs")
    practice = docs["practice"]
    require(practice.get("passed") is True and practice.get("errors") == [] and practice.get("source_commit") == ci
            and practice.get("source_tree") == TREE and practice.get("selection_sha256") == SOURCE_JSON_SHA
            and practice.get("physical_device_audio_latency_GUI_complete_score_editing_validated") is False,
            "Native MIDI/history source identity or scope differs")
    rows = practice.get("observations", [])
    require(len(rows) == 3 and all(r.get("passed") is True for r in rows)
            and {(r.get("kind"), r.get("variant")) for r in rows} == {("actual_midi_event_and_router", "ON"), ("actual_midi_event_and_router", "OFF"), ("actual_QtCore_history", None)}, "MIDI ON/OFF/history observations incomplete")
    on = next(r for r in rows if r.get("variant") == "ON"); history = next(r for r in rows if r.get("kind") == "actual_QtCore_history")
    require(on.get("matcher_groups") == 14 and on.get("matcher_assertions") == 12764 and on.get("event_groups") == 5
            and on.get("route_groups") == 4 and history.get("passed_scenarios") == 13
            and len(history.get("skipped_scenarios", [])) == 2, "Reviewed MIDI/history counts differ")
    off = next(r for r in rows if r.get("variant") == "OFF")
    require(off.get("route_groups") == 4 and all(off.get(k) == 0 for k in ("matcher_groups", "matcher_assertions", "event_groups"))
            and on.get("physical_device_or_score_editing_test") is False
            and off.get("physical_device_or_score_editing_test") is False
            and history.get("windows_ACL_junction_fixture_executed") is False,
            "Actual MIDI OFF routing counts or unvalidated hardware/history scope differs")
    audio = docs["audio_transcription"]
    require(audio.get("passed") is True and audio.get("status") == "passed-Windows2008-native-WAV-engine-and-real-MIDI-import-reopen"
            and audio.get("errors") == [] and audio.get("source_commit") == ci and audio.get("build_number") == 2008
            and audio.get("executable_sha256") == exe and audio.get("executable_unchanged") is True
            and audio.get("GUI_tested") is False and audio.get("human_listening") is False
            and audio.get("downloads") is False and audio.get("ctest", {}).get("passed") is True
            and audio.get("ctest", {}).get("groups_observed") == 9, "Monophonic native engine/application receipts differ")
    require(len(audio.get("cases", [])) == 2 and len(audio.get("commands", [])) == 8
            and all(type(r.get("exit_code")) is int and r["exit_code"] == 0 and r.get("timed_out") is False for r in audio["commands"])
            and all(all(r.get(k) is True for k in ("exact_native_pitches_and_timing", "WAV_source_unchanged", "WAV_working_copy_unchanged", "MIDI_unchanged_by_import", "native_score_unchanged_after_reopens")) for r in audio["cases"]), "Actual sampled WAV/import/reopen checks incomplete")
    omr = docs["omr_runner"]
    require(omr.get("status") == "passed-native-Windows-OMR-runner-boundary"
            and omr.get("windows_job_descendant_terminated") is True
            and omr.get("copied_input_with_spaces_accents_metacharacters") is True
            and omr.get("test_group_counts") == [15, 17]
            and omr.get("model", {}).get("bytes") == 23466654
            and omr.get("model", {}).get("sha256") == "daa0c97d651c19fba3b25e81317cd697e9908c8208090c94c3905381c23fc047"
            and omr.get("model", {}).get("unchanged") is True and omr.get("real_Audiveris_executed") is False
            and omr.get("integrated_dialog_executed") is False and omr.get("listening_performed") is False,
            "OMR process-boundary evidence/scope differs; no recognition or dialogue validation inferred")

    https = docs["authorized_wav_https"]
    require(https.get("status") == "passed-Windows-native-authorized-WAV-HTTPS-only" and https.get("error") is None
            and len(https.get("pass_groups", [])) == 14 and len(set(https["pass_groups"])) == 14
            and all(https.get(k) is False for k in ("application_executed", "GUI_validated", "system_trust_changed", "physical_audio_or_MIDI_tested", "cleanup_changes_to_source")),
            "Native authorized WAV HTTPS qualification/scope differs")
    prerequisite = https.get("prerequisite_probe", {})
    require(prerequisite.get("passed") is True and prerequisite.get("supports_ssl") is True
            and prerequisite.get("qt_version") == "6.10.2"
            and prerequisite.get("ordinary_file_dangling_directory_symlinks_available") is True
            and prerequisite.get("system_trust_changed") is False,
            "Actual Windows TLS/link prerequisites were not proved")
    require(https.get("tested_source_sha256") == EXPECTED["authorized_wav_tested_source_sha256"],
            "Authorized WAV qualification did not test the exact frozen source")
    macro, unity = docs["macro_profile"], docs["unity_syntax"]
    require(macro.get("status") == "PASS" and macro.get("expected_profile") == "ON"
            and macro.get("config_matches_profile") is True and macro.get("errors") == []
            and macro.get("error_count") == 0 and macro.get("failed_units") == 0
            and all(type(macro.get(k)) is int and macro[k] > 0 for k in ("notationscene_units", "notationscene_unity_units", "pch_units", "checked_units"))
            and macro.get("application_built") is False and macro.get("application_executed") is False,
            "Actual Unity/PCH macro profile was not consistent")
    units = unity.get("units", [])
    require(unity.get("status") == "PASS" and unity.get("errors") == [] and unity.get("syntax_only") is True
            and unity.get("application_built") is False and unity.get("application_executed") is False
            and type(unity.get("selected_units")) is int and unity["selected_units"] == len(units) and 1 <= len(units) <= 32
            and all(u.get("passed") is True and u.get("exit_code") == 0 and "/Zs" in u.get("command", []) and "/Y-" in u.get("command", []) for u in units)
            and unity.get("compile_commands_sha256") == macro.get("compile_commands_sha256")
            and unity.get("config_sha256") == macro.get("config_header_sha256"),
            "Actual configured MSVC syntax/precompiled-header inputs did not qualify")
    included = {name for unit in units for name in unit.get("included_sources", [])}
    require({"mdlmigrator.cpp", "localscorelibrarystore.cpp", "localaudiotranscriptionmodel.cpp", "authorizedwavedownload.cpp"} <= included,
            "Required real MDL/library/audio-model Unity sources were not syntax checked")

def zip_inventory(path):
    # Stream each inner stage once. Do not materialize a second runtime tree.
    rows = {}; keys = set(); total = 0
    with zipfile.ZipFile(path) as archive:
        require(len(archive.infolist()) <= 30000, "ZIP count bound")
        for info in archive.infolist():
            if info.is_dir(): continue
            name = info.filename[2:] if info.filename.startswith("./") else info.filename
            relative(name); require(name.casefold() not in keys, "Duplicate/case-colliding ZIP entry"); keys.add(name.casefold())
            require(not info.flag_bits & 1 and stat.S_IFMT(info.external_attr >> 16) != stat.S_IFLNK
                    and info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED) and 0 <= info.file_size <= MAX, "Unsupported ZIP entry")
            total += info.file_size; require(total <= 4 * MAX, "ZIP total byte bound")
            with archive.open(info) as stream: measured = hashlib.file_digest(stream, "sha256").hexdigest()
            rows[name] = {"bytes": info.file_size, "sha256": measured}
    require(rows, "Empty runtime ZIP")
    return rows

def stored_notices_zip(destination, stage_zip, notes, stage_files):
    require(not destination.exists() and notes, "New nonempty notice archive required")
    with zipfile.ZipFile(stage_zip) as source, zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_STORED, allowZip64=True) as output:
        names = {i.filename[2:] if i.filename.startswith("./") else i.filename: i for i in source.infolist() if not i.is_dir()}
        seen = set()
        for row in sorted(notes, key=lambda r: r["stage_path"]):
            name = relative(row["stage_path"]); require(name not in seen, "Duplicate notice"); seen.add(name)
            require(stage_files.get(name) == {"bytes": row["bytes"], "sha256": row["sha256"]}, "Original stage notice bytes differ")
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0)); info.create_system = 3; info.external_attr = 0o100644 << 16
            with source.open(names[name]) as stream, output.open(info, "w", force_zip64=True) as target: shutil.copyfileobj(stream, target, 1048576)
    require(destination.stat().st_size <= MAX, "Notice archive bound")

def inventory(root):
    output = {}
    for path in sorted(root.rglob("*")):
        plain(path)
        if path.is_file():
            name = relative(path.relative_to(root).as_posix()); output[name] = {"bytes": path.stat().st_size, "sha256": digest(path)}
    require(len(output) <= 30000, "File inventory exceeds bound")
    return output

def verify_ledger(root):
    rows = (root / "SHA256SUMS.txt").read_text(encoding="ascii").splitlines(); expected = {}
    for line in rows:
        match = re.fullmatch(r"([a-f0-9]{64})  (.+)", line); require(match is not None, "Invalid source/delivery ledger")
        name = relative(match[2]); require(name not in expected and name != "SHA256SUMS.txt", "Duplicate ledger member")
        expected[name] = match[1]
    actual = inventory(root)
    require(set(actual) == set(expected) | {"SHA256SUMS.txt"} and all(actual[n]["sha256"] == s for n, s in expected.items()), "Original ledger does not cover exact member bytes")
    return actual

def unique_suffix(root, suffix):
    suffix = relative(suffix)
    found = [p for p in root.rglob("*") if p.is_file() and (p.relative_to(root).as_posix() == suffix or p.relative_to(root).as_posix().endswith("/" + suffix))]
    require(len(found) == 1, "One actual member required: " + suffix)
    plain(found[0]); return found[0]

def extract_zip(source, destination):
    require(not destination.exists(), "ZIP destination must be new")
    destination.mkdir(parents=True); seen = set(); total = 0
    with zipfile.ZipFile(source) as bundle:
        require(len(bundle.infolist()) <= 30000, "ZIP count bound")
        for info in bundle.infolist():
            if info.is_dir(): continue
            name = info.filename[2:] if info.filename.startswith("./") else info.filename; relative(name)
            key = name.casefold(); require(key not in seen, "Duplicate/case-colliding ZIP entry"); seen.add(key)
            require(not info.flag_bits & 1 and stat.S_IFMT(info.external_attr >> 16) != stat.S_IFLNK
                    and info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED) and 0 <= info.file_size <= MAX, "Unsupported ZIP entry")
            total += info.file_size; require(total <= 4 * MAX, "ZIP total byte bound")
            path = destination / name; path.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(info) as stream, path.open("xb") as output: shutil.copyfileobj(stream, output, 1048576)
            require(path.stat().st_size == info.file_size, "ZIP member length differs")

def stored_zip(destination, entries):
    require(not destination.exists() and entries, "New nonempty companion archive required")
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_STORED, allowZip64=True) as output:
        for name, path in sorted(entries.items()):
            relative(name); plain(path)
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0)); info.create_system = 3; info.external_attr = 0o100644 << 16
            with path.open("rb") as source, output.open(info, "w", force_zip64=True) as target: shutil.copyfileobj(source, target, 1048576)
    require(destination.stat().st_size <= MAX, "Companion archive exceeds public asset bound")

def read_msi_tables(path, target):
    require(os.name == "nt", "Actual MSI table inspection requires Windows; no simulated success")
    import _msi
    database = _msi.OpenDatabase(str(path), _msi.MSIDBOPEN_READONLY)
    properties = {}
    for name in ("ProductVersion", "ProductName", "UpgradeCode"):
        view = database.OpenView("SELECT `Value` FROM `Property` WHERE `Property`='" + name + "'")
        try:
            view.Execute(None); row = view.Fetch(); require(row is not None, "MSI Property missing")
            properties[name] = row.GetString(1)
        finally: view.Close()
    require(properties["ProductVersion"] == "4.7.6.2008" and properties["ProductName"] in ("Cadence Studio", "Cadence Studio 4")
            and properties["UpgradeCode"].upper() == "{319B992F-470A-465B-9A79-6B0CBFC7D6C7}", "Actual MSI Property identity differs")
    view = database.OpenView("SELECT `FileName` FROM `File`"); count = 0
    try:
        view.Execute(None)
        while True:
            row = view.Fetch()
            if row is None: break
            count += 1; require(count <= 30000, "MSI File table count bound")
            filename = row.GetString(1)
            require(isinstance(filename, str) and len(filename) <= 512 and filename.split("|")[-1].casefold() != "icuuc.dll", "The MSI File table still contains an ICU forwarder")
    finally: view.Close()
    require(count > 0 and digest(path) == target["msi_sha256"], "MSI bytes changed during read-only table inspection")
    return {"open_mode": int(_msi.MSIDBOPEN_READONLY), "properties": properties, "file_rows": count,
            "local_icuuc_file_table_absent": True, "installer_or_custom_action_executed": False}

def check_retained_reports(target, docs, acquired):
    ci, exe = target["source"]["ci_commit"], target["executable_sha256"]
    qa, package, wrapper = (docs[k] for k in ("retained_qualification", "retained_packaging", "retained_installer_wrapper"))
    expected_qa = EXPECTED["retained_qualification_receipt"]
    require(all(target["reports"]["retained_qualification"].get(k) == expected_qa[k] for k in ("bytes", "sha256")), "Original measured QA aggregate changed")
    require(qa.get("status") == "passed-actual-retained2008-QA-only-no-installer-produced"
            and qa.get("ready") is True and qa.get("passed") is True and qa.get("errors") == []
            and qa.get("source_original_commit") == SOURCE and qa.get("source_ci_commit") == ci and qa.get("source_tree") == TREE
            and qa.get("executable_sha256") == exe and qa.get("application_recompiled") is False
            and qa.get("original_build_run_id") == EXPECTED["stage_producer"]["run_id"]
            and qa.get("original_build_job_id") == EXPECTED["stage_producer"]["job_id"]
            and qa.get("original_producer_overall_conclusion") == "failure" and qa.get("original_producer_failed_step") == 31
            and qa.get("installer_produced") is False and qa.get("installer_tested") is False
            and qa.get("counts") == {"cli_checks":57,"reference_outputs":35,"music_aac_cases":5}, "Actual retained QA closure differs")
    gates = qa.get("gates", {})
    require(set(gates) == {"native_practice", "native_omr", "native_transcription", "audio_transcription_import", "cli57", "reference35", "aac5", "stage_notices", "stage_GUI", "musical_roundtrip"}, "Ten actual retained QA gates required")
    # These are actual report byte checks, not a second implementation of the QA tests.
    for row in gates.values():
        require(row.get("passed") is True and isinstance(row.get("path"), str), "Actual QA gate receipt missing")
        parts = row["path"].replace("\\", "/").split("/_temp/", 1)
        require(len(parts) == 2, "Actual hosted QA temporary report path required")
        path = unique_suffix(acquired / "qa_logs", relative(parts[1]))
        receipt(path.parent, {**row, "member_path": path.name}, 4_000_000)
    hook = qa.get("optional_app_library_hook", {})
    require(hook.get("qualified") is False and hook.get("report", {}).get("passed") is False, "Unavailable optional app-library hook must stay unqualified")
    require(package.get("status") == "packaged-immutable2008-stage-awaiting-actual-MSI-installation-test"
            and package.get("source_original_commit") == SOURCE and package.get("source_ci_commit") == ci
            and package.get("source_tree") == TREE and package.get("executable_sha256") == exe
            and all(package.get(k) is True for k in ("stage_preserved", "source_preserved", "component_sources_preserved", "job_closed"))
            and package.get("application_recompiled") is False and package.get("actual_installer_tested") is False
            and package.get("forced_descendants") == 0 and package.get("forced_tools") == [] and package.get("error") is None
            and package.get("installer", {}).get("sha256") == target["msi_sha256"], "Actual immutable MSI packaging did not pass")
    require(wrapper.get("status") == "passed-retained2008-msi-and-installed-gui" and wrapper.get("error") is None
            and wrapper.get("source_original_commit") == SOURCE and wrapper.get("source_CI_commit") == ci
            and wrapper.get("source_tree") == TREE and wrapper.get("executable_sha256") == exe
            and all(wrapper.get(k) is True for k in ("original_inputs_preserved", "installer_cli_verified", "installed_gui_verified", "installer_qualified_for_experimental_release", "require_gui"))
            and wrapper.get("inner_report") == docs["msi"]
            and wrapper.get("input_sha256_before") == wrapper.get("input_sha256_after")
            and wrapper.get("input_sha256_before", {}).get("msi") == target["msi_sha256"]
            and wrapper.get("input_sha256_before", {}).get("build_result") == target["reports"]["build"]["sha256"]
            and wrapper.get("input_sha256_before", {}).get("notice_report") == target["reports"]["notices"]["sha256"], "Actual installed MSI GUI wrapper did not pass")

def prepare(target, acquired, output):
    validate_target(target, approval=False)
    require(not output.exists(), "Prepared public asset root must be new")
    docs = json_receipts(target, acquired); check_reports(target, docs); check_retained_reports(target, docs, acquired)
    acquisition = json.loads((acquired / "artifact-acquisition.json").read_text())
    require(acquisition.get("producer_run") == RUN and acquisition.get("producer_driver_commit") == DRIVER
            and acquisition.get("original_outer_digests_recomputed") is True and acquisition.get("artifacts") == target["artifacts"]
            and acquisition.get("all_retained_producers_authenticated") is True, "Exact multi-origin acquisition receipt required")
    delivery = unique_suffix(acquired / "delivery", ASSET_NAMES["msi"]).parent
    require(set(inventory(delivery)) == set(ASSET_NAMES.values()), "Exactly the seven original retained public files required")
    verify_ledger(delivery)
    msi = delivery / ASSET_NAMES["msi"]; require(digest(msi) == target["msi_sha256"], "Actual installed MSI differs")
    require(msi.stat().st_size == docs["retained_packaging"]["installer"]["bytes"], "Packaged MSI size differs")
    msi_tables = read_msi_tables(msi, target)
    source = delivery / ASSET_NAMES["source_archive"]; plain(source)
    with tarfile.open(source, "r:gz") as archive:
        require(archive.pax_headers.get("comment") == target["source"]["ci_commit"], "Source archive does not identify the actual git archive commit")
        source_members = set(archive.getnames())
        required = {"src/importexport/audiotranscription/audiotranscription.cpp", "src/importexport/audiotranscription/audiotranscription.h",
                    "src/project/internal/cadencesyncclient.cpp", "services/cadence-library/server.py", "services/cadence-library/README.md",
                    "docs/licenses/omr/Audiveris-LICENSE-AGPL-3.0.txt",
                    "src/project/qml/MuseScore/Project/resources/omr/Tesseract-tessdata-LICENSE.txt", "docs/NOTICE-FR.md", "src/project/qml/MuseScore/Project/internal/LocalAudioTranscription/authorizedwavedownload.cpp", "src/project/qml/MuseScore/Project/internal/LocalAudioTranscription/authorizedwavedownload.h", "src/framework/ui/qml/Muse/Ui/qmlaccessible.h", "src/musesounds/internal/musesoundsconfiguration.cpp"}
        require(required <= source_members, "New original engine, optional service and external component licence sources are missing")
    stage_zip = unique_suffix(acquired / "stage", EXPECTED["stage_inner_archive"]["archive"])
    verify_ledger(stage_zip.parent)
    require(digest(stage_zip) == docs["stage_manifest"].get("stage_archive_sha256") == EXPECTED["stage_inner_archive"]["archive_sha256"], "Original stage inner ZIP differs")
    stage_files = zip_inventory(stage_zip)
    validated = json.loads(unique_suffix(acquired / "msi_logs", "retained2008-package/validated-inputs.json").read_text(encoding="utf-8-sig"))
    require(validated.get("source_ci_commit") == target["source"]["ci_commit"] and validated.get("source_tree") == TREE
            and validated.get("executable_sha256") == target["executable_sha256"] and validated.get("application_recompiled") is False
            and validated.get("stage_files") == stage_files, "MSI preflight does not identify the exact original stage inventory")
    require(stage_files.get("bin/CadenceStudio4.exe", {}).get("sha256") == target["executable_sha256"]
            and stage_files.get("bin/Qt6Core.dll", {}).get("sha256") == QTCORE_SHA and "bin/Qt6Network.dll" in stage_files
            and not any(n.casefold() == "bin/icuuc.dll" for n in stage_files), "Original runtime/Qt/system ICU differs")
    components = delivery / ASSET_NAMES["component_sources"]
    component_files = zip_inventory(components)
    zlib_names = {"Cadence-zlib-1.3.2-corresponding-source.zip", "zlib-source-profile.lock.json", "zlib-source-supplement.MEASURED.json"}
    require(set(component_files) == set(validated.get("component_files", {})) | zlib_names
            and all(component_files.get(n) == v for n,v in validated["component_files"].items()), "Corresponding source companion differs from packaging preflight")
    zlib_receipts = docs["release_manifest"].get("component_source_original_zlib_companions", {})
    require(set(zlib_receipts) == zlib_names, "Original zlib companions and explicit derived measurement required")
    for name in zlib_names:
        row = zlib_receipts[name]
        require(component_files[name] == {"bytes":row["bytes"],"sha256":row["sha256"]}, "Zlib companion ZIP bytes differ")
        if name != "zlib-source-supplement.MEASURED.json":
            receipt(stage_zip.parent, {**row,"member_path":name})
    with zipfile.ZipFile(components) as archive:
        profile = json.loads(archive.read("zlib-source-profile.lock.json"))
        measured = json.loads(archive.read("zlib-source-supplement.MEASURED.json"))
    require(zlib_receipts["zlib-source-supplement.MEASURED.json"].get("derived_measurement") is True
            and measured.get("scope", "").startswith("NEW derived packaging measurement; not an original")
            and measured.get("application_recompiled") is False and measured.get("component") == "zlib" and measured.get("version") == "1.3.2"
            and measured.get("producer_run_id") == profile["ci"]["run_id"] == 43101767743
            and measured.get("producer_artifact_id") == profile["ci"]["artifact_id"] == 13891238030
            and measured.get("source_commit") == profile["source_commit"]
            and measured.get("upstream_source_archive_sha256") == profile["source_archive_sha256"]
            and measured.get("original_stage_companions") == {n:zlib_receipts[n] for n in zlib_names if n != "zlib-source-supplement.MEASURED.json"}, "Derived zlib measurement disagrees with original profile/companions")
    require(component_files.get("collection-report.json", {}).get("sha256") == target["reports"]["components"]["sha256"], "Original component source report differs")
    with zipfile.ZipFile(components) as archive:
        lock = json.loads(archive.read("sources.lock.json"))
    require(component_files["sources.lock.json"]["sha256"] == docs["components"]["source_lock_sha256"]
            and lock.get("qt_version") == "6.10.2" and any(r.get("id") == "qtbase" and r.get("version") == "6.10.2" for r in lock["archives"]), "Matching QtNetwork/qtbase sources missing")
    for row in lock["archives"]:
        require(component_files.get("archives/" + relative(row["archive"])) == {"bytes":row["archive_bytes"],"sha256":row["sha256"]}, "Corresponding source archive differs")
    notes = {row["stage_path"]:{"bytes":row["bytes"],"sha256":row["sha256"]} for row in docs["notices"]["notices"]}
    require(zip_inventory(delivery / ASSET_NAMES["notices"]) == notes
            and all(stage_files.get(name) == value for name,value in notes.items()), "Public, staged and installed notices differ")
    recipe_files = zip_inventory(delivery / ASSET_NAMES["build_recipe"])
    require(recipe_files.get("original-profile/source.json", {}).get("sha256") == SOURCE_JSON_SHA, "Exact source selection absent from retained recipe")
    patches = [v for n,v in recipe_files.items() if n.endswith("combined-2008-source/changes.patch.gz")]
    require(len(patches) == 1 and patches[0]["sha256"] == PATCH_SHA, "Exact original source patch absent from retained recipe")
    bundle_assets = docs["release_manifest"].get("assets", [])
    require(len(bundle_assets) == 6 and {r.get("name") for r in bundle_assets} == set(ASSET_NAMES.values()) - {ASSET_NAMES["checksums"]}, "Bundle six asset receipts differ")
    for row in bundle_assets: receipt(delivery, {**row, "member_path":row["name"]})
    sums = "".join(str(digest(delivery / n)) + "  " + n + "\n" for n in sorted(ASSET_NAMES.values()) if n != ASSET_NAMES["checksums"])
    require((delivery / ASSET_NAMES["checksums"]).read_text(encoding="ascii") == sums, "Original retained checksums differ")
    output.mkdir(parents=True)
    for name in ASSET_NAMES.values(): shutil.copyfile(delivery / name, output / name)
    assets = [{"kind":kind,"name":name,"member_path":name,"bytes":(output/name).stat().st_size,"sha256":digest(output/name)} for kind,name in ASSET_NAMES.items()]
    return {"schema_version":1,"prepared_from_originals":True,"ready":False,"asset_receipts":assets,"source":target["source"],"producer":target["producer"],"stage_producer":target["stage_producer"],"qualification_producer":target["qualification_producer"],"msi_readonly_tables":msi_tables,"application_or_installer_executed":False}

def validate(target, acquired, prepared):
    validate_target(target)
    docs = json_receipts(target, acquired); check_reports(target, docs); check_retained_reports(target, docs, acquired)
    facts = json.loads((prepared / "asset-preparation.json").read_text())
    require(facts.get("prepared_from_originals") is True and facts.get("source") == target["source"] and facts.get("producer") == target["producer"]
            and facts.get("asset_receipts") == target["assets"], "Prepared exact asset receipts were not reviewed")
    table_facts = facts.get("msi_readonly_tables", {})
    require(type(table_facts.get("open_mode")) is int and table_facts["open_mode"] == 0
            and table_facts.get("local_icuuc_file_table_absent") is True and table_facts.get("installer_or_custom_action_executed") is False
            and table_facts.get("properties", {}).get("ProductVersion") == "4.7.6.2008", "Actual read-only MSI table/ICU evidence is missing")
    for row in target["assets"]: receipt(prepared, row)
    require(next(a for a in target["assets"] if a["kind"] == "msi")["sha256"] == target["msi_sha256"], "Public MSI differs from tested installer")
    sums = next(a for a in target["assets"] if a["kind"] == "checksums")
    expected_sums = "".join(a["sha256"] + "  " + a["name"] + "\n" for a in sorted(target["assets"], key=lambda a:a["name"]) if a["kind"] != "checksums")
    require(receipt(prepared, sums).read_text(encoding="ascii") == expected_sums, "Public SHA manifest does not cover the exact other six files")
    install = docs["msi"]
    summary = {"msi_product_version": install["product_version"], "install_exit_code": install["install_exit_code"],
               "uninstall_exit_code": install["uninstall_exit_code"], "install_reboot_required": install.get("install_reboot_required"),
               "uninstall_reboot_required": install.get("uninstall_reboot_required"), "installed_notice_files": install["installed_notices_verified"],
               "gui_status": install["gui_status"], "cli_checks": len(docs["cli"]["checks"]), "tested_platform": target["limitations"]["tested_platform"],
               "first_launch_wizard_tested": False, "msi_file_table_icuuc_absent": facts["msi_readonly_tables"]["local_icuuc_file_table_absent"]}
    return {"schema_version": 1, "allowed": True, "asset_receipts": target["assets"], "source": target["source"], "producer": target["producer"], "actual_qualification": summary, "scope": "Experimental Windows2008 bytes only; no publication performed by this validator"}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("check-target", "prepare", "validate")); parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--acquired", type=Path); parser.add_argument("--root", type=Path); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); result = {"schema_version": 1, "allowed": False, "error": None}
    try:
        plain(args.target); require(args.target.stat().st_size <= 4_000_000, "Oversized target")
        target = json.loads(args.target.read_text(encoding="utf-8-sig"))
        if args.mode == "check-target": validate_target(target); result.update(allowed=True)
        elif args.mode == "prepare":
            result = prepare(target, args.acquired.resolve(strict=True), args.root)
            (args.root / "asset-preparation.json").write_text(json.dumps(result, indent=2) + "\n")
        else: result = validate(target, args.acquired.resolve(strict=True), args.root.resolve(strict=True))
    except Exception as error:
        result["error"] = str(error); result["error_type"] = type(error).__name__
    require(not args.output.exists(), "Output receipt must be new")
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(result, indent=2) + "\n"); print(json.dumps(result))
    return 0 if result.get("allowed") is True or (args.mode == "prepare" and result.get("prepared_from_originals") is True and not result.get("error")) else 2

if __name__ == "__main__": raise SystemExit(main())
