#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Ubuntu data-only readback of two exact, previously produced evidence artifacts.

No binary is loaded/executed and no network request is made by this reader.
Original RTF bytes are base64 encoded without conversion or legal interpretation.
Known report envelopes in stdout are omitted; their independent JSON files remain
eligible diagnostics. Large text is omitted explicitly, never silently truncated.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import stat
import struct
import sys
import types

HEAD = "f46d6bf3777a4153979fd075cc7cc8a7bf4d1818"
PINS = {
    "microsoft": {"id": 13948435202, "run_id": 43224732688,
                  "name": "cadence-full2005-named-redist-origins-43224732688-1", "size_in_bytes": 173115,
                  "digest": "sha256:b06559b0b66270da1013e03022395b835287f977545099c2a4838aa2461d1b76"},
    "asio": {"id": 13948201375, "run_id": 43224732699,
             "name": "cadence-asio-phase2-43224732699-1", "size_in_bytes": 4141794,
             "digest": "sha256:ed9e13ad987644ddca4f091a04eac2a47bceb6176e6b891f29bcd62e16996471"},
}
CURRENT_SDK = "10.0.26100.0"
RTF_PINS = {
    "sdk_license.rtf": (248573, "0f4a26ac9dc50066f8a1bfeaaf3f092d1b9e4791df5487b9f3c31e7c3dc4d7f5"),
    "sdk_third_party_notices.rtf": (22279, "ebb6640a8246b39b70322c5cec9aad7a71e86ea7b86c9c604d3a7f3ff1b30e89"),
}
MAX_CONSOLE = 512 * 1024
MAX_TEXT = 128 * 1024
MAX_ORIGINAL = 256 * 1024
MAX_FILE = 64 * 1024 * 1024
MAX_TREE = 256 * 1024 * 1024
WAV_PATH = 'GUI-retention/basic-control.wav'
WAV_BYTES = 4390286
WAV_SHA256 = '9bb1578b6b09a2ddd01a0a03dddd22a74c0f21b4409cef81ced10cd99ec1d676'
AUDIO_HELPER_SHA256 = 'f701874e7a37b8d3148f0bb99477b60b96865e804ed238372d75c06598027d82'
BEGIN = "CADENCE_DIAGNOSTIC_DATA_READBACK_V1_BEGIN"
END = "CADENCE_DIAGNOSTIC_DATA_READBACK_V1_END"
ENVELOPES = {
    "CADENCE_RESOURCE_RETENTION_REPORT_BEGIN": "CADENCE_RESOURCE_RETENTION_REPORT_END",
    "CADENCE_ASIO_PHASE2_RESULT_BEGIN": "CADENCE_ASIO_PHASE2_RESULT_END",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def decode_json(data: bytes) -> dict:
    result = json.loads(data.decode("utf-8-sig"), object_pairs_hook=unique_object)
    if not isinstance(result, dict):
        raise ValueError("JSON object required")
    return result


def safe_relative(value: str) -> PurePosixPath:
    if (not isinstance(value, str) or not value or len(value) > 512 or "\\" in value or ":" in value
            or any(ord(c) < 32 for c in value)):
        raise ValueError("Unsafe artifact-relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or str(path) != value or any(p in (".", "..") for p in path.parts):
        raise ValueError("Unsafe artifact-relative path")
    return path


def plain(path: Path, kind=None):
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("Absolute plain path required")
    for current in reversed((path, *path.parents)):
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode):
            raise ValueError("Artifact/output symlink refused")
        if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
            raise ValueError("Nonregular artifact object refused")
        if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
            raise ValueError("Hard-linked artifact/output file refused")
    if kind:
        info = path.lstat()
        if kind == "directory" and not stat.S_ISDIR(info.st_mode):
            raise ValueError("Directory required")
        if kind == "file" and not stat.S_ISREG(info.st_mode):
            raise ValueError("File required")


def read_bytes(path: Path, limit: int) -> bytes:
    plain(path, "file")
    before = path.lstat()
    if before.st_size > limit:
        raise ValueError("Selected file exceeds its read bound")
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino, opened.st_size) != (before.st_dev, before.st_ino, before.st_size):
            raise ValueError("Selected file changed before read")
        data = stream.read(limit + 1)
    after = path.lstat()
    if (len(data) > limit or len(data) != before.st_size
            or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
        raise ValueError("Selected file changed during bounded read")
    return data


def inventory(root: Path) -> dict[str, dict]:
    plain(root, "directory")
    found = {}
    pending = [(root, 0)]
    entries = total = 0
    while pending:
        directory, depth = pending.pop()
        if depth > 16:
            raise ValueError("Artifact tree is too deep")
        for path in directory.iterdir():
            entries += 1
            if entries > 4096:
                raise ValueError("Artifact tree exceeds 4096 entries")
            plain(path)
            info = path.lstat()
            if stat.S_ISDIR(info.st_mode):
                pending.append((path, depth + 1))
                continue
            if info.st_size > MAX_FILE:
                raise ValueError("Artifact file exceeds 64 MiB")
            total += info.st_size
            if total > MAX_TREE:
                raise ValueError("Artifact exceeds 256 MiB")
            name = path.relative_to(root).as_posix()
            safe_relative(name)
            found[name] = {"bytes": info.st_size}
    return found


def verify_metadata(value: dict) -> None:
    if set(value) != set(PINS):
        raise ValueError("Both exact artifact metadata records required")
    for area, pin in PINS.items():
        row = value[area]
        if not isinstance(row, dict) or any(row.get(key) != expected for key, expected in pin.items()):
            raise ValueError("Artifact API identity differs: " + area)
        if row.get("head_sha") != HEAD or row.get("expired") is not False or row.get("run_status") != "completed":
            raise ValueError("Artifact run/head/expiry differs: " + area)


def strip_known_envelopes(text: str) -> tuple[str, list[str]]:
    output, removed = [], []
    ending = None
    for line in text.splitlines(keepends=True):
        token = line.strip()
        if ending:
            if token == ending:
                ending = None
            continue
        if token in ENVELOPES:
            removed.append(token)
            ending = ENVELOPES[token]
        else:
            output.append(line)
    if ending:
        removed.append("unterminated-known-envelope")
    return "".join(output), removed


def microsoft_data(root: Path, files: dict) -> dict:
    name = "named-redist-origins.json"
    if name not in files:
        raise ValueError("Microsoft collector JSON is missing")
    data = read_bytes(root / name, MAX_TEXT)
    collector = decode_json(data)
    if (collector.get("run_id") != str(PINS["microsoft"]["run_id"])
            or collector.get("driver_commit") != HEAD or collector.get("status") != "completed"
            or collector.get("errors") != [] or collector.get("license_approval") is not False):
        raise ValueError("Microsoft collector identity/status differs")
    if str(collector.get("developer_environment", {}).get("WindowsSDKVersion", "")).rstrip("\\") != CURRENT_SDK:
        raise ValueError("Exported SDK differs from the selected current SDK")
    originals = collector.get("original_texts")
    if not isinstance(originals, list) or len(originals) > 128:
        raise ValueError("Bounded original-text manifest required")
    selected, other = [], []
    seen = set()
    for row in originals:
        relative = str(safe_relative(row["retained_path"]))
        source = row.get("source_path", "").replace("\\", "/")
        basename = source.rsplit("/", 1)[-1]
        if "/Licenses/" + CURRENT_SDK + "/" in source and basename in RTF_PINS:
            if basename in seen:
                raise ValueError("Duplicate current SDK original")
            seen.add(basename)
            expected_size, expected_sha = RTF_PINS[basename]
            if row.get("bytes") != expected_size or row.get("sha256") != expected_sha or relative not in files:
                raise ValueError("Current SDK original manifest differs")
            raw = read_bytes(root / relative, MAX_ORIGINAL)
            if len(raw) != expected_size or digest(raw) != expected_sha:
                raise ValueError("Current SDK original bytes differ")
            selected.append({**row, "encoding": "base64", "data_base64": base64.b64encode(raw).decode("ascii")})
        else:
            other.append({"source_path": row.get("source_path"), "retained_path": relative,
                          "bytes": row.get("bytes"), "sha256": row.get("sha256"),
                          "printed": False, "reason": "Not one of the two current SDK RTF originals"})
    if seen != set(RTF_PINS):
        raise ValueError("Both pinned current SDK original RTF files are required")
    return {"collector_file": {"path": name, "bytes": len(data), "sha256": digest(data)},
            "collector": collector, "current_sdk_originals": selected, "other_originals_not_printed": other,
            "terms_interpreted_or_redistribution_approved": False}


def file_sha(path: Path) -> str:
    plain(path, "file")
    before = path.lstat()
    if before.st_size > MAX_FILE:
        raise ValueError("Inventory hash exceeds 64 MiB")
    algorithm = hashlib.sha256()
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino, opened.st_size) != (before.st_dev, before.st_ino, before.st_size):
            raise ValueError("Inventory file changed before hashing")
        total = 0
        while chunk := stream.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_FILE:
                raise ValueError("Inventory file grew beyond hash bound")
            algorithm.update(chunk)
    after = path.lstat()
    if (total != before.st_size or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
        raise ValueError("Inventory file changed during hashing")
    return algorithm.hexdigest()


def strict_wav_structure(data: bytes) -> dict:
    """Bound RIFF chunks before using the existing trusted sample analyzer."""
    if (len(data) < 44 or data[:4] != b'RIFF' or data[8:12] != b'WAVE'
            or struct.unpack_from('<I', data, 4)[0] + 8 != len(data)):
        raise ValueError('Complete exact-length RIFF/WAVE required')
    position = 12
    count = 0
    fmt = None
    data_size = None
    while position < len(data):
        count += 1
        if count > 128 or position + 8 > len(data):
            raise ValueError('Incomplete or excessive RIFF chunks')
        kind, size = struct.unpack_from('<4sI', data, position)
        position += 8
        end = position + size
        padded_end = end + (size & 1)
        if end > len(data) or padded_end > len(data):
            raise ValueError('RIFF chunk exceeds original file bounds')
        if kind == b'fmt ':
            if fmt is not None or not 16 <= size <= 4096:
                raise ValueError('Unique bounded WAV format chunk required')
            fmt = struct.unpack_from('<HHIIHH', data, position)
        elif kind == b'data':
            if data_size is not None or not size:
                raise ValueError('Unique nonempty WAV data chunk required')
            data_size = size
        position = padded_end
    if position != len(data) or fmt is None or data_size is None:
        raise ValueError('Complete WAV format and data required')
    code, channels, rate, byte_rate, align, bits = fmt
    if ((code, bits) not in {(1,16), (1,24), (1,32), (3,32), (3,64)}
            or not 1 <= channels <= 64 or not 1 <= rate <= 384000
            or align != channels * (bits // 8) or byte_rate != rate * align
            or data_size % align):
        raise ValueError('Unsupported or inconsistent bounded WAV sample format')
    return {'riff_chunks': count, 'data_bytes': data_size, 'frames': data_size // align,
            'sample_count': data_size // (bits // 8), 'encoding': code, 'bits': bits,
            'channels': channels, 'sample_rate': rate,
            'duration_seconds': data_size / byte_rate}


def measure_exact_wav(path: Path, helper: Path | None = None,
                      expected_bytes: int = WAV_BYTES, expected_sha256: str = WAV_SHA256) -> dict:
    raw = read_bytes(path, MAX_FILE)
    if len(raw) != expected_bytes or digest(raw) != expected_sha256:
        raise ValueError('The exact original GUI WAV bytes are required')
    structure = strict_wav_structure(raw)
    if helper is None:
        # Published reader lives in .cadence-studio/full2005-provenance/
        # diagnostic-readback; reuse the already published corpus source.
        helper = Path(__file__).resolve().parents[2] / 'asio-qa-phase2/corpus_run_exports.py'
    helper_bytes = read_bytes(helper, 32768)
    if digest(helper_bytes) != AUDIO_HELPER_SHA256:
        raise ValueError('Previously qualified WAV analyzer source changed')
    # Execute the exact verified source bytes; do not consult an unverified pyc
    # or reopen a path after its hash check. The module's CLI guard stays false.
    module = types.ModuleType('cadence_pinned_audio_data_helper')
    module.__file__ = str(helper)
    exec(compile(helper_bytes, str(helper), 'exec'), module.__dict__)
    metrics = module.inspect_wav(path)
    if not isinstance(metrics, dict) or type(metrics.get('passed')) is not bool:
        raise ValueError('Analyzer metrics and result types differ')
    for key in ('encoding', 'bits', 'channels', 'sample_rate', 'full_scale_samples', 'nonfinite_samples'):
        if type(metrics.get(key)) is not int or metrics[key] < 0:
            raise ValueError('Invalid numeric sample counter/format: ' + key)
    for key in ('peak', 'rms', 'duration_seconds'):
        if type(metrics.get(key)) not in (int, float) or not math.isfinite(metrics[key]) or metrics[key] < 0:
            raise ValueError('Nonfinite or invalid numeric sample measurement: ' + key)
    if (metrics['full_scale_samples'] > structure['sample_count']
            or metrics['nonfinite_samples'] > structure['sample_count']):
        raise ValueError('Analyzer counters exceed the sample population')
    for key in ('encoding', 'bits', 'channels', 'sample_rate', 'duration_seconds'):
        if metrics.get(key) != structure[key]:
            raise ValueError('Container and sample analyzer disagree: ' + key)
    if file_sha(path) != expected_sha256:
        raise ValueError('Original WAV changed while measuring samples')
    return {**structure, **metrics,
            'finite_samples': structure['sample_count'] - metrics['nonfinite_samples'],
            'analysis_helper_sha256': AUDIO_HELPER_SHA256,
            'original_bytes_verified': True, 'numeric_metrics_only': True,
            'pcm_printed': False, 'human_listening': False,
            'GUI_API_return_or_native_save_qualified': False}


def asio_data(root: Path, files: dict) -> dict:
    fixed = ["phase2-result.json", "registry-scope.json", "profile-scope.json",
             "profile-scope-prepared.snapshot.json", "GUI-retention/retention-report.json",
             "GUI-retention/own-profile-settings-after.ini",
             "GUI-render-native-save.stdout.log", "GUI-render-native-save.stderr.log",
             "registered-harness.stdout.log", "registered-harness.stderr.log"]
    dynamic = sorted(name for name in files if name.startswith("GUI-retention/")
                     and len(PurePosixPath(name).parts) == 2
                     and name.endswith((".cadence-log-delta.txt", ".stdout.txt", ".stderr.txt")))
    if len(dynamic) > 32:
        raise ValueError("Too many GUI diagnostic text files")
    # The failed basic-control GUI log is the first optional console diagnostic.
    critical = "GUI-retention/basic-control-gui.cadence-log-delta.txt"
    names = [critical] + [name for name in dynamic if name != critical] + fixed
    rows = []
    for name in names:
        if name not in files:
            rows.append({"path": name, "present": False})
            continue
        path = root / name
        row = {"path": name, "present": True, "bytes": files[name]["bytes"], "sha256": file_sha(path)}
        if files[name]["bytes"] > MAX_TEXT:
            row.update(printed=False, reason="Full text exceeds 128 KiB; no truncation performed")
        else:
            data = read_bytes(path, MAX_TEXT)
            text, removed = strip_known_envelopes(data.decode("utf-8-sig", errors="replace"))
            row.update(printed=True, text=text, known_envelopes_omitted=removed)
        rows.append(row)
    waves = []
    for name in sorted(files):
        if name.startswith("GUI-retention/") and name.lower().endswith(".wav"):
            waves.append({"path": name, "bytes": files[name]["bytes"], "sha256": file_sha(root / name),
                          "pcm_printed": False})
    if len(waves) > 32:
        raise ValueError("Too many WAV files")
    selected = [row for row in waves if row['path'] == WAV_PATH]
    if len(selected) != 1:
        raise ValueError('The original observed basic-control WAV is missing')
    selected[0]['strict_audio_measurement'] = measure_exact_wav(root / WAV_PATH)
    return {"diagnostic_files": rows, "wav_inventory": waves, "binaries_executed": False,
            "absent_files_are_expected_diagnostics": True, "application_or_driver_qualification": False}


def encoded_report(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode("ascii")


def fit_console(report: dict) -> bytes:
    # Preserve both exact RTF originals and the Microsoft collector. If necessary,
    # omit lower-priority ASIO texts, retaining every file's size/hash/reason.
    for row in reversed(report["asio"]["diagnostic_files"]):
        if len(encoded_report(report)) + len(BEGIN) + len(END) + 4 <= MAX_CONSOLE:
            break
        if "text" in row:
            del row["text"]
            row.update(printed=False, reason="Global 512 KiB console budget; full file remains in producer artifact")
    data = encoded_report(report)
    if len(data) + len(BEGIN) + len(END) + 4 > MAX_CONSOLE:
        raise ValueError("Pinned originals and metadata exceed the console budget")
    return data


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("microsoft", "asio", "metadata", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if (sys.platform != "linux" or os.name != "posix" or os.environ.get("CI") != "true"
            or os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUNNER_OS") != "Linux"
            or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"):
        raise ValueError("Only hosted Ubuntu CI data readback is permitted")
    temporary = Path(os.environ["RUNNER_TEMP"])
    plain(temporary, "directory")
    for path in (args.microsoft, args.asio, args.metadata, args.output):
        plain(path)
        if temporary not in path.parents:
            raise ValueError("All input and output paths must be strictly below RUNNER_TEMP")
    if (args.output.exists() or args.microsoft == args.asio
            or args.microsoft in args.asio.parents or args.asio in args.microsoft.parents
            or any(root == args.output or root in args.output.parents or args.output in root.parents
                   for root in (args.microsoft, args.asio))):
        raise ValueError("Separate input roots and new independent output required")
    plain(args.output.parent, "directory")
    metadata = decode_json(read_bytes(args.metadata, 16384))
    verify_metadata(metadata)
    microsoft_files, asio_files = inventory(args.microsoft), inventory(args.asio)
    report = {"schema_version": 1, "scope": "Read existing artifacts as data on Ubuntu; no Windows execution or legal approval",
              "artifact_metadata_verified": metadata, "microsoft": microsoft_data(args.microsoft, microsoft_files),
              "asio": asio_data(args.asio, asio_files), "console_limit_bytes": MAX_CONSOLE}
    data = fit_console(report)
    args.output.mkdir()
    with (args.output / "diagnostic-readback.json").open("xb") as stream:
        stream.write(data + b"\n")
    print(BEGIN)
    print(data.decode("ascii"))
    print(END)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
