#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Read reports and hash existing AAC bytes; never run or decode a codec.

Invoke with python -I to prevent this file's name from shadowing the standard
library inspect module for any imports. Only the downloaded artifact is read.
"""
import argparse
import hashlib
import json
from pathlib import Path


MAX_JSON_BYTES = 100_000


def fingerprint(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--artifact-id", type=int, required=True)
    parser.add_argument("--artifact-name", required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output.resolve()
    if not root.is_dir() or output == root or output.is_relative_to(root):
        parser.error("Existing artifact directory and a separate summary output directory are required")
    output.mkdir(parents=True, exist_ok=True)
    summary = {
        "schema_version": 1,
        "source_run_id": args.run_id,
        "source_artifact_id": args.artifact_id,
        "source_artifact_name": args.artifact_name,
        "reader_only": True,
        "codec_executed_by_reader": False,
        "audio_reencoded_by_reader": False,
        "audio_bytes_printed": False,
        "human_listening": False,
        "passed": False,
        "reports": [],
        "aac_files": [],
        "skipped_large_json": [],
        "errors": [],
    }
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            summary["errors"].append("Symlink excluded: " + path.relative_to(root).as_posix())
            continue
        if not path.is_file():
            continue
        if not path.resolve().is_relative_to(root):
            summary["errors"].append("File outside artifact root")
            continue
        relative = path.relative_to(root).as_posix()
        if path.suffix.lower() == ".json":
            if path.stat().st_size > MAX_JSON_BYTES:
                summary["skipped_large_json"].append(relative)
                continue
            raw = path.read_bytes()
            try:
                report = json.loads(raw.decode("utf-8-sig"))
            except (UnicodeError, ValueError) as error:
                summary["errors"].append("Invalid small JSON " + relative + ": " + str(error))
                continue
            entry = {"path": relative, "size_bytes": len(raw),
                     "sha256": hashlib.sha256(raw).hexdigest(), "report": report}
            summary["reports"].append(entry)
            print("CADENCE_MF_REPORT_BEGIN")
            print(json.dumps(entry, ensure_ascii=False, sort_keys=True))
            print("CADENCE_MF_REPORT_END")
        elif path.suffix.lower() == ".aac":
            entry = {"path": relative, "size_bytes": path.stat().st_size,
                     "sha256": fingerprint(path)}
            summary["aac_files"].append(entry)
            print("CADENCE_MF_AAC_BEGIN")
            print(json.dumps(entry, sort_keys=True))
            print("CADENCE_MF_AAC_END")

    if len(summary["aac_files"]) != 2:
        summary["errors"].append("Expected exactly two existing AAC files")
    validations = [entry["report"] for entry in summary["reports"]
                   if isinstance(entry["report"], dict)
                   and "expected_sample_rate" in entry["report"] and "structure" in entry["report"]]
    matched_rates = []
    for audio in summary["aac_files"]:
        matching = [report for report in validations if report.get("sha256") == audio["sha256"]]
        if len(matching) != 1:
            summary["errors"].append("AAC has no unique matching validation SHA: " + audio["path"])
            continue
        validation = matching[0]
        audio["sample_rate_from_matching_validation"] = validation.get("expected_sample_rate")
        matched_rates.append(validation.get("expected_sample_rate"))
        if not validation.get("passed") or validation.get("status") != "passed_with_decode":
            summary["errors"].append("Original validation did not pass with decode: " + audio["path"])
    if len(matched_rates) != 2 or matched_rates.count(44100) != 1 or matched_rates.count(48000) != 1:
        summary["errors"].append("Expected SHA-matched validations at 44100 and 48000 Hz")
    summary["passed"] = not summary["errors"]
    summary_path = output / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("CADENCE_MF_REPORT_BEGIN")
    print(json.dumps({"path": "reader-summary", "passed": summary["passed"],
                      "reports_printed": len(summary["reports"]), "aac_files": summary["aac_files"],
                      "skipped_large_json": summary["skipped_large_json"], "errors": summary["errors"]},
                     ensure_ascii=False, sort_keys=True))
    print("CADENCE_MF_REPORT_END")
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
