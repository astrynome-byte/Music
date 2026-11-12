#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare fresh full-application outputs with a fixed Windows reference subset.

This is a strict byte regression gate. It neither normalizes mismatches away nor
claims that a byte difference establishes a musical defect. Files are read only
inside the freshly created QA result directory; no score is rewritten.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def compare(expected_path, candidate_report, output_path):
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    candidate = json.loads(candidate_report.read_text(encoding="utf-8"))
    if expected.get("schema_version") != 1 or expected.get("expected_output_count") != 35:
        raise ValueError("Expected a fixed schema1 reference of thirty-five outputs")
    if len(expected.get("outputs", [])) != 35:
        raise ValueError("Reference output count does not match its declaration")
    if output_path.exists():
        raise ValueError("Comparison output must be new; previous evidence is never replaced")
    root = candidate_report.parent.resolve()
    observed = {}
    for check in candidate.get("checks", []):
        for file in check.get("outputs", []):
            path = Path(file["path"]).resolve()
            path.relative_to(root)
            key = (check["fixture"], check["stage"], path.name)
            if key in observed:
                raise ValueError("Duplicate candidate output identity")
            observed[key] = (check, file, path)
    rows = []
    seen = set()
    for item in expected["outputs"]:
        key = (item["fixture"], item["stage"], item["name"])
        if key in seen:
            raise ValueError("Duplicate reference output identity")
        seen.add(key)
        row = dict(item, passed=False)
        actual = observed.get(key)
        if actual is None:
            row["error"] = "Expected candidate output missing from the report"
        else:
            check, file, path = actual
            try:
                if not check.get("passed") or not path.is_file():
                    raise ValueError("Candidate check failed or its output is missing")
                size = path.stat().st_size
                sha = hashlib.sha256(path.read_bytes()).hexdigest()
                row.update(candidate_sha256=sha, candidate_bytes=size,
                           candidate_path=str(path.relative_to(root)))
                if file.get("sha256") != sha or file.get("bytes") != size:
                    raise ValueError("Candidate file differs from its own recorded size/hash")
                row["passed"] = sha == item["sha256"] and size == item["bytes"]
                if not row["passed"]:
                    row["error"] = "Byte difference; inspect configuration, determinism and musical content"
            except (OSError, ValueError) as error:
                row["error"] = str(error)
        rows.append(row)
    result = {
        "schema_version": 1,
        "scope": "Strict byte comparison only; no new reference build, GUI editing or listening",
        "checked_utc": datetime.now(timezone.utc).isoformat(),
        "expected_reference_sha256": hashlib.sha256(expected_path.read_bytes()).hexdigest(),
        "reference_run_id": expected["reference_run_id"],
        "candidate_executable_sha256": candidate.get("executable_sha256"),
        "candidate_report_sha256": hashlib.sha256(candidate_report.read_bytes()).hexdigest(),
        "passed": len(rows) == 35 and all(row["passed"] for row in rows),
        "matching_outputs": sum(row["passed"] for row in rows),
        "outputs": rows,
        "limits": expected.get("limits", []),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8") as destination:
        json.dump(result, destination, ensure_ascii=False, indent=2)
        destination.write("\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected", required=True, type=Path)
    parser.add_argument("--candidate-report", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = compare(args.expected, args.candidate_report, args.output)
    print(f"{result['matching_outputs']}/35 fixed reference outputs match the fresh candidate")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
