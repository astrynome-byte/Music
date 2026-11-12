#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare staged notice bytes with the actual source install rules.

A separate CMake project includes only CadenceNotices.cmake, with no compiler
or application target. Its small reference install is data for comparison, not
a substitute application. No program from the Cadence stage is executed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import time


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def cmake_path(path: Path) -> str:
    value = path.as_posix()
    if "]==]" in value or "\x00" in value or "\n" in value or "\r" in value:
        raise ValueError("Unsupported path for a literal CMake argument")
    return "[==[" + value + "]==]"


def build_expected(source: Path, output: Path, report: dict,
                   corresponding_bundle: Path | None = None,
                   corresponding_report_sha256: str | None = None) -> Path:
    cmake = shutil.which("cmake")
    if not cmake:
        raise ValueError("CMake is required for the exact notice install rules")
    project, build, expected = (output / name for name in ("notice-project", "notice-build", "expected-notices"))
    project.mkdir()
    # Only source notice/data install rules are evaluated. No source root CMake
    # project, compiler, SDK, target, executable or codec is configured here.
    (project / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.22)\n"
        "project(CadenceNoticeReference LANGUAGES NONE)\n"
        "set(CADENCE_BUILD ON)\n"
        "set(Mscore_SHARE_NAME \"\")\n"
        "set(Mscore_INSTALL_NAME \"\")\n"
        f"set(PROJECT_SOURCE_DIR {cmake_path(source)})\n"
        f"include({cmake_path(source / 'buildscripts/cmake/CadenceNotices.cmake')})\n",
        encoding="utf-8",
    )
    commands = [
        ("configure-notice-rules", [cmake, "-S", str(project), "-B", str(build),
                                    "-DCMAKE_INSTALL_PREFIX=" + str(expected)] + (
             ["-DCADENCE_CORRESPONDING_SOURCE_BUNDLE=" + str(corresponding_bundle),
              "-DCADENCE_CORRESPONDING_SOURCE_REPORT_SHA256=" + str(corresponding_report_sha256)]
             if corresponding_bundle is not None else [])),
        ("install-reference-notices", [cmake, "--install", str(build)]),
    ]
    for name, command in commands:
        record = {"name": name, "command": command, "exit_code": None, "timed_out": False}
        report["commands"].append(record)
        started = time.monotonic()
        try:
            with (output / (name + ".stdout.log")).open("xb") as stdout, \
                    (output / (name + ".stderr.log")).open("xb") as stderr:
                process = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=45, check=False)
                record["exit_code"] = process.returncode
        except subprocess.TimeoutExpired:
            record["timed_out"] = True
        record["elapsed_seconds"] = time.monotonic() - started
        if record["timed_out"] or record["exit_code"] != 0:
            raise ValueError("Notice-only CMake command failed: " + name)
    return expected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--stage-root", type=Path, required=True)
    parser.add_argument("--expected-executable-sha256", required=True)
    parser.add_argument("--corresponding-source-bundle", type=Path)
    parser.add_argument("--corresponding-source-report-sha256")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source, stage = args.source_root.resolve(strict=True), args.stage_root.resolve(strict=True)
    output = args.output.resolve()
    if output.is_relative_to(source) or output.is_relative_to(stage) or source.is_relative_to(output) or stage.is_relative_to(output):
        parser.error("Use a new output directory separate from source and application stage")
    output.mkdir(parents=True, exist_ok=False)
    report = {
        "schema_version": 1, "status": "failed", "passed": False,
        "scope": "Exact staged notice/data bytes, actual source CMake install rules and absence of development mnxdom archive",
        "platform": platform.platform(), "source_root": str(source), "stage_root": str(stage),
        "application_executed": False, "application_built_by_this_check": False,
        "all_transitive_license_audit_completed": False,
        "commands": [], "notices": [], "errors": [],
    }
    try:
        expected_hash = args.expected_executable_sha256
        if len(expected_hash) != 64 or any(c not in "0123456789abcdef" for c in expected_hash):
            raise ValueError("Require the authenticated current executable SHA-256")
        executable = stage / "bin/CadenceStudio4.exe"
        if not executable.is_file() or sha(executable) != expected_hash:
            raise ValueError("Stage executable differs from the authenticated current build result")
        report["executable_sha256"] = expected_hash
        module = source / "buildscripts/cmake/CadenceNotices.cmake"
        modules = {module: sha(module)}
        corresponding_bundle = None
        source_archive_names = set()
        if bool(args.corresponding_source_bundle) != bool(args.corresponding_source_report_sha256):
            raise ValueError("Provide the verified source bundle and its report SHA-256 together")
        if args.corresponding_source_bundle:
            corresponding_bundle = args.corresponding_source_bundle.resolve(strict=True)
            if corresponding_bundle.is_relative_to(stage) or stage.is_relative_to(corresponding_bundle):
                raise ValueError("Corresponding sources must remain outside the application runtime")
            expected_report_sha = args.corresponding_source_report_sha256
            if len(expected_report_sha) != 64 or any(c not in "0123456789abcdef" for c in expected_report_sha):
                raise ValueError("Require the authenticated corresponding-source report SHA-256")
            source_report_path = corresponding_bundle / "collection-report.json"
            if sha(source_report_path) != expected_report_sha:
                raise ValueError("Corresponding-source report differs from the verified build input")
            corresponding_module = source / "buildscripts/cmake/CadenceCorrespondingNotices.cmake"
            modules[corresponding_module] = sha(corresponding_module)
            source_lock = json.loads((corresponding_bundle / "sources.lock.json").read_text(encoding="utf-8"))
            source_archive_names = {record["archive"].casefold() for record in source_lock["archives"]}
            report["corresponding_source_report_sha256"] = expected_report_sha
            report["corresponding_sources_remain_companion_files"] = True
        report["source_notice_modules"] = {path.relative_to(source).as_posix(): value for path, value in modules.items()}
        expected = build_expected(source, output, report, corresponding_bundle,
                                  args.corresponding_source_report_sha256)
        expected_files = sorted(path for path in expected.rglob("*") if path.is_file())
        names = {path.relative_to(expected).as_posix() for path in expected_files}
        required = {"doc/LICENSE.txt", "doc/NOTICE-FR.md", "doc/source-license-inventory.json", "licenses/README.fr.txt"}
        if corresponding_bundle is not None:
            required.update({"doc/corresponding-sources/sources.lock.json",
                             "doc/corresponding-sources/collection-report.json"})
            if not any(name.startswith("licenses/corresponding/") for name in names):
                raise ValueError("Source install rules omitted the requested original corresponding-source notices")
        if not required.issubset(names) or any(path.is_symlink() for path in expected_files):
            raise ValueError("Actual source install rules do not provide the required plain notice files")
        if any(path.name == ".gitattributes" for path in expected_files):
            raise ValueError("Development Git attributes must not be installed as a notice")
        guides = [path for path in stage.rglob("NOTICE-FR.md") if path.is_file() and path.parent.name == "doc"]
        if len(guides) != 1:
            raise ValueError("Expected exactly one installed doc/NOTICE-FR.md in the real application stage")
        data_root = guides[0].parent.parent
        report["stage_notice_data_root"] = data_root.relative_to(stage).as_posix()
        for reference in expected_files:
            relative = reference.relative_to(expected)
            actual = data_root / relative
            if not actual.is_file() or actual.is_symlink():
                raise ValueError("Missing or linked staged notice: " + relative.as_posix())
            expected_sha = sha(reference)
            actual_sha = sha(actual)
            if actual.stat().st_size != reference.stat().st_size or actual_sha != expected_sha:
                raise ValueError("Staged notice differs from the actual source install rules: " + relative.as_posix())
            report["notices"].append({
                "stage_path": actual.relative_to(stage).as_posix(), "bytes": actual.stat().st_size,
                "sha256": actual_sha,
            })
        archives = [path.relative_to(stage).as_posix() for path in stage.rglob("*")
                    if path.is_file() and path.name.lower() == "mnxdom.lib"]
        report["mnxdom_development_archives_found"] = archives
        if archives:
            raise ValueError("The Cadence runtime stage must not include the MNX development static library")
        leaked_sources = [path.relative_to(stage).as_posix() for path in stage.rglob("*")
                          if path.is_file() and path.name.casefold() in source_archive_names]
        report["corresponding_source_archives_found_in_runtime"] = leaked_sources
        if leaked_sources:
            raise ValueError("Original corresponding-source archives must remain companion files outside the runtime")
        if sha(executable) != expected_hash or any(sha(path) != value for path, value in modules.items()):
            raise ValueError("Executable or source notice rules changed during the read-only comparison")
        report["notice_files_verified"] = len(report["notices"])
        report["expected_count_source"] = "Real standalone install of the current CadenceNotices.cmake; no constant count"
        report["passed"] = True
        report["status"] = "passed_staged_notice_bytes_and_development_archive_exclusion"
        (output / "stage-notices-sha256.txt").write_text(
            "".join(item["sha256"] + "  " + item["stage_path"] + "\n" for item in report["notices"]),
            encoding="utf-8",
        )
    except (OSError, ValueError) as error:
        report["errors"].append(str(error))
    (output / "stage-notices-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("CADENCE_STAGE_NOTICES_REPORT_BEGIN")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    print("CADENCE_STAGE_NOTICES_REPORT_END")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
