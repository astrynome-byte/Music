#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Read the actual GUI-saved three-note fixture MIDI and optional CLI MusicXML.

No musical file is modified. A timing difference is reported and exits 2;
passing a MIDI alone never claims GUI import or notation fidelity.
"""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import struct
import xml.etree.ElementTree as ET


def require(ok, message):
    if not ok:
        raise ValueError(message)


def actual_midi(path):
    raw = path.read_bytes()
    require(22 <= len(raw) <= 1024 * 1024, 'Bounded MIDI fixture required')
    require(raw[:14] == b'MThd\x00\x00\x00\x06\x00\x00\x00\x01\x01\xe0',
            'Exact format0, one-track, PPQ480 output expected')
    require(raw[14:18] == b'MTrk' and struct.unpack('>I', raw[18:22])[0] == len(raw) - 22,
            'One complete MIDI track required')
    index, tick, events = 22, 0, 0
    active = None
    notes, metadata, programs = [], {}, []

    def take(count):
        nonlocal index
        require(0 <= count <= len(raw) - index, 'Truncated MIDI event')
        result = raw[index:index + count]
        index += count
        return result

    def vlq():
        result = 0
        for _ in range(4):
            value = take(1)[0]
            result = (result << 7) | (value & 127)
            if value < 128:
                return result
        raise ValueError('Oversized MIDI variable integer')

    finished = False
    while index < len(raw):
        events += 1
        require(events <= 256 and not finished, 'Unexpected extra MIDI events')
        tick += vlq()
        status = take(1)[0]
        if status == 0xff:
            kind = take(1)[0]
            value = take(vlq())
            require(kind in (0x03, 0x2f, 0x51, 0x58) and kind not in metadata,
                    'Unexpected or repeated metadata')
            metadata[kind] = value
            if kind == 0x2f:
                require(not value and active is None, 'Invalid track end')
                finished = True
        elif status == 0xc0:
            programs.append(take(1)[0])
        elif status in (0x90, 0x80):
            pitch, velocity = take(2)
            require(pitch < 128 and velocity < 128 and tick % 120 == 0,
                    'Expected bounded channel0 notes on sixteenth-note grid')
            if status == 0x90:
                require(active is None and velocity == 80, 'No overlap and exact draft velocity80 expected')
                active = (pitch, tick)
            else:
                require(active and active[0] == pitch and velocity == 0 and tick > active[1],
                        'Matched positive-duration note-off expected')
                notes.append({'midi': pitch, 'start_quarters': str(Fraction(active[1], 480)),
                              'duration_quarters': str(Fraction(tick - active[1], 480))})
                active = None
        else:
            raise ValueError('Unexpected status, running status, channel or SysEx')
    require(finished and programs == [0] and [n['midi'] for n in notes] == [64, 67, 69],
            'Three actual E4/G4/A4 notes and GM piano program expected')
    require(notes == [
        {'midi': 64, 'start_quarters': '0', 'duration_quarters': '1'},
        {'midi': 67, 'start_quarters': '3/2', 'duration_quarters': '1'},
        {'midi': 69, 'start_quarters': '11/4', 'duration_quarters': '1'},
    ], 'Actual saved notes must match independently observed native-engine fixture positions and durations')
    require(metadata.get(0x51) == bytes([0x07, 0xa1, 0x20]) and metadata.get(0x58) == bytes([4, 2, 24, 8])
            and metadata.get(0x03) == b'Cadence - brouillon monodique a corriger',
            'Exact tempo120, meter4/4 and draft track name expected')
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'ppq': 480,
            'tempo_microseconds': 500000, 'meter': '4/4', 'program': 0, 'notes': notes}


def actual_musicxml(path):
    raw = path.read_bytes()
    require(0 < len(raw) <= 2 * 1024 * 1024 and b'<!ENTITY' not in raw, 'Bounded entity-free XML required')
    root = ET.fromstring(raw)
    parts = root.findall('part')
    require(root.tag == 'score-partwise' and len(parts) == 1, 'One-part native MusicXML expected')
    divisions, measure_start = None, Fraction(0)
    segments = []
    for measure in parts[0].findall('measure'):
        position, end = Fraction(0), Fraction(0)
        for element in measure:
            if element.tag == 'attributes':
                value = element.findtext('divisions')
                if value is not None:
                    divisions = int(value)
                continue
            if element.tag not in ('note', 'backup', 'forward'):
                continue
            require(divisions and divisions > 0, 'Positive MusicXML divisions required')
            duration = Fraction(int(element.findtext('duration')), divisions)
            require(duration > 0, 'Positive imported durations required')
            if element.tag == 'backup':
                position -= duration
                require(position >= 0, 'Invalid backup position')
            elif element.tag == 'forward':
                position += duration
                end = max(end, position)
            else:
                require(element.find('grace') is None and element.find('chord') is None,
                        'No grace or chords in monophonic fixture')
                pitch = element.find('pitch')
                if pitch is not None:
                    step = pitch.findtext('step')
                    require(step in 'CDEFGAB', 'Named pitch expected')
                    midi = 12 * (int(pitch.findtext('octave')) + 1) + dict(C=0, D=2, E=4, F=5, G=7, A=9, B=11)[step]
                    midi += int(pitch.findtext('alter', '0'))
                    ties = {t.attrib['type'] for t in element.findall('tie')}
                    segments.append({'midi': midi, 'start': measure_start + position, 'duration': duration, 'ties': ties})
                position += duration
                end = max(end, position)
        measure_start += end
    notes = []
    for segment in sorted(segments, key=lambda row: row['start']):
        if 'stop' in segment['ties']:
            require(notes and notes[-1]['midi'] == segment['midi']
                    and notes[-1]['start'] + notes[-1]['duration'] == segment['start'], 'Contiguous matching tie required')
            notes[-1]['duration'] += segment['duration']
        else:
            notes.append({k: segment[k] for k in ('midi', 'start', 'duration')})
    require([n['midi'] for n in notes] == [64, 67, 69], 'Native import must retain E4/G4/A4 without extra pitches')
    observed = [{'midi': n['midi'], 'start_quarters': str(n['start']), 'duration_quarters': str(n['duration'])} for n in notes]
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'notes': observed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--midi', type=Path, required=True)
    parser.add_argument('--musicxml', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    midi = actual_midi(args.midi)
    xml = actual_musicxml(args.musicxml) if args.musicxml else None
    exact = xml is not None and midi['notes'] == xml['notes']
    report = {'schema_version': 1, 'status': 'passed_actual_saved_fixture_MIDI_only' if xml is None else
              'passed_actual_saved_MIDI_and_native_import_exact' if exact else 'pitches_pass_timing_diff_unqualified',
              'midi': midi, 'musicxml': xml, 'midi_vs_musicxml_timing_exact': exact,
              'graphical_open_or_focus_inferred_by_reader': False, 'human_listening_performed': False}
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(json.dumps(report, separators=(',', ':')))
    raise SystemExit(0 if xml is None or exact else 2)


if __name__ == '__main__':
    main()
