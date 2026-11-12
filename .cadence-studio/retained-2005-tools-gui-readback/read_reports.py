# SPDX-License-Identifier: GPL-3.0-only
"""Read only two pinned existing QA reports, never execute their producer."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import stat


REPORTS = {
    "uia-report.json": (75050, "bb46a9c6f1245f3d59f02f3dc4b00f6d0504a17581706a763f69ae077218cd7f"),
    "close-report.json": (44279, "3ddb8dea86a5c5be2cd1da39f1063952dd00991a377e1515dfed5cb8cf8efa88"),
}


def read_reports(directory, output):
    directory = Path(directory).resolve(strict=True)
    output = Path(output)
    if not directory.is_dir() or output.exists():
        raise ValueError("Input directory required; output must be new")
    all_files = list(directory.rglob("*"))
    if len(all_files) > 256:
        raise ValueError("Artifact exceeds bounded inventory")
    receipts = []
    retained = []
    for name, (expected_bytes, expected_sha) in REPORTS.items():
        found = [p for p in all_files if p.name == name]
        if len(found) != 1:
            raise ValueError("Expected one exact existing report: " + name)
        source = found[0]
        for part in (source, *source.parents):
            if part == directory:
                break
            if part.is_symlink():
                raise ValueError("Linked report refused")
        source.resolve(strict=True).relative_to(directory)
        metadata = source.stat(follow_symlinks=False)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size != expected_bytes:
            raise ValueError("Report type or size differs: " + name)
        raw = source.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if len(raw) != expected_bytes or digest != expected_sha:
            raise ValueError("Report digest differs: " + name)
        document = json.loads(raw.decode("utf-8-sig"))
        if type(document) is not dict or document.get("pid") != 692:
            raise ValueError("Expected actual owned PID report")
        receipt = {
            "source_run_id": 43236835262,
            "artifact_id": 13953546227,
            "name": name,
            "bytes": len(raw),
            "sha256": digest,
            "base64_original_bytes": base64.b64encode(raw).decode("ascii"),
        }
        receipts.append(receipt)
        retained.append((name, raw))
    output.mkdir()
    for name, raw in retained:
        (output / name).write_bytes(raw)
    summary = {
        "schema_version": 1,
        "scope": "Read only pinned complete JSON reports from the existing GUI3 artifact",
        "source_run_id": 43236835262,
        "artifact_id": 13953546227,
        "producer_driver_commit": "31847788ef33e3b7b38581206a7c7a8be7c89fd2",
        "reader_only": True,
        "application_executed": False,
        "new_GUI_or_listening_result_inferred": False,
        "files": [{k: v for k, v in r.items() if k != "base64_original_bytes"} for r in receipts],
    }
    (output / "readback-receipt.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    for receipt in receipts:
        print("CADENCE_TOOLS_COMPLETE_REPORT_BEGIN")
        print(json.dumps(receipt, ensure_ascii=True, separators=(",", ":")))
        print("CADENCE_TOOLS_COMPLETE_REPORT_END")
    print(json.dumps(summary, separators=(",", ":")))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    read_reports(args.directory, args.output)
