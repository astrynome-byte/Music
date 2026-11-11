#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Validate an AAC-LC ADTS probe, optionally decoding its known stereo tones.

This is an independent checker, not an AAC encoder or a listening test. Header
checks alone cannot establish that the compressed payload contains valid audio.
"""
from __future__ import annotations

import argparse
from array import array
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


SAMPLE_RATES = (96000, 88200, 64000, 48000, 44100, 32000, 24000,
                22050, 16000, 12000, 11025, 8000, 7350)
SAMPLES_PER_FRAME = 1024
MAX_EXTRA_AAC_FRAMES = 4


def parse_adts(raw: bytes, sample_rate: int, pcm_frames: int) -> dict:
    """Inspect every ADTS frame; payload validity needs the optional decoder."""
    if sample_rate not in (44100, 48000):
        raise ValueError("Expected sample rate must be 44100 or 48000 Hz")
    if pcm_frames <= 0:
        raise ValueError("Expected real PCM frame count must be positive")
    cursor = 0
    count = 0
    crc_frames = 0
    mpeg_ids = set()
    while cursor < len(raw):
        remaining = len(raw) - cursor
        if remaining < 7:
            raise ValueError(f"Truncated ADTS header or trailing bytes at offset {cursor}")
        header = raw[cursor:cursor + 7]
        if header[0] != 0xFF or header[1] & 0xF0 != 0xF0:
            raise ValueError(f"Missing ADTS sync at offset {cursor}")
        if (header[1] >> 1) & 3:
            raise ValueError(f"ADTS layer must be zero at offset {cursor}")
        if (header[2] >> 6) != 1:
            raise ValueError(f"Expected AAC-LC ADTS profile at offset {cursor}")
        frequency_index = (header[2] >> 2) & 15
        if frequency_index >= len(SAMPLE_RATES):
            raise ValueError(f"Reserved/unsupported ADTS sample-rate index at offset {cursor}")
        actual_rate = SAMPLE_RATES[frequency_index]
        if actual_rate != sample_rate:
            raise ValueError(f"ADTS sample rate {actual_rate} != expected {sample_rate}")
        channels = ((header[2] & 1) << 2) | (header[3] >> 6)
        if channels != 2:
            raise ValueError(f"Expected stereo channel configuration, got {channels}")
        if header[6] & 3:
            raise ValueError(f"Multiple raw data blocks are unsupported at offset {cursor}")
        header_size = 7 if header[1] & 1 else 9
        frame_size = ((header[3] & 3) << 11) | (header[4] << 3) | (header[5] >> 5)
        if frame_size <= header_size:
            raise ValueError(f"ADTS frame has no payload or invalid length at offset {cursor}")
        if frame_size > remaining:
            raise ValueError(f"Truncated ADTS frame at offset {cursor}: needs {frame_size}, has {remaining}")
        crc_frames += header_size == 9
        mpeg_ids.add((header[1] >> 3) & 1)
        count += 1
        cursor += frame_size
    minimum = (pcm_frames + SAMPLES_PER_FRAME - 1) // SAMPLES_PER_FRAME
    if count < minimum:
        raise ValueError(f"Too few ADTS frames: {count}, at least {minimum} required for {pcm_frames} PCM frames")
    if count > minimum + MAX_EXTRA_AAC_FRAMES:
        raise ValueError(f"Too many ADTS frames: {count}, at most {minimum + MAX_EXTRA_AAC_FRAMES} allowed")
    decoded_pcm_frames = count * SAMPLES_PER_FRAME
    return {
        "passed": True,
        "profile": "AAC-LC",
        "sample_rate": sample_rate,
        "channels": 2,
        "mpeg_ids": sorted(mpeg_ids),
        "frame_count": count,
        "samples_per_aac_frame": SAMPLES_PER_FRAME,
        "encoded_pcm_frames": decoded_pcm_frames,
        "adts_duration_seconds": decoded_pcm_frames / sample_rate,
        "expected_real_pcm_frames": pcm_frames,
        "expected_real_duration_seconds": pcm_frames / sample_rate,
        "minimum_frame_count": minimum,
        "maximum_frame_count": minimum + MAX_EXTRA_AAC_FRAMES,
        "extra_frames_above_rounded_input": count - minimum,
        "crc_present_frames": crc_frames,
        "crc_verified": False,
        "size_bytes": len(raw),
        "average_bitrate_bits_per_second": len(raw) * 8 * sample_rate / decoded_pcm_frames,
        "payload_validation": "requires_decode",
    }


def tone_energy_fraction(values: list[float], frequency: float, sample_rate: int) -> float:
    """Goertzel projection at the exact expected frequency, normalized to energy."""
    total_energy = sum(value * value for value in values)
    if not values or total_energy == 0:
        return 0.0
    coefficient = 2 * math.cos(2 * math.pi * frequency / sample_rate)
    previous = 0.0
    previous_previous = 0.0
    for value in values:
        current = value + coefficient * previous - previous_previous
        previous_previous, previous = previous, current
    power = previous * previous + previous_previous * previous_previous - coefficient * previous * previous_previous
    return max(0.0, min(1.0, 2 * power / (len(values) * total_energy)))


def inspect_decoded_pcm(raw: bytes, sample_rate: int, pcm_frames: int, encoded_pcm_frames: int) -> dict:
    if not raw or len(raw) % 8:
        raise ValueError("Decoded f32le stereo PCM is empty or has a partial frame")
    samples = array("f")
    samples.frombytes(raw)
    if sys.byteorder != "little":
        samples.byteswap()
    if not all(math.isfinite(value) for value in samples):
        raise ValueError("Decoded PCM contains NaN or infinite samples")
    decoded_frames = len(samples) // 2
    if decoded_frames < pcm_frames or decoded_frames - pcm_frames > MAX_EXTRA_AAC_FRAMES * SAMPLES_PER_FRAME:
        raise ValueError(f"Decoded duration differs from real PCM input by more than the allowed padding: {decoded_frames} vs {pcm_frames} frames")
    if abs(decoded_frames - encoded_pcm_frames) > SAMPLES_PER_FRAME:
        raise ValueError("Decoded duration differs from the counted ADTS duration by more than one AAC frame")
    # Remove potential priming/tail frames from the known-tone analysis. The
    # complete signal is still checked for nonfinite values and saturation.
    trim = min(2 * SAMPLES_PER_FRAME, decoded_frames // 8)
    channel_reports = []
    for channel, frequency in enumerate((440.0, 660.0)):
        full = list(samples[channel::2])
        middle = full[trim:len(full) - trim] if trim else full
        peak = max(abs(value) for value in full)
        rms = math.sqrt(sum(value * value for value in middle) / len(middle))
        energy_fraction = tone_energy_fraction(middle, frequency, sample_rate)
        other_fraction = tone_energy_fraction(middle, (660.0, 440.0)[channel], sample_rate)
        if peak >= 0.9:
            raise ValueError(f"Decoded channel {channel} exceeds the probe headroom (peak {peak:.6f})")
        if not 0.05 <= rms <= 0.30:
            raise ValueError(f"Decoded channel {channel} is silent or has an unexpected level (RMS {rms:.6f})")
        if energy_fraction < 0.80 or other_fraction > 0.10:
            raise ValueError(f"Decoded channel {channel} does not contain its expected {frequency:g} Hz tone")
        channel_reports.append({
            "channel": channel,
            "expected_frequency_hz": frequency,
            "peak": peak,
            "rms_trimmed": rms,
            "expected_tone_energy_fraction": energy_fraction,
            "other_channel_tone_energy_fraction": other_fraction,
        })
    return {
        "status": "passed",
        "pcm_format": "f32le_stereo",
        "decoded_pcm_frames": decoded_frames,
        "decoded_duration_seconds": decoded_frames / sample_rate,
        "duration_difference_from_real_input_seconds": (decoded_frames - pcm_frames) / sample_rate,
        "channels": channel_reports,
        "listening_test": "not_performed",
    }


def run_checked(command: list[str]) -> subprocess.CompletedProcess:
    run = subprocess.run(command, capture_output=True, text=True, timeout=60)
    if run.returncode:
        raise ValueError(f"{Path(command[0]).name} failed with exit code {run.returncode}: {run.stderr.strip()[:2000]}")
    return run


def verify_file(path: Path, sample_rate: int, pcm_frames: int, decode_if_available: bool = False) -> dict:
    report = {
        "schema_version": 1,
        "input": str(path.resolve()),
        "expected_sample_rate": sample_rate,
        "expected_real_pcm_frames": pcm_frames,
        "passed": False,
        "status": "failed",
        "validation_level": "none",
        "structure": {"passed": False},
        "decode": {"status": "not_requested"},
        "ffprobe": {"status": "not_requested"},
        "errors": [],
    }
    try:
        raw = path.read_bytes()
        report["sha256"] = hashlib.sha256(raw).hexdigest()
        structure = parse_adts(raw, sample_rate, pcm_frames)
        report["structure"] = structure
        report["validation_level"] = "structure_only"
        if decode_if_available:
            ffprobe = shutil.which("ffprobe")
            if ffprobe:
                report["ffprobe"] = {"status": "failed", "executable": ffprobe}
                probe = run_checked([ffprobe, "-v", "error", "-select_streams", "a:0", "-show_entries",
                                     "stream=codec_name,sample_rate,channels,duration", "-of", "json", str(path)])
                info = json.loads(probe.stdout)
                streams = info.get("streams", [])
                if len(streams) != 1:
                    raise ValueError("ffprobe did not find exactly one selected audio stream")
                stream = streams[0]
                if stream.get("codec_name") != "aac" or int(stream.get("sample_rate", 0)) != sample_rate or stream.get("channels") != 2:
                    raise ValueError("ffprobe codec/rate/channels disagree with the expected AAC probe")
                report["ffprobe"] = {"status": "passed", "executable": ffprobe, "stream": stream,
                                     "duration_note": "ADTS estimated duration is not the decoded PCM duration gate"}
            else:
                report["ffprobe"] = {"status": "skipped", "reason": "ffprobe is not available on PATH"}
            ffmpeg = shutil.which("ffmpeg")
            if ffmpeg:
                report["decode"] = {"status": "failed", "executable": ffmpeg}
                with tempfile.TemporaryDirectory(prefix="cadence-mf-aac-decode-") as directory:
                    pcm = Path(directory) / "decoded.f32le"
                    run_checked([ffmpeg, "-nostdin", "-v", "error", "-i", str(path), "-map", "0:a:0",
                                 "-vn", "-c:a", "pcm_f32le", "-f", "f32le", str(pcm)])
                    report["decode"] = inspect_decoded_pcm(pcm.read_bytes(), sample_rate, pcm_frames,
                                                           structure["encoded_pcm_frames"])
                    report["decode"]["executable"] = ffmpeg
                report["validation_level"] = "decoded_signal"
                report["structure"]["payload_validation"] = "decoded_signal_checked"
            else:
                report["decode"] = {"status": "skipped", "reason": "ffmpeg is not available on PATH; compressed payload was not decoded"}
        report["passed"] = True
        report["status"] = "passed_with_decode" if report["validation_level"] == "decoded_signal" else "passed_structure_only"
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        report["errors"].append(str(error))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--sample-rate", type=int, choices=(44100, 48000), required=True)
    parser.add_argument("--pcm-frames", type=int, required=True, help="Real input frames, excluding padding")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--decode-if-available", action="store_true")
    args = parser.parse_args()
    if args.input.resolve() == args.report.resolve():
        parser.error("The report path must differ from the audio input path")
    report = verify_file(args.input, args.sample_rate, args.pcm_frames, args.decode_if_available)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "validation_level": report["validation_level"],
                      "report": str(args.report), "errors": report["errors"]}, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
