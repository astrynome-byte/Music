#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Raw sfizz-ui 1.2.3 component state for the pinned Windows VST3 plugin.

The wire layout is read from SfizzVstState::store/load at source commit
6ef7b89b6e5aa914593c7f3ca19b859915c30337. Strings and booleans follow
Steinberg FStreamer: int32 length INCLUDING NUL, and a signed int16 bool.
This is raw componentState, without a .vstpreset or class UID wrapper.
Generating these bytes does not establish that a host loaded the plugin.
"""
from __future__ import annotations

import argparse
import base64
import copy
import json
import math
from pathlib import Path, PureWindowsPath
import struct


SOURCE_COMMIT = "6ef7b89b6e5aa914593c7f3ca19b859915c30337"
STATE_VERSION = 5
PROCESSOR_UID = "E8FAB71815ED46E38B5983101E12993F"


def str8(text: str) -> bytes:
    if "\0" in text:
        raise ValueError("A state path cannot contain NUL")
    encoded = text.encode("utf-8") + b"\0"
    if len(encoded) > 8192:
        raise ValueError("The controlled state path exceeds 8191 UTF-8 bytes")
    return struct.pack("<i", len(encoded)) + encoded


def build_component_state(sfz_path: str, *, volume_db: float = 0.0,
                          controllers: dict[int, float] | None = None) -> bytes:
    """Build the exact default v5 state with an explicit absolute SFZ path.

    Paths use the plugin's platform-agnostic forward-slash serialization.
    Unicode is encoded as UTF-8; its actual Windows plugin path handling still
    requires a runtime test. A first runtime test should use a controlled ASCII
    RUNNER_TEMP directory and a real authorized SFZ with its sample files.
    """
    if not isinstance(sfz_path, str) or not PureWindowsPath(sfz_path).is_absolute():
        raise ValueError("The Windows SFZ path must be absolute, including drive or UNC share")
    if not sfz_path.lower().endswith(".sfz") or any(ord(c) < 32 for c in sfz_path):
        raise ValueError("An explicit SFZ path without control characters is required")
    if not math.isfinite(volume_db) or not -60.0 <= volume_db <= 6.0:
        raise ValueError("Use a finite volume between -60 and +6 dB")
    cc = {} if controllers is None else dict(controllers)
    if len(cc) > 512 or any(type(k) is not int or not 0 <= k < 512
                            or not math.isfinite(v) or not 0.0 <= v <= 1.0
                            for k, v in cc.items()):
        raise ValueError("Controller indices must be 0..511 and values finite normalized floats")

    result = [struct.pack("<Q", STATE_VERSION), str8(sfz_path.replace("\\", "/")),
              struct.pack("<fiii", volume_db, 64, 0, 8192),
              str8(""),  # Empty scala file is length1 + NUL, NOT a null pointer.
              struct.pack("<iff", 60, 440.0, 0.0),
              struct.pack("<iiii", 2, 1, 10, 3),
              struct.pack("<h", 0),  # FStreamer::writeBool uses int16.
              struct.pack("<iI", -1, len(cc))]
    result.extend(struct.pack("<Hf", key, float(value)) for key, value in sorted(cc.items()))
    return b"".join(result)


def read_component_state(data: bytes) -> dict:
    """Bounded v5 reader for QA receipts; not an SFZ parser or audio engine."""
    if len(data) > 16384:
        raise ValueError("QA component state exceeds its size bound")
    position = 0

    def take(fmt: str):
        nonlocal position
        size = struct.calcsize(fmt)
        if position + size > len(data):
            raise ValueError("Truncated component state")
        values = struct.unpack_from(fmt, data, position)
        position += size
        return values[0] if len(values) == 1 else values

    def string8():
        nonlocal position
        size = take("<i")
        if size < 1 or size > 8192 or position + size > len(data):
            raise ValueError("Invalid component-state string size")
        raw = data[position:position + size]
        position += size
        if not raw.endswith(b"\0") or b"\0" in raw[:-1]:
            raise ValueError("Invalid component-state string terminator")
        return raw[:-1].decode("utf-8")

    version = take("<Q")
    if version != STATE_VERSION:
        raise ValueError("This QA reader deliberately accepts only pinned state version5")
    result = {"version": version, "sfz_file": string8()}
    result["volume_db"], result["voices"], result["oversampling_log2"], result["preload"] = take("<fiii")
    result["scala_file"] = string8()
    result["scala_root"], result["tuning_frequency"], result["stretched_tuning"] = take("<iff")
    (result["sample_quality"], result["oscillator_quality"], result["offline_sample_quality"],
     result["offline_oscillator_quality"]) = take("<iiii")
    boolean = take("<h")
    if boolean not in (0, 1):
        raise ValueError("The QA bool must use canonical int16 encoding")
    result["sustain_cancels_release"] = bool(boolean)
    result["last_keyswitch"], count = take("<iI")
    if count > 512:
        raise ValueError("Too many QA controllers")
    result["controllers"] = {}
    for _ in range(count):
        key, value = take("<Hf")
        if key in result["controllers"] or not math.isfinite(value):
            raise ValueError("Duplicate controller or nonfinite value")
        result["controllers"][key] = value
    if position != len(data):
        raise ValueError("Unexpected component-state trailing bytes")
    return result


def unit_configuration(sfz_path: str, **options) -> dict[str, str]:
    return {"componentState": base64.b64encode(build_component_state(sfz_path, **options)).decode("ascii")}


def audio_input_from_registered_plugin(record: dict, sfz_path: str, **options) -> dict:
    """Use real --register-audio-plugin output, rather than guessing a class ID.

    The register spells its type VstPlugin; native audiosettings.json uses
    vst_plugin. The caller must separately authenticate the plugin binary and
    verify the registered path belongs to its controlled extracted copy.
    """
    meta = record.get("meta")
    if not isinstance(meta, dict) or meta.get("type") != "VstPlugin" or record.get("enabled") is not True:
        raise ValueError("Use an enabled VST plugin entry produced by the real host scan")
    if not isinstance(meta.get("id"), str) or not meta["id"] or not isinstance(record.get("path"), str):
        raise ValueError("Registered plugin ID and path are required")
    if not record["path"].lower().endswith(".vst3"):
        raise ValueError("The registered VST3 bundle or binary path must end with .vst3")
    attributes = meta.get("attributes", {})
    if not isinstance(attributes, dict) or "Instrument" not in attributes.get("categories", "").split("|"):
        raise ValueError("The registered plugin must expose an instrument class")
    converted = copy.deepcopy(meta)
    converted["type"] = "vst_plugin"
    converted.setdefault("attributes", {})["playbackSetupData"] = "generic"
    return {"resourceMeta": converted, "unitConfiguration": unit_configuration(sfz_path, **options)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sfz", required=True, help="Controlled absolute Windows SFZ path")
    parser.add_argument("--volume-db", type=float, default=0.0)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--json", action="store_true", help="Write the MuseScore unitConfiguration JSON object")
    args = parser.parse_args()
    data = build_component_state(args.sfz, volume_db=args.volume_db)
    read_component_state(data)
    output = (json.dumps({"componentState": base64.b64encode(data).decode("ascii")}, indent=2) + "\n").encode("utf-8") if args.json else data
    with args.output.open("xb") as stream:
        stream.write(output)


if __name__ == "__main__":
    main()
