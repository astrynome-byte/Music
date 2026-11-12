#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Check the real generated application graph before compiling system AAC.

This establishes configured source/link selection, not successful compilation,
runtime availability, or absence of unrelated third-party licensing duties.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


def check(build: Path) -> dict:
    cache_path = build / "CMakeCache.txt"
    cache_text = cache_path.read_text(encoding="utf-8-sig")
    cache = {}
    for line in cache_text.splitlines():
        if line and not line.startswith(("#", "//")) and "=" in line and ":" in line.split("=", 1)[0]:
            name, value = line.split("=", 1)
            cache[name.split(":", 1)[0]] = value
    for option in ("CADENCE_BUILD", "CADENCE_USE_WINDOWS_SYSTEM_AAC", "MUSE_MODULE_AUDIO_EXPORT",
                   "MUE_BUILD_IMPEXP_VIDEOEXPORT_MODULE"):
        if cache.get(option) != "ON":
            raise ValueError(f"Expected {option}=ON, got {cache.get(option)!r}")
    state_path = build / "cadence-build.json"
    state = json.loads(state_path.read_text(encoding="utf-8-sig"))
    if state.get("variant") != "Cadence" or state.get("windows_system_aac") is not True:
        raise ValueError("Build state does not identify the explicit Cadence system AAC profile")
    commands_path = build / "compile_commands.json"
    commands = json.loads(commands_path.read_text(encoding="utf-8-sig"))
    files = [item["file"].replace("\\", "/").lower() for item in commands]
    # Upstream enables Unity builds. Only inspect generated units that are
    # actually in compile_commands, instead of assuming each .cpp has its own
    # compiler command or disabling the established build recipe.
    unity_hashes = {}
    for item in commands:
        unit = Path(item["file"])
        if unit.parent.name.lower() != "unity" or not unit.name.lower().startswith("unity_"):
            continue
        unit = unit.resolve(strict=True)
        if not unit.is_relative_to(build.resolve()):
            raise ValueError(f"Generated Unity compilation unit is outside the build: {unit}")
        content = unit.read_text(encoding="utf-8-sig")
        included = re.findall(r'^\s*#\s*include\s+"([^"\r\n]+)"', content, flags=re.MULTILINE)
        if not included:
            raise ValueError(f"Generated Unity unit includes no source files: {unit}")
        files.extend(name.replace("\\", "/").lower() for name in included)
        unity_hashes[str(unit)] = hashlib.sha256(unit.read_bytes()).hexdigest()
    stems = {name.rsplit("/", 1)[-1] for name in files}
    required = {"windowsaacencoder.cpp", "windowsaacstream.cpp", "wavencoder.cpp",
                "flacencoder.cpp", "mp3encoder.cpp", "oggencoder.cpp",
                "aacwriter.cpp", "wavewriter.cpp", "flacwriter.cpp", "mp3writer.cpp", "oggwriter.cpp", "videowriter.cpp"}
    if required - stems:
        raise ValueError(f"Missing production encode/export sources: {sorted(required - stems)}")
    if "aacencoder.cpp" in stems or any("/fdk-aac/" in name or "/fdk_aac/" in name for name in files):
        raise ValueError("FDK encoder/source is still selected in the generated compilation graph")
    ninja_path = build / "build.ninja"
    ninja = ninja_path.read_text(encoding="utf-8-sig").lower()
    if re.search(r"(?:fdk[_-]aac|fdk-aac[/\\])", ninja):
        raise ValueError("FDK target/source/link remains in the real Ninja graph")
    for library in ("ole32", "mfuuid", "wmcodecdspuuid"):
        if not re.search(r"\b" + library + r"(?:\.lib)?\b", ninja):
            raise ValueError(f"Expected Windows SDK link dependency {library}")
    return {"schema_version": 1, "status": "passed_configured_graph", "passed": True,
            "backend": "Windows system Media Foundation", "fdk_selected": False,
            "other_encode_and_writer_sources_present": True, "required_sources": sorted(required),
            "compile_command_entries": len(commands), "source_commit": state.get("source_commit"),
            "compiled_unity_units": len(unity_hashes),
            "unity_unit_manifest_sha256": hashlib.sha256(
                json.dumps(unity_hashes, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(),
            "application_compiled_by_this_check": False, "runtime_checked_by_this_check": False,
            "file_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in (cache_path, state_path, commands_path, ninja_path)}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        parser.error("Refusing to overwrite an existing graph report")
    try:
        report = check(args.build.resolve())
    except (OSError, ValueError, KeyError, TypeError) as error:
        report = {"schema_version": 1, "status": "failed", "passed": False, "error": str(error)}
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("CADENCE_BACKEND_REPORT_BEGIN")
    print(json.dumps(report, sort_keys=True, ensure_ascii=False))
    print("CADENCE_BACKEND_REPORT_END")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
