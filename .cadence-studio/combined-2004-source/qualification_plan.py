#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Validate reviewed test expectations bound to the reconstructed source tree.

The qualification section is part of the same source.json as the pinned patch.
It declares reviewed expectations; observed unit/runtime counts are still read
from the real completed process logs. This helper executes no application.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


FIELDS = {
    "python_unit_tests": "CADENCE_QA_EXPECTED_PYTHON_UNITS",
    "store_scenarios": "CADENCE_QA_EXPECTED_STORE_SCENARIOS",
    "cli_checks": "CADENCE_QA_EXPECTED_CLI_CHECKS",
    "reference_outputs": "CADENCE_QA_EXPECTED_REFERENCE_OUTPUTS",
    "music_aac_cases": "CADENCE_QA_EXPECTED_AAC_CASES",
}
UPSTREAM = "96480d58445e3b24b230a3fe7d4725d639aa2eb3"


def read_plan(selection: dict, bootstrap: dict) -> dict:
    upstream, source = selection["upstream"], selection["source"]
    if selection["schema_version"] != 1 or upstream != {
        "repository": "https://github.com/musescore/MuseScore.git", "tag": "v4.7.6", "commit": UPSTREAM,
    }:
        raise ValueError("Qualification requires the reviewed v4.7.6 upstream reference")
    for key in ("commit", "tree"):
        if not re.fullmatch(r"[a-f0-9]{40}", source[key]):
            raise ValueError("Qualification source identity must use full Git identifiers")
    if bootstrap["original_source_commit"] != source["commit"] or bootstrap["source_tree"] != source["tree"] \
            or bootstrap["upstream_tag"] != "v4.7.6" or bootstrap["upstream_commit"] != UPSTREAM \
            or bootstrap["compressed_patch_sha256"] != selection["patch"]["sha256"]:
        raise ValueError("Qualification plan differs from the actually reconstructed source tree")
    plan = selection["qualification"]
    if plan["schema_version"] != 1:
        raise ValueError("Unsupported qualification plan schema")
    for key in FIELDS:
        if type(plan[key]) is not int or not 1 <= plan[key] <= 4096:
            raise ValueError("Expected a positive reviewed count for " + key)
    return {key: plan[key] for key in FIELDS}


def unit_observation(text: str, expected: int) -> dict:
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    summaries = re.findall(r"(?m)^Ran (\d+) tests? in [0-9.]+s\s*$", text)
    successful = [line.strip() for line in re.findall(r"(?m)^OK(?:[ \t]*\([^\n]*\))?[ \t]*$", text)]
    if summaries != [str(expected)] or successful != ["OK"]:
        raise ValueError("Unit log must contain the reviewed count and an unskipped successful summary")
    return {"kind": "python_unit_tests", "expected": expected, "observed": int(summaries[0]), "passed": True}


def store_observation(text: str, expected: int) -> dict:
    summaries = re.findall(
        r"(?m)^(?:\d+:\s*)?(\d+)/(\d+) production-store runtime scenarios passed \(Qt 6\.10\.2\)\.\s*$", text)
    successful = re.findall(r"(?m)^(?:\d+:\s*)?PASS:", text)
    failures = re.findall(r"(?m)^(?:\d+:\s*)?FAIL:", text)
    if summaries != [(str(expected), str(expected))] or len(successful) != expected or failures:
        raise ValueError("Store log must prove every reviewed scenario passing with actual Qt6.10.2")
    return {"kind": "production_store_scenarios", "expected": expected, "observed": expected, "passed": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--bootstrap", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--github-env", type=Path)
    parser.add_argument("--unit-log", type=Path)
    parser.add_argument("--store-log", type=Path)
    args = parser.parse_args()
    report = {"schema_version": 1, "passed": False, "application_executed": False, "observations": [], "errors": []}
    try:
        raw = args.selection.read_bytes()
        selection = json.loads(raw.decode("utf-8-sig"))
        bootstrap = json.loads(args.bootstrap.read_text(encoding="utf-8-sig"))
        plan = read_plan(selection, bootstrap)
        report.update(source_commit=selection["source"]["commit"], source_tree=selection["source"]["tree"],
                      upstream_tag="v4.7.6", selection_sha256=hashlib.sha256(raw).hexdigest(), expected=plan)
        if args.unit_log:
            report["observations"].append(unit_observation(args.unit_log.read_text(encoding="utf-8-sig"), plan["python_unit_tests"]))
        if args.store_log:
            report["observations"].append(store_observation(args.store_log.read_text(encoding="utf-8-sig"), plan["store_scenarios"]))
        if args.github_env:
            with args.github_env.open("a", encoding="utf-8") as stream:
                for key, name in FIELDS.items():
                    stream.write(name + "=" + str(plan[key]) + "\n")
        report["passed"] = True
    except (OSError, ValueError, KeyError, TypeError) as error:
        report["errors"].append(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print("CADENCE_QUALIFICATION_PLAN_REPORT_BEGIN")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    print("CADENCE_QUALIFICATION_PLAN_REPORT_END")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
