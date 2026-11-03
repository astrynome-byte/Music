#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Run the real Windows probe in a fresh directory, then validate its output."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from verify_adts import verify_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--encoder", type=Path, required=True)
    parser.add_argument("--sample-rate", type=int, choices=(44100, 48000), required=True)
    parser.add_argument("--results-root", type=Path, required=True)
    args = parser.parse_args()
    args.results_root.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix=f"{args.sample_rate}-", dir=args.results_root))
    audio = folder / "sine.aac"
    native_metadata = folder / "native.json"
    case = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "sample_rate": args.sample_rate,
        "seconds_requested": 1.25,
        "pcm_frames_expected": args.sample_rate * 5 // 4,
        "encoder_path": str(args.encoder.resolve()),
        "status": "failed",
        "passed": False,
        "target_backend": "Windows Media Foundation system AAC MFT",
        "native_encoding_completed": False,
        "errors": [],
    }
    try:
        case["encoder_sha256"] = hashlib.sha256(args.encoder.read_bytes()).hexdigest()
        run = subprocess.run(
            [str(args.encoder), "--output", str(audio), "--metadata", str(native_metadata),
             "--rate", str(args.sample_rate), "--seconds", "1.25", "--bitrate", "128000"],
            capture_output=True, text=True, errors="replace", timeout=30)
        (folder / "native.stdout.log").write_text(run.stdout, encoding="utf-8")
        (folder / "native.stderr.log").write_text(run.stderr, encoding="utf-8")
        case["native_return_code"] = run.returncode
        if run.returncode:
            raise ValueError(f"Real system encoder failed with exit code {run.returncode}; see native.stderr.log")
        native = json.loads(native_metadata.read_text(encoding="utf-8"))
        if (native.get("backend") != "Windows system AAC MFT"
                or native.get("native_adts_check") != "PASS" or native.get("sample_rate") != args.sample_rate):
            raise ValueError("Native probe metadata does not confirm the requested ADTS sample rate")
        if native.get("pcm_frames") != case["pcm_frames_expected"]:
            raise ValueError("Native input length differs from requested sine duration")
        case["native"] = native
        case["native_encoding_completed"] = True
        validation = verify_file(audio, args.sample_rate, case["pcm_frames_expected"], True)
        (folder / "validation.json").write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
        if not validation["passed"]:
            raise ValueError("ADTS/decode validation failed: " + "; ".join(validation["errors"]))
        case["status"] = validation["status"]
        case["validation_level"] = validation["validation_level"]
        case["passed"] = True
    except (OSError, ValueError, subprocess.TimeoutExpired, KeyError) as error:
        case["errors"].append(str(error))
    report = folder / "case.json"
    report.write_text(json.dumps(case, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": case["status"], "report": str(report), "errors": case["errors"]}))
    return 0 if case["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
