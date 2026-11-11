#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Read existing CI evidence only. Invoke with python -I (filename is inspect.py)."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import zipfile


MAX_JSON = 256_000
MAX_REPORTS = 16
MAX_LOG = 16_000_000
MAX_MEMBERS = 128
MAX_LOG_TEXT = 8_000_000
MAX_EXCERPT_LINES = 100
ERROR = re.compile(r"Traceback|\bERROR\b|\b\w*(?:Error|Exception)\b|##\[error\]|fatal:|error:|failed with", re.I)
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def safe_log(value, limit=1500):
    value = ANSI.sub("", value)
    value = re.sub(r"(?:github_pat_[A-Za-z0-9_]+|gh[pousr]_[A-Za-z0-9_]+)", "[REDACTED]", value)
    value = re.sub(r"(?i)(authorization\s*[:=]\s*)(?:bearer\s+|token\s+)?\S+", r"\1[REDACTED]", value)
    value = re.sub(r"(?i)((?:GH_TOKEN|GITHUB_TOKEN|password|secret)\s*[:=]\s*)\S+", r"\1[REDACTED]", value)
    value = re.sub(r"(https?://[^\s?]+)\?[^\s]+", r"\1?[REDACTED]", value)
    return "".join(c for c in value if c.isprintable() or c == "\t")[:limit]


def ascii_summary(value):
    value = safe_log(value, 2000).encode("ascii", "replace").decode("ascii")
    return " ".join(value.split())[:180]


def log_documents(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("Job log file missing or symlink excluded")
    if path.stat().st_size > MAX_LOG:
        raise ValueError("Job log exceeds 16 MB reader limit")
    raw = path.read_bytes()
    metadata = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "format": "plain"}
    if raw.startswith(b"PK"):
        metadata["format"] = "zip"
        documents = []
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = [m for m in archive.infolist() if not m.is_dir()]
            if len(members) > MAX_MEMBERS or sum(m.file_size for m in members) > MAX_LOG_TEXT:
                raise ValueError("Job log ZIP exceeds bounded member/expanded-size limits")
            for member in members:
                if member.file_size > MAX_LOG_TEXT or member.flag_bits & 1:
                    raise ValueError("Oversized or encrypted job log member excluded")
                # Read ZIP members in memory only; never extract or execute a file.
                documents.append((safe_log(member.filename, 250), archive.read(member).decode("utf-8-sig", errors="replace")))
        return metadata, documents
    if len(raw) > MAX_LOG_TEXT:
        raise ValueError("Plain job log exceeds 8 MB text limit")
    return metadata, [("job-log", raw.decode("utf-8-sig", errors="replace"))]


def inspect_logs(path, fetch_status):
    result = {"source_run_id": 43094504840, "source_job_id": 130779749675,
              "fetch_status": fetch_status, "reader_status": "unavailable", "first_error": None,
              "excerpts": [], "errors": [], "note": "Existing failed job only; no new zlib build or test"}
    if fetch_status != "success":
        result["errors"].append("GitHub CLI could not retrieve the existing job log")
        return result
    try:
        result["log"], documents = log_documents(path)
        remaining = MAX_EXCERPT_LINES
        for name, text in documents:
            lines = text.splitlines()
            matches = [i for i, line in enumerate(lines) if ERROR.search(line)]
            selected = set()
            for index in matches:
                selected.update(range(max(0, index - 2), min(len(lines), index + 6)))
                if len(selected) >= remaining:
                    break
            excerpt = [{"line": i + 1, "text": safe_log(lines[i])} for i in sorted(selected)[:remaining]]
            remaining -= len(excerpt)
            if excerpt:
                result["excerpts"].append({"member": name, "lines": excerpt})
            # Prefer an actual exception message over the generic Traceback header
            # or a shell command containing the word "error".
            if result["first_error"] is None:
                for index in matches:
                    clean = re.sub(r"^\d{4}-\d\d-\d\dT\S+\s+", "", lines[index]).strip()
                    if re.search(r"^(?:\w*(?:Error|Exception):|##\[error\]|ERROR\b|fatal:|error:)", clean, re.I):
                        result["first_error"] = safe_log(clean)
                        break
            if remaining <= 0:
                break
        if result["first_error"] is None and result["excerpts"]:
            result["first_error"] = "Traceback/error marker found; inspect retained excerpts"
        result["reader_status"] = "read"
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as error:
        result["errors"].append(safe_log(str(error)))
    return result


def inspect_coexistence(root):
    result = {"source_run_id": 43094504811, "source_job_id": 130779790459,
              "source_artifact_id": 13890845538, "source_artifact_name": "cadence-coexistence-qa-1-1",
              "status": "unavailable", "reports": [], "errors": []}
    if not root.is_dir():
        result["errors"].append("Downloaded coexistence artifact directory missing")
        return result
    candidates = sorted(root.rglob("coex*.json"))
    if len(candidates) > MAX_REPORTS:
        result["errors"].append("More than sixteen coexistence reports; reader stopped")
        return result
    for path in candidates:
        relative = path.relative_to(root).as_posix()
        if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
            result["errors"].append("Non-regular/outside-root report excluded: " + relative)
            continue
        if path.stat().st_size > MAX_JSON:
            result["errors"].append("Report exceeds 256 KB limit: " + relative)
            continue
        try:
            raw = path.read_bytes()
            report = json.loads(raw.decode("utf-8-sig"))
            entry = {"path": relative, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "report": report}
            result["reports"].append(entry)
            print("CADENCE_COEXISTENCE_EVIDENCE_BEGIN")
            print(json.dumps(entry, ensure_ascii=True, sort_keys=True))
            print("CADENCE_COEXISTENCE_EVIDENCE_END")
        except (OSError, ValueError, UnicodeError) as error:
            result["errors"].append("Invalid report " + relative + ": " + safe_log(str(error)))
    main = [e["report"] for e in result["reports"] if Path(e["path"]).name == "coexistence-report.json"]
    if len(main) != 1 or not isinstance(main[0], dict) or main[0].get("schema_version") != 1:
        result["errors"].append("Expected exactly one schema-1 coexistence-report.json")
    else:
        report = main[0]
        result["status"] = str(report.get("status", "missing_status"))
        required = ("after_cadence_install_preserved", "after_cadence_uninstall_preserved", "cadence_removed", "official_removed")
        if result["status"] == "passed" and (any(report.get(key) is not True for key in required) or report.get("errors")):
            result["errors"].append("Reported PASS contradicts preservation/cleanup fields")
            result["status"] = "inconsistent_pass"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--zlib-log", required=True, type=Path)
    parser.add_argument("--zlib-fetch-status", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root, output = args.root.resolve(), args.output.resolve()
    if output.exists() or output == root or output.is_relative_to(root):
        parser.error("Output directory must be new and outside the downloaded artifact")
    coexistence = inspect_coexistence(root)
    try:
        fetch_status = args.zlib_fetch_status.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        fetch_status = "unavailable"
    zlib = inspect_logs(args.zlib_log, fetch_status)
    short = ascii_summary("coex=" + coexistence["status"] + "; zlib=" + (zlib["first_error"] or ("no error message found" if zlib["reader_status"] == "read" else "job log unavailable")))
    summary = {"schema_version": 1, "scope": "Read existing own-repository GitHub Actions reports/logs only",
               "reader_only": True, "application_executed": False, "codec_executed": False,
               "system_probe_executed": False, "audio_bytes_printed": False, "human_listening": False,
               "coexistence": coexistence, "zlib": zlib, "workflow_step_summary": short,
               "source_execution_repeated": False}
    output.mkdir(parents=True)
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print("CADENCE_CI_EVIDENCE_SUMMARY_BEGIN")
    print(json.dumps(summary, ensure_ascii=True, sort_keys=True))
    print("CADENCE_CI_EVIDENCE_SUMMARY_END")
    destination = os.environ.get("GITHUB_OUTPUT")
    if destination:
        with open(destination, "a", encoding="utf-8") as stream:
            stream.write("summary=" + short + "\n")
    print(short)
    # Successful diagnostic production does not certify the original jobs.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
