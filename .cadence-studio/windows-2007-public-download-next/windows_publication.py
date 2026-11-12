# SPDX-License-Identifier: GPL-3.0-only
"""Bounded data-only preparation of an experimental 2007 delivery; no MSI/app execution."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tarfile
import zipfile

RUN = 43266732201
DRIVER = "c3421a217c76a1b2cc5d4fab74305d209491d82f"
SOURCE = "5058d29dad67e6131ee46ee617258ccfed8ba4b0"
TREE = "58d06a1c89e99173b0473587245187df5bc3b3cf"
SOURCE_JSON_SHA = "e0e36a40d2bee76337d8117016d0ca064e24fb2be2b9713b69855d6182a61fa9"
PATCH_SHA = "87de70f2c00e2d0e92efd1056a6bd7fab50f95a06c1fcc94a728fb3262e946d7"
QTCORE_SHA = "b98eea394a95563879b614dbd4432ce074b0fceeb154c3bae252f4e7a9376a40"
PREFIX = "CadenceStudio-4.7.6-cadence.2007-x86_64"
ROLES = ("msi", "source_archive", "build_recipe", "component_sources", "notices", "guide", "checksums")
ASSET_NAMES = dict(zip(ROLES, (PREFIX + ".msi", PREFIX + "-source.tar.gz", PREFIX + "-build-recipe.zip", PREFIX + "-component-sources.zip", PREFIX + "-notices.zip", PREFIX + "-GUIDE-FR.txt", PREFIX + "-SHA256SUMS.txt")))
REPORTS = ("bootstrap", "build", "stage_manifest", "release_manifest", "cli", "msi", "notices", "components", "icu_policy", "icu_exports")
SHA = re.compile(r"[a-f0-9]{64}")
GIT = re.compile(r"[a-f0-9]{40}")
MAX = 2_147_483_648

def require(ok, message):
    if not ok: raise ValueError(message)

def digest(path):
    with Path(path).open("rb") as stream: return hashlib.file_digest(stream, "sha256").hexdigest()

def relative(name):
    require(isinstance(name, str) and 0 < len(name) <= 2048 and not name.startswith("/")
            and not re.search(r"[\\:\x00-\x1f]", name)
            and all(part not in ("", ".", "..") for part in name.split("/")), "Unsafe relative member")
    return name

def plain(path):
    for part in (path, *path.parents):
        require(not part.is_symlink() and not getattr(part, "is_junction", lambda: False)(), "Linked path refused")

def receipt(root, entry, maximum=MAX):
    require(isinstance(entry, dict) and isinstance(entry.get("sha256"), str) and SHA.fullmatch(entry["sha256"])
            and type(entry.get("bytes")) is int and 0 < entry["bytes"] <= maximum, "Exact byte/SHA receipt required")
    path = root / relative(entry.get("member_path")); plain(path)
    require(path.is_file() and path.resolve().is_relative_to(root.resolve()) and path.stat().st_size == entry["bytes"]
            and digest(path) == entry["sha256"], "Missing or changed receipt member: " + entry["member_path"])
    return path

def validate_target(target, approval=True):
    require(type(target.get("schema_version")) is int and target["schema_version"] == 1, "Unsupported target schema")
    require(target.get("repository") == "astrynome-byte/Music" and target.get("version") == "4.7.6-cadence.2007"
            and type(target.get("build_number")) is int and target["build_number"] == 2007, "Only the frozen experimental2007 delivery is supported")
    require(type(target.get("ready")) is bool and (target["ready"] or not approval), "ready must be the reviewed boolean true")
    producer = target.get("producer", {})
    require(producer.get("run_id") == RUN and type(producer.get("run_id")) is int and producer.get("driver_commit") == DRIVER, "Original producer changed")
    source = target.get("source", {})
    require(source.get("original_commit") == SOURCE and source.get("tree") == TREE and source.get("source_json_sha256") == SOURCE_JSON_SHA
            and source.get("patch_sha256") == PATCH_SHA and isinstance(source.get("ci_commit"), str) and GIT.fullmatch(source["ci_commit"]), "Actual frozen source/CI tree required")
    require(all(isinstance(target.get(k), str) and SHA.fullmatch(target[k]) for k in ("executable_sha256", "msi_sha256")), "Actual EXE/MSI hashes required; template deliberately refused")
    limitations = target.get("limitations", {})
    require(limitations.get("tested_platform") == "Windows Server 2022 (GitHub Actions)"
            and all(limitations.get(k) is False for k in ("windows10_client_tested", "windows11_client_tested", "human_listening_completed", "paid_equivalence_complete", "final_gift")), "Experimental platform and incomplete-feature limits must remain explicit")
    artifacts = target.get("artifacts")
    require(isinstance(artifacts, list) and len(artifacts) == 3 and all(isinstance(a, dict) for a in artifacts)
            and {a.get("role") for a in artifacts} == {"stage", "delivery", "logs"}, "Three exact original artifact roles required")
    require(len({a.get("id") for a in artifacts}) == 3, "Duplicate artifact id")
    for row in artifacts:
        require(type(row.get("id")) is int and row["id"] > 0 and row.get("run_id") == RUN
                and isinstance(row.get("name"), str) and re.fullmatch(r"cadence-combined-system-aac-(?:stage-experimental-|experimental-|logs-)7-1", row["name"])
                and isinstance(row.get("digest"), str) and re.fullmatch(r"sha256:[a-f0-9]{64}", row["digest"])
                and type(row.get("bytes")) is int and 0 < row["bytes"] <= MAX and isinstance(row.get("expires_at"), str)
                and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", row["expires_at"]), "Actual original artifact identity/digest/size/expiry required")
        expected_name = {"stage": "cadence-combined-system-aac-stage-experimental-7-1", "delivery": "cadence-combined-system-aac-experimental-7-1", "logs": "cadence-combined-system-aac-logs-7-1"}[row["role"]]
        require(row["name"] == expected_name, "Artifact role/name differs")
    require(isinstance(target.get("reports"), dict) and set(target["reports"]) == set(REPORTS), "Exact original report receipts required")
    for row in target["reports"].values():
        require(row.get("artifact_role") in ("stage", "delivery", "logs"), "Report must belong to the pinned fullrun")
        relative(row.get("member_path"))
        require(isinstance(row.get("sha256"), str) and SHA.fullmatch(row["sha256"]) and type(row.get("bytes")) is int and 0 < row["bytes"] <= 4_000_000, "Actual report byte receipts required")
    if approval:
        review = target.get("review", {})
        require(review.get("approved") is True and isinstance(review.get("reviewed_by"), str) and review["reviewed_by"].strip()
                and isinstance(review.get("reviewed_utc"), str) and review["reviewed_utc"], "Root review of actual bytes/notices remains required")
        release = target.get("release", {})
        require(release.get("prerelease") is True and release.get("target_commit_mode") == "workflow_head" and "target_commit" not in release
                and isinstance(release.get("tag"), str) and re.fullmatch(r"cadence-studio/v?4\.7\.6-cadence\.2007-experimental\.[1-9][0-9]*", release["tag"])
                and isinstance(release.get("title"), str) and len(release["title"]) <= 140 and re.search(r"exp[eé]rimental", release["title"], re.I), "New explicitly experimental prerelease at the workflow HEAD required")
        require(not re.search(r"\b(?:finale?|cadeau|compl[eè]te?|complete)\b", release["title"], re.I), "Final/gift/complete claims are outside this experimental delivery")
        rows = target.get("assets")
        require(isinstance(rows, list) and len(rows) == 7 and {a.get("kind") for a in rows} == set(ROLES)
                and len({a.get("name") for a in rows}) == 7, "Exactly seven distinct approved assets required")
        for row in rows:
            require(isinstance(row.get("name"), str) and re.fullmatch(re.escape(PREFIX) + r"[A-Za-z0-9._-]*", row["name"])
                    and row["name"] == ASSET_NAMES[row["kind"]] and row.get("member_path") == row["name"] and isinstance(row.get("sha256"), str) and SHA.fullmatch(row["sha256"])
                    and type(row.get("bytes")) is int and 0 < row["bytes"] <= MAX, "Immutable reviewed asset receipt required")
    return target

def json_receipts(target, acquired):
    docs = {}
    for kind, row in target["reports"].items():
        docs[kind] = json.loads(receipt(acquired / row["artifact_role"], row, 4_000_000).read_text(encoding="utf-8-sig"))
    return docs

def check_reports(target, docs):
    ci = target["source"]["ci_commit"]; exe = target["executable_sha256"]; msi = target["msi_sha256"]
    boot, build, release = (docs[k] for k in ("bootstrap", "build", "release_manifest"))
    require(boot.get("original_source_commit") == SOURCE and boot.get("source_tree") == TREE and boot.get("ci_source_commit") == ci, "Bootstrap source mismatch")
    require(build.get("source_commit") == ci and build.get("source_dirty_at_build") is False and build.get("executable_sha256") == exe, "Build/executable mismatch")
    require(release.get("source_commit") == ci and release.get("source_tree") == TREE and release.get("build_number") == 2007 and release.get("installer") == PREFIX + ".msi", "Package source/version/installer mismatch")
    stage_manifest = docs["stage_manifest"]
    require(stage_manifest.get("original_source_commit") == SOURCE and stage_manifest.get("source_commit") == ci
            and stage_manifest.get("source_tree") == TREE and stage_manifest.get("build_number") == 2007
            and stage_manifest.get("run_number") == 7 and stage_manifest.get("run_attempt") == 1
            and stage_manifest.get("qt_version") == "6.10.2" and stage_manifest.get("executable_sha256") == exe, "Stage provenance differs")
    cli = docs["cli"]; rows = cli.get("checks")
    expected = {(f, s) for f in ("piano", "voice", "guitar", "percussion", "ensemble") for s in ("import-save-native", "reopen-native", "export-mxl", "export-pdf", "export-svg", "export-png", "export-mid", "export-wav", "export-flac", "export-mp3")}
    expected |= {("ensemble", "extract-native-parts")} | {("ensemble", f"part-{i:02d}-reopen-pdf") for i in range(1, 7)}
    require(cli.get("executable_sha256") == exe and type(cli.get("version_exit_code")) is int and cli["version_exit_code"] == 0
            and isinstance(rows, list) and len(rows) == 57 and {(r.get("fixture"), r.get("stage")) for r in rows} == expected, "Actual CLI57 coverage differs")
    for row in rows:
        require(row.get("passed") is True and not row.get("error") and "FAIL" not in str(row.get("stage", "")).upper()
                and type(row.get("exit_code")) is int and row["exit_code"] == 0 and row.get("outputs"), "CLI failure or missing outputs")
        for output in row["outputs"]:
            require(type(output.get("bytes")) is int and output["bytes"] > 0 and isinstance(output.get("sha256"), str) and SHA.fullmatch(output["sha256"]), "CLI output byte evidence missing")
            if row["stage"] == "export-wav": require(output.get("audio", {}).get("passed") is True, "CLI audio gate missing")
    install = docs["msi"]
    require(install.get("status") == "passed" and install.get("source_commit") == ci and install.get("msi_sha256") == msi
            and install.get("installed_executable_sha256") == exe and install.get("product_version") == "4.7.6.2007"
            and install.get("upgrade_code") == "{319B992F-470A-465B-9A79-6B0CBFC7D6C7}" and install.get("summary_template") == "x64;1033", "Actual MSI identity differs")
    require(all(type(install.get(k)) is int and install[k] in (0, 3010) for k in ("install_exit_code", "uninstall_exit_code"))
            and install.get("product_removed") is True and type(install.get("cli_exit_code")) is int and install["cli_exit_code"] == 0
            and install.get("cli_version_matched") is True and install.get("error") is None and install.get("cleanup_error") is None, "MSI install/CLI/uninstall did not pass")
    require(all(install.get(k) is True for k in ("gui_requested", "gui_tested", "gui_startup_observed", "clean_exit_observed", "require_system_icu", "installed_local_icuuc_absent"))
            and install.get("expected_product_version") == "4.7.6.2007" and install.get("gui_status") == "startup_observed_closed_cleanly"
            and type(install.get("gui_exit_status")) is int and install["gui_exit_status"] == 0, "MSI GUI/system ICU prerequisite missing")
    absence = install.get("installed_icu_absence_checks", [])
    require({r.get("phase") for r in absence} == {"before-installed-cli", "before-installed-gui"} and all(r.get("absent") is True for r in absence), "Installed ICU absence checks missing")
    notices = docs["notices"]; notes = notices.get("notices")
    require(notices.get("passed") is True and notices.get("status") == "passed_staged_notice_bytes_and_development_archive_exclusion"
            and notices.get("executable_sha256") == exe and notices.get("errors") == [] and isinstance(notes, list) and len(notes) > 0
            and type(notices.get("notice_files_verified")) is int and notices["notice_files_verified"] == len(notes), "Final stage notices not verified")
    expected_notes = [{"path": n["stage_path"], "bytes": n["bytes"], "sha256": n["sha256"]} for n in notes]
    require(install.get("notice_verification_requested") is True and type(install.get("installed_notices_verified")) is int and install["installed_notices_verified"] == len(notes)
            and install.get("installed_notices") == expected_notes and notices.get("mnxdom_development_archives_found") == []
            and notices.get("corresponding_source_archives_found_in_runtime") == [] and notices.get("corresponding_sources_remain_companion_files") is True, "Installed notice bytes/development archive exclusion differs")
    components = docs["components"]
    require(components.get("source_archives_verified") is True and components.get("errors") == []
            and notices.get("corresponding_source_report_sha256") == target["reports"]["components"]["sha256"], "Original component source collection/notices disagree")
    policy, exports = docs["icu_policy"], docs["icu_exports"]
    require(policy.get("status") == "local-forwarder-absent-and-system20exports-proved" and policy.get("local_forwarder_absent") is True
            and policy.get("qtcore_sha256") == QTCORE_SHA and policy.get("candidate_executable_sha256") == exe
            and policy.get("export_report_sha256") == target["reports"]["icu_exports"]["sha256"], "Stage ICU omission policy differs")
    require(exports.get("status") == "complete-static-export-evidence" and exports.get("complete") is True
            and exports.get("host_is_windows") is True and exports.get("local_forwarder_omission_export_gate_passed") is True
            and exports.get("errors") == [] and len(exports.get("resolutions", [])) == 20
            and all(r.get("complete") is True for r in exports["resolutions"]), "Actual system ICU20 export evidence incomplete")

def inventory(root):
    output = {}
    for path in sorted(root.rglob("*")):
        plain(path)
        if path.is_file():
            name = relative(path.relative_to(root).as_posix()); output[name] = {"bytes": path.stat().st_size, "sha256": digest(path)}
    require(len(output) <= 30000, "File inventory exceeds bound")
    return output

def verify_ledger(root):
    rows = (root / "SHA256SUMS.txt").read_text(encoding="ascii").splitlines(); expected = {}
    for line in rows:
        match = re.fullmatch(r"([a-f0-9]{64})  (.+)", line); require(match is not None, "Invalid source/delivery ledger")
        name = relative(match[2]); require(name not in expected and name != "SHA256SUMS.txt", "Duplicate ledger member")
        expected[name] = match[1]
    actual = inventory(root)
    require(set(actual) == set(expected) | {"SHA256SUMS.txt"} and all(actual[n]["sha256"] == s for n, s in expected.items()), "Original ledger does not cover exact member bytes")
    return actual

def unique_suffix(root, suffix):
    suffix = relative(suffix)
    found = [p for p in root.rglob("*") if p.is_file() and (p.relative_to(root).as_posix() == suffix or p.relative_to(root).as_posix().endswith("/" + suffix))]
    require(len(found) == 1, "One actual member required: " + suffix)
    plain(found[0]); return found[0]

def extract_zip(source, destination):
    require(not destination.exists(), "ZIP destination must be new")
    destination.mkdir(parents=True); seen = set(); total = 0
    with zipfile.ZipFile(source) as bundle:
        require(len(bundle.infolist()) <= 30000, "ZIP count bound")
        for info in bundle.infolist():
            if info.is_dir(): continue
            name = info.filename[2:] if info.filename.startswith("./") else info.filename; relative(name)
            key = name.casefold(); require(key not in seen, "Duplicate/case-colliding ZIP entry"); seen.add(key)
            require(not info.flag_bits & 1 and stat.S_IFMT(info.external_attr >> 16) != stat.S_IFLNK
                    and info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED) and 0 <= info.file_size <= MAX, "Unsupported ZIP entry")
            total += info.file_size; require(total <= 4 * MAX, "ZIP total byte bound")
            path = destination / name; path.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(info) as stream, path.open("xb") as output: shutil.copyfileobj(stream, output, 1048576)
            require(path.stat().st_size == info.file_size, "ZIP member length differs")

def stored_zip(destination, entries):
    require(not destination.exists() and entries, "New nonempty companion archive required")
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_STORED, allowZip64=True) as output:
        for name, path in sorted(entries.items()):
            relative(name); plain(path)
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0)); info.create_system = 3; info.external_attr = 0o100644 << 16
            with path.open("rb") as source, output.open(info, "w", force_zip64=True) as target: shutil.copyfileobj(source, target, 1048576)
    require(destination.stat().st_size <= MAX, "Companion archive exceeds public asset bound")

def read_msi_tables(path, target):
    require(os.name == "nt", "Actual MSI table inspection requires Windows; no simulated success")
    import _msi
    database = _msi.OpenDatabase(str(path), _msi.MSIDBOPEN_READONLY)
    properties = {}
    for name in ("ProductVersion", "ProductName", "UpgradeCode"):
        view = database.OpenView("SELECT `Value` FROM `Property` WHERE `Property`='" + name + "'")
        try:
            view.Execute(None); row = view.Fetch(); require(row is not None, "MSI Property missing")
            properties[name] = row.GetString(1)
        finally: view.Close()
    require(properties["ProductVersion"] == "4.7.6.2007" and properties["ProductName"] in ("Cadence Studio", "Cadence Studio 4")
            and properties["UpgradeCode"].upper() == "{319B992F-470A-465B-9A79-6B0CBFC7D6C7}", "Actual MSI Property identity differs")
    view = database.OpenView("SELECT `FileName` FROM `File`"); count = 0
    try:
        view.Execute(None)
        while True:
            row = view.Fetch()
            if row is None: break
            count += 1; require(count <= 30000, "MSI File table count bound")
            filename = row.GetString(1)
            require(isinstance(filename, str) and len(filename) <= 512 and filename.split("|")[-1].casefold() != "icuuc.dll", "The MSI File table still contains an ICU forwarder")
    finally: view.Close()
    require(count > 0 and digest(path) == target["msi_sha256"], "MSI bytes changed during read-only table inspection")
    return {"open_mode": int(_msi.MSIDBOPEN_READONLY), "properties": properties, "file_rows": count,
            "local_icuuc_file_table_absent": True, "installer_or_custom_action_executed": False}

def prepare(target, acquired, output):
    validate_target(target, approval=False)
    require(not output.exists(), "Prepared public asset root must be new"); output.mkdir(parents=True)
    docs = json_receipts(target, acquired); check_reports(target, docs)
    acquisition = json.loads((acquired / "artifact-acquisition.json").read_text())
    require(acquisition.get("producer_run") == RUN and acquisition.get("producer_driver_commit") == DRIVER
            and acquisition.get("original_outer_digests_recomputed") is True and acquisition.get("artifacts") == target["artifacts"], "Exact original acquisition receipt required")
    delivery = unique_suffix(acquired / "delivery", PREFIX + ".msi").parent
    verify_ledger(delivery)
    msi = delivery / (PREFIX + ".msi"); require(digest(msi) == target["msi_sha256"], "Actual installer differs")
    msi_tables = read_msi_tables(msi, target)
    source = delivery / (PREFIX + "-source.tar.gz"); plain(source)
    with tarfile.open(source, "r:gz") as archive:
        require(archive.pax_headers.get("comment") == target["source"]["ci_commit"], "Source archive does not identify the actual git archive commit")
    stage_zip = unique_suffix(acquired / "stage", "CadenceStudio-v4.7.6-combined-system-aac-stage-build-2007-attempt-1-x64.zip")
    verify_ledger(stage_zip.parent)
    require(digest(stage_zip) == docs["stage_manifest"].get("stage_archive_sha256"), "Original stage inner ZIP hash differs")
    stage = acquired / "stage-data-only"; extract_zip(stage_zip, stage)
    delivered_stage = acquired / "delivery-stage-data-only"
    extract_zip(delivery / (PREFIX + "-staged.zip"), delivered_stage)
    require(inventory(stage) == inventory(delivered_stage), "Actual stage/delivery runtime file inventories differ")
    require(digest(stage / "bin/CadenceStudio4.exe") == target["executable_sha256"] and digest(stage / "bin/Qt6Core.dll") == QTCORE_SHA, "Actual stage executable/QtCore differs")
    require(not any(n.casefold() == "bin/icuuc.dll" for n in inventory(stage)), "A local ICU forwarder remains in actual stage")
    recipe = delivery / "build-recipe"; recipe_files = inventory(recipe)
    require(recipe_files and digest(unique_suffix(recipe, "combined-2007-source/source.json")) == SOURCE_JSON_SHA
            and digest(unique_suffix(recipe, "combined-2007-source/changes.patch.gz")) == PATCH_SHA, "Original exact source selection absent from build recipe")
    components = delivery / "corresponding-sources"; verify_ledger(components)
    require(digest(components / "collection-report.json") == target["reports"]["components"]["sha256"], "Companion component collection differs")
    lock = json.loads((components / "sources.lock.json").read_text(encoding="utf-8"))
    require(digest(components / "sources.lock.json") == docs["components"]["source_lock_sha256"], "Component source lock differs")
    for row in lock["archives"]:
        path = components / "archives" / relative(row["archive"])
        require(path.stat().st_size == row["archive_bytes"] and digest(path) == row["sha256"], "Original corresponding archive changed")
    for original in (msi, source): shutil.copyfile(original, output / original.name)
    stored_zip(output / (PREFIX + "-build-recipe.zip"), {**{"build-recipe/" + n: recipe / n for n in recipe_files},
        "from-upstream.patch": delivery / (PREFIX + "-from-upstream.patch"), "release-manifest.json": delivery / "release-manifest.json"})
    stored_zip(output / (PREFIX + "-component-sources.zip"), {**{"corresponding-sources/" + n: components / n for n in inventory(components)},
        **{n: delivery / n for n in ("Cadence-zlib-1.3.2-corresponding-source.zip", "zlib-source-profile.lock.json", "zlib-source-supplement.json")}})
    note_entries = {}
    for row in docs["notices"]["notices"]:
        path = receipt(stage, {"member_path": row["stage_path"], "bytes": row["bytes"], "sha256": row["sha256"]})
        note_entries[relative(row["stage_path"])] = path
    stored_zip(output / (PREFIX + "-notices.zip"), note_entries)
    shutil.copyfile(Path(__file__).with_name("GUIDE-FR.txt"), output / (PREFIX + "-GUIDE-FR.txt"))
    kinds = ("msi", "source_archive", "build_recipe", "component_sources", "notices", "guide")
    names = (PREFIX + ".msi", PREFIX + "-source.tar.gz", PREFIX + "-build-recipe.zip", PREFIX + "-component-sources.zip", PREFIX + "-notices.zip", PREFIX + "-GUIDE-FR.txt")
    assets = [{"kind": k, "name": n, "member_path": n, "bytes": (output / n).stat().st_size, "sha256": digest(output / n)} for k, n in zip(kinds, names)]
    sums = output / (PREFIX + "-SHA256SUMS.txt"); sums.write_text("".join(a["sha256"] + "  " + a["name"] + "\n" for a in assets), encoding="ascii")
    assets.append({"kind": "checksums", "name": sums.name, "member_path": sums.name, "bytes": sums.stat().st_size, "sha256": digest(sums)})
    return {"schema_version": 1, "prepared_from_originals": True, "ready": False, "asset_receipts": assets, "source": target["source"], "producer": target["producer"], "msi_readonly_tables": msi_tables, "application_or_installer_executed": False}

def validate(target, acquired, prepared):
    validate_target(target)
    docs = json_receipts(target, acquired); check_reports(target, docs)
    facts = json.loads((prepared / "asset-preparation.json").read_text())
    require(facts.get("prepared_from_originals") is True and facts.get("source") == target["source"] and facts.get("producer") == target["producer"]
            and facts.get("asset_receipts") == target["assets"], "Prepared exact asset receipts were not reviewed")
    table_facts = facts.get("msi_readonly_tables", {})
    require(type(table_facts.get("open_mode")) is int and table_facts["open_mode"] == 0
            and table_facts.get("local_icuuc_file_table_absent") is True and table_facts.get("installer_or_custom_action_executed") is False
            and table_facts.get("properties", {}).get("ProductVersion") == "4.7.6.2007", "Actual read-only MSI table/ICU evidence is missing")
    for row in target["assets"]: receipt(prepared, row)
    require(next(a for a in target["assets"] if a["kind"] == "msi")["sha256"] == target["msi_sha256"], "Public MSI differs from tested installer")
    sums = next(a for a in target["assets"] if a["kind"] == "checksums")
    expected_sums = "".join(a["sha256"] + "  " + a["name"] + "\n" for a in target["assets"] if a["kind"] != "checksums")
    require(receipt(prepared, sums).read_text(encoding="ascii") == expected_sums, "Public SHA manifest does not cover the exact other six files")
    install = docs["msi"]
    summary = {"msi_product_version": install["product_version"], "install_exit_code": install["install_exit_code"],
               "uninstall_exit_code": install["uninstall_exit_code"], "install_reboot_required": install.get("install_reboot_required"),
               "uninstall_reboot_required": install.get("uninstall_reboot_required"), "installed_notice_files": install["installed_notices_verified"],
               "gui_status": install["gui_status"], "cli_checks": len(docs["cli"]["checks"]), "tested_platform": target["limitations"]["tested_platform"],
               "first_launch_wizard_tested": False, "msi_file_table_icuuc_absent": facts["msi_readonly_tables"]["local_icuuc_file_table_absent"]}
    return {"schema_version": 1, "allowed": True, "asset_receipts": target["assets"], "source": target["source"], "producer": target["producer"], "actual_qualification": summary, "scope": "Experimental Windows2007 bytes only; no publication performed by this validator"}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("check-target", "prepare", "validate")); parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--acquired", type=Path); parser.add_argument("--root", type=Path); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); result = {"schema_version": 1, "allowed": False, "error": None}
    try:
        plain(args.target); require(args.target.stat().st_size <= 4_000_000, "Oversized target")
        target = json.loads(args.target.read_text(encoding="utf-8-sig"))
        if args.mode == "check-target": validate_target(target); result.update(allowed=True)
        elif args.mode == "prepare":
            result = prepare(target, args.acquired.resolve(strict=True), args.root)
            (args.root / "asset-preparation.json").write_text(json.dumps(result, indent=2) + "\n")
        else: result = validate(target, args.acquired.resolve(strict=True), args.root.resolve(strict=True))
    except Exception as error:
        result["error"] = str(error); result["error_type"] = type(error).__name__
    require(not args.output.exists(), "Output receipt must be new")
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(result, indent=2) + "\n"); print(json.dumps(result))
    return 0 if result.get("allowed") is True or (args.mode == "prepare" and result.get("prepared_from_originals") is True and not result.get("error")) else 2

if __name__ == "__main__": raise SystemExit(main())
