#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Print bounded existing UIA evidence; never launch the application or inspector."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re

MAX_JSON_BYTES = 1_000_000
MAX_PNG_BASE64_BYTES = 2_000_000
MAX_FILES = 128
MAX_LOG_BYTES = 32_000
REPORT_NAMES = {"uia-report.json", "library-ui-report.json", "stage-restoration.json",
                "stage-manifest.json", "cadence-build-result.json"}
LOG_NAMES = {"application.stdout.log", "application.stderr.log", "probe.stdout.log",
             "probe.stderr.log", "compile.log"}


def emit(label, value):
    print("CADENCE_UI_EVIDENCE_" + label + "_BEGIN")
    print(json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True))
    print("CADENCE_UI_EVIDENCE_" + label + "_END")


def sanitize(text):
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    text = re.sub(r"(?:github_pat_[A-Za-z0-9_]+|gh[pousr]_[A-Za-z0-9_]+)", "[REDACTED]", text)
    text = re.sub(r"(?i)(authorization\s*[:=]\s*)(?:bearer\s+|token\s+)?\S+", r"\1[REDACTED]", text)
    text = re.sub(r"(https?://[^\s?]+)\?[^\s]+", r"\1?[REDACTED]", text)
    return "".join(c for c in text if c.isprintable() or c in "\n\t")


def read(root):
    summary = {"schema_version": 1, "source_run_id": 43101086728, "source_artifact_id": 13891631675,
               "scope": "Read already completed retained-stage UIA reports and captures only",
               "reader_only": True, "application_executed": False, "uia_executed": False,
               "source_validation_repeated": False, "ui_validation_inferred_from_reading": False,
               "json_print_limit_bytes": MAX_JSON_BYTES, "png_base64_print_limit_bytes": MAX_PNG_BASE64_BYTES,
               "json_printed_bytes": 0, "png_base64_printed_bytes": 0,
               "files": [], "errors": [], "source_ui_status": None}
    if not root.is_dir():
        summary["errors"].append("Downloaded artifact directory missing")
        return summary
    paths = sorted(root.rglob("*"))
    if len(paths) > MAX_FILES:
        summary["errors"].append("Artifact exceeds bounded 128 member reader limit")
        return summary
    for path in paths:
        if path.is_dir() and not path.is_symlink():
            continue
        relative = path.relative_to(root).as_posix()
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
            summary["errors"].append("Excluded non-regular/outside-root member: " + relative)
            continue
        entry = {"path": relative, "bytes": path.stat().st_size}
        summary["files"].append(entry)
        name = path.name
        if name in REPORT_NAMES or (name.startswith("tree-") and path.suffix == ".json"):
            if entry["bytes"] > MAX_JSON_BYTES:
                entry["printed"] = False
                summary["errors"].append("Oversized JSON excluded: " + relative)
                continue
            try:
                raw = path.read_bytes()
                document = json.loads(raw.decode("utf-8-sig"))
                entry["sha256"] = hashlib.sha256(raw).hexdigest()
                envelope = {"path": relative, "bytes": len(raw), "sha256": entry["sha256"], "report": document}
                printed_size = len(json.dumps(envelope, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("ascii"))
                if summary["json_printed_bytes"] + printed_size > MAX_JSON_BYTES:
                    entry["printed"] = False
                    summary["errors"].append("JSON total print budget reached: " + relative)
                    continue
                emit("JSON", envelope)
                summary["json_printed_bytes"] += printed_size
                entry["printed"] = True
                if name == "library-ui-report.json" and isinstance(document, dict):
                    summary["source_ui_status"] = document.get("status")
            except (OSError, ValueError, UnicodeError) as error:
                summary["errors"].append("Invalid JSON " + relative + ": " + str(error)[:200])
        elif path.suffix.lower() == ".png":
            encoded_size = 4 * ((entry["bytes"] + 2) // 3)
            if summary["png_base64_printed_bytes"] + encoded_size > MAX_PNG_BASE64_BYTES:
                entry["printed"] = False
                summary["errors"].append("PNG total base64 print budget reached: " + relative)
                continue
            raw = path.read_bytes()
            if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
                summary["errors"].append("Invalid PNG signature excluded: " + relative)
                continue
            entry["sha256"] = hashlib.sha256(raw).hexdigest()
            emit("PNG", {"path": relative, "bytes": len(raw), "sha256": entry["sha256"],
                         "base64": base64.b64encode(raw).decode("ascii")})
            summary["png_base64_printed_bytes"] += encoded_size
            entry["printed"] = True
        elif name in LOG_NAMES:
            with path.open("rb") as stream:
                stream.seek(max(0, entry["bytes"] - MAX_LOG_BYTES))
                raw = stream.read(MAX_LOG_BYTES)
            emit("LOG", {"path": relative, "tail_only": entry["bytes"] > MAX_LOG_BYTES,
                         "text": sanitize(raw.decode("utf-8-sig", errors="replace"))})
            entry["printed"] = True
    if summary["source_ui_status"] is None:
        summary["errors"].append("No source library-ui-report.json was read")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.root.resolve(), args.output.resolve()
    if args.root.is_symlink() or output.exists() or output == root or output.is_relative_to(root):
        parser.error("Input must not be symlink; output must be new and outside artifact")
    result = read(root)
    output.mkdir(parents=True)
    (output / "summary.json").write_text(json.dumps(result, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    emit("SUMMARY", result)
    destination = os.environ.get("GITHUB_OUTPUT")
    if destination:
        with open(destination, "a", encoding="utf-8") as stream:
            stream.write("source_status=" + re.sub(r"[^A-Za-z0-9_]", "_", str(result["source_ui_status"]))[:120] + "\n")
    # A successful reader never certifies the original UI inspection.
    return 0 if not result["errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
