# SPDX-License-Identifier: GPL-3.0-only
"""Decode the pinned original CC0 test input, never a recognition result."""
from pathlib import Path
import argparse,base64,hashlib,json,zlib,wave
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
f=Path(__file__).resolve().parent/'fixtures';m=json.loads((f/'manifest.json').read_text())
encoded=(f/'original-three-notes.wav.zlib.b64').read_bytes()
assert hashlib.sha256(encoded).hexdigest()==m['encoded_sha256']
decoder=zlib.decompressobj()
data=decoder.decompress(base64.b64decode(b''.join(encoded.split()),validate=True),m['expected_bytes']+1)
assert decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail
assert len(data)==m['expected_bytes'] and hashlib.sha256(data).hexdigest()==m['expected_sha256']
with a.output.open('xb')as stream:stream.write(data)
with wave.open(str(a.output),'rb')as stream:assert(stream.getnchannels(),stream.getsampwidth(),stream.getframerate())==(1,2,16000)
print(json.dumps(dict(status='original-input-prepared',path=str(a.output),bytes=len(data),sha256=m['expected_sha256'],license=m['license'],expected_notes=m['notes_MIDI'])))
