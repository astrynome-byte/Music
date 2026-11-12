# Native Windows2007 QA for three pinned VSCO SF2 collections

Prepared only, not yet executed on Windows. The executable is the existing
full2007 source5058d29d/tree58d06a1c, EXEdcfbf9155c6c972c37966a4b2b0dcd212133c8e31fb397c644dda800ac7122be.
This job does not rebuild/install the app or publish any file. It rebuilds the
three pinned CC0 banks from original individual WAVs, verifies exact known
bytes against bank-lock.json, then runs27 native commands across8cases.

Cases: MS Basic and expansion cello/trumpet/contrabass; a technical trumpet
minus18dB bank; a deliberately absent cello resource. MusicXML programs43/57/44
are one based, matching native programs42/56/43. Cello and bass use the bass
clef; bass explicitly transposes down12semitones. Original CC0 scores contain
p/mf/f, three isolated notes, a20second tied hold and final rest. Native
preservation is CLI save-only then reopen/render, not GUI save after live playback.
Master gain is controlled at minus18dB; clipping results do not qualify every
possible end-user mixer setting. Real MIDI velocities are not measured here.

The new2007 backend keeps missing requested IDs, so saved metadata/nonmute
alone cannot prove load. Mandatory independent controls require fresh/reopened
trumpetquiet/normal RMS ratios10^(-18/20) within3percent, identical shape,
actual SF2 PCM different from MS Basic, and the deliberately missing cello
render matching MS Basic PCM. Only attenuation generators change in the
technical quiet SF2; it is not a fourth public collection. Default dynamics
must increase and new banks must exhibit their documented finite unlooped
sustain and release. All these assertions may genuinely fail the future run;
none has been reported as native Windows passed at preparation time.

Suboctave/fundamental Goertzel powers are diagnostic-only, not a pitch/tuning
qualification. Harmonics and overlapping releases can suggest a virtual
fundamental; no NSDF output is used to mark musical correctness.

## Exact retained stage provenance

The fixed successful producer43266732201/driverc3421a21 and stageartifact
13970570430 are checked by authenticated GET metadata before downloading.
The306532246-byte outer digest88a07b09...1db3250 remains API metadata in this
job, not a falsely claimed local outer ZIP recomputation. The downloaded
original stage-manifest.json must match3776bytes andSHA256
ba985694173769bded900789a57952eef564026626e8be68e3484c583541ad05,
a receipt already authenticated by DATAONLY43277515426. Only then is its
actual stage_archive_sha256 used to rehash the original innerZIP. Its hash is
not guessed from2005/2006. Source/CI/tree, the build-result report, companion
ledger, extracted EXE and no-local-icuuc.dll policy are checked. Stage files,
banks and original exercises are hashed before/after the native commands.

The KnownFolder profile helper and source contract remain byte-identical to
the previously qualified0e namespace helper. This is the original provenance
of that path contract, not a claim that2007 source is0e or that the whole
source files remained identical. Actual2007 CLI/profile behavior was exercised
by the full producer. The helper verifies ownership, source contract and exact
ASIO seed first; this renderer then changes only its owned INI to WASAPI plus
its own temporary SoundFont folder. The enclosing unchanged native Job proves
drainage before cleanup. An existing Cadence profile is never replaced.
The app environment removes SDK Qt/QML paths, GitHub tokens and secrets.

## What is actually tested in preparation

Eight Linux data/refusal checks execute real parser/window-analysis code,
including synthetic float PCM dynamics/release/silence/clipping and wrong
native instrument/GM rejection. Three real Linux bank file sizes/hashes and
the8case/27command plan are checked separately (actual-linux-bank-lock-check).
These are not a Windows renderer, GUI, hardware or listening qualification.
The workflow is the only proposed entrypoint; no active target or release is
created. It uploads factual reports/WAVs/saved copies, retaining failures.
Artifacts expire after14days and are not an anonymous final gift download.
