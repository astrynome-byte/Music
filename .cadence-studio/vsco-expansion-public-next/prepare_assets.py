#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Create only the reviewed VSCO CC0 sounds/source assets; no network or release call."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

VERSION = "1.1.0-exp.1"
PREFIX = "Cadence-VSCO-CE-Expansion-"
BANKS = {'Cadence-VSCO-Cello-Ensemble.sf2': (48400382, '7c5d177057ef73bf6ccf2a7618b0516de678c4a98160d95c1a4e66fd6f670685'), 'Cadence-VSCO-Trumpet.sf2': (21599476, '8e6a212811ca9431c03c73a0c0fa1a5b3dd28038848ca7524137e7343ccbfc7c'), 'Cadence-VSCO-Contrabass.sf2': (47966050, 'a5e307c5eafe24c79a51229ee0a0b1e0d76d2626a6fd07fea6f663e6be4181f3')}
CONVERTER_FILES = ['build_vsco_sf2.py', 'build_collections.py', 'asset-source-manifest.json', 'expansion-source-manifest.json', 'VSCO-CC0-LICENSE.txt', 'CODE-GPL-3.0.txt', 'UPSTREAM-README-md', 'UPSTREAM-Readme-txt', 'UPSTREAM-LICENSE', 'mappings/FluteSusVib.sfz', 'mappings/SViolinVib.sfz', 'mappings/CelloEnsSusVib.sfz', 'mappings/TrumpetSusVib.sfz', 'mappings/ContrabassSusVB.sfz', 'checks/test_converter.py', 'checks/test_collections.py', 'README.md']
EVIDENCE_FILES = ['assessment.json', 'native-report.console-capture.json', 'owned-job.console-capture.json', 'workflow-run.metadata.json', 'artifacts.metadata.json', 'evidence-sha256.json', 'provenance.json']

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def plain(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError("A plain reviewed input file is required: " + str(path))
    return path.read_bytes()

def text_manifest(files: dict[str, bytes]) -> bytes:
    return "".join(f"{sha(data)}  {name}\n" for name, data in sorted(files.items())).encode()

def archive(path: Path, files: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_STORED, allowZip64=False) as output:
        for name, data in sorted(files.items()):
            if name.startswith("/") or "\\" in name or any(part in ("", ".", "..") for part in name.split("/")):
                raise ValueError("Unsafe archive member")
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 12, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_STORED
            output.writestr(info, data)

def prepare(support: Path, banks: Path, output: Path) -> dict:
    catalog_raw = plain(support / "bank-catalog.json")
    catalog = json.loads(catalog_raw)
    if catalog["version"] != VERSION or catalog["sounds_license"] != "CC0-1.0" or catalog["qualified_run"] != 43304846264:
        raise ValueError("The reviewed VSCO catalog is required")
    if {(x["file"], x["bytes"], x["sha256"]) for x in catalog["banks"]} != {(n, *v) for n, v in BANKS.items()}:
        raise ValueError("Only the three qualified musical banks are allowed")
    musical = {}
    for name, (size, digest) in BANKS.items():
        data = plain(banks / name)
        if len(data) != size or sha(data) != digest:
            raise ValueError("Qualified bank bytes differ: " + name)
        musical[name] = data
    notice = plain(support / "NOTICE-FR.txt")
    cc0 = plain(support / "converter/VSCO-CC0-LICENSE.txt")
    musical.update({"NOTICE-FR.txt": notice, "LICENSE-CC0.txt": cc0, "bank-catalog.json": catalog_raw})
    musical["SHA256SUMS.txt"] = text_manifest(musical)
    source = {"converter/" + name: plain(support / "converter" / name) for name in CONVERTER_FILES}
    source.update({"evidence/" + name: plain(support / "evidence" / name) for name in EVIDENCE_FILES})
    for name in ["NOTICE-FR.txt", "RECONSTRUIRE-FR.txt", "bank-catalog.json", "prepare_assets.py"]:
        source[name] = plain(support / name)
    source["SOURCE-SHA256SUMS.txt"] = text_manifest(source)
    output.mkdir(parents=True, exist_ok=False)
    names = {"sounds": f"{PREFIX}sons-{VERSION}.zip", "sources": f"{PREFIX}convertisseur-{VERSION}.zip",
             "notice": f"{PREFIX}notice-{VERSION}.txt", "license": f"{PREFIX}CC0-{VERSION}.txt",
             "checksums": f"{PREFIX}SHA256SUMS-{VERSION}.txt"}
    names.update(cello_sf2="Cadence-VSCO-Cello-Ensemble.sf2", trumpet_sf2="Cadence-VSCO-Trumpet.sf2", contrabass_sf2="Cadence-VSCO-Contrabass.sf2")
    archive(output / names["sounds"], musical)
    archive(output / names["sources"], source)
    (output / names["notice"]).write_bytes(notice)
    (output / names["license"]).write_bytes(cc0)
    for kind in ("cello_sf2", "trumpet_sf2", "contrabass_sf2"):
        # Raw assets are immutable verified source banks. A hard link avoids a
        # second local 118 MB copy; Windows/filesystems may fall back to copy.
        import os, shutil
        try:
            os.link(banks / names[kind], output / names[kind])
        except OSError:
            shutil.copyfile(banks / names[kind], output / names[kind])
    (output / names["checksums"]).write_bytes(text_manifest({name: plain(output / name) for kind, name in names.items() if kind != "checksums"}))
    receipts = [{"kind": kind, "name": name, "member_path": name, "bytes": (output / name).stat().st_size,
                 "sha256": sha(plain(output / name))} for kind, name in names.items()]
    return {"schema_version": 1, "scope": "Sounds and independent converter only; no application/installer", "version": VERSION,
            "ready": False, "qualified_run": 43304846264, "assets": receipts, "publication_performed": False}

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--support-root", type=Path, required=True)
    parser.add_argument("--banks", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.support_root, args.banks, args.output)
    (args.output / "asset-preparation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
