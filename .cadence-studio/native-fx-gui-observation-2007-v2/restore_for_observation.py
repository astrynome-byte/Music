#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Reuse the exact full2007 restoration, with no SF2 build or app invocation."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys


def main():
    if (os.name != "nt" or os.environ.get("CI") != "true"
            or os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"):
        raise ValueError("Only disposable hosted Windows may restore the stage")
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    source = Path(__file__).with_name("runtime") / "Test-VscoExpansion.py"
    manifest = json.loads(Path(__file__).with_name("observation-plan.json").read_text())
    if manifest.get("status") != "private-source-only-no-Windows-GUI-execution":
        raise ValueError("Exact private observation source profile required")
    expected = next(row["sha256"] for row in manifest["files"] if row["path"] == "runtime/Test-VscoExpansion.py")
    if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
        raise ValueError("Byte-pinned restoration helper changed")
    spec = importlib.util.spec_from_file_location("cadence2007_observation_restoration", source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    artifact = module.owned(args.artifact)
    stage = module.owned(args.stage)
    result = module.owned(args.result)
    if result.exists() or not result.parent.is_dir():
        raise ValueError("New result with existing owned parent required")
    executable, original = module.restore_stage(artifact, stage)
    report = {"schema_version": 1, "status": "actual2007-stage-restored-no-app-start",
              "application_started": False, "source_commit": module.SOURCE,
              "executable_path": str(executable), "executable_sha256": module.sha(executable),
              "original_stage_manifest": original}
    with result.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
