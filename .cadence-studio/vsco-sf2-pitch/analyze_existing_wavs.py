#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Read the retained Windows WAVs as data; never launch any application or DLL.

Pitch selection is blind to the score: normalized square-difference / MPM local
peaks over 90..2000 Hz, then compare the resulting sustained semitone sequence.
Only the exact ten prior WAVs and two generated CC0 MusicXMLs are accepted.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import stat
import statistics
import struct
import sys
import urllib.request
import xml.etree.ElementTree as ET

REPO = 'astrynome-byte/Music'
RUN = 43231480145
HEAD = '1fbc211789c7698c4c191fa204ddbb00216209ec'
ARTIFACT = 13949852671
DIGEST = 'sha256:3e0863479ac9a118d58e4082eaf3905838519346e4a3c8ff02a00eb9a78d3604'
ARTIFACT_BYTES = 21278275
WAVS = {
    'basic-flute': 'f65f39a3821ba939117a9508b76c91a217e91d53c933c79139d1efb69ce3851f',
    'flute': 'a53c4c26449770843c09a467c6bb2f0a9de3ec1e08e42a7f5549100fa7e7714a',
    'flute-minus18': '78ffe402ff453de52125673ad5f0b3683880fb143a4e1f411fad69f6ee57e406',
    'basic-violin': '35e058d0d696908400b9598e0f049fd7bc3c8359cd1f0414a2d07a4188029388',
    'violin': '7fe0ab3500cbb3863e4ca35e1952cf04b7637bfc0916fc28229e23ea47dca92a',
}
SCORES = {'flute': ('4ef020f2e036f6aeefe1b2a9b1c6fa5db6568c6e46303620d825a5f35d27a269', [72, 74, 76, 79] * 2),
          'violin': ('18fe9c3053f6795f125f90b571ba2aa95bec33a5bea1224ce9696f11fd90cc38', [67, 69, 71, 74] * 2)}
WINDOW = .160
HOP = .080
CLARITY = .85
PEAK_FRACTION = .97
CENTS_LIMIT = 60


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def plain(path):
    path = Path(path).absolute()
    require('..' not in path.parts, 'Parent traversal in runtime path refused')
    for component in (path, *path.parents):
        if component.exists() or component.is_symlink():
            info = component.lstat()
            require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400,
                    'Link or reparse path refused')
    return path


def ci_path(path):
    result = plain(path)
    temporary = plain(os.environ['RUNNER_TEMP'])
    require(temporary in result.parents, 'All runtime inputs/outputs must be below RUNNER_TEMP')
    return result


def guard_ci():
    require(sys.platform == 'linux' and platform.machine().lower() in ('x86_64', 'amd64')
            and os.environ.get('CI') == 'true' and os.environ.get('GITHUB_ACTIONS') == 'true'
            and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted',
            'Only hosted native Linux x64 DATAONLY CI is permitted')


def check_metadata(run, artifact):
    require(run.get('id') == RUN and run.get('head_sha') == HEAD and run.get('status') == 'completed'
            and run.get('conclusion') == 'success', 'Wrong or unsuccessful source run')
    require(artifact.get('id') == ARTIFACT and artifact.get('size_in_bytes') == ARTIFACT_BYTES
            and artifact.get('digest') == DIGEST and artifact.get('expired') is False
            and artifact.get('name') == 'cadence-vsco-sf2-qa-43231480145-1'
            and artifact.get('workflow_run', {}).get('id') == RUN
            and artifact.get('workflow_run', {}).get('head_sha') == HEAD, 'Wrong artifact metadata')
    return {'schema_version': 1, 'run_id': RUN, 'head_sha': HEAD, 'artifact_id': ARTIFACT,
            'artifact_bytes': ARTIFACT_BYTES, 'artifact_digest_from_API': DIGEST,
            'raw_outer_ZIP_digest_verified_by_this_reader': False,
            'member_WAV_and_MusicXML_bytes_independently_SHA256_pinned': True}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Metadata API redirect refused')


def metadata_receipt():
    token = os.environ['GH_TOKEN']
    opener = urllib.request.build_opener(NoRedirect)
    def fetch(suffix):
        request = urllib.request.Request('https://api.github.com/repos/' + REPO + suffix,
                                         headers={'Authorization': 'Bearer ' + token,
                                                  'Accept': 'application/vnd.github+json',
                                                  'X-GitHub-Api-Version': '2022-11-28'})
        with opener.open(request, timeout=30) as response:
            data = response.read(512 * 1024 + 1)
        require(len(data) <= 512 * 1024, 'Metadata response exceeds bound')
        return json.loads(data)
    run = fetch('/actions/runs/' + str(RUN))
    artifact = fetch('/actions/artifacts/' + str(ARTIFACT))
    return check_metadata(run, artifact)


def file_index(root):
    require(root.is_dir(), 'Downloaded original artifact directory required')
    files = {}
    total = 0
    entries = list(root.rglob('*'))
    require(len(entries) <= 512, 'Artifact entry count exceeds bound')
    for path in entries:
        plain(path)
        info = path.lstat()
        require(stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode), 'Non-regular artifact entry')
        if path.is_file():
            require(info.st_size <= 4 * 1024**2, 'Artifact member exceeds four MiB')
            total += info.st_size
            files[path.relative_to(root).as_posix()] = path
    require(total <= 80 * 1024**2, 'Artifact expanded bytes exceed bound')
    return files


def member(files, name, checksum):
    candidates = [path for key, path in files.items() if key == name or key.endswith('/' + name)]
    require(len(candidates) == 1, 'Exactly one retained member required: ' + name)
    data = candidates[0].read_bytes()
    require(sha(data) == checksum, 'Retained bytes differ: ' + name)
    return data


def score_notes(data):
    require(len(data) <= 8192 and b'<!' not in data, 'Only small declaration-free MusicXML accepted')
    root = ET.fromstring(data)
    require(len(root.findall('part')) == 1, 'Single-part exercise required')
    notes = []
    offsets = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
    for note in root.findall('./part/measure/note'):
        require(note.find('rest') is None and note.find('chord') is None
                and note.findtext('duration') == '1' and note.findtext('type') == 'quarter', 'Only eight single quarter notes accepted')
        pitch = note.find('pitch')
        require(pitch is not None and pitch.find('alter') is None, 'Natural pitched note required')
        notes.append(12 * (int(pitch.findtext('octave')) + 1) + offsets[pitch.findtext('step')])
    require(len(notes) == 8 and root.findtext('./part/measure/attributes/divisions') == '1', 'Exercise timing differs')
    return notes


def wav_channels(data):
    require(len(data) >= 12 and data[:4] == b'RIFF' and data[8:12] == b'WAVE'
            and struct.unpack_from('<I', data, 4)[0] + 8 == len(data), 'Exact RIFF/WAVE size required')
    position = 12
    fmt = payload = None
    chunks = 0
    while position < len(data):
        chunks += 1
        require(chunks <= 128 and position + 8 <= len(data), 'WAV chunk header exceeds bound')
        tag, size = struct.unpack_from('<4sI', data, position)
        start = position + 8
        position = start + size + (size & 1)
        require(position <= len(data), 'Truncated WAV chunk/pad')
        if tag == b'fmt ':
            require(fmt is None and 16 <= size <= 1024, 'Duplicate or malformed WAV format')
            fmt = struct.unpack_from('<HHIIHH', data, start)
        elif tag == b'data':
            require(payload is None, 'Duplicate WAV data')
            payload = data[start:start + size]
    require(fmt == (3, 2, 44100, 352800, 8, 32) and payload is not None
            and len(payload) == 7 * 44100 * 8, 'Only actual seven-second stereo44.1kHz float32 renders accepted')
    left, right = [], []
    for first, second in struct.iter_unpack('<ff', payload):
        require(math.isfinite(first) and math.isfinite(second) and abs(first) < 1 and abs(second) < 1,
                'Nonfinite or clipped original sample')
        left.append(first)
        right.append(second)
    return left, right


def lowpass_decimate(values, rate=44100):
    #63-tap Hamming-windowed sinc4kHz, then4:1 decimation to11025Hz.
    #Applied independently to each selected window; no new audio file is made.
    taps = []
    cutoff = 4000 / rate
    for index in range(63):
        x = index - 31
        sinc = 2 * cutoff if x == 0 else math.sin(2 * math.pi * cutoff * x) / (math.pi * x)
        taps.append(sinc * (.54 - .46 * math.cos(2 * math.pi * index / 62)))
    scale = sum(taps)
    taps = [value / scale for value in taps]
    return [sum(tap * values[index + j] for j, tap in enumerate(taps)) for index in range(0, len(values) - 62, 4)]


def estimate_pitch(values, rate=11025):
    """Return blind MPM frequency/clarity; the expected score is not an input."""
    require(len(values) >= 1000 and all(math.isfinite(x) for x in values), 'Finite bounded analysis window required')
    average = statistics.fmean(values)
    values = [x - average for x in values]
    rms = math.sqrt(statistics.fmean(x * x for x in values))
    if rms < 1e-9:
        return {'frequency_hz': None, 'clarity': 0.0, 'rms': rms, 'subharmonic_ambiguity': False}
    prefix = [0.0]
    for value in values:
        prefix.append(prefix[-1] + value * value)
    minimum, maximum = math.ceil(rate / 2000), math.floor(rate / 90)
    nsdf = [0.0] * (maximum + 2)
    count = len(values)
    for lag in range(1, maximum + 2):
        denominator = prefix[count - lag] + prefix[count] - prefix[lag]
        nsdf[lag] = 2 * sum(values[i] * values[i + lag] for i in range(count - lag)) / denominator
    #Exclude the zero-lag main lobe before looking for positive local maxima.
    crossed_zero = False
    peaks = []
    for lag in range(1, maximum + 1):
        crossed_zero |= nsdf[lag] <= 0
        if crossed_zero and lag >= minimum and nsdf[lag] > 0 and nsdf[lag] > nsdf[lag - 1] and nsdf[lag] >= nsdf[lag + 1]:
            peaks.append(lag)
    if not peaks:
        return {'frequency_hz': None, 'clarity': 0.0, 'rms': rms, 'subharmonic_ambiguity': False}
    interpolated = []
    for lag in peaks:
        before, center, after = nsdf[lag - 1:lag + 2]
        curvature = before - 2 * center + after
        shift = max(-.5, min(.5, .5 * (before - after) / curvature)) if curvature else 0
        height = min(1., center - .25 * (before - after) * shift)
        interpolated.append((lag, shift, height))
    #Compare interpolated peak heights: comparing integer-lag heights can make
    #a half-sample fundamental lose to its two-period peak and invent an octave.
    best = max(row[2] for row in interpolated)
    selected, shift, center = next(row for row in interpolated if row[2] >= PEAK_FRACTION * best)
    frequency = rate / (selected + shift)
    #A dominant second/third harmonic can fool a period picker into an octave.
    #Refuse such a window if a measurable lower component is present. This is
    #a conservative ambiguity guard, not a proof of absent subthreshold tones.
    tapered = [value * (.5 - .5 * math.cos(2 * math.pi * i / (count - 1))) for i, value in enumerate(values)]
    def amplitude(target):
        coefficient = 2 * math.cos(2 * math.pi * target / rate)
        previous = previous2 = 0.
        for value in tapered:
            current = value + coefficient * previous - previous2
            previous2, previous = previous, current
        return math.sqrt(max(0., previous * previous + previous2 * previous2 - coefficient * previous * previous2))
    principal = max(amplitude(frequency * harmonic) for harmonic in (1, 2, 3) if frequency * harmonic < rate / 2)
    lower = max(amplitude(frequency / divisor) for divisor in (2, 3))
    ratio = lower / principal if principal else 0.
    return {'frequency_hz': frequency, 'clarity': center, 'rms': rms,
            'subharmonic_amplitude_ratio': ratio, 'subharmonic_ambiguity': ratio >= .05}


def sustained_runs(windows):
    """Group independent nearest-semitone results; discard isolated transients."""
    groups = []
    current = []
    for row in windows:
        if row['usable'] and (not current or (current[-1]['midi'] == row['midi'] and row['index'] == current[-1]['index'] + 1)):
            current.append(row)
        else:
            if len(current) >= 2:
                groups.append(current)
            current = [row] if row['usable'] else []
    if len(current) >= 2:
        groups.append(current)
    #Low-clarity release/transition gaps may split one sustained pitch.
    merged = []
    for group in groups:
        if merged and merged[-1][-1]['midi'] == group[0]['midi'] and group[0]['center_seconds'] - merged[-1][-1]['center_seconds'] <= .32:
            merged[-1].extend(group)
        else:
            merged.append(group)
    return merged


def analyze_channels(left, right, expected):
    windows = []
    width, hop = round(WINDOW * 44100), round(HOP * 44100)
    for index, start in enumerate(range(0, len(left) - width + 1, hop)):
        channels = (left[start:start + width], right[start:start + width])
        channel = max(range(2), key=lambda i: sum(x * x for x in channels[i]))
        result = estimate_pitch(lowpass_decimate(channels[channel]))
        frequency = result['frequency_hz']
        midi_float = 69 + 12 * math.log2(frequency / 440) if frequency else None
        windows.append({'index': index, 'center_seconds': (start + width / 2) / 44100, 'selected_channel': channel,
                        **result, 'midi_float': midi_float, 'midi': round(midi_float) if midi_float is not None else None})
    maximum = max(row['rms'] for row in windows)
    for row in windows:
        row['usable'] = bool(row['frequency_hz'] is not None and row['clarity'] >= CLARITY
                             and not row['subharmonic_ambiguity'] and row['rms'] >= max(1e-8, maximum * .03))
    groups = sustained_runs(windows)
    notes = []
    for index, group in enumerate(groups):
        midi = statistics.median(row['midi_float'] for row in group)
        target = expected[index] if index < len(expected) else None
        cents = 100 * (midi - target) if target is not None else None
        notes.append({'observed_midi': round(midi), 'median_frequency_hz': 440 * 2 ** ((midi - 69) / 12),
                      'expected_midi': target, 'median_cents_from_expected': cents,
                      'octave_displacement_semitones': 12 * round((midi - target) / 12) if target is not None else None,
                      'window_count': len(group), 'start_center_seconds': group[0]['center_seconds'],
                      'end_center_seconds': group[-1]['center_seconds'],
                      'cents_span': 100 * (max(row['midi_float'] for row in group) - min(row['midi_float'] for row in group)),
                      'minimum_clarity': min(row['clarity'] for row in group)})
    passed = len(notes) == len(expected) and all(abs(row['median_cents_from_expected']) <= CENTS_LIMIT for row in notes)
    return {'status': 'pitch-and-octave-match' if passed else 'mismatch-or-inconclusive', 'notes': notes,
            'expected_notes': expected, 'usable_windows': sum(row['usable'] for row in windows),
            'total_windows': len(windows), 'windows': windows}


def analyze_artifact(root):
    files = file_index(root)
    expected = {}
    for instrument, (checksum, notes) in SCORES.items():
        actual = score_notes(member(files, instrument + '-original.musicxml', checksum))
        require(actual == notes, 'Actual MusicXML pitches differ')
        expected[instrument] = actual
    cases = []
    for label, checksum in WAVS.items():
        data = member(files, label + '.wav', checksum)
        reopened = member(files, label + '-reopened.wav', checksum)
        require(data == reopened, 'Save/reload WAV bytes differ')
        left, right = wav_channels(data)
        instrument = 'violin' if 'violin' in label else 'flute'
        cases.append({'name': label, 'wav_bytes': len(data), 'wav_sha256': checksum,
                      'reopened_WAV_identical_and_independently_SHA_verified': True,
                      **analyze_channels(left, right, expected[instrument])})
    passed = all(case['status'] == 'pitch-and-octave-match' for case in cases)
    comparisons = []
    by_name = {case['name']: case for case in cases}
    for label in ('flute', 'flute-minus18', 'violin'):
        control = by_name['basic-violin' if label == 'violin' else 'basic-flute']
        candidate = by_name[label]
        deltas = ([1200 * math.log2(actual['median_frequency_hz'] / basic['median_frequency_hz'])
                   for actual, basic in zip(candidate['notes'], control['notes'])]
                  if candidate['status'] == control['status'] == 'pitch-and-octave-match' else None)
        comparisons.append({'case': label, 'positive_control': control['name'], 'per_note_cents_relative_to_MS_Basic': deltas})
    return {'schema_version': 1, 'status': 'all-five-existing-Windows-WAV-pitch-sequences-match' if passed else 'mismatch-or-inconclusive',
            'source_run_id': RUN, 'artifact_id': ARTIFACT, 'cases': cases, 'MS_Basic_comparisons': comparisons,
            'method': {'selection': 'Blind NSDF/MPM90..2000Hz; first local peak>=0.97 of best; parabolic lag interpolation',
                       'window_seconds': WINDOW, 'hop_seconds': HOP, 'minimum_clarity': CLARITY,
                       'relative_RMS_floor': .03, 'median_tolerance_cents': CENTS_LIMIT,
                       'subharmonic_guard': 'Hann/Goertzel at f/2 and f/3; refuse windows with>=5% of principal harmonic amplitude',
                       'stereo': 'Analyze the stronger channel per window; no L+R cancellation',
                       'score_alignment': 'Blind sustained semitone runs compared in order; no target-frequency search or assumed120BPM window placement'},
            'application_or_DLL_executed': False, 'PCM_printed': False,
            'limits': ['Pitch is a numeric estimate, not human listening or timbre qualification.',
                       'Strong even harmonics, overlapping release tails or low periodicity can make a result inconclusive; subharmonics below the5% amplitude guard are not excluded.',
                       'Only these eight quarter notes per exercise and their byte-identical reopened WAVs are covered.',
                       'No long-held note, tuning across the entire keyboard or GUI interaction is inferred.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--metadata-only', action='store_true')
    parser.add_argument('--input', type=Path)
    parser.add_argument('--metadata', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    guard_ci()
    output = ci_path(args.output)
    require(not output.exists(), 'New output file required')
    if args.metadata_only:
        result = metadata_receipt()
    else:
        require(args.input is not None and args.metadata is not None, 'Original artifact and metadata receipt required')
        metadata = json.loads(ci_path(args.metadata).read_bytes())
        require(metadata == {'schema_version': 1, 'run_id': RUN, 'head_sha': HEAD, 'artifact_id': ARTIFACT,
                             'artifact_bytes': ARTIFACT_BYTES, 'artifact_digest_from_API': DIGEST,
                             'raw_outer_ZIP_digest_verified_by_this_reader': False,
                             'member_WAV_and_MusicXML_bytes_independently_SHA256_pinned': True}, 'Metadata receipt differs')
        result = analyze_artifact(ci_path(args.input))
        result['artifact_metadata_receipt'] = metadata
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    compact = json.loads(json.dumps(result))
    for case in compact.get('cases', []):
        del case['windows']
    print('CADENCE_SF2_EXISTING_WAV_PITCH_BEGIN')
    print(json.dumps(compact, allow_nan=False))
    print('CADENCE_SF2_EXISTING_WAV_PITCH_END')
    return 0 if args.metadata_only or result['status'] == 'all-five-existing-Windows-WAV-pitch-sequences-match' else 2


if __name__ == '__main__':
    raise SystemExit(main())
