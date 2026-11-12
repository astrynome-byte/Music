#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Validate corpus structure, then optionally exercise the real MuseScore CLI.

All conversions use fresh copies. No executable means no runtime test.
Only standard-library Python is needed; no shell command interpolation.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

FIXTURES = Path(__file__).resolve().parent / "fixtures"
FORMATS = ("mscz", "mxl", "pdf", "svg", "png", "mid", "wav", "flac", "mp3")


def validate_fixtures() -> list[dict]:
    manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    if manifest["license"] != "CC0-1.0":
        raise ValueError("Unexpected corpus license")
    results = []
    for fixture in manifest["fixtures"]:
        path = FIXTURES / fixture["path"]
        root = ET.parse(path).getroot()
        if root.tag != "score-partwise":
            raise ValueError(f"{path}: score-partwise expected")
        parts = root.findall("part")
        declared = {p.get("id") for p in root.findall("part-list/score-part")}
        if len(parts) != fixture["parts"] or {p.get("id") for p in parts} != declared:
            raise ValueError(f"{path}: wrong or undeclared part IDs")
        notes = 0
        for part in parts:
            measures = part.findall("measure")
            if len(measures) != fixture["measures_per_part"]:
                raise ValueError(f"{path}: wrong measure count")
            divisions = 12
            beats, beat_type = 4, 4
            for measure in measures:
                divisions = int(measure.findtext("attributes/divisions", str(divisions)))
                beats = int(measure.findtext("attributes/time/beats", str(beats)))
                beat_type = int(measure.findtext("attributes/time/beat-type", str(beat_type)))
                length = divisions * beats * 4 // beat_type
                cursor = 0
                furthest = 0
                prior_note = False
                for item in measure:
                    if item.tag == "note":
                        notes += 1
                        duration = int(item.findtext("duration", "0"))
                        chord = item.find("chord") is not None
                        if chord and not prior_note:
                            raise ValueError(f"{path}: chord without preceding note")
                        if not chord:
                            cursor += duration
                        prior_note = True
                    elif item.tag == "backup":
                        cursor -= int(item.findtext("duration", "0"))
                        prior_note = False
                    elif item.tag == "forward":
                        cursor += int(item.findtext("duration", "0"))
                        prior_note = False
                    furthest = max(cursor, furthest)
                    if not 0 <= cursor <= length:
                        raise ValueError(f"{path}: measure {measure.get('number')} has invalid timing")
                if cursor != length or furthest != length:
                    raise ValueError(f"{path}: incomplete measure {measure.get('number')}")
        results.append({**fixture, "bytes": path.stat().st_size,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "notes": notes, "structure": "passed", "runtime": "not_run"})
    return results


def inspect_wav(path: Path) -> dict:
    """Read RIFF PCM16/24/32 or IEEE Float32/64, including padded chunks.

    This detects silence, nonfinite samples, and digital full scale. It cannot
    establish the intended orchestration or musical quality.
    """
    with path.open("rb") as source:
        header = source.read(12)
        if len(header) != 12 or header[:4] != b"RIFF" or header[8:] != b"WAVE":
            raise ValueError("RIFF/WAVE expected")
        fmt, data_offset, data_size = None, None, None
        while True:
            header = source.read(8)
            if len(header) < 8:
                break
            tag, size = struct.unpack("<4sI", header)
            offset = source.tell()
            if tag == b"fmt ":
                payload = source.read(size)
                if len(payload) < 16:
                    raise ValueError("Truncated WAV format chunk")
                fmt = struct.unpack("<HHIIHH", payload[:16])
            elif tag == b"data":
                data_offset, data_size = offset, size
            source.seek(offset + size + (size & 1))
        if fmt is None or data_offset is None:
            raise ValueError("WAV lacks fmt/data chunks")
        code, channels, rate, byte_rate, align, bits = fmt
        if (code, bits) not in {(1, 16), (1, 24), (1, 32), (3, 32), (3, 64)}:
            raise ValueError(f"Unsupported WAV encoding {code}/{bits}; analyze externally")
        width = bits // 8
        if channels < 1 or rate < 1 or align != channels * width or byte_rate != rate * align:
            raise ValueError("Invalid WAV frame format")
        if not data_size or data_size % align or data_offset + data_size > path.stat().st_size:
            raise ValueError("Empty, truncated, or unaligned WAV data")
        source.seek(data_offset)
        count, total_square, peak, full_scale, nonfinite = 0, 0.0, 0.0, 0, 0
        remaining = data_size
        integer_scale = 2 ** (bits - 1)
        while remaining:
            payload = source.read(min(align * 4096, remaining))
            if not payload:
                raise ValueError("Truncated WAV data")
            remaining -= len(payload)
            if code == 3:
                values = (value[0] for value in struct.iter_unpack("<f" if bits == 32 else "<d", payload))
            else:
                values = (int.from_bytes(payload[i:i + width], "little", signed=True) / integer_scale
                          for i in range(0, len(payload), width))
            for value in values:
                count += 1
                if not math.isfinite(value):
                    nonfinite += 1
                    continue
                amplitude = abs(value)
                peak = max(peak, amplitude)
                total_square += value * value
                # Count both PCM rails, not only negative -1.0.
                if amplitude >= (1.0 if code == 3 else (integer_scale - 1) / integer_scale):
                    full_scale += 1
        rms = math.sqrt(total_square / count)
        return {"encoding": code, "bits": bits, "channels": channels, "sample_rate": rate,
                "duration_seconds": data_size / byte_rate, "peak": peak, "rms": rms,
                "full_scale_samples": full_scale, "nonfinite_samples": nonfinite,
                "passed": rms > 1e-6 and full_scale == 0 and nonfinite == 0}


def inspect_output(path: Path, extension: str) -> dict:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"Missing or empty output: {path}")
    with path.open("rb") as source:
        prefix = source.read(16)
    result = {"path": str(path), "bytes": path.stat().st_size}
    if extension in ("mscz", "mxl"):
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None or "META-INF/container.xml" not in archive.namelist():
                raise ValueError("Invalid score ZIP/container")
    elif extension in ("svg", "mscx"):
        root = ET.parse(path).getroot()
        expected = "svg" if extension == "svg" else "museScore"
        if root.tag.rsplit("}", 1)[-1] != expected:
            raise ValueError(f"Unexpected XML root {root.tag}")
    elif extension == "pdf" and not prefix.startswith(b"%PDF-"):
        raise ValueError("Invalid PDF signature")
    elif extension == "png" and not prefix.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Invalid PNG signature")
    elif extension == "mid" and not prefix.startswith(b"MThd"):
        raise ValueError("Invalid MIDI signature")
    elif extension == "flac" and not prefix.startswith(b"fLaC"):
        raise ValueError("Invalid FLAC signature")
    elif extension == "mp3" and not (prefix.startswith(b"ID3") or (len(prefix) > 1 and prefix[0] == 255 and prefix[1] & 224 == 224)):
        raise ValueError("Invalid MP3 signature")
    elif extension == "wav":
        result["audio"] = inspect_wav(path)
        if not result["audio"]["passed"]:
            raise ValueError(f"WAV silence/full scale/nonfinite gate failed: {result['audio']}")
    elif extension == "json":
        parts = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(parts.get("parts"), list) or not parts["parts"] or len(parts["parts"]) != len(parts.get("partsBin", [])):
            raise ValueError("Invalid or empty native-parts JSON")
        result["parts_count"] = len(parts["parts"])
    result["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, help="Real compiled MuseScore/Cadence executable")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--output", type=Path, help="New, nonexistent result directory")
    parser.add_argument("--formats", nargs="+", choices=FORMATS, default=list(FORMATS))
    parser.add_argument("--fixture", action="append", help="Fixture ID (repeatable); excludes large by default")
    parser.add_argument("--include-large", action="store_true")
    parser.add_argument("--timeout", type=int, default=180, help="Per-process timeout in seconds")
    parser.add_argument("--png-dpi", type=int, default=150, help="Explicit PNG resolution for reproducible, bounded raster tests")
    args = parser.parse_args()
    fixtures = validate_fixtures()
    if args.validate_only or args.executable is None:
        print(json.dumps({"scope": "XML structure and measure timing; not schema/import/layout/audio validation",
                          "runtime": "not_run", "fixtures": fixtures}, ensure_ascii=False, indent=2))
        return 0
    executable = args.executable.resolve(strict=True)
    if not executable.is_file():
        parser.error("--executable must be a file")
    selected = [f for f in fixtures if (f["id"] in args.fixture if args.fixture else args.include_large or not f["slow"])]
    if args.fixture and set(args.fixture) - {f["id"] for f in fixtures}:
        parser.error("Unknown fixture ID")
    output = (args.output or Path("cadence-results") / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")).resolve()
    if output == FIXTURES or FIXTURES in output.parents:
        parser.error("Result directory must be outside fixtures")
    output.mkdir(parents=True, exist_ok=False)
    report = {"executable": str(executable), "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
              "started_utc": datetime.now(timezone.utc).isoformat(),
              "fixtures": [{k: v for k, v in fixture.items() if k != "runtime"} for fixture in selected],
              "checks": [], "limits": ["No GUI editing, listening, or visual comparison",
                                          "FLAC/MP3 signatures only; audio gate applies to WAV",
                                          "MusicXML timing checks do not replace XSD or import tests"]}
    version = subprocess.run([str(executable), "--long-version"], stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, timeout=args.timeout, check=False)
    (output / "version.log").write_bytes(version.stdout)
    report["version_output"] = version.stdout.decode("utf-8", errors="replace")
    report["version_exit_code"] = version.returncode

    def run(fixture, stage, command, extension, destination):
        start = time.monotonic()
        item = {"fixture": fixture["id"], "stage": stage, "command": [str(c) for c in command]}
        try:
            process = subprocess.run(item["command"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     timeout=args.timeout, cwd=destination.parent, check=False)
            destination.with_suffix(destination.suffix + ".log").write_bytes(process.stdout)
            item["exit_code"] = process.returncode
            if process.returncode:
                raise ValueError(f"Process failed: {process.returncode}")
            paths = [destination] if destination.exists() else sorted(destination.parent.glob(destination.stem + "-*." + extension))
            if not paths:
                raise ValueError("No output created")
            item["outputs"] = [inspect_output(path, extension) for path in paths]
            item["passed"] = True
        except (OSError, ValueError, subprocess.TimeoutExpired, zipfile.BadZipFile, ET.ParseError) as error:
            item["passed"] = False
            item["error"] = str(error)
            if isinstance(error, subprocess.TimeoutExpired):
                destination.with_suffix(destination.suffix + ".log").write_bytes(error.stdout or b"")
        item["elapsed_seconds"] = time.monotonic() - start
        report["checks"].append(item)
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{fixture['id']}: {stage}: {'PASS' if item['passed'] else 'FAIL'}", flush=True)
        return item["passed"]

    for fixture in selected:
        target = output / fixture["id"]
        target.mkdir()
        source = target / fixture["path"]
        shutil.copy2(FIXTURES / fixture["path"], source)
        native = target / "saved.mscz"
        if not run(fixture, "import-save-native", [executable, "--test-mode", "-o", native, source], "mscz", native):
            continue
        reopened = target / "reopened.mscx"
        run(fixture, "reopen-native", [executable, "--test-mode", "-o", reopened, native], "mscx", reopened)
        for extension in args.formats:
            if extension == "mscz":
                continue
            destination = target / ("export." + extension)
            # Batch conversion supports sound-profile for every target, including WAV.
            job = target / (extension + "-job.json")
            job.write_text(json.dumps([{"in": str(native), "out": str(destination)}]), encoding="utf-8")
            options = ["--image-resolution", str(args.png_dpi)] if extension == "png" else []
            run(fixture, "export-" + extension,
                [executable, "--test-mode", "--sound-profile", "MuseScore Basic", *options, "-j", job], extension, destination)
        if fixture["parts"] > 1 and "pdf" in args.formats:
            # -P only exports excerpts already materialized in the native score.
            # MusicXML imports have potential excerpts; --score-parts creates them.
            destination = target / "native-parts.json"
            if run(fixture, "extract-native-parts", [executable, "--score-parts", "-o", destination, native], "json", destination):
                parts = json.loads(destination.read_text(encoding="utf-8"))
                if len(parts["parts"]) != fixture["parts"]:
                    report["checks"].append({"fixture": fixture["id"], "stage": "parts-count", "passed": False,
                                              "error": f"Expected {fixture['parts']} parts; got {len(parts['parts'])}"})
                else:
                    for index, data in enumerate(parts["partsBin"], 1):
                        native_part = target / f"part-{index:02d}.mscz"
                        native_part.write_bytes(base64.b64decode(data, validate=True))
                        inspect_output(native_part, "mscz")
                        destination = target / f"part-{index:02d}.pdf"
                        run(fixture, f"part-{index:02d}-reopen-pdf", [executable, "-o", destination, native_part], "pdf", destination)
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Report: {output / 'report.json'}")
    return 0 if report["checks"] and all(c["passed"] for c in report["checks"]) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, ET.ParseError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
