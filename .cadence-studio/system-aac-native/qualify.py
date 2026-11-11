#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Verify exact production sources, prepare test data stubs, inspect real output.

The encoder is the committed WindowsAacStream class. The finalization test uses
the real AbstractAudioEncoder/Ret and minimal unrelated Progress/path/format/log
data stubs; it does not qualify the Qt WindowsAacEncoder adapter or full engine.
"""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import xml.etree.ElementTree as ET


COMMIT = "0feb75b7abc54c4b239fd7313b90ba0fa020d930"
TREE = "1744f82e9a05de784f9ea6bb6a185d418ce4eb0b"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def emit(kind, report):
    print("CADENCE_SYSTEM_AAC_" + kind + "_BEGIN", flush=True)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True), flush=True)
    print("CADENCE_SYSTEM_AAC_" + kind + "_END", flush=True)


def publish_step_summary(report):
    # Redundant small metadata path for the controller if full log fetch times out.
    # Only computed, validated numbers/hashes enter this single-line step name.
    if not report["passed"] or not os.environ.get("GITHUB_OUTPUT"):
        return
    parts = ["Stream PASS x64/MD 10tests"]
    for entry in sorted(report["cases"], key=lambda case: case["native"]["rate"]):
        structure = entry["validation"]["structure"]
        parts.append(str(entry["native"]["rate"]) + ":" + str(entry["aac_size_bytes"])
                     + "B/" + str(structure["frame_count"]) + "fr/"
                     + format(structure["adts_duration_seconds"], ".9f") + "s SHA=" + entry["aac_sha256"])
    parts.append("QtApp/MP4/listening=NO")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write("report_step_name=" + "; ".join(parts) + "\n")


def verify_sources(root):
    manifest = json.loads((root / "source-manifest.json").read_text(encoding="utf-8-sig"))
    if manifest["source_original_commit"] != COMMIT or manifest["source_original_tree"] != TREE:
        raise ValueError("Unexpected original production commit/tree")
    for entry in [*manifest["files"], manifest["decoder"]]:
        path = (root / entry["path"]).resolve()
        if not path.is_relative_to(root) or path.is_symlink():
            raise ValueError("Source path escaped the namespace")
        if path.stat().st_size != entry["size_bytes"] or sha256(path) != entry["sha256"]:
            raise ValueError("Exact source mismatch: " + entry["path"])
    return manifest


def literal_assignment(path, name):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError("Missing committed harness assignment " + name)


def prepare(args, root):
    manifest = verify_sources(root)
    generated = args.generated.resolve()
    generated.mkdir(parents=True, exist_ok=True)
    if any(generated.iterdir()):
        raise ValueError("Choose a fresh generated-test directory")
    tests = root / "source/test/cadence"
    (generated / "pcm16.cpp").write_bytes(literal_assignment(tests / "test_aac_pcm16.py", "HARNESS").encode("utf-8"))
    (generated / "finalization.cpp").write_bytes(
        literal_assignment(tests / "test_audio_encoder_finalization.py", "HARNESS").encode("utf-8"))
    stubs = literal_assignment(tests / "test_audio_encoder_finalization.py", "stubs")
    # Ret.h normally imports the application's logger. No logging path is used
    # by this contract test; retain assertion control flow without that module.
    stubs["global/log.h"] = "#pragma once\n#define IF_ASSERT_FAILED_X(condition, message) if (!(condition))\n"
    for name, content in stubs.items():
        path = generated / "stubs" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    report = {
        "source_original_commit": COMMIT, "source_original_tree": TREE,
        "exact_sources": len(manifest["files"]), "all_source_hashes_passed": True,
        "generated_harness_sha256": {name: sha256(generated / name) for name in ("pcm16.cpp", "finalization.cpp")},
        "qt_adapter_qualified": False, "full_application_qualified": False,
    }
    (args.summary / "prepared.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    emit("REPORT", {"path": "prepared.json", "report": report})


def inspect(args, root):
    verify_sources(root)
    build = args.build.resolve()
    report = {
        "schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_original_commit": COMMIT, "source_original_tree": TREE,
        "passed": False, "cases": [], "errors": [],
        "qt_adapter_qualified": False, "full_application_qualified": False,
        "mp4_mux_qualified": False, "human_listening": False,
        "system_dlls_redistributed": False,
        "finalization_scope": "Real AbstractAudioEncoder/Ret contract; unrelated data/log stubs, no Qt adapter or file I/O test",
    }
    try:
        abi = json.loads((build / "qualification-abi.json").read_text(encoding="utf-8-sig"))
        report["abi"] = abi
        if abi.get("pointer_bytes") != 8 or abi.get("compiler") != "MSVC" or abi.get("build_type") != "Release":
            raise ValueError("Expected x64 MSVC Release qualification")
        if abi.get("native_runtime") != "MultiThreadedDLL" or abi.get("finalization_runtime") != "MultiThreadedDLL":
            raise ValueError("Qualification targets did not select /MD")
        commands = json.loads((build / "compile_commands.json").read_text(encoding="utf-8-sig"))
        native_commands = [entry for entry in commands if entry["file"].replace("\\", "/").endswith("/windowsaacstream.cpp")]
        if len(native_commands) != 1:
            raise ValueError("Expected one compiled production windowsaacstream.cpp")
        command = native_commands[0].get("command", " ".join(native_commands[0].get("arguments", [])))
        if not re.search(r"(?:^|\s)[/-]MD(?:\s|$)", command) or re.search(r"(?:^|\s)[/-](?:MTd?|MDd)(?:\s|$)", command):
            raise ValueError("Actual production compile command does not use Release /MD")
        report["production_compile_command"] = command
        junit = ET.parse(args.summary / "ctest.xml").getroot()
        cases = list(junit.iter("testcase"))
        if len(cases) != 10 or any(any(case.find(tag) is not None for tag in ("failure", "error", "skipped"))
                                   or case.get("status") in ("notrun", "disabled") for case in cases):
            raise ValueError("Expected all ten real native/policy/finalization tests to pass")
        report["ctest_cases"] = [case.get("name") for case in cases]
        spec = importlib.util.spec_from_file_location("cadence_original_adts_validator", root / "decoder/verify_adts.py")
        validator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(validator)
        native_reports = sorted((build / "production-native/native-results").glob("*/native.json"))
        if len(native_reports) != 2:
            raise ValueError("Expected exactly two fresh production AAC native reports")
        for path in native_reports:
            native = json.loads(path.read_text(encoding="utf-8-sig"))
            audio = Path(native["output"])
            if not audio.resolve().is_relative_to(build) or not native.get("passed") or not native.get("production_stream"):
                raise ValueError("Native test output does not identify the actual production stream")
            validation = validator.verify_file(audio, native["rate"], native["pcm_frames"], True)
            entry = {"native": native, "validation": validation, "aac_size_bytes": audio.stat().st_size, "aac_sha256": sha256(audio)}
            report["cases"].append(entry)
            (args.summary / (str(native["rate"]) + "-validation.json")).write_text(
                json.dumps(entry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            emit("REPORT", {"path": str(native["rate"]) + "-validation.json", "report": entry})
            if not validation.get("passed") or validation.get("status") != "passed_with_decode":
                raise ValueError("Required external decode/frequency/level/duration checks failed")
        if sorted(entry["native"]["rate"] for entry in report["cases"]) != [44100, 48000]:
            raise ValueError("Both 44100 and 48000 Hz must be qualified")
        report["passed"] = True
    except (OSError, ValueError, KeyError, ET.ParseError) as error:
        report["errors"].append(str(error))
    (args.summary / "qualification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    emit("REPORT", {"path": "qualification.json", "report": report})
    publish_step_summary(report)
    return 0 if report["passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "inspect"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--generated", type=Path)
    parser.add_argument("--build", type=Path)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    args.summary = args.summary.resolve()
    args.summary.mkdir(parents=True, exist_ok=True)
    if args.action == "prepare":
        if args.generated is None:
            parser.error("prepare requires --generated")
        prepare(args, root)
        return 0
    if args.build is None:
        parser.error("inspect requires --build")
    return inspect(args, root)


if __name__ == "__main__":
    raise SystemExit(main())
