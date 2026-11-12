#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""DATAONLY spectral postmortem of existing pitch failure; no new musical PASS.

Read exactly the same retained MusicXML/WAV pins as the first reader. Measure
Hann/Goertzel bands to distinguish an acoustic low component from a common
period of overlapping C5/G5 (or G4/D5). Never launch Cadence, DLLs or audio.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import types

HELPER_SHA = 'd03da527fdaee7af6105654a26d2edcfc5f3e760b285d1479048d00b8a2df52c'
CENTERS = (.24, .40, 1.76, 1.92, 2.08, 2.20, 2.32, 2.44, 2.56)
BAND_CENTS = (-40, -30, -20, -10, 0, 10, 20, 30, 40)


def pinned_helper():
    path = Path(__file__).with_name('analyze_existing_wavs.py')
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != HELPER_SHA:
        raise ValueError('Published pitch reader helper bytes differ')
    module = types.ModuleType('cadence_pinned_pitch_reader')
    module.__file__ = str(path)
    exec(compile(data, str(path), 'exec'), module.__dict__)
    return module


def goertzel_amplitude(values, frequency, rate=11025):
    count = len(values)
    taper = [.5 - .5 * math.cos(2 * math.pi * index / (count - 1)) for index in range(count)]
    coefficient = 2 * math.cos(2 * math.pi * frequency / rate)
    previous = previous2 = 0.
    mean = sum(values) / count
    for value, weight in zip(values, taper):
        current = (value - mean) * weight + coefficient * previous - previous2
        previous2, previous = previous, current
    power = max(0., previous * previous + previous2 * previous2 - coefficient * previous * previous2)
    return 2 * math.sqrt(power) / sum(taper)


def spectral_window(values, fundamentals):
    bands = []
    for multiple in range(1, 7):
        center = fundamentals * multiple
        measured = [(goertzel_amplitude(values, center * 2 ** (cents / 1200)), cents) for cents in BAND_CENTS]
        amplitude, cents = max(measured)
        bands.append({'multiple_of_lower_note': multiple, 'nominal_hz': center,
                      'peak_grid_hz': center * 2 ** (cents / 1200), 'peak_amplitude': amplitude})
    #Separate nearby non-harmonic probes give context, not a calibrated noise floor.
    probes = [goertzel_amplitude(values, fundamentals * factor) for factor in (1.35, 1.55, 2.35, 2.65)]
    strongest = max(row['peak_amplitude'] for row in bands)
    for row in bands:
        row['db_relative_to_strongest_measured_band'] = (20 * math.log10(row['peak_amplitude'] / strongest)
                                                       if row['peak_amplitude'] and strongest else None)
    return {'bands': bands, 'off_harmonic_probe_amplitudes': probes,
            'lower_band_relative_amplitude': bands[0]['peak_amplitude'] / strongest if strongest else None}


def diagnose(root, helper):
    files = helper.file_index(root)
    for instrument, (checksum, notes) in helper.SCORES.items():
        actual = helper.score_notes(helper.member(files, instrument + '-original.musicxml', checksum))
        helper.require(actual == notes, 'Retained MusicXML pitches differ')
    cases = []
    for label, checksum in helper.WAVS.items():
        raw = helper.member(files, label + '.wav', checksum)
        helper.require(raw == helper.member(files, label + '-reopened.wav', checksum), 'Retained reopened WAV differs')
        left, right = helper.wav_channels(raw)
        lower = 195.99771799087463 if 'violin' in label else 261.6255653005986
        windows = []
        for center in CENTERS:
            start = round((center - .08) * 44100)
            end = start + round(.16 * 44100)
            channels = []
            for channel, source in enumerate((left, right)):
                values = helper.lowpass_decimate(source[start:end])
                estimate = helper.estimate_pitch(values)
                channels.append({'channel': channel, 'blind_MPM': estimate,
                                 **spectral_window(values, lower)})
            windows.append({'center_seconds': center, 'channels': channels})
        cases.append({'name': label, 'wav_sha256': checksum, 'wav_bytes': len(raw), 'windows': windows})
    return {'schema_version': 1, 'status': 'completed-spectral-postmortem-no-musical-PASS-issued',
            'original_pitch_run_id': 43242767374, 'original_pitch_result_reclassified_PASS': False,
            'source_WAV_run_id': helper.RUN, 'source_WAV_artifact_id': helper.ARTIFACT,
            'helper_sha256': HELPER_SHA, 'cases': cases,
            'method': '160ms Hann/Goertzel;63tap4kHz FIR before4:1decimation;9frequency grid points within40cents of each nominal band; channels separate',
            'interpretation_limit': 'Band1 weak with bands2/3 present supports virtual common periodicity, but no automated diagnosis, hearing or corrected global PASS is asserted.',
            'application_or_DLL_executed': False, 'PCM_printed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    helper = pinned_helper()
    helper.guard_ci()
    root, output, metadata = map(helper.ci_path, (args.input, args.output, args.metadata))
    helper.require(not output.exists(), 'New numeric diagnostic output required')
    receipt = json.loads(metadata.read_bytes())
    helper.require(receipt.get('run_id') == helper.RUN and receipt.get('artifact_id') == helper.ARTIFACT
                   and receipt.get('head_sha') == helper.HEAD and receipt.get('artifact_digest_from_API') == helper.DIGEST,
                   'Source artifact metadata receipt differs')
    result = diagnose(root, helper)
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print('CADENCE_SF2_EXISTING_WAV_SPECTRUM_BEGIN')
    print(json.dumps(result, separators=(',', ':'), allow_nan=False))
    print('CADENCE_SF2_EXISTING_WAV_SPECTRUM_END')


if __name__ == '__main__':
    main()
