#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Validate only VSCO CC0 bank assets; inspect mode can never authorize publication."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import zipfile
import prepare_assets as assets

NAMES = dict(zip(("sounds", "sources", "notice", "license", "checksums"), [f"Cadence-VSCO-CE-Expansion-{part}-{assets.VERSION}{suffix}" for part, suffix in
                       [("sons", ".zip"), ("convertisseur", ".zip"), ("notice", ".txt"), ("CC0", ".txt"), ("SHA256SUMS", ".txt")]]))
NAMES.update(cello_sf2="Cadence-VSCO-Cello-Ensemble.sf2", trumpet_sf2="Cadence-VSCO-Trumpet.sf2", contrabass_sf2="Cadence-VSCO-Contrabass.sf2")
KINDS = tuple(NAMES)

def require(test: bool, reason: str) -> None:
    if not test:
        raise ValueError(reason)

def actual_qualification(support: Path) -> dict:
    proof = json.loads(assets.plain(support / "evidence/assessment.json"))
    native = json.loads(assets.plain(support / "evidence/native-report.console-capture.json"))
    owned = json.loads(assets.plain(support / "evidence/owned-job.console-capture.json"))
    require(proof["run_id"] == 43304846264 and proof["driver_commit"] == "21e29c9633f13c3e1b4681e5bddbcb5dfc8f4ce5"
            and proof["conclusion"] == "success" and proof["actual_WAV_count"] == 16 and proof["cases"] == 8,
            "Exact actual Windows sound qualification required")
    for key in ("all_commands_zero_exit_without_timeout", "all_original_scores_and_resources_preserved", "all_save_reopened_wav_hashes_equal", "every_case_has_two_explicit_disabled_auxiliary_sends", "stage_files_unchanged", "banks_unchanged", "original_exercises_unchanged"):
        require(proof[key] is True, "Missing real sound proof: " + key)
    require(native["status"] == "passed-native-expansion-render-gain-save-reload-and-controls" and native["native_SF2_loader_used"] is True
            and native["SFZ_or_VST_loader_used"] is False and len(native["cases"]) == 8 and len(native["commands"]) == 27,
            "Actual eight native SF2 cases and 27 commands required")
    require({x["name"] for x in native["cases"]} == {"basic-cello", "cello", "basic-trumpet", "trumpet", "basic-contrabass", "contrabass", "trumpet-minus18", "missing-cello"},
            "Exact original eight cases required")
    require(all(x["exit_code"] == 0 and x["timed_out"] is False for x in native["commands"]), "Real native command completion required")
    for case in native["cases"]:
        require(case["source_unchanged"] is True and case["resource_preserved_on_save"] is True
                and case["wav_sha256"] == case["reopened_wav_sha256"], "Native save/reload preservation is incomplete")
        require(case["requested_track"]["out"]["auxSends"] == [{"active": False, "signalAmount": 0.0}] * 2,
                "Two explicit disabled auxiliary sends required for intended dry render")
        for key in ("audio", "reopened_audio"):
            audio = case[key]
            require(audio["passed"] is True and audio["nonfinite_samples"] == 0 and audio["full_scale_samples"] == 0
                    and 0 < audio["rms"] < 1 and 0 < audio["peak"] < 1 and audio["dynamics"]["strictly_rising"] is True,
                    "Nonempty finite unclipped actual WAV and rising dynamics required")
            require(audio["envelope_observations"]["post_release_is_quiet"] is True
                    and audio["envelope_observations"]["hold_tail_is_quiet"] is True, "Actual envelope checks required")
    controls = native["native_load_gain_and_fallback_controls"]
    require(controls["gain_matches"] is True and controls["same_shape"] is True
            and controls["missing_cello_PCM_matches_MSBasic"] is True and all(x is True for x in controls["expansion_PCM_differs_from_MSBasic"].values()), "Actual gain/fallback/loading controls required")
    require(owned["status"] == "passed-native-SF2-with-owned-cleanup" and owned["profile_cleanup_verified"] is True
            and owned["job_closed_cleanly"] is True and not owned["errors"] and not owned["forced_descendants"], "Owned process cleanup required")
    require({(x["file"],x["bytes"],x["sha256"]) for x in native["banks_manifest"]["banks"]}
            == {(name,*info) for name,info in assets.BANKS.items()}, "Real Windows banks must match the exact distributed bytes")
    return proof

def verify_archives(root: Path, support: Path) -> None:
    musical = set(assets.BANKS) | {"NOTICE-FR.txt", "LICENSE-CC0.txt", "bank-catalog.json", "SHA256SUMS.txt"}
    with zipfile.ZipFile(root / NAMES["sounds"]) as archive:
        require(set(archive.namelist()) == musical and len(archive.infolist()) == len(musical), "Only three sounds and their notices are allowed")
        for info in archive.infolist():
            require(info.compress_type == zipfile.ZIP_STORED and not info.is_dir(), "Deterministic regular ZIP members required")
            data = archive.read(info)
            if info.filename in assets.BANKS:
                size, digest = assets.BANKS[info.filename]
                require(len(data) == size and assets.sha(data) == digest, "A sound differs from the actual qualified bank")
        require(archive.read("NOTICE-FR.txt") == assets.plain(support / "NOTICE-FR.txt")
                and archive.read("LICENSE-CC0.txt") == assets.plain(support / "converter/VSCO-CC0-LICENSE.txt"), "Original French notice/CC0 bytes required")
        require(archive.read("SHA256SUMS.txt") == assets.text_manifest({n: archive.read(n) for n in sorted(musical - {"SHA256SUMS.txt"})}), "Internal sound checksums differ")
    members = {"converter/" + n for n in assets.CONVERTER_FILES} | {"evidence/" + n for n in assets.EVIDENCE_FILES}
    members |= {"NOTICE-FR.txt", "RECONSTRUIRE-FR.txt", "bank-catalog.json", "prepare_assets.py", "SOURCE-SHA256SUMS.txt"}
    with zipfile.ZipFile(root / NAMES["sources"]) as archive:
        require(set(archive.namelist()) == members and len(archive.infolist()) == len(members), "Complete converter/mappings/recipe GPL source set required")
        require(sum(x.file_size for x in archive.infolist()) < 2_000_000, "Source archive outside reviewed size bound")
        for name in members - {"SOURCE-SHA256SUMS.txt"}:
            require(archive.read(name) == assets.plain(support / name), "Corresponding converter/source member differs: " + name)
        require(archive.read("SOURCE-SHA256SUMS.txt") == assets.text_manifest({n: archive.read(n) for n in sorted(members - {"SOURCE-SHA256SUMS.txt"})}), "Corresponding source checksums differ")

def validate(target: dict, root: Path, support: Path, inspect_only: bool = False) -> dict:
    require(type(target.get("schema_version")) is int and target["schema_version"] == 1, "Unsupported target schema")
    require(target.get("repository") == "astrynome-byte/Music" and target.get("scope") == "vsco_cc0_sounds_only"
            and target.get("version") == assets.VERSION, "Only the reviewed sounds-only release is allowed")
    require(target["source"]["application_included"] is False and target["source"]["samples_license"] == "CC0-1.0"
            and target["source"]["converter_license"] == "GPL-3.0-only", "Only CC0 sounds and independent GPL source assets allowed")
    require(type(target.get("ready")) is bool, "ready must be a real boolean")
    if not inspect_only:
        require(target["ready"] is True and target["audit"]["approved"] is True
                and isinstance(target["audit"]["reviewed_by"], str) and target["audit"]["reviewed_by"].strip(), "Actual root review and ready=true required")
        require(target["android"]["audit_status"] == "reviewed-no-android-release-or-tag-trigger"
                and isinstance(target["android"]["reviewed_by"], str) and target["android"]["reviewed_by"].strip()
                and target["android"]["main_workflows"] and target["android"]["tag_workflows"], "Current exhaustive workflow review required")
    release = target["release"]
    require(release["tag"] == "cadence-studio/sounds-vsco-ce-expansion-1.1.0-exp.1" and release["prerelease"] is True
            and release["target_commit_mode"] == "workflow_head" and "target_commit" not in release,
            "Immutable experimental sounds-only workflow HEAD tag required")
    require(isinstance(release["title"], str) and re.search(r"sons.*exp[eé]riment", release["title"], re.I), "Explicit experimental sounds title required")
    proof = actual_qualification(support)
    require(target["proof"]["assessment_sha256"] == assets.sha(assets.plain(support / "evidence/assessment.json"))
            and target["proof"]["native_report_sha256"] == assets.sha(assets.plain(support / "evidence/native-report.console-capture.json")), "Reviewed actual qualification hashes differ")
    rows = target["assets"]
    require(type(rows) is list and len(rows) == 8 and {x["kind"] for x in rows} == set(KINDS), "Exactly eight sound/source/legal assets required; no application installer")
    for row in rows:
        require(row["name"] == NAMES[row["kind"]] and row["member_path"] == row["name"], "Immutable flat asset names required")
        require(type(row["bytes"]) is int and 0 < row["bytes"] < 150_000_000 and re.fullmatch(r"[0-9a-f]{64}", row["sha256"]), "Exact asset bytes/hash required")
        if row["kind"] in ("cello_sf2", "trumpet_sf2", "contrabass_sf2"):
            require((row["bytes"], row["sha256"]) == assets.BANKS[row["name"]], "Raw SF2 asset must match the actual qualified bank")
        data = assets.plain(root / row["name"])
        require(len(data) == row["bytes"] and assets.sha(data) == row["sha256"], "Approved actual asset differs: " + row["name"])
    verify_archives(root, support)
    expected = assets.text_manifest({x["name"]: assets.plain(root / x["name"]) for x in rows if x["kind"] != "checksums"})
    require(assets.plain(root / NAMES["checksums"]) == expected, "Public checksum inventory differs")
    return {"schema_version": 1, "allowed": not inspect_only, "inspect_only": inspect_only, "ready": target["ready"],
            "scope": "Only the exact three CC0 banks and independent converter/legal assets; no application", "qualified_run": proof["run_id"],
            "asset_receipts": rows, "network_or_publication_performed": False}

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--inspect-only", action="store_true")
    args = parser.parse_args()
    try:
        result = validate(json.loads(args.target.read_text(encoding="utf-8-sig")), args.root, Path(__file__).parent, args.inspect_only)
        code = 0
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as error:
        result, code = {"schema_version": 1, "allowed": False, "errors": [str(error)], "network_or_publication_performed": False}, 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))
    return code

if __name__ == "__main__":
    raise SystemExit(main())
