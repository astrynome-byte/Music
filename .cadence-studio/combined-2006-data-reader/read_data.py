# SPDX-License-Identifier: GPL-3.0-only
"""Authenticate retained2006 stage/delivery/logs as data; execute no staged program or MSI."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parent))
from download_originals import acquire, require, RUN, DRIVER
from read_only_msi import properties

ORIGINAL = "ac9a24933f78f22ea630570910848201baad3d3b"
TREE = "a94a09974229c47e7b90b593a7649c29d6a6d190"
SOURCE_JSON_SHA = "0d6c5944374cfa2b58ee8f81a3912b36585ed263ed79ffb3ff1968f2bd07ca1b"
PATCH_SHA = "cba5d10112b8cd7ce470577e07cc70fb8d1cd849ec412b652c0a6b71bf4e3ce7"
EXE_SHA = "c29d7c8c76b213b79d7390acd65cbabc6fb940f06e3e7f86c0ce60be7e9b9520"
MSI_SHA = "47e93cedd47d76baa7f91542cc937ea1ee3797e45d47d3532b327b90879fe5e9"
STAGE_ZIP = "CadenceStudio-v4.7.6-combined-system-aac-stage-build-2006-attempt-1-x64.zip"
PREFIX = "CadenceStudio-4.7.6-cadence.2006-x86_64"

# Reused unchanged from the preserved 2005 reader.
def digest(stream):
    sha = hashlib.sha256()
    for data in iter(lambda: stream.read(1024 * 1024), b''):
        sha.update(data)
    return sha.hexdigest()

def file_hash(path):
    with path.open('rb') as stream:
        return digest(stream)

def relative(name):
    require(isinstance(name, str) and len(name) <= 2048, "Missing/oversized member path")
    if name.startswith("./"): name = name[2:]
    require(name and not name.startswith("/") and not re.search(r"[\\:\x00-\x1f]", name)
            and all(part not in ("", ".", "..") for part in name.split("/")), "Unsafe member path")
    return name

class Container:
    def __init__(self, path):
        self.zip = zipfile.ZipFile(path)
        self.files = {}
        total = 0
        infos = self.zip.infolist()
        require(len(infos) <= 25000, "ZIP inventory exceeds bound")
        for info in infos:
            if info.is_dir(): continue
            name = relative(info.filename)
            require(name not in self.files and not info.flag_bits & 1 and (info.external_attr >> 16) & 0o170000 != 0o120000,
                    "Duplicate, encrypted or linked ZIP member")
            require(info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED) and 0 <= info.file_size <= 838860800,
                    "Unsupported or oversized ZIP member")
            total += info.file_size
            require(total <= 3221225472, "ZIP uncompressed total exceeds bound")
            self.files[name] = info

    def rooted(self, prefix):
        # upload-artifact's common ancestor can be above RUNNER_TEMP because
        # the original delivery also includes files from GITHUB_WORKSPACE.
        view = object.__new__(Container)
        view.zip = self.zip
        view.files = {name[len(prefix):]: info for name, info in self.files.items() if name.startswith(prefix)}
        require(view.files, "Empty exact delivery subtree")
        return view

    def raw(self, name, maximum=2097152):
        require(name in self.files and self.files[name].file_size <= maximum, "Missing/large requested data member")
        return self.zip.read(self.files[name])

    def obj(self, name):
        return json.loads(self.raw(name).decode("utf-8-sig"))

    def hashes(self):
        records = {}
        for name, info in self.files.items():
            with self.zip.open(info) as stream:
                checksum = digest(stream)
            records[name] = {"bytes": info.file_size, "sha256": checksum}
        return records

    def ledger(self):
        expected = {}
        for line in self.raw("SHA256SUMS.txt", 1048576).decode("ascii").splitlines():
            match = re.fullmatch(r"([a-f0-9]{64})  (.+)", line)
            require(match is not None, "Malformed original checksum record")
            checksum, name = match.groups(); name = relative(name)
            require(name != "SHA256SUMS.txt" and name not in expected, "Duplicate or self-referential checksum")
            expected[name] = checksum
        require(set(self.files) == set(expected) | {"SHA256SUMS.txt"}, "Original checksum inventory incomplete")
        measured = self.hashes()
        require(all(measured[name]["sha256"] == checksum for name, checksum in expected.items()), "Original member checksum mismatch")
        return measured

    def materialize(self, name, destination):
        require(name in self.files and not destination.exists(), "Exact selected data member and new destination required")
        with self.zip.open(self.files[name]) as source, destination.open("xb") as output:
            shutil.copyfileobj(source, output, 1048576)
        require(destination.stat().st_size == self.files[name].file_size, "Selected member length differs")
        return destination

def plain_path(path):
    for item in (path, *path.parents):
        require(not item.is_symlink() and not (getattr(item, "is_junction", lambda: False)()), "Linked input/output path refused")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-selection", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted", "Hosted disposable CI required")
    temporary = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    for path in (args.work, args.output):
        plain_path(path)
        require(path.is_absolute() and path.resolve().is_relative_to(temporary) and not path.exists(), "New owned paths under RUNNER_TEMP required")
    require(not args.work.is_relative_to(args.output) and not args.output.is_relative_to(args.work), "Separate work and receipt roots required")
    for name, expected in (("source.json", SOURCE_JSON_SHA), ("changes.patch.gz", PATCH_SHA)):
        require(file_hash(args.source_selection / name) == expected, "Frozen source-selection bytes changed")
    args.output.mkdir(parents=True)
    result = {"schema_version": 1, "status": "failed", "producer_run_id": RUN, "driver_commit": DRIVER,
              "original_source_commit": ORIGINAL, "source_tree": TREE, "build_number": 2006,
              "source_json_sha256": SOURCE_JSON_SHA, "source_patch_sha256": PATCH_SHA,
              "application_executed": False, "installer_executed": False, "application_rebuilt": False,
              "registry_or_product_state_queried": False, "new_installation_test_performed": False,
              "distribution_compliance_closed": False, "error": None}
    opened = []
    try:
        acquired = acquire(args.work); result["acquisition"] = acquired
        stage = Container(args.work / "stage.zip"); delivery_outer = Container(args.work / "delivery.zip"); logs = Container(args.work / "logs.zip")
        opened += [stage, delivery_outer, logs]
        stage_hashes, delivery_outer_hashes = stage.ledger(), delivery_outer.hashes()
        ledgers = [name for name in delivery_outer.files if name == "SHA256SUMS.txt" or name.endswith("/cadence-delivery/SHA256SUMS.txt")
                   or name == "cadence-delivery/SHA256SUMS.txt"]
        require(len(ledgers) == 1, "One actual delivery checksum subtree required")
        delivery_prefix = ledgers[0][:-len("SHA256SUMS.txt")]
        delivery = delivery_outer.rooted(delivery_prefix)
        delivery_hashes = delivery.ledger()
        result["delivery_archive_root"] = delivery_prefix
        manifest, build, state = stage.obj("stage-manifest.json"), stage.obj("cadence-build-result.json"), stage.obj("cadence-build.json")
        require(manifest["original_source_commit"] == ORIGINAL and manifest["source_tree"] == TREE and manifest["build_number"] == 2006
                and manifest["run_number"] == 6 and manifest["run_attempt"] == 1 and manifest["qt_version"] == "6.10.2"
                and manifest["stage_archive"] == STAGE_ZIP and manifest["status"] == "experimental-stage-before-qa", "Actual stage provenance differs")
        ci = manifest["source_commit"]; result["source_commit"] = ci
        require(re.fullmatch(r"[a-f0-9]{40}", ci) and build["source_commit"] == ci and state["source_commit"] == ci
                and state["source_dirty_at_configure"] is False and build["source_dirty_at_build"] is False
                and state["build_number"] == 2006 and state["variant"] == "Cadence", "Clean build/source records disagree")
        require(stage_hashes[STAGE_ZIP]["sha256"] == manifest["stage_archive_sha256"], "Measured stage ZIP differs from manifest")
        release = delivery.obj("release-manifest.json")
        require(release["source_commit"] == ci and release["source_tree"] == TREE and release["build_number"] == 2006
                and release["installer"] == PREFIX + ".msi", "Delivery provenance/installer name differs")
        stage_zip = stage.materialize(STAGE_ZIP, args.work / "stage-inner.zip")
        delivery_zip = delivery.materialize(PREFIX + "-staged.zip", args.work / "delivery-inner.zip")
        inner_stage, inner_delivery = Container(stage_zip), Container(delivery_zip); opened += [inner_stage, inner_delivery]
        stage_files, delivery_files = inner_stage.hashes(), inner_delivery.hashes()
        require(stage_files == delivery_files, "Staged file contents changed between retained stage and delivery")
        exe = stage_files["bin/CadenceStudio4.exe"]
        require(exe["sha256"] == EXE_SHA == manifest["executable_sha256"] == build["executable_sha256"], "Actual EXE differs from pinned stage/build")
        msi_name = PREFIX + ".msi"
        require(delivery_hashes[msi_name]["sha256"] == MSI_SHA, "Actual MSI differs from the authenticated full2006 hash")
        msi = delivery.materialize(msi_name, args.work / "installer.msi")
        result["msi"] = {"name": msi_name, **delivery_hashes[msi_name], "readonly_database": properties(msi)}
        require(file_hash(msi) == MSI_SHA, "MSI bytes changed during the read-only database query")
        if os.name == "nt":
            require(result["msi"]["readonly_database"]["version_matches_expected_family"]
                    and result["msi"]["readonly_database"]["upgrade_matches_cadence_identity"], "MSI version or independent identity differs")
        report_matches = [(container, name) for container in (delivery_outer, logs) for name in container.files
                          if name == "msi-install-report.json" or name.endswith("/msi-qa/msi-install-report.json")
                          or name == "msi-qa/msi-install-report.json"]
        require(len(report_matches) == 1, "One exact existing historical MSI report required")
        result["historical_msi_report"] = {"found": False, "install_exit_code": None, "uninstall_exit_code": None}
        if report_matches:
            owner, name = report_matches[0]; raw = owner.raw(name); historical = json.loads(raw.decode("utf-8-sig"))
            (args.output / "actual-msi-install-report.json").write_bytes(raw)
            require(historical["msi_sha256"] == MSI_SHA and historical["installed_executable_sha256"] == EXE_SHA
                    and historical["source_commit"] == ci, "Historical install report belongs to different bytes/source")
            result["historical_msi_report"] = {"found": True, "member_path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                **{key: historical.get(key) for key in ("status", "product_name", "product_code", "product_version", "upgrade_code", "summary_template",
                    "install_exit_code", "install_reboot_required", "cli_exit_code", "cli_version_matched", "uninstall_exit_code",
                    "uninstall_reboot_required", "product_removed", "gui_tested", "gui_status", "gui_exit_status", "gui_startup_observed",
                    "clean_exit_observed", "notice_verification_requested", "installed_notices_verified", "error", "cleanup_error")}}
            if os.name == "nt":
                require(historical["product_version"] == result["msi"]["readonly_database"]["properties"]["ProductVersion"], "Historical MSI version differs from actual read-only Property table")
        result.update(status="authenticated-actual-2006-stage-and-delivery-as-data", executable=exe,
                      stage_archive={"name": STAGE_ZIP, **stage_hashes[STAGE_ZIP]},
                      delivery_stage_archive={"name": PREFIX + "-staged.zip", **delivery_hashes[PREFIX + "-staged.zip"]},
                      inner_stage_files_equal=True, inner_stage_files_hashed=len(stage_files),
                      original_stage_members_hashed=len(stage_hashes), original_delivery_members_hashed=len(delivery_outer_hashes),
                      delivery_subtree_members_hashed=len(delivery_hashes))
        for name, data in (("stage-file-hashes.json", stage_files), ("stage-original-member-hashes.json", stage_hashes),
                           ("delivery-original-member-hashes.json", delivery_outer_hashes), ("delivery-subtree-member-hashes.json", delivery_hashes)):
            (args.output / name).write_text(json.dumps(data, indent=2) + "\n")
        for name, container in (("stage-manifest.json", stage), ("cadence-build-result.json", stage), ("cadence-build.json", stage), ("release-manifest.json", delivery)):
            (args.output / ("actual-" + name)).write_bytes(container.raw(name))
    except Exception as error:
        result["error"] = str(error)
    finally:
        for container in opened: container.zip.close()
        (args.output / "data-receipt.json").write_text(json.dumps(result, indent=2) + "\n")
        print("CADENCE_2006_DATA_RECEIPT_BEGIN"); print(json.dumps(result, separators=(",", ":"))); print("CADENCE_2006_DATA_RECEIPT_END")
    return 0 if result["error"] is None else 1

if __name__ == "__main__":
    raise SystemExit(main())
