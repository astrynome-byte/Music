#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Data-load/render generated banks using an EXISTING Linux FluidSynth library.

No audio driver, app, installer, Windows qualification or listening is involved.
No library is installed. This complements the future real Cadence Windows job.
"""
import argparse
import ctypes
import ctypes.util
import hashlib
import json
import math
import os
from pathlib import Path


def check(banks):
    if os.name == "nt": raise ValueError("This check intentionally describes Linux only")
    library = ctypes.util.find_library("fluidsynth")
    if not library: raise RuntimeError("An already installed FluidSynth library is required")
    lib = ctypes.CDLL(library)
    pointer, integer, string = ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p
    def api(name, result, args):
        function = getattr(lib, name);function.restype = result;function.argtypes = args;return function
    api("fluid_version_str", string, [])
    api("new_fluid_settings", pointer, []);api("delete_fluid_settings", None, [pointer])
    api("fluid_settings_setnum", integer, [pointer, string, ctypes.c_double])
    api("fluid_settings_setint", integer, [pointer, string, integer])
    api("new_fluid_synth", pointer, [pointer]);api("delete_fluid_synth", None, [pointer])
    api("fluid_synth_sfload", integer, [pointer, string, integer])
    api("fluid_synth_program_select", integer, [pointer, integer, integer, integer, integer])
    api("fluid_synth_noteon", integer, [pointer, integer, integer, integer])
    api("fluid_synth_noteoff", integer, [pointer, integer, integer])
    api("fluid_synth_write_float", integer, [pointer, integer, pointer, integer, integer, pointer, integer, integer])
    manifest = json.loads((banks / "banks-manifest.json").read_text())
    results = []
    for bank in manifest["banks"]:
        path = banks / bank["file"]
        with path.open("rb") as stream: checksum = hashlib.file_digest(stream, "sha256").hexdigest()
        if checksum != bank["sha256"]: raise ValueError("Bank changed before real FluidSynth load")
        settings = lib.new_fluid_settings()
        lib.fluid_settings_setnum(settings, b"synth.sample-rate", 44100)
        lib.fluid_settings_setnum(settings, b"synth.gain", 0.2)
        lib.fluid_settings_setint(settings, b"synth.reverb.active", 0)
        lib.fluid_settings_setint(settings, b"synth.chorus.active", 0)
        synth = lib.new_fluid_synth(settings)
        try:
            sfont = lib.fluid_synth_sfload(synth, str(path).encode(), 0)
            if sfont <= 0: raise RuntimeError("Real FluidSynth rejected " + path.name)
            if lib.fluid_synth_program_select(synth, 0, sfont, 0, bank["program"]) != 0:
                raise RuntimeError("The bank lacks its actual GM preset")
            if lib.fluid_synth_noteon(synth, 0, 72, 100) != 0: raise RuntimeError("Native note-on failed")
            frames = 44100 * 2
            left = (ctypes.c_float * frames)();right = (ctypes.c_float * frames)()
            if lib.fluid_synth_write_float(synth, frames, left, 0, 1, right, 0, 1) != 0:
                raise RuntimeError("Native in-memory rendering failed")
            values = [*left, *right];peak = max(map(abs, values))
            rms = math.sqrt(sum(value * value for value in values) / len(values))
            if not (rms > 1e-6 and peak < 1 and all(math.isfinite(value) for value in values)
                    and any(left) and any(right)):
                raise RuntimeError("Actual bank render is silent/nonfinite/clipped or lacks a stereo side")
            results.append({"file": path.name, "sha256": checksum, "sfont_id": sfont,
                            "bank": 0, "program": bank["program"], "note": 72, "velocity": 100,
                            "frames": frames, "peak": peak, "rms": rms,
                            "left_nonzero": any(left), "right_nonzero": any(right)})
            if bank["gain_delta_db"] == 0:
                # A new voice held beyond every selected recording proves the
                # finite-sample limitation without inventing a sustain loop.
                if lib.fluid_synth_noteoff(synth, 0, 72) != 0: raise RuntimeError("Native note-off failed")
                discard = (ctypes.c_float * 88200)()
                lib.fluid_synth_write_float(synth, 88200, discard, 0, 1, discard, 0, 1)
                lib.fluid_synth_noteon(synth, 0, 72, 100)
                frames_long = 20 * 44100
                held_left = (ctypes.c_float * frames_long)();held_right = (ctypes.c_float * frames_long)()
                if lib.fluid_synth_write_float(synth, frames_long, held_left, 0, 1, held_right, 0, 1) != 0:
                    raise RuntimeError("Long-note native render failed")
                held_tail = [*held_left[-22050:], *held_right[-22050:]]
                held_rms = math.sqrt(sum(value * value for value in held_tail) / len(held_tail))
                if held_rms > 1e-9: raise RuntimeError("Finite source unexpectedly sustained beyond its recording")
                lib.fluid_synth_noteoff(synth, 0, 72)
                lib.fluid_synth_noteon(synth, 0, 72, 100)
                pre_left = (ctypes.c_float * 44100)();pre_right = (ctypes.c_float * 44100)()
                lib.fluid_synth_write_float(synth, 44100, pre_left, 0, 1, pre_right, 0, 1)
                lib.fluid_synth_noteoff(synth, 0, 72)
                post_left = (ctypes.c_float * 88200)();post_right = (ctypes.c_float * 88200)()
                lib.fluid_synth_write_float(synth, 88200, post_left, 0, 1, post_right, 0, 1)
                release_head_peak = max(map(abs, [*post_left[:4410], *post_right[:4410]]))
                release_tail_peak = max(map(abs, [*post_left[-11025:], *post_right[-11025:]]))
                if release_head_peak <= 1e-6 or release_tail_peak > 1e-9:
                    raise RuntimeError("Recorded release did not decay to silence within two seconds")
                results[-1]["long_note"] = {"held_seconds": 20, "last_half_second_rms": held_rms,
                                             "finite_sample_end_observed": True}
                results[-1]["release"] = {"note_off_after_seconds": 1, "rendered_post_noteoff_seconds": 2,
                                           "first_100ms_peak": release_head_peak,
                                           "last_250ms_peak": release_tail_peak, "decayed_to_silence": True}
        finally:
            lib.delete_fluid_synth(synth);lib.delete_fluid_settings(settings)
    by_name = {row["file"]: row for row in results}
    ratio = by_name["Cadence-VSCO-Flute-minus18.sf2"]["rms"] / by_name["Cadence-VSCO-Flute.sf2"]["rms"]
    delta = 20 * math.log10(ratio)
    if abs(delta + 18) > 0.02: raise RuntimeError("Real derivative gain response differs from -18 dB")
    return {"schema_version": 1, "scope": __doc__, "fluid_library": library,
            "fluid_version": lib.fluid_version_str().decode(), "results": results,
            "attenuated_rms_ratio": ratio, "attenuated_db": delta, "passed": True,
            "audio_driver_created": False, "windows_app_executed": False,
            "new_system_library_installed": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--banks", type=Path, required=True);parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists(): raise ValueError("New check output required")
    report = check(args.banks)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
