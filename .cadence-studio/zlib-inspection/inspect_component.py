"""Inspect retained zlib component data; never compile, load or execute it."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import xml.etree.ElementTree as ET

RUN_ID = 43101767743
ARTIFACT_ID = 13891238030
ARTIFACT_DIGEST = "d8e12e1fd1498b1ecb7967818bfb9b5769b8e16b7257239c9307dbf7f64d3b99"
SOURCE_COMMIT = "da607da739fa6047df13e66a2af6b8bec7c2a498"
SOURCE_HASH = "bb329a0a2cd0274d05519d61c667c062e06990d72e125ee2dfa8de64f0119d16"


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for data in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(data)
    return digest.hexdigest()


def child(root, name):
    relative = PurePosixPath(name.replace("\\", "/"))
    if relative.is_absolute() or ".." in relative.parts or ":" in name:
        raise ValueError(f"Unsafe retained path: {name}")
    result = root.joinpath(*relative.parts)
    if not result.resolve().is_relative_to(root.resolve()) or not result.is_file() or result.is_symlink():
        raise ValueError(f"Missing or linked retained file: {name}")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.input.resolve()
    if args.output.exists():
        raise ValueError("Inspection output must be new; nothing is replaced")
    sums_path = child(root, "SHA256SUMS.txt")
    checksums = {}
    for line in sums_path.read_text(encoding="utf-8-sig").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match or match[2] in checksums:
            raise ValueError("Malformed or duplicate SHA256SUMS entry")
        actual = sha(child(root, match[2]))
        if actual != match[1]:
            raise ValueError(f"Retained checksum mismatch: {match[2]}")
        checksums[match[2]] = actual
    manifest_path = child(root, "zlib-profile-manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    expected = {
        "schema_version": 1, "component": "zlib", "version": "1.3.2",
        "status": "component-tested-awaiting-Cadence-link-and-file-compatibility-tests",
        "upstream_commit": SOURCE_COMMIT, "archive_sha256": SOURCE_HASH,
        "target_platform": "Windows x64", "linkage": "static", "runtime": "/MD", "configuration": "Release",
        "source_unchanged": True, "upstream_tests_passed": True, "installed_api_probe_passed": True,
        "cadence_application_link_tested": False, "retained_stage7_changed": False,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise ValueError(f"Unexpected native manifest field: {key}")
    if str(manifest.get("ci_run_id")) != str(RUN_ID):
        raise ValueError("Component manifest belongs to another workflow run")
    critical = {}
    for relative in ("lib/zs.lib", "include/zlib.h", "include/zconf.h"):
        name = "stage/" + relative
        digest = sha(child(root, name))
        if manifest["artifact_sha256"].get(relative) != digest or checksums.get(name) != digest:
            raise ValueError(f"Installed component does not match the manifest: {name}")
        critical[name] = digest
    source_archive = "sources/zlib-1.3.2.tar.gz"
    if sha(child(root, source_archive)) != SOURCE_HASH:
        raise ValueError("Retained upstream source archive changed")
    source_snapshot = json.loads(child(root, "source-file-sha256.json").read_text(encoding="utf-8-sig"))
    for name, digest in source_snapshot.items():
        if sha(child(root, "sources/unmodified/zlib-1.3.2/" + name)) != digest:
            raise ValueError(f"Retained source file changed: {name}")
    tests = {}
    for name, count in (("upstream-tests.xml", 13), ("profile-api-tests.xml", 1)):
        suite = ET.parse(child(root, name)).getroot()
        if int(suite.get("tests", "0")) != count or int(suite.get("failures", "0")) or int(suite.get("errors", "0")):
            raise ValueError(f"Native CTest report is not the expected successful suite: {name}")
        tests[name] = {"tests": count, "failures": 0, "errors": 0}
    headers = child(root, "archive-headers.log").read_text(encoding="utf-8-sig", errors="replace")
    directives = child(root, "archive-directives.log").read_text(encoding="utf-8-sig", errors="replace")
    if not re.search(r"8664 machine", headers, re.I) or not re.search("MSVCRT", directives, re.I) or re.search("LIBCMT|MSVCRTD", directives, re.I):
        raise ValueError("Native dumpbin proof does not identify x64 /MD Release")
    report = {
        "schema_version": 1, "status": "verified-retained-component-only", "reader_platform": sys.platform,
        "run_id": RUN_ID, "artifact_id": ARTIFACT_ID, "artifact_digest_from_github_metadata": ARTIFACT_DIGEST,
        "outer_archive_digest_recomputed_by_reader": False,
        "manifest_sha256": sha(manifest_path), "checksum_file_sha256": sha(sums_path),
        "verified_checksum_entries": len(checksums), "verified_source_files": len(source_snapshot),
        "source_archive_sha256": SOURCE_HASH, "critical_sha256": critical, "native_tests": tests,
        "native_manifest": manifest, "reader_compiled_or_executed_any_payload": False,
        "cadence_migrated_to_this_component": False,
    }
    # Persist exact original bytes, rather than rewriting provenance as a build.
    args.output.mkdir(parents=True)
    for name in ("zlib-profile-manifest.json", "SHA256SUMS.txt", "upstream-tests.xml", "profile-api-tests.xml", "zlib.lock.json"):
        shutil.copyfile(child(root, name), args.output / name)
    (args.output / "zlib-component-inspection.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("ZLIB_COMPONENT_INSPECTION_BEGIN")
    print(json.dumps(report, indent=2))
    print("ZLIB_COMPONENT_INSPECTION_END")


if __name__ == "__main__":
    main()
