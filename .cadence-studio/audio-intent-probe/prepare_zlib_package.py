"""Inspect retained zlib component data; never compile, load or execute it."""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tarfile
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


@contextmanager
def verified_hash_reader(root):
    archive_path = child(root, "sources/zlib-1.3.2.tar.gz")
    if sha(archive_path) != SOURCE_HASH:
        raise ValueError("Retained upstream source archive changed")
    reconstructed = []
    cache = {}
    with tarfile.open(archive_path, "r:gz") as source_archive:
        def retained_sha(name):
            if name in cache:
                return cache[name]
            relative = PurePosixPath(name.replace("\\", "/"))
            if relative.is_absolute() or ".." in relative.parts or ":" in name:
                raise ValueError(f"Unsafe retained path: {name}")
            candidate = root.joinpath(*relative.parts)
            if candidate.exists():
                digest = sha(child(root, name))
            elif name.startswith("sources/unmodified/zlib-1.3.2/"):
                # upload-artifact excludes hidden files. Recover ONLY original
                # source bytes from the independently pinned complete archive;
                # never ignore a missing checksum or invent missing payload.
                member_name = "zlib-1.3.2/" + name.removeprefix("sources/unmodified/zlib-1.3.2/")
                member = source_archive.getmember(member_name)
                if not member.isfile() or member.size > 64 * 1024 * 1024:
                    raise ValueError(f"Missing source is not an ordinary bounded archive file: {name}")
                with source_archive.extractfile(member) as stream:
                    digest = hashlib.file_digest(stream, "sha256").hexdigest()
                reconstructed.append({"path": name, "sha256": digest, "bytes": member.size})
            else:
                raise ValueError(f"Missing retained non-source file: {name}")
            cache[name] = digest
            return digest
        yield retained_sha, reconstructed


def prepare_package(root, destination, reconstructed):
    """Create a new complete package; original transport and existing files stay intact."""
    if destination.exists() or destination.resolve().is_relative_to(root.resolve()):
        raise ValueError("Prepared package must be a new directory outside the input")
    for source in root.rglob("*"):
        if source.is_symlink() or getattr(source, "is_junction", lambda: False)():
            raise ValueError("Original package contains a linked path")
    shutil.copytree(root, destination)
    with tarfile.open(child(root, "sources/zlib-1.3.2.tar.gz"), "r:gz") as archive:
        for item in reconstructed:
            relative = PurePosixPath(item["path"])
            target = destination.joinpath(*relative.parts)
            if target.exists():
                raise ValueError("Source transport repair would replace an existing file")
            member = archive.getmember("zlib-1.3.2/" + item["path"].removeprefix("sources/unmodified/zlib-1.3.2/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output)
            if sha(target) != item["sha256"]:
                raise ValueError("Reconstituted source file does not match its original checksum")
    for line in child(destination, "SHA256SUMS.txt").read_text(encoding="utf-8-sig").splitlines():
        digest, name = line.split("  ", 1)
        if sha(child(destination, name)) != digest:
            raise ValueError("Prepared package checksum verification failed")
    repair = {"schema_version": 1, "operation": "restore source transport omissions into a new package only",
              "original_input": str(root), "source_archive_sha256": SOURCE_HASH,
              "restored_source_files": reconstructed, "existing_files_overwritten": False,
              "component_recompiled_or_executed": False}
    (destination / "transport-repair.json").write_text(json.dumps(repair, indent=2) + "\n", encoding="utf-8")
    return str(destination.resolve())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepared-package", type=Path)
    args = parser.parse_args()
    root = args.input.resolve()
    destinations = [args.output.resolve()] + ([args.prepared_package.resolve()] if args.prepared_package else [])
    for destination in destinations:
        if destination.is_relative_to(root) or root.is_relative_to(destination):
            raise ValueError("Output directories must be disjoint from the original input")
    if len(destinations) == 2 and (destinations[0].is_relative_to(destinations[1]) or destinations[1].is_relative_to(destinations[0])):
        raise ValueError("Inspection and prepared package directories must be disjoint")
    if args.output.exists():
        raise ValueError("Inspection output must be new; nothing is replaced")
    if args.prepared_package and (args.prepared_package.exists() or args.prepared_package.resolve() == args.output.resolve()):
        raise ValueError("Prepared package must be new and distinct from the inspection output")
    with verified_hash_reader(root) as (retained_sha, reconstructed):
        sums_path = child(root, "SHA256SUMS.txt")
        checksums = {}
        for line in sums_path.read_text(encoding="utf-8-sig").splitlines():
            match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
            if not match or match[2] in checksums:
                raise ValueError("Malformed or duplicate SHA256SUMS entry")
            actual = retained_sha(match[2])
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
            if retained_sha("sources/unmodified/zlib-1.3.2/" + name) != digest:
                raise ValueError(f"Retained source file changed: {name}")
        tests = {}
        for name, count in (("upstream-tests.xml", 13), ("profile-api-tests.xml", 1)):
            suite = ET.parse(child(root, name)).getroot()
            if int(suite.get("tests", "0")) != count or int(suite.get("failures", "0")) or int(suite.get("errors", "0")) or int(suite.get("skipped", "0")):
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
            "transport_missing_source_files_verified_from_pinned_archive": reconstructed,
            "source_archive_sha256": SOURCE_HASH, "critical_sha256": critical, "native_tests": tests,
            "native_manifest": manifest, "reader_compiled_or_executed_any_payload": False,
            "cadence_migrated_to_this_component": False,
        }
    if args.prepared_package:
        report["prepared_package"] = prepare_package(root, args.prepared_package, reconstructed)
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
