#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Verify real Windows CTest observations; no musical or hardware simulation."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import re
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET

REVIEWED = {
    "schema_version": 1, "matcher_groups": 14, "matcher_assertions": 12764,
    "event_groups": 5, "route_on_groups": 4, "route_off_groups": 4,
    "history_passed": 13, "history_skipped": 2, "history_total": 15,
    "qt_version": "6.10.2",
}
EVENTS = [
    "actual MuseScore MIDI1 note/channel/zero conventions",
    "actual MIDI2 low velocities and WinMidiInPort conversion",
    "sustain ignored, reset controllers distinguished, NOOP safe",
    "unsupported groups and microtonal pitch attributes explicit",
    "real Event to production matcher polyphonic lifecycle",
]
ROUTE_BASE = ["inactive exercise preserves actual remote then notation route",
              "ordinary remote command still takes precedence"]
ROUTE_END = "stop restores routing and empty context is safe"
ROUTES = {
    "ON": ROUTE_BASE + ["actual armed route intercepts before remote and delayed editor queue", ROUTE_END],
    "OFF": ROUTE_BASE + ["reference build never calls the practice service", ROUTE_END],
}
HISTORY = [
    "missing history stays absent", "manual and MIDI summaries roundtrip, exact Unicode and IDs",
    "invalid summaries leave no file and do not alter previous bytes",
    "malformed JSON survives load, append and clear", "future history survives all operations",
    "unrelated JSON cannot be overwritten", "oversized history is preserved",
    "duplicate IDs and invalid persisted fields are preserved",
    "held process lock blocks append and clear without losing cache",
    "stale readers do not overwrite another writer",
    "denied directory permissions preserve summaries and old bytes",
    "three concurrent processes preserve all summaries",
    "retention keeps exactly the latest fifty summaries",
    "score paths, missing parents and directory targets are refused",
    "symbolic history, lock and parent links are refused",
]
SKIPPED = {
    HISTORY[10]: "Unix directory permissions are not Windows ACLs",
    HISTORY[14]: "symbolic-link construction requires a separate Windows native fixture",
}


def normalized(text: str) -> list[str]:
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    return [re.sub(r"^\s*\d+:\s?", "", line).strip() for line in text.splitlines()]


def midi_observation(text: str, variant: str) -> dict:
    lines = normalized(text)
    expected_pass = (EVENTS if variant == "ON" else []) + ROUTES[variant]
    observed_pass = [line[6:] for line in lines if line.startswith("PASS: ")]
    summaries = [line for line in lines if line.startswith("PASS 14 musical/")]
    expected_summary = ["PASS 14 musical/lifecycle groups, 12764 assertions"] if variant == "ON" else []
    if observed_pass != expected_pass or summaries != expected_summary or any(line.startswith("FAIL") for line in lines):
        raise ValueError("MIDI " + variant + " log differs from the exact reviewed native scenarios")
    return {"kind": "actual_midi_event_and_router", "variant": variant,
            "matcher_groups": 14 if variant == "ON" else 0,
            "matcher_assertions": 12764 if variant == "ON" else 0,
            "event_groups": len(EVENTS) if variant == "ON" else 0,
            "route_groups": len(ROUTES[variant]), "passed": True,
            "physical_device_or_score_editing_test": False}


def history_observation(text: str) -> dict:
    lines = normalized(text)
    passed = [line[5:] for line in lines if line.startswith("PASS ")]
    expected_passed = [name for name in HISTORY if name not in SKIPPED]
    skipped = [line[5:] for line in lines if line.startswith("SKIP ")]
    expected_skipped = [name + ": " + reason for name, reason in SKIPPED.items()]
    summary = [line for line in lines if line.startswith("PASSED ")]
    if passed != expected_passed or skipped != expected_skipped or summary != [
            "PASSED 13 meaningful production-store scenarios; SKIPPED 2; Qt 6.10.2"] \
            or any(line.startswith("FAIL") for line in lines):
        raise ValueError("History requires 13 actual passes and exactly the two declared Unix-only skips on Qt6.10.2")
    return {"kind": "actual_QtCore_history", "passed_scenarios": 13,
            "skipped_scenarios": [{"name": name, "reason": reason} for name, reason in SKIPPED.items()],
            "windows_ACL_junction_fixture_executed": False, "passed": True}


def ctest_xml(path: Path, names: list[str]) -> dict:
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    if [case.get("name") for case in cases] != names or any(
            any(child.tag in ("failure", "error", "skipped") for child in case) for case in cases):
        raise ValueError("CTest XML does not prove the exact targets completed successfully: " + str(path))
    if any(case.get("status") not in (None, "run") for case in cases):
        raise ValueError("CTest target was not executed")
    return {"path": str(path), "sha256": sha(path), "completed_targets": names}



def reference_framework_header(raw: bytes) -> bytes:
    # Preserve every configured feature except the independently reviewed
    # Cadence compile-time routing flag. This is a derived test profile, not
    # an assertion that the official upstream application was compiled.
    directives = re.findall(rb"(?m)^[ \t]*#[ \t]*(?:define|undef)[ \t]+CADENCE_BUILD\b[^\r\n]*", raw)
    if directives != [b"#define CADENCE_BUILD 1"]:
        raise ValueError("Expected exactly the real candidate CADENCE_BUILD=1 directive")
    result, count = re.subn(rb"(?m)^#define CADENCE_BUILD 1(?=\r?$)", b"/* #undef CADENCE_BUILD */", raw)
    if count != 1:
        raise ValueError("Reference routing header must have exactly one known transformation")
    return result


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pe_x64(path: Path) -> dict:
    data = path.read_bytes()
    if len(data) < 0x40 or data[:2] != b"MZ":
        raise ValueError("Not a native Windows executable: " + str(path))
    offset = struct.unpack_from("<I", data, 0x3c)[0]
    if offset > len(data) - 6 or data[offset:offset+4] != b"PE\0\0" \
            or struct.unpack_from("<H", data, offset + 4)[0] != 0x8664:
        raise ValueError("Executable does not have the AMD64 PE machine: " + str(path))
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "pe_machine": "0x8664"}


def git_text(source: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(source), *args], text=True).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--bootstrap", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--application-build", type=Path, required=True)
    parser.add_argument("--on-build", type=Path, required=True)
    parser.add_argument("--off-build", type=Path, required=True)
    parser.add_argument("--history-build", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = {"schema_version": 1, "passed": False, "application_or_hardware_executed_by_helper": False,
              "physical_device_audio_latency_GUI_complete_score_editing_validated": False,
              "observations": [], "errors": []}
    try:
        if sys.platform != "win32" or struct.calcsize("P") != 8 or platform.machine().lower() not in ("amd64", "x86_64"):
            raise ValueError("The qualification must run in a real Windows x64 Python process")
        source, app_build = args.source_root.resolve(), args.application_build.resolve()
        selection = json.loads(args.selection.read_text(encoding="utf-8-sig"))
        bootstrap = json.loads(args.bootstrap.read_text(encoding="utf-8-sig"))
        common = args.selection.parent / "qualification_plan.py"
        spec = importlib.util.spec_from_file_location("cadence_source_qualification", common)
        if not spec or not spec.loader:
            raise ValueError("Missing actual source qualification helper")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.read_plan(selection, bootstrap)
        if selection["qualification"]["practice"] != REVIEWED:
            raise ValueError("Reviewed practice counts differ from the source-bound plan")
        if git_text(source, "rev-parse", "HEAD") != bootstrap["ci_source_commit"] \
                or git_text(source, "rev-parse", "HEAD^{tree}") != bootstrap["source_tree"] \
                or git_text(source, "status", "--porcelain", "--untracked-files=all"):
            raise ValueError("Source changed after the exact bootstrap")
        report.update(source_commit=bootstrap["ci_source_commit"], source_tree=bootstrap["source_tree"],
                      selection_sha256=sha(args.selection), reviewed=REVIEWED,
                      generated_framework_header_sha256=sha(app_build / "muse_framework_config.h"))
        reference = args.off_build / "framework-reference-profile"
        reference_file = reference / "muse_framework_config.h"
        source_header = app_build / "muse_framework_config.h"
        reference_receipt = json.loads((reference / "profile.json").read_text(encoding="utf-8"))
        if reference_file.read_bytes() != reference_framework_header(source_header.read_bytes()) \
                or reference_receipt["original_sha256"] != sha(source_header) \
                or reference_receipt["derived_sha256"] != sha(reference_file) \
                or reference_receipt["status"] != "derived-reference-routing-flag-only":
            raise ValueError("OFF test did not use the exact reviewed derived routing header")
        report["reference_routing_header_profile"] = reference_receipt
        for variant, build, targets in (
                ("ON", args.on_build, ["midi_practice_matcher", "midi_practice_event", "midi_practice_routing"]),
                ("OFF", args.off_build, ["midi_practice_routing"]),
                ("history", args.history_build, ["practice_history"])):
            text = (build / "ctest.log").read_text(encoding="utf-8-sig")
            item = history_observation(text) if variant == "history" else midi_observation(text, variant)
            item["ctest"] = ctest_xml(build / "ctest-results.xml", targets)
            item["ctest_log_sha256"] = sha(build / "ctest.log")
            item["native_executables"] = [pe_x64(build / (name + "_tests.exe")) for name in targets]
            report["observations"].append(item)
        report["passed"] = True
    except (OSError, ValueError, KeyError, TypeError, ET.ParseError, subprocess.SubprocessError) as error:
        report["errors"].append(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print("CADENCE_PRACTICE_NATIVE_REPORT_BEGIN")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    print("CADENCE_PRACTICE_NATIVE_REPORT_END")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
