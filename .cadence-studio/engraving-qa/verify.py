#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Check existing upstream test declarations, actual discovery and result counts."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET


def selection(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data["tests"]
    names = [row["name"] for row in rows]
    if data.get("schema_version") != 1 or len(names) != 11 or len(set(names)) != 11:
        raise ValueError("Expected the eleven unique reviewed tests")
    if any("DISABLED_" in name or not re.fullmatch(r"\w+\.\w+", name) for name in names):
        raise ValueError("Disabled or non-exact test selection rejected")
    return data, rows, names


def source_audit(root, rows):
    result = []
    for row in rows:
        suite, name = row["name"].split(".")
        path = (root / row["file"]).resolve()
        path.relative_to(root.resolve())
        raw = path.read_bytes()
        text = raw.decode("utf-8-sig")
        matches = list(re.finditer(r"\bTEST_F\s*\(\s*" + re.escape(suite) + r"\s*,\s*" + re.escape(name) + r"\s*\)", text))
        if len(matches) != 1:
            raise ValueError("Missing/ambiguous active TEST_F declaration: " + row["name"])
        result.append(dict(row, line=text.count("\n", 0, matches[0].start()) + 1,
                           source_file_sha256=hashlib.sha256(raw).hexdigest()))
    return {"scope": "Source declaration lookup only; not executed tests", "declarations": result}


def listed_audit(path, names):
    suite = None
    found = []
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        header = re.fullmatch(r"(\w+)\.\s*(?:#.*)?", line)
        case = re.fullmatch(r"  (\w+)\s*(?:#.*)?", line)
        if header:
            suite = header.group(1)
        elif case and suite:
            found.append(suite + "." + case.group(1))
    if len(found) != len(names) or sorted(found) != sorted(names):
        raise ValueError("Real --gtest_list_tests selection differs: " + repr(found))
    return {"scope": "Actual binary discovery only; no tests run by list mode", "discovered": found}


def result_audit(path, names):
    root = ET.parse(path).getroot()
    if root.tag != "testsuites":
        raise ValueError("Expected GoogleTest testsuites XML")
    cases = list(root.iter("testcase"))
    observed = [case.get("classname", "") + "." + case.get("name", "") for case in cases]
    if len(cases) != len(names) or len(cases) < 10 or sorted(observed) != sorted(names):
        raise ValueError("Exactly eleven named executed cases required; zero/partial run rejected: " + repr(observed))
    failed = [name for name, case in zip(observed, cases)
              if case.get("status") != "run" or case.get("result") != "completed"
              or list(case.iter("failure")) or list(case.iter("error")) or list(case.iter("skipped"))]
    if failed or int(root.get("tests", "-1")) != 11 or int(root.get("failures", "-1")) != 0 or int(root.get("disabled", "-1")) != 0 or int(root.get("errors", "-1")) != 0:
        raise ValueError("Failures/errors/skipped/disabled/non-run cases rejected: " + repr(failed))
    return {"scope": "Native headless engraving model assertions only; no GUI gestures or sound",
            "passed": True, "executed_count": len(cases), "tests": observed,
            "gtest_xml_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "editing_gestures_tested": False, "audio_tested": False, "installation_tested": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("source", "list", "results"))
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    _, rows, names = selection(args.selection)
    if args.output.exists():
        parser.error("Output must be new; existing evidence is never overwritten")
    if args.mode == "source":
        result = source_audit(args.input, rows)
    elif args.mode == "list":
        result = listed_audit(args.input, names)
    else:
        result = result_audit(args.input, names)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
