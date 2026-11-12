#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Build explicitly selected, pinned VSCO CE CC0 native SoundFonts.

This developer tool supports three audited sustain mappings only. It is not an
SFZ reader in Cadence and does not install or execute any application/plugin.
Existing flute and violin outputs remain the separate, unchanged 1.0.0 set.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import sys
import urllib.parse
import urllib.request

HERE = Path(__file__).resolve().parent
SOURCE_MANIFEST_SHA256 = "0884c11a1ee7024dfc7ffa6fd96945e5e756774755095a701d43b379df7af0e0"
MAX_COLLECTION_BYTES = 118 * 1024**2
_spec = importlib.util.spec_from_file_location("_cadence_vsco_core", HERE / "build_vsco_sf2.py")
core = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = core
_spec.loader.exec_module(core)


def sha_file(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_manifest(path=HERE / "expansion-source-manifest.json"):
    if sha_file(path) != SOURCE_MANIFEST_SHA256:
        raise ValueError("The audited expansion source manifest differs")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if (manifest["commit"] != core.COMMIT or manifest["sounds_license"] != "CC0-1.0"
            or len(manifest["profiles"]) != 3):
        raise ValueError("Only the audited three-profile CC0 expansion is supported")
    return manifest


def validate_profiles(manifest, selected):
    by_id = {row["id"]: row for row in manifest["profiles"]}
    if not selected or len(selected) != len(set(selected)) or set(selected) - by_id.keys():
        raise ValueError("Explicit, unique reviewed collection IDs are required")
    pins = {row["path"]: row for row in manifest["files"]}
    plans = []
    for ident in selected:
        profile = by_id[ident]
        raw = (HERE / "mappings" / profile["mapping"]).read_bytes()
        core.verify_source(raw, pins[profile["mapping"]])
        regions, attack, release = core.parse_mapping(
            raw, expected_releases=(profile["release_seconds"],),
            expected_group=profile["expected_group"])
        if (len(regions) != profile["regions"] or attack != profile["attack_seconds"]
                or [min(r.low for r in regions), max(r.high for r in regions)] != profile["midi_range"]
                or any(r.sample not in pins for r in regions)
                or len({r.sample for r in regions}) != len(regions)):
            raise ValueError("Mapping zones, source selection or playable range changed")
        plans.append((profile, regions, attack, release))
    license_raw = (HERE / "VSCO-CC0-LICENSE.txt").read_bytes()
    core.verify_source(license_raw, pins["LICENSE"])
    for original, local in (("README.md", "UPSTREAM-README-md"), ("Readme.txt", "UPSTREAM-Readme-txt")):
        core.verify_source((HERE / local).read_bytes(), pins[original])
    return plans, pins


def make_provider(pins, source_root=None):
    """Keep at most one bounded original sample in memory; never cache WAVs."""
    if source_root is not None:
        source_root = source_root.resolve(strict=True)

    def provider(name):
        pin = pins[name]
        if not 44 <= pin["bytes"] <= core.MAX_WAV_BYTES:
            raise ValueError("Pinned source WAV exceeds the reviewed bound")
        if source_root is None:
            url = ("https://raw.githubusercontent.com/sgossner/VSCO-2-CE/"
                   + core.COMMIT + "/" + urllib.parse.quote(name, safe="/"))
            request = urllib.request.Request(url, headers={"User-Agent": "Cadence-VSCO-CC0-builder/1.1"})
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read(pin["bytes"] + 1)
        else:
            path = source_root.joinpath(*PurePosixPath(name).parts)
            if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file():
                raise ValueError("Local sample cannot traverse a symlink")
            if not path.resolve(strict=True).is_relative_to(source_root):
                raise ValueError("Local source escapes its explicit root")
            raw = path.read_bytes() if path.stat().st_size == pin["bytes"] else b""
        core.verify_source(raw, pin)
        return raw, {"file": name, "bytes": len(raw), "sha256": core.digest(raw),
                     "git_blob_sha1": pin["git_blob_sha1"]}
    return provider


def build(output, selected, source_root=None):
    manifest = load_manifest()
    plans, pins = validate_profiles(manifest, selected)
    if output.exists():
        raise ValueError("Output must be a new directory")
    output.mkdir(parents=True)
    provider = make_provider(pins, source_root)
    result = {
        "schema_version": 1, "status": "building", "version": manifest["collection_version"],
        "source_commit": core.COMMIT, "sounds_license": "CC0-1.0", "code_license": "GPL-3.0-only",
        "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
        "banks": [], "original_samples_cached_on_disk": False,
        "application_executed": False, "windows_qualified": False, "human_listening": False,
        "limitations": [
            "Only the three audited sustain-vibrato mappings are supported; no general SFZ interpreter.",
            "Cello is a recorded ensemble, not a solo-cello recording.",
            "Single-member seq_length/seq_position=1 is static; round-robin sequencing is not implemented.",
            "group_label is informational only; all other unaudited group opcodes are refused.",
            "PCM24/32 integer samples are truncated to PCM16 without dithering; stereo is preserved.",
            "Positive region gains share one common bank headroom, targeting Cadence FluidSynth attenuation factor0.4.",
            "Fixed attack/release envelopes; no live ampeg_dynamic or recorded legato/staccato transitions.",
            "Only original WAV forward infinite smpl loops are retained. No sustain loop is invented.",
            "A held unlooped voice ends with its sample. UI installation and human listening require separate tests."
        ]}
    try:
        for profile, regions, attack, release in plans:
            path = output / (profile["soundfont_name"] + ".sf2")
            details = core.build_bank(path, regions, provider, title=profile["soundfont_name"],
                                      program=profile["program"], attack=attack, release=release,
                                      preset_name=profile["preset_name"])
            core.sf2_chunks(path)
            row = {
                "collection_id": profile["id"], "label_fr": profile["label_fr"],
                "file": path.name, "bytes": path.stat().st_size, "sha256": sha_file(path),
                "soundfont_name": profile["soundfont_name"], "preset_name": profile["preset_name"],
                "resource_id": profile["soundfont_name"] + "\\0\\" + str(profile["program"]),
                "bank": 0, "program": profile["program"], "midi_range": profile["midi_range"],
                "mapping": profile["mapping"], "source_sample_bytes": profile["source_sample_bytes"],
                "gain_delta_db": 0, **details}
            result["banks"].append(row)
            if sum(p.stat().st_size for p in output.iterdir()) > MAX_COLLECTION_BYTES:
                raise ValueError("Selected derived data exceeds the118MiB reviewed collection budget")
        for name in ("VSCO-CC0-LICENSE.txt", "UPSTREAM-README-md", "UPSTREAM-Readme-txt"):
            (output / name).write_bytes((HERE / name).read_bytes())
        result["status"] = "built-pinned-vsco-expansion-sf2"
        result["total_output_bytes_excluding_manifest"] = sum(p.stat().st_size for p in output.iterdir())
    except Exception as error:
        result["status"] = "failed_or_blocked"
        result["error"] = str(error)
        raise
    finally:
        (output / "banks-manifest.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="Print available audited profiles without fetching samples")
    parser.add_argument("--collection", action="append", help="Repeat to build several explicit collection IDs")
    parser.add_argument("--output", type=Path)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--download", action="store_true")
    source.add_argument("--source-root", type=Path)
    args = parser.parse_args(argv)
    manifest = load_manifest()
    if args.list:
        print(json.dumps(manifest["profiles"], indent=2, ensure_ascii=False))
        return 0
    if not args.collection or args.output is None or not (args.download or args.source_root):
        parser.error("--collection, --output and exactly one explicit source mode are required")
    report = build(args.output, args.collection, args.source_root)
    print(json.dumps({"status": report["status"], "banks": [
        {k: b[k] for k in ("collection_id", "file", "bytes", "sha256", "resource_id")}
        for b in report["banks"]]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
