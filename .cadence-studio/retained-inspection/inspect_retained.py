#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Inspect this project's retained CI outputs without executing their binaries."""
import argparse
import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import zipfile

EXPECTED_TREE = "65322ea3a3fbb419695a9b226607153b1c698886"


def digest_file(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def safe_leaf(name):
    if not isinstance(name, str) or name in ("", ".", "..") or any(c in name for c in "/\\:"):
        raise ValueError(f"Unsafe artifact filename: {name!r}")
    return name


def inspect_stage(root):
    for line in (root / "SHA256SUMS.txt").read_text(encoding="utf-8-sig").splitlines():
        match = re.fullmatch(r"([a-f0-9]{64})  (.+)", line)
        if not match:
            raise ValueError("Malformed stage checksum entry")
        path = root / safe_leaf(match[2])
        if digest_file(path) != match[1]:
            raise ValueError(f"Stage checksum mismatch: {path.name}")
    manifest = json.loads((root / "stage-manifest.json").read_text(encoding="utf-8-sig"))
    result = json.loads((root / "cadence-build-result.json").read_text(encoding="utf-8-sig"))
    state = json.loads((root / "cadence-build.json").read_text(encoding="utf-8-sig"))
    if manifest["variant"] != "Cadence" or manifest["source_tree"] != EXPECTED_TREE:
        raise ValueError("Unexpected retained source tree or variant")
    if state["source_commit"] != result["source_commit"] or result["source_commit"] != manifest["source_commit"]:
        raise ValueError("Inconsistent original source commits")
    if state["source_dirty_at_configure"] or result["source_dirty_at_build"]:
        raise ValueError("Original source was dirty")
    archive_path = root / safe_leaf(manifest["stage_archive"])
    if digest_file(archive_path) != manifest["stage_archive_sha256"]:
        raise ValueError("Stage archive differs from its original manifest")
    binaries = []
    executable = None
    soundfont = None
    with zipfile.ZipFile(archive_path) as archive:
        seen = set()
        for member in archive.infolist():
            path = PurePosixPath(member.filename.replace("\\", "/"))
            if path.is_absolute() or ".." in path.parts or ":" in member.filename:
                raise ValueError("Unsafe stage archive path")
            name = str(path)
            if name in seen:
                raise ValueError("Duplicate stage archive path")
            seen.add(name)
            if member.is_dir():
                continue
            if name.lower().endswith((".dll", ".exe", ".lib")):
                binaries.append({"path": name, "size_bytes": member.file_size})
            if name == "bin/CadenceStudio4.exe" or name.endswith("/MS Basic.sf3"):
                with archive.open(member) as stream:
                    sha = hashlib.file_digest(stream, "sha256").hexdigest()
                if name == "bin/CadenceStudio4.exe":
                    executable = {"path": name, "size_bytes": member.file_size, "sha256": sha}
                else:
                    soundfont = {"path": name, "size_bytes": member.file_size, "sha256": sha}
        if executable is None or executable["sha256"] != result["executable_sha256"] or executable["sha256"] != manifest["executable_sha256"]:
            raise ValueError("Actual executable does not match the retained build")
        if soundfont is None or soundfont["sha256"] != "5ea2375e8bd7d8e71def1036978c1621e85b66934169b6a2744b27b9b3c2d99c":
            raise ValueError("Bundled MS Basic is missing or changed")
    return {"manifest": manifest, "original_build_state": state, "original_build_result": result,
            "stage_archive_sha256": digest_file(archive_path), "executable": executable,
            "soundfont": soundfont, "binaries": binaries, "binary_count": len(binaries)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs", type=Path, required=True)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output file must be new")
    output = {"scope": "Retained run41740259712; no binaries executed", "reports": [], "screenshots": []}
    wanted = {"gui-report.json", "roundtrip-report.json", "report.json"}
    for path in sorted(args.logs.rglob("*.json")):
        if path.name not in wanted:
            continue
        document = json.loads(path.read_text(encoding="utf-8-sig"))
        relative = path.relative_to(args.logs).as_posix()
        output["reports"].append({"path": relative, "sha256": digest_file(path), "data": document})
        print("CADENCE_REPORT_BEGIN " + relative)
        print(json.dumps(document, ensure_ascii=False, indent=2))
        print("CADENCE_REPORT_END " + relative)
    if not any(r["path"].endswith("gui-report.json") for r in output["reports"]):
        raise ValueError("The actual GUI report is missing")
    for path in sorted(args.logs.rglob("*")):
        if path.is_file() and "gui-cadence" in path.as_posix() and path.suffix == ".log":
            print("CADENCE_GUI_LOG_BEGIN " + path.name)
            print(path.read_text(encoding="utf-8-sig", errors="replace")[:50000])
            print("CADENCE_GUI_LOG_END " + path.name)
    for path in sorted(args.logs.rglob("gui-*.png"))[:2]:
        data = path.read_bytes()
        item = {"filename": path.name, "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        output["screenshots"].append(item)
        print("CADENCE_PNG_BEGIN " + json.dumps(item))
        if len(data) <= 750000:
            encoded = base64.b64encode(data).decode("ascii")
            chunks = [encoded[i:i + 12000] for i in range(0, len(encoded), 12000)]
            for index, chunk in enumerate(chunks):
                print(f"CADENCE_PNG_CHUNK {index + 1}/{len(chunks)} {chunk}")
        else:
            print("CADENCE_PNG_OMITTED size exceeds bounded inspection output")
        print("CADENCE_PNG_END " + path.name)
    output["stage"] = inspect_stage(args.stage)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("CADENCE_STAGE_VERIFIED_BEGIN")
    print(json.dumps(output["stage"], ensure_ascii=False, indent=2))
    print("CADENCE_STAGE_VERIFIED_END")


if __name__ == "__main__":
    main()
