#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Run the upstream large-score CLI sequence with Windows process evidence.

The original harness is copied verbatim and supplies corpus/output validators.
No GUI, playback, listening, performance target, or source-tree write is tested.
"""
from __future__ import annotations

import argparse
import base64
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import struct
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

HERE = Path(__file__).resolve().parent
EXE_SHA = "0aba4ced85a18a781c76c27f0072f2a761f7dee87f73610493887790f38fdb6a"
FIXTURE_SHA = "9086e86d9f59334c4aa691ea3b30b63c1d04676e96aa58993fc53178e3ec500d"
HARNESS_SHA = "f701874e7a37b8d3148f0bb99477b60b96865e804ed238372d75c06598027d82"
POLL_SECONDS = 0.05


def sha(path):
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def guard():
    if (sys.platform != "win32" or os.name != "nt" or struct.calcsize("P") != 8
            or platform.machine().upper() != "AMD64"
            or os.environ.get("OS") != "Windows_NT"
            or any(os.environ.get(key) != "true" for key in ("GITHUB_ACTIONS", "CI"))
            or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"):
        raise ValueError("Only disposable native Windows x64 GitHub-hosted runners are permitted.")
    if not os.environ.get("RUNNER_TEMP"):
        raise ValueError("RUNNER_TEMP is required.")


def below(path, parent):
    return path != parent and parent in path.parents


def safe_path(value):
    path = Path(os.path.abspath(value))
    for ancestor in (path, *path.parents):
        try:
            info = ancestor.lstat()
        except FileNotFoundError:
            continue
        if info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError(f"Reparse points are forbidden: {ancestor}")
    return path


class ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
        (name, ctypes.c_size_t) for name in (
            "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
            "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
            "PagefileUsage", "PeakPagefileUsage")]


class WindowsMemory:
    def __init__(self):
        self.api = ctypes.WinDLL("psapi", use_last_error=True).GetProcessMemoryInfo
        self.api.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessMemoryCounters), wintypes.DWORD]
        self.api.restype = wintypes.BOOL

    def read(self, process):
        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        # CPython's existing Popen handle belongs to this exact child. No PID
        # search, other-process handle, or process-tree termination is used.
        if not self.api(wintypes.HANDLE(int(process._handle)), ctypes.byref(counters), counters.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return counters.PeakWorkingSetSize


def score_structure(root, expected_parts):
    if root.tag != "museScore":
        raise ValueError("Native museScore XML root expected")
    score = root.find("Score")
    if score is None:
        raise ValueError("Native Score missing")
    staffs = score.findall("Staff")
    counts = [len(staff.findall("Measure")) for staff in staffs]
    notes = len(score.findall(".//Note"))
    if len(score.findall("Part")) != expected_parts or len(staffs) != expected_parts or counts != [256] * expected_parts or not notes:
        raise ValueError(f"Unexpected native structure: parts={len(score.findall('Part'))}, measures={counts}, notes={notes}")
    return {"parts": expected_parts, "staffs": len(staffs), "measures_per_staff": counts, "notes": notes}


def zipped_root(path):
    with zipfile.ZipFile(path) as archive:
        container = ET.fromstring(archive.read("META-INF/container.xml"))
        roots = [item.attrib.get("full-path") for item in container.iter() if item.tag.rsplit("}", 1)[-1] == "rootfile"]
        if not roots or not roots[0] or roots[0] not in archive.namelist():
            raise ValueError("Missing root score ZIP member")
        return ET.fromstring(archive.read(roots[0]))


def inspect(path, extension, harness, expected_parts=16):
    result = harness.inspect_output(path, extension)
    if extension == "mscz":
        result["structure"] = score_structure(zipped_root(path), expected_parts)
    elif extension == "mscx":
        result["structure"] = score_structure(ET.parse(path).getroot(), expected_parts)
    elif extension == "pdf":
        with path.open("rb") as source:
            source.seek(max(0, path.stat().st_size - 1024))
            if b"%%EOF" not in source.read():
                raise ValueError("PDF lacks final EOF marker")
    elif extension == "mxl":
        root = zipped_root(path)
        parts = root.findall("part")
        counts = [len(part.findall("measure")) for part in parts]
        if root.tag != "score-partwise" or len(parts) != 16 or counts != [256] * 16:
            raise ValueError("MXL lacks the complete 16-part, 256-measure score")
        result["structure"] = {"parts": len(parts), "measures_per_part": counts}
    elif extension == "mid":
        payload = path.read_bytes()
        if len(payload) < 14 or int.from_bytes(payload[4:8], "big") != 6:
            raise ValueError("Invalid MIDI header length")
        tracks = int.from_bytes(payload[10:12], "big")
        offset = 14
        for _ in range(tracks):
            if payload[offset:offset + 4] != b"MTrk" or offset + 8 > len(payload):
                raise ValueError("Missing MIDI track")
            size = int.from_bytes(payload[offset + 4:offset + 8], "big")
            offset += 8 + size
            if not size or offset > len(payload) or payload[offset - 3:offset] != b"\xff\x2f\x00":
                raise ValueError("Truncated/empty MIDI track or missing end-of-track")
        if not tracks or offset != len(payload) or int.from_bytes(payload[12:14], "big") == 0:
            raise ValueError("Invalid MIDI track count, division, or trailing bytes")
        result["tracks"] = tracks
    return result


def main():
    guard()  # No writes, module loading, DLL access, or child process before guard.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--restoration-record", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    temp = safe_path(os.environ["RUNNER_TEMP"])
    stage, restoration, output = map(safe_path, (args.stage, args.restoration_record, args.output))
    if any(not below(path, temp) for path in (stage, restoration, output)):
        raise ValueError("Every runtime path must be strictly below RUNNER_TEMP")
    if (output.exists() or stage == output or below(output, stage) or below(stage, output)
            or below(restoration, output)):
        raise ValueError("Output must be new and separate from stage and restoration record")
    output.mkdir(parents=True, exist_ok=False)
    report = {"schema_version": 1, "status": "blocked", "phase": "preflight", "error": None,
              "started_utc": utc(), "finished_utc": None, "application_executed": False,
              "gui_editing_tested": False, "playback_tested": False, "human_listening_performed": False,
              "source_run_id": 42793810996, "source_artifact_id": 13755702885, "build_number": 1001,
              "original_source_commit": "76b51af495b721776945717a812e1de2394a689a",
              "source_tree": "59d63e6f93b3bb7e8e5291cf57f57f9c5d61a06b",
              "commands": [], "checks": [], "metrics_blocked": False,
              "memory_method": "Windows GetProcessMemoryInfo/PROCESS_MEMORY_COUNTERS.PeakWorkingSetSize, bytes, owned CPython Popen process handle",
              "memory_poll_interval_seconds": POLL_SECONDS,
              "limits": ["CLI import/save/reopen/exports only; no interactive editing, playback, listening, or visual correctness claim",
                         "Process elapsed wall time includes creation and observation of exit; 50 ms polling plus scheduling may delay exit observation; validation time is separate; no performance gate",
                         "PeakWorkingSetSize is the kernel high-water mark through the last successful query; a failed final query may omit the final interval",
                         "Polling queries the kernel peak, not a sampled maximum of current WorkingSet; no private bytes, total machine memory, child-process or GPU memory",
                         "PDF signature/EOF, native/MXL structure, MIDI chunks, ZIP CRC and part reopening do not establish musical or visual fidelity",
                         "Only the owned direct child is terminated on timeout; no other process is searched or killed"]}

    def save():
        (output / "large-qa-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    try:
        fixture = HERE / "fixtures/large.musicxml"
        executable = stage / "bin/CadenceStudio4.exe"
        for path in (fixture, executable, restoration, HERE / "upstream_run_exports.py"):
            safe_path(path)
        if sha(executable) != EXE_SHA or sha(fixture) != FIXTURE_SHA or sha(HERE / "upstream_run_exports.py") != HARNESS_SHA:
            raise ValueError("Pinned executable, corpus, or original harness digest mismatch")
        record = json.loads(restoration.read_text(encoding="utf-8-sig"))
        expected = {"status": "retained-stage-restored-sha256-verified", "repository": "astrynome-byte/Music",
                    "original_run_id": 42793810996, "original_artifact_id": 13755702885, "build_number": 1001,
                    "original_source_commit": report["original_source_commit"], "source_tree": report["source_tree"],
                    "executable_sha256": EXE_SHA, "application_recompiled": False}
        if any(record.get(key) != value for key, value in expected.items()) or safe_path(record["stage_path"]) != stage or safe_path(record["executable_path"]) != executable:
            raise ValueError("Restoration record does not authenticate the selected retained stage")
        spec = importlib.util.spec_from_file_location("cadence_original_exports", HERE / "upstream_run_exports.py")
        harness = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(harness)
        fixture_info = harness.validate_fixtures()
        if len(fixture_info) != 1 or fixture_info[0]["id"] != "large":
            raise ValueError("Only the original large corpus is selected")
        report.update(executable=str(executable), executable_sha256=sha(executable),
                      stage_restoration_sha256=sha(restoration), fixture=fixture_info[0], harness_sha256=HARNESS_SHA)
        memory = WindowsMemory()  # Missing Windows API blocks before launching Cadence.
        app_env = {key: value for key, value in os.environ.items() if not re.match(
            r"(?i)^(QT|QML|CMAKE_|VCPKG_|VSCMD_|VSINSTALLDIR$|VCINSTALLDIR$|VCTools|INCLUDE$|LIB$|LIBPATH$|WindowsSdk|UniversalCRTSdkDir$|UCRTVersion$|DevEnvDir$|ExtensionSdkDir$|FrameworkDir|FrameworkVersion|.*_PROXY$|GITHUB_|GH_TOKEN$|ACTIONS_|AZURE_|AWS_|GOOGLE_|OPENAI_)", key)}
        app_env["PATH"] = str(executable.parent) + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32")
        app_env["TEMP"] = app_env["TMP"] = str(output / "temp")
        (output / "temp").mkdir()
        report["application_path"] = app_env["PATH"]
        copied = output / "large-input.musicxml"
        shutil.copy2(fixture, copied)
        report["input_copy_sha256"] = sha(copied)
        if report["input_copy_sha256"] != FIXTURE_SHA:
            raise ValueError("Copied input digest mismatch")

        suite_deadline = time.perf_counter() + 17 * 60
        report["suite_time_budget_seconds"] = 17 * 60

        def run(name, arguments, destination=None, extension=None, validate=None, timeout=180):
            report["phase"] = name
            item = {"stage": name, "arguments": [str(arg) for arg in arguments], "pid": None,
                    "timeout_seconds": timeout, "timed_out": False, "exit_code": None,
                    "elapsed_seconds": None, "passed": False, "outputs": [],
                    "stdout": name + ".stdout.log", "stderr": name + ".stderr.log",
                    "peak_working_set_bytes": None, "memory_query_count": 0,
                    "memory_query_errors": [], "last_memory_query_seconds": None,
                    "final_memory_query_succeeded": False, "cleanup_error": None}
            report["commands"].append(item)
            if destination is not None:
                report["checks"].append(item)
            stage_clock = time.perf_counter()
            clock = None
            process = None

            def query(final=False):
                try:
                    peak = memory.read(process)
                    item["peak_working_set_bytes"] = max(item["peak_working_set_bytes"] or 0, peak)
                    item["memory_query_count"] += 1
                    item["last_memory_query_seconds"] = time.perf_counter() - clock
                    if final:
                        item["final_memory_query_succeeded"] = True
                except OSError as error:
                    # Preserve bounded error evidence without suppressing missing metrics.
                    if len(item["memory_query_errors"]) < 4:
                        item["memory_query_errors"].append({"final": final, "error": str(error)})
            try:
                remaining = suite_deadline - time.perf_counter()
                if remaining <= 0:
                    raise ValueError("Suite time budget exhausted; command not launched")
                item["timeout_seconds"] = min(timeout, remaining)
                if sha(executable) != EXE_SHA:
                    raise ValueError("Executable changed before launch")
                with (output / item["stdout"]).open("xb") as stdout, (output / item["stderr"]).open("xb") as stderr:
                    clock = time.perf_counter()
                    process = subprocess.Popen([str(executable), *item["arguments"]], cwd=output, env=app_env,
                                               stdout=stdout, stderr=stderr, stdin=subprocess.DEVNULL, shell=False)
                    item["pid"] = process.pid
                    report["application_executed"] = True
                    while True:
                        query()
                        if process.poll() is not None:
                            break
                        if time.perf_counter() - clock >= item["timeout_seconds"]:
                            item["timed_out"] = True
                            process.kill()  # Only our Popen child; never a PID/name search.
                            break
                        time.sleep(POLL_SECONDS)
                    item["exit_code"] = process.wait(timeout=10)
                    item["elapsed_seconds"] = time.perf_counter() - clock
                    query(final=True)
                if not item["memory_query_count"] or not item["peak_working_set_bytes"]:
                    report["metrics_blocked"] = True
                    raise ValueError("Windows process-memory measurement unavailable; no peak is inferred")
                if item["timed_out"] or item["exit_code"] != 0:
                    raise ValueError("Owned process timed out" if item["timed_out"] else f"CLI exit {item['exit_code']}")
                if destination is not None:
                    item["outputs"] = [inspect(destination, extension, harness)] if extension else validate()
                elif b"4.7.6" not in (output / item["stdout"]).read_bytes() + (output / item["stderr"]).read_bytes():
                    raise ValueError("Long version does not identify 4.7.6")
                item["passed"] = True
            except Exception as error:
                item["error"] = f"{type(error).__name__}: {error}"
            finally:
                if process is not None and process.poll() is None:
                    try:
                        process.kill()
                        process.wait(timeout=10)
                    except (OSError, subprocess.TimeoutExpired) as error:
                        item["cleanup_error"] = str(error)
                        item["passed"] = False
                if process is not None and item["elapsed_seconds"] is None:
                    item["elapsed_seconds"] = time.perf_counter() - clock
                item["stage_elapsed_seconds"] = time.perf_counter() - stage_clock
                item["memory_coverage"] = ("unavailable" if not item["memory_query_count"] else
                                           "through_exit" if item["final_memory_query_succeeded"] else "through_last_successful_query")
                save()
                print(f"{name}: {'PASS' if item['passed'] else 'FAIL'}; process_seconds={item['elapsed_seconds']}; peak_working_set_bytes={item['peak_working_set_bytes']}", flush=True)
            return item["passed"]

        if not run("version", ["--long-version"], timeout=30):
            raise ValueError("Version or version-process measurement failed; no score command launched")
        native = output / "saved.mscz"
        if not run("import-save-native", ["--test-mode", "-o", native, copied], native, "mscz"):
            raise ValueError("Native import/save precondition failed; no dependent exports or parts launched")
        reopened = output / "reopened.mscx"
        run("reopen-native", ["--test-mode", "-o", reopened, native], reopened, "mscx")
        for extension in ("pdf", "mid", "mxl"):
            destination = output / ("export." + extension)
            job = output / (extension + "-job.json")
            job.write_text(json.dumps([{"in": str(native), "out": str(destination)}]) + "\n", encoding="utf-8")
            run("export-" + extension, ["--test-mode", "--sound-profile", "MuseScore Basic", "-j", job], destination, extension)
        parts_json = output / "native-parts.json"
        decoded_parts = []

        def validate_parts():
            checked = harness.inspect_output(parts_json, "json")
            parts = json.loads(parts_json.read_text(encoding="utf-8"))
            if len(parts["parts"]) != 16 or len(parts["partsBin"]) != 16:
                raise ValueError("Exactly 16 materialized native parts are required")
            results = [checked]
            for index, encoded in enumerate(parts["partsBin"], 1):
                part = output / f"part-{index:02d}.mscz"
                with part.open("xb") as stream:
                    stream.write(base64.b64decode(encoded, validate=True))
                results.append(inspect(part, "mscz", harness, expected_parts=1))
                decoded_parts.append(part)
            return results

        # Critical native precondition: --score-parts never receives MusicXML.
        if run("extract-native-parts", ["--score-parts", "-o", parts_json, native], parts_json, validate=validate_parts):
            for index, part in enumerate(decoded_parts, 1):
                destination = output / f"part-{index:02d}.pdf"
                run(f"part-{index:02d}-reopen-pdf", ["-o", destination, part], destination, "pdf", timeout=60)
        report["expected_checks"] = 22
        report["completed_checks"] = len(report["checks"])
        report["fixture_original_unchanged"] = sha(fixture) == FIXTURE_SHA
        report["input_copy_unchanged"] = sha(copied) == FIXTURE_SHA
        report["executable_unchanged"] = sha(executable) == EXE_SHA
        report["status"] = ("blocked" if report["metrics_blocked"] else "passed" if len(report["checks"]) == 22
                            and all(item["passed"] for item in report["commands"])
                            and all(report[key] for key in ("fixture_original_unchanged", "input_copy_unchanged", "executable_unchanged")) else "failed")
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
        report["status"] = "blocked" if not report["application_executed"] or report["metrics_blocked"] else "failed"
    finally:
        report["finished_utc"] = utc()
        save()
        files = sorted(path for path in output.rglob("*") if path.is_file() and path.name != "SHA256SUMS.txt")
        (output / "SHA256SUMS.txt").write_text("".join(f"{sha(path)}  {path.relative_to(output).as_posix()}\n" for path in files), encoding="utf-8")
        print("CADENCE_LARGE_QA_REPORT_BEGIN")
        print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
        print("CADENCE_LARGE_QA_REPORT_END")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(f"BLOCKED before runtime output: {error}", file=sys.stderr)
        raise SystemExit(1)
