#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Export five real application AAC scores and compare decoded music with WAV.

The candidate report must come from the same executable and contain all 57
successful run_exports.py checks. All inputs are copied from that report's
fresh result tree. FFmpeg is a decoder only and must already be on PATH.
This checks files and signal levels, not listening quality, GUI, or MP4.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time


# Loading the candidate's inspector must not write caches into its source tree.
sys.dont_write_bytecode = True

FIXTURE_IDS = {"piano", "voice", "guitar", "percussion", "ensemble"}
SAMPLES_PER_AAC_FRAME = 1024
MAX_PADDING_FRAMES = 4096


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: dict | list) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def run_logged(command: list[str], cwd: Path, prefix: Path, timeout: int) -> dict:
    """Keep actual native statuses and separate streams, including on timeout."""
    result = {"command": command, "exit_code": None, "timed_out": False,
              "stdout_log": str(prefix.with_suffix(".stdout.log")),
              "stderr_log": str(prefix.with_suffix(".stderr.log"))}
    started = time.monotonic()
    stdout = stderr = b""
    try:
        native = subprocess.run(command, cwd=cwd, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=timeout, check=False)
        result["exit_code"] = native.returncode
        stdout, stderr = native.stdout, native.stderr
    except subprocess.TimeoutExpired as error:
        result["timed_out"] = True
        stdout, stderr = error.stdout or b"", error.stderr or b""
    except OSError as error:
        result["launch_error"] = str(error)
    finally:
        prefix.with_suffix(".stdout.log").write_bytes(stdout)
        prefix.with_suffix(".stderr.log").write_bytes(stderr)
        result["elapsed_seconds"] = time.monotonic() - started
    return result


def require_native_success(result: dict, operation: str) -> None:
    if result["timed_out"] or result["exit_code"] != 0:
        raise ValueError(f"{operation} failed or timed out; inspect {result['stderr_log']}")


def reported_file(entry: dict, results_root: Path, suffix: str) -> Path:
    path = Path(entry["path"]).resolve(strict=True)
    if not path.is_file() or path.suffix.lower() != suffix or not path.is_relative_to(results_root):
        raise ValueError(f"Reported {suffix} must be a file inside the candidate results tree: {path}")
    if not path.stat().st_size or entry.get("sha256") != sha256(path):
        raise ValueError(f"Reported file is empty, changed, or lacks its matching SHA-256: {path}")
    if entry.get("bytes") != path.stat().st_size:
        raise ValueError(f"Reported file size differs: {path}")
    return path


def select_inputs(candidate: dict, results_root: Path) -> list[dict]:
    fixtures = candidate.get("fixtures", [])
    if (len(fixtures) != 5 or {item.get("id") for item in fixtures} != FIXTURE_IDS
            or any(item.get("slow") is not False for item in fixtures)):
        raise ValueError("Candidate must contain exactly the five non-large musical fixtures")
    checks = candidate.get("checks", [])
    if len(checks) != 57 or any(item.get("passed") is not True for item in checks):
        raise ValueError("All 57 candidate application regression checks must have passed")
    selected = []
    for fixture_id in sorted(FIXTURE_IDS):
        paths = {}
        for stage, suffix in (("export-wav", ".wav"), ("import-save-native", ".mscz")):
            matches = [item for item in checks if item.get("fixture") == fixture_id and item.get("stage") == stage]
            if len(matches) != 1 or len(matches[0].get("outputs", [])) != 1:
                raise ValueError(f"{fixture_id}: expected one successful {stage} output")
            paths[stage] = reported_file(matches[0]["outputs"][0], results_root, suffix)
        selected.append({"fixture": fixture_id, "wav": paths["export-wav"], "native": paths["import-save-native"]})
    return selected


def inspect_adts(path: Path, rate: int, reference_frames: int) -> dict:
    """Independent structural check; compressed payload validity needs decoding."""
    data = path.read_bytes()
    cursor = frames = 0
    rates = (96000, 88200, 64000, 48000, 44100, 32000, 24000,
             22050, 16000, 12000, 11025, 8000, 7350)
    while cursor < len(data):
        if len(data) - cursor < 7:
            raise ValueError(f"Truncated ADTS header at byte {cursor}")
        h = data[cursor:cursor + 7]
        frequency_index = (h[2] >> 2) & 15
        channel_config = ((h[2] & 1) << 2) | (h[3] >> 6)
        if (h[0] != 0xFF or h[1] & 0xF6 != 0xF0 or h[2] >> 6 != 1
                or frequency_index >= len(rates) or rates[frequency_index] != rate
                or rate not in (44100, 48000) or channel_config != 2 or h[6] & 3):
            raise ValueError(f"Expected AAC-LC, stereo, {rate} Hz, one raw block per ADTS frame at byte {cursor}")
        header_size = 7 if h[1] & 1 else 9
        length = ((h[3] & 3) << 11) | (h[4] << 3) | (h[5] >> 5)
        if length <= header_size or length > len(data) - cursor:
            raise ValueError(f"Invalid or truncated ADTS frame length at byte {cursor}")
        frames += 1
        cursor += length
    expected = (reference_frames + SAMPLES_PER_AAC_FRAME - 1) // SAMPLES_PER_AAC_FRAME
    if not expected <= frames <= expected + 4:
        raise ValueError(f"ADTS frame count {frames} outside [{expected}, {expected + 4}]")
    return {"profile": "AAC-LC", "channels": 2, "sample_rate": rate,
            "frame_count": frames, "minimum_frames": expected, "maximum_frames": expected + 4,
            "duration_seconds": frames * SAMPLES_PER_AAC_FRAME / rate,
            "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "crc_verified": False}


def inspect_pcm(path: Path, rate: int, reference_frames: int) -> dict:
    """Measure generic music, without assuming a test tone or resampling."""
    size = path.stat().st_size
    if not size or size % 8:
        raise ValueError("Decoded f32le stereo is empty or has an incomplete frame")
    frames = size // 8
    if not reference_frames <= frames <= reference_frames + MAX_PADDING_FRAMES:
        raise ValueError(f"Decoded frames {frames} outside [{reference_frames}, {reference_frames + MAX_PADDING_FRAMES}]")
    peak = square_sum = 0.0
    count = 0
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 8192), b""):
            for (value,) in struct.iter_unpack("<f", block):
                if not math.isfinite(value):
                    raise ValueError("Decoded AAC contains NaN/Inf")
                peak = max(peak, abs(value))
                square_sum += value * value
                count += 1
    rms = math.sqrt(square_sum / count)
    if not rms > 1e-6 or not peak < 1.0:
        raise ValueError(f"Decoded AAC silence/full-scale gate failed: RMS={rms}, peak={peak}")
    return {"format": "f32le_stereo", "sample_rate": rate, "channels": 2, "frames": frames,
            "duration_seconds": frames / rate, "rms": rms, "peak": peak,
            "nonfinite_samples": 0, "bytes": size, "sha256": sha256(path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--candidate-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New nonexistent directory outside source/results")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=180, help="Timeout per native process, seconds")
    args = parser.parse_args()
    if not 1 <= args.timeout <= 3600:
        parser.error("--timeout must be between 1 and 3600 seconds")
    output = args.output.resolve()
    source_root = args.source_root.resolve()
    candidate_path = args.candidate_report.resolve()
    if output == source_root or output.is_relative_to(source_root) or output.is_relative_to(candidate_path.parent):
        parser.error("Output must be separate from source code and the original candidate results tree")
    output.mkdir(parents=True, exist_ok=False)
    report_path = output / "report.json"
    report = {"schema_version": 1, "started_utc": utc_now(), "platform": sys.platform,
              "status": "failed", "passed": False, "application_exports_exercised": False,
              "executable": str(args.executable), "candidate_report": str(candidate_path),
              "source_root": str(source_root), "cases": [], "errors": [],
              "gui_validated": False, "listening_validated": False, "mp4_validated": False,
              "missing_video_encoder_qualification": "Independent Test-VideoUnavailable.py step; outside this music-only report",
              "backend_verified_by_this_script": False, "unicode_and_spaces_paths_exercised": False,
              "scope": "Application AAC batch exports; independent ADTS and decoded generic music vs prior WAV",
              "limits": ["No human listening or musical/articulation fidelity validation",
                         "RMS and peak aggregate both channels; stereo balance is not validated",
                         "No GUI, MP4, installation, missing-component or cancellation test",
                         "Backend selection must also be established by the build configuration",
                         "RMS and duration gates do not establish waveform identity or gapless playback"]}
    print(json.dumps({"event": "begin", "report": str(report_path)}, ensure_ascii=False), flush=True)
    started = time.monotonic()
    try:
        if os.name != "nt":
            raise ValueError("This application qualification requires Windows; no Windows execution is inferred on this host")
        executable = args.executable.resolve(strict=True)
        if not executable.is_file():
            raise ValueError("Executable must be a real file")
        report["executable"] = str(executable)
        report["executable_sha256"] = sha256(executable)
        candidate = json.loads(candidate_path.read_text(encoding="utf-8-sig"))
        report["candidate_report_sha256"] = sha256(candidate_path)
        if (candidate.get("executable_sha256") != report["executable_sha256"]
                or candidate.get("version_exit_code") != 0):
            raise ValueError("Candidate report does not identify this executable and a successful version query")
        inspector_path = source_root / "test/cadence/run_exports.py"
        spec = importlib.util.spec_from_file_location("cadence_aac_wav_inspector", inspector_path)
        if spec is None or spec.loader is None:
            raise ValueError("Cannot load the candidate's WAV inspector")
        inspector = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(inspector)
        report["wav_inspector_sha256"] = sha256(inspector_path)
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise ValueError("FFmpeg must already be available on PATH; this script downloads nothing")
        report["decoder"] = {"path": ffmpeg, "sha256": sha256(Path(ffmpeg))}
        version = run_logged([ffmpeg, "-version"], output, output / "ffmpeg-version", args.timeout)
        report["decoder_version_query"] = version
        require_native_success(version, "FFmpeg version query")
        jobs = []
        for selected in select_inputs(candidate, candidate_path.parent):
            folder = output / selected["fixture"]
            folder.mkdir()
            common_stem = "Été " + selected["fixture"] + " – test"
            native = folder / (common_stem + ".mscz")
            wav = folder / (common_stem + ".wav")
            shutil.copy2(selected["native"], native)
            shutil.copy2(selected["wav"], wav)
            audio = inspector.inspect_wav(wav)
            if audio.get("passed") is not True or audio.get("channels") != 2 or audio.get("sample_rate") not in (44100, 48000):
                raise ValueError(f"{selected['fixture']}: reference WAV must pass the stereo 44100/48000 Hz signal gate")
            exact_frames = audio["duration_seconds"] * audio["sample_rate"]
            frames = round(exact_frames)
            if not frames or abs(exact_frames - frames) > 1e-5:
                raise ValueError("Reference WAV frame count is invalid")
            case = {"fixture": selected["fixture"], "passed": False,
                    "input_copy": str(native), "input_sha256": sha256(native),
                    "reference_wav": {"path": str(wav), "sha256": sha256(wav), "frames": frames, **audio},
                    "aac_path": str(folder / (common_stem + ".aac")), "errors": []}
            report["cases"].append(case)
            jobs.append({"in": str(native), "out": case["aac_path"]})
        job_path = output / "aac-jobs.json"
        write_json(job_path, jobs)
        command = [str(executable), "--test-mode", "--sound-profile", "MuseScore Basic", "-b", "128", "-j", str(job_path)]
        batch = run_logged(command, output, output / "application-aac-batch", args.timeout)
        report["application_batch"] = batch
        report["application_exports_exercised"] = batch["exit_code"] is not None
        require_native_success(batch, "Application AAC batch export")
        for case in report["cases"]:
            try:
                aac = Path(case["aac_path"])
                rate = case["reference_wav"]["sample_rate"]
                frames = case["reference_wav"]["frames"]
                case["adts"] = inspect_adts(aac, rate, frames)
                decoded = aac.with_suffix(".decoded.f32le")
                decode_command = [ffmpeg, "-nostdin", "-v", "error", "-xerror", "-i", str(aac),
                                  "-map", "0:a:0", "-vn", "-sn", "-dn", "-c:a", "pcm_f32le", "-f", "f32le", str(decoded)]
                decode = run_logged(decode_command, output, aac.parent / "ffmpeg-decode", args.timeout)
                case["decode"] = decode
                require_native_success(decode, "AAC decode")
                case["decoded_pcm"] = inspect_pcm(decoded, rate, frames)
                ratio = case["decoded_pcm"]["rms"] / case["reference_wav"]["rms"]
                case["rms_ratio_to_wav"] = ratio
                case["decoded_duration_difference_frames"] = case["decoded_pcm"]["frames"] - frames
                if not 0.8 <= ratio <= 1.2:
                    raise ValueError(f"AAC/WAV RMS ratio {ratio:.6g} outside [0.8, 1.2]")
                case["passed"] = True
            except (OSError, ValueError, KeyError) as error:
                case["errors"].append(str(error))
            write_json(report_path, report)
        music_passed = len(report["cases"]) == 5 and all(case["passed"] for case in report["cases"])
        report["passed"] = music_passed
        report["status"] = "passed_five_music_aac_exports_and_decodes" if report["passed"] else "failed"
        report["unicode_and_spaces_paths_exercised"] = report["passed"]
    except (OSError, ValueError, KeyError, TypeError, ImportError) as error:
        report["errors"].append(str(error))
    finally:
        report["finished_utc"] = utc_now()
        report["elapsed_seconds"] = time.monotonic() - started
        write_json(report_path, report)
        print(json.dumps({"event": "end", "status": report["status"], "passed": report["passed"],
                          "passed_cases": sum(case["passed"] for case in report["cases"]),
                          "failed_fixtures": [case["fixture"] for case in report["cases"] if not case["passed"]],
                          "report": str(report_path), "errors": report["errors"]}, ensure_ascii=False), flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
