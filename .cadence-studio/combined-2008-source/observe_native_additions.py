#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Read actual separate CTest logs; never execute or simulate an application."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

METADATA_GROUPS = (
    "metadata migration and concurrent fields", "malformed metadata preserved",
    "playlist codec paths and duplicate keys", "normalized mixed network paths rejected",
    "ordered transfer and privacy", "atomic failures and export guards",
    "symlink export preserves unregistered scores", "concurrent real metadata processes",
    "playlist file/count/text bounds", "actual production query and exact filters",
)
FOCUS_CASES = (
    "normal restoration survives watcher delay exactly once",
    "interaction before worker success cancels its request",
    "interaction while waiting for reload cancels pending focus",
    "interaction after emission rejects queued delivery",
    "read-only reload inspection keeps the token",
    "newer action fences the old queued callback",
)
FOCUS_GROUP = "deferred action focus tickets in Qt event loop"
POSIX_SKIP = "SKIP actual symlink preservation on Windows: needs native reparse fixture"
SOURCES = (
    "src/project/internal/cadencesyncclient.cpp", "src/project/internal/cadencesyncclient.h",
    "test/cadence/sync_client/CMakeLists.txt", "test/cadence/sync_client/client_tests.cpp",
    "test/cadence/sync_client/service_fixture.py", "test/cadence/sync_client/reentrancy_tests.cpp",
    "src/project/internal/localscorelibrarystore.cpp", "src/project/internal/localscoreplaylist.h",
    "src/project/internal/locallibraryactionfocus.h", "test/cadence/local_library_store/metadata_tests.cpp",
)

def lines(text: str) -> list[str]:
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    return [re.sub(r"^\d+:\s?", "", line).strip() for line in text.splitlines()]

def ctest_success(text: str, tests: tuple[str, ...]) -> list[str]:
    rows = lines(text)
    summaries = [row for row in rows if re.fullmatch(r"\d+% tests passed, \d+ tests failed out of \d+", row)]
    if summaries != [f"100% tests passed, 0 tests failed out of {len(tests)}"]:
        raise ValueError("Expected one complete, successful CTest summary for " + ", ".join(tests))
    for test in tests:
        passed = [row for row in rows if re.search(r"\b" + re.escape(test) + r"\b.*\bPassed\s", row)]
        if len(passed) != 1:
            raise ValueError("Expected exactly one completed CTest case: " + test)
    if any(re.match(r"(?:FAIL\b|\*\*\*Failed)", row) for row in rows):
        raise ValueError("A native test emitted a failure")
    return rows

def metadata_observation(text: str, allow_posix_skip: bool) -> dict:
    rows = ctest_success(text, ("local_library_metadata",))
    expected = set(METADATA_GROUPS + FOCUS_CASES + (FOCUS_GROUP,))
    passed = [row[5:] for row in rows if row.startswith("PASS ")]
    if len(passed) != len(expected) or set(passed) != expected:
        raise ValueError("Metadata log must contain every reviewed group and all six focus cases exactly once")
    skipped = [row for row in rows if row.startswith("SKIP")]
    if skipped and (not allow_posix_skip or skipped != [POSIX_SKIP]):
        raise ValueError("Unexpected or unapproved metadata coverage skip")
    exceptions = ["symlink export preserves unregistered scores"] if skipped else []
    return {
        "kind": "metadata_and_focus_runtime", "reported_metadata_groups": len(METADATA_GROUPS),
        "executed_metadata_groups": len(METADATA_GROUPS) - len(exceptions),
        "focus_cases_passed": len(FOCUS_CASES), "focus_group_passed": True,
        "not_executed": exceptions, "skip_messages": skipped,
        "windows_reparse_point_runtime_validated": False,
        "gui_focus_validated": False,
    }

def sync_observation(text: str) -> dict:
    rows = ctest_success(text, ("cadence_sync_client_real_http", "cadence_sync_reentrancy_tests"))
    if any(row.startswith("SKIP") for row in rows):
        raise ValueError("Native sync qualification must not skip")
    counts = [int(match.group(1)) for row in rows if (match := re.fullmatch(
        r"PASS native Qt client: (\d+) checks;.*No GUI or musical rendering claimed\.", row))]
    if counts != [128]:
        raise ValueError("Expected the unchanged 128 real native HTTP checks exactly once")
    gates = [int(match.group(1)) for row in rows if (match := re.fullmatch(
        r"PASS native Qt reentrancy: (\d+) checks; pending=0 and server_hits=0 after synchronous start cancellation\.", row))]
    if gates != [35]:
        raise ValueError("Missing successful native synchronous-cancellation probe")
    return {"kind": "optional_sync_runtime", "real_http_checks_passed": 128,
            "reentrancy_checks_passed": gates[0], "pending_after_synchronous_cancel": 0,
            "server_hits_after_synchronous_cancel": 0, "https_remote_validated": False,
            "gui_validated": False, "musical_rendering_validated": False}

def identity(selection: dict, bootstrap: dict) -> dict:
    source = selection["source"]
    if selection["schema_version"] != 1 or bootstrap["schema_version"] != 1:
        raise ValueError("Unsupported source identity schema")
    for key in ("commit", "tree"):
        if not re.fullmatch(r"[a-f0-9]{40}", source[key]):
            raise ValueError("Expected full Git source identifiers")
    if not re.fullmatch(r"[a-f0-9]{64}", selection["patch"]["sha256"]):
        raise ValueError("Expected the frozen patch SHA-256")
    if source["commit"] != bootstrap["original_source_commit"] or source["tree"] != bootstrap["source_tree"] \
       or selection["patch"]["sha256"] != bootstrap["compressed_patch_sha256"]:
        raise ValueError("Native observations must use the exact reconstructed source")
    return {"source_commit": source["commit"], "source_tree": source["tree"]}

def source_observation(root: Path, tree: str) -> dict:
    actual = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD^{tree}"],
                            capture_output=True, text=True, check=True).stdout.strip()
    if actual != tree:
        raise ValueError("Native test source tree differs from the frozen selection")
    subprocess.run(["git", "-C", str(root), "diff", "--quiet", "HEAD", "--", *SOURCES], check=True)
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in SOURCES}

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("selection", "bootstrap", "source-root", "metadata-log", "sync-log", "output"):
        parser.add_argument("--" + arg, type=Path, required=True)
    parser.add_argument("--allow-windows-posix-symlink-skip", action="store_true")
    args = parser.parse_args()
    report = {"schema_version": 1, "observations_verified": False,
              "application_or_tests_executed_by_observer": False, "observations": [], "errors": []}
    try:
        raw = args.selection.read_bytes()
        report.update(identity(json.loads(raw.decode("utf-8-sig")), json.loads(args.bootstrap.read_text(encoding="utf-8-sig"))))
        report["selection_sha256"] = hashlib.sha256(raw).hexdigest()
        report["tested_source_sha256"] = source_observation(args.source_root, report["source_tree"])
        for kind, path in (("metadata", args.metadata_log), ("sync", args.sync_log)):
            data = path.read_bytes()
            observation = metadata_observation(data.decode("utf-8-sig"), args.allow_windows_posix_symlink_skip) if kind == "metadata" \
                else sync_observation(data.decode("utf-8-sig"))
            observation["log_sha256"] = hashlib.sha256(data).hexdigest()
            report["observations"].append(observation)
        report["observations_verified"] = True
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        report["errors"].append(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["observations_verified"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
