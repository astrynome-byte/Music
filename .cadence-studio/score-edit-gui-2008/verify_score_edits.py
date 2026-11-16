#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Inspect independent native CLI MusicXML exports, never mutate scores."""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def facts(path):
    raw = path.read_bytes()
    if not 0 < len(raw) <= 2 * 1024 * 1024 or b'<!ENTITY' in raw:
        raise ValueError('Bounded entity-free MusicXML required')
    root = ET.fromstring(raw)
    parts = root.findall('part')
    if root.tag != 'score-partwise' or len(parts) != 1:
        raise ValueError('Exactly one part required')
    divisions = None
    notes = []
    measures = parts[0].findall('measure')
    # Entering the final note may create a following empty measure for the
    # insertion cursor. Its rests are harmless; all pitched notes remain checked.
    if not 1 <= len(measures) <= 2:
        raise ValueError('Expected one exercise measure and at most one auto-appended measure')
    for index, measure in enumerate(measures):
        value = measure.findtext('attributes/divisions')
        if value is not None:
            divisions = int(value)
        if not divisions or divisions <= 0 or measure.find('backup') is not None:
            raise ValueError('Positive divisions and a single voice required')
        position = Fraction(0)
        for note in measure.findall('note'):
            if note.find('grace') is not None or note.find('chord') is not None or note.find('tie') is not None:
                raise ValueError('No grace/chord/tie expected')
            duration = Fraction(int(note.findtext('duration')), divisions)
            if note.find('rest') is None:
                pitch = note.find('pitch')
                if pitch is None or index != 0:
                    raise ValueError('Every pitched note must be in the first measure')
                step = pitch.findtext('step'); octave = int(pitch.findtext('octave'))
                alter = int(pitch.findtext('alter', '0'))
                midi = 12 * (octave + 1) + {'C':0,'D':2,'E':4,'F':5,'G':7,'A':9,'B':11}[step] + alter
                notes.append({'midi':midi, 'start_quarters':str(position), 'duration_quarters':str(duration),
                              'type':note.findtext('type'), 'measure':index+1})
            position += duration
    return {'bytes':len(raw), 'sha256':hashlib.sha256(raw).hexdigest(), 'notes':notes, 'measures':len(measures)}


def verify(directory):
    observed = {name:facts(directory / (name + '.musicxml')) for name in ('baseline','edited','undo','redo')}
    if observed['baseline']['notes']:
        raise ValueError('CLI-created native baseline was not empty')
    for name, pitches in [('edited',[72,74,76,77]), ('undo',[72,74,76]), ('redo',[72,74,76,77])]:
        expected = [{'midi':pitch,'start_quarters':str(index),'duration_quarters':'1','type':'quarter','measure':1}
                    for index,pitch in enumerate(pitches)]
        if observed[name]['notes'] != expected:
            raise ValueError(f'{name}: exact pitches, quarters, positions or count differ: {observed[name]["notes"]}')
    if observed['edited']['notes'] != observed['redo']['notes']:
        raise ValueError('Redo did not regain the identical last note')
    return {'schema_version':1,'status':'passed_independent_native_MusicXML_edit_undo_redo_comparison',
            'expected_midi':[72,74,76,77], 'expected_counts':[4,3,4], 'exports':observed,
            'graphical_gestures_or_focus_inferred_by_this_reader':False}


def main():
    p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); report=verify(a.directory)
    with a.output.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps(report,separators=(',',':')))


if __name__ == '__main__':main()
