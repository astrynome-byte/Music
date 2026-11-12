# SPDX-License-Identifier: GPL-3.0-only
"""Discover and inspect the real full2007 outputs before target activation: GET/data only."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import windows_publication as w
from acquire_originals import acquire_from_producer

REPORT_SUFFIXES = {
    "bootstrap": ("logs", "cadence-bootstrap.json"),
    "build": ("stage", "cadence-build-result.json"),
    "stage_manifest": ("stage", "stage-manifest.json"),
    "release_manifest": ("delivery", "release-manifest.json"),
    "cli": ("logs", "qa-cadence/report.json"),
    "msi": ("logs", "msi-qa/msi-install-report.json"),
    "notices": ("logs", "qa-stage-notices/stage-notices-report.json"),
    "components": ("delivery", "corresponding-sources/collection-report.json"),
    "icu_policy": ("delivery", "stage-system-icu-policy.json"),
    "icu_exports": ("delivery", "system-icu-exports.json"),
}

def observe_reports(acquired):
    refs = {}; originals = {}
    for kind, (role, suffix) in REPORT_SUFFIXES.items():
        path = w.unique_suffix(acquired / role, suffix)
        w.require(0 < path.stat().st_size <= 4_000_000, "Original report byte bound")
        refs[kind] = {"artifact_role": role, "member_path": path.relative_to(acquired / role).as_posix(),
                      "bytes": path.stat().st_size, "sha256": w.digest(path)}
        originals[kind] = path
    return refs, originals

def inspect(work):
    w.require(not work.exists(), "Inspection work folder must be new")
    w.plain(work)
    temporary = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    w.require(work.is_absolute() and work.resolve().is_relative_to(temporary), "Inspection work must be below RUNNER_TEMP")
    # No target, artifact ID, report receipt or binary hash is supplied here.
    # The fixed producer must finish successfully before artifact discovery.
    acquisition = acquire_from_producer(work / "originals")
    acquired = work / "originals"
    refs, originals = observe_reports(acquired)
    observed = {kind: json.loads(path.read_text(encoding="utf-8-sig")) for kind, path in originals.items()}
    inputs = json.loads(Path(__file__).with_name("target.json.template").read_text(encoding="utf-8-sig"))
    w.require(inputs["ready"] is False and inputs["review"]["approved"] is False, "Inspection must never enable publication")
    inputs["source"]["ci_commit"] = observed["bootstrap"].get("ci_source_commit")
    inputs["executable_sha256"] = observed["build"].get("executable_sha256")
    msi = w.unique_suffix(acquired / "delivery", w.PREFIX + ".msi")
    inputs["msi_sha256"] = w.digest(msi)
    inputs["artifacts"] = acquisition["artifacts"]
    inputs["reports"] = refs
    # This input object stays in memory. No target.json or approving document
    # is written; prepare verifies source, stage, MSI File table and all reports.
    facts = w.prepare(inputs, acquired, work / "assets")
    (work / "assets/asset-preparation.json").write_text(json.dumps(facts, indent=2) + "\n")
    reports_folder = work / "observed-reports"; reports_folder.mkdir()
    for kind, path in originals.items(): shutil.copyfile(path, reports_folder / (kind + ".original.json"))
    recipe_source = w.unique_suffix(msi.parent / "build-recipe", "combined-2007-source/source.json")
    shutil.copyfile(recipe_source, reports_folder / "source.original.json")
    return {"schema_version": 1, "status": "actual-full2007-data-inspected-seven-assets-prepared",
            "ready": False, "publication_authorized": False, "activation_target_written": False,
            "producer": inputs["producer"], "source": inputs["source"], "artifacts": acquisition["artifacts"],
            "reports": refs, "executable_sha256": inputs["executable_sha256"], "msi_sha256": inputs["msi_sha256"],
            "asset_receipts": facts["asset_receipts"], "msi_readonly_tables": facts["msi_readonly_tables"],
            "original_outer_digests_recomputed": True, "original_reports_copied_under": str(reports_folder),
            "application_or_installer_executed": False, "github_write_performed": False}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    w.plain(args.output)
    w.require(args.output.name.rstrip(" .").casefold() != "target.json" and not args.output.exists(), "Inspection output must be new and cannot be an activation target")
    temporary = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    w.require(args.output.is_absolute() and args.output.resolve().is_relative_to(temporary), "Inspection receipt must be below RUNNER_TEMP")
    try: result = inspect(args.work)
    except Exception as error:
        result = {"schema_version": 1, "status": "blocked-data-inspection", "ready": False,
                  "publication_authorized": False, "activation_target_written": False,
                  "github_write_performed": False, "error": str(error), "error_type": type(error).__name__}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print("CADENCE_WINDOWS2007_INSPECTION_BEGIN"); print(json.dumps(result, separators=(",", ":"))); print("CADENCE_WINDOWS2007_INSPECTION_END")
    return 0 if result["status"] == "actual-full2007-data-inspected-seven-assets-prepared" else 2

if __name__ == "__main__": raise SystemExit(main())
