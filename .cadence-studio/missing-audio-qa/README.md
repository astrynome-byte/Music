# Missing audio resources — retained Windows build2002

Prepared; **not executed on Windows yet**. This driver reuses the authentic
compiled stage from run43108867145 / artifact13898607081. It does not rebuild
Cadence, install a plugin, remove MS Basic, or change MuseScore profiles.

## Scope

1. Refuse existing Cadence profiles; require disposable Windows x64 GitHub-hosted
   runner, native executable SHA35d8…cf39e and the source0e/treef95 records.
2. Verify all ten original artifact root file hashes, nested archive hash and
   source selection before restoring the ZIP into a new RUNNER_TEMP directory.
3. Convert a copy of the original CC0 piano MSCX into native MSCZ using the real
   retained executable; check Part1 / instrumentpiano identifiers.
4. Write three new ZIP copies changing **only audiosettings.json**: MS Basic
   control, a deliberately nonexistent SF name, a nonexistent VST resource ID.
   Resource/vendor/type and a harmless opaque unitConfiguration sentinel are
   explicit. These names do not refer to commercial products.
5. Save each to a new native file and inspect the recorded identity/state.
   Export each input to a new WAV; check every sample with the unchanged
   existing corpus WAV checker. Require the exact missing SF ID in the real
   FluidResolver `Not found:` export-log delta before claiming that path was
   exercised. Keep VST log observation separate from SF-specific diagnostic. The pinned
   VstiResolver returnsnull silently when its repository does not contain the ID;
   a non-silent WAV alone **does not confirm that the VST resolver was reached**.
   The report explicitly leaves this path unconfirmed unless the module-level
   missing-ID diagnostic is actually present; no such diagnostic is assumed.
6. Prove fixture/copies/executable/MS Basic remain unchanged; keep reports,
   diagnostic deltas, generated scores and WAV. Each owned child has90 seconds;
   timeout terminates only the exact Popen child handle, and fails the check.

The save-only conversion creates another project before the WAV conversion.
**This does not test saving the same GUI project after fallback has happened.**
The WAV export does not save its source score. A successful save-only identity
roundtrip is therefore insufficient to establish long-term missing-resource
preservation. No user-facing warning, plugin restoration, audio listening,
physical output or global offline behavior is validated here.

## Source findings to qualify

Pinned source `/workspace/cadence-system-aac` at0e05d04a:

- `ProjectAudioSettings::read/write` serializes native `audiosettings.json`,
  `tracks[].in.resourceMeta`, and base64 `unitConfiguration`.
- `FluidResolver::resolveSynth` logs `Not found: <requested ID>` then returnsnull.
- `EventAudioSource::applyInputParams` attempts `resolveDefaultSynth` after a
  resolver failure; it emits the applied synthesizer's parameters.
- `PlaybackController::doAddTrack` and its input-change subscription write
  applied parameters into project settings. This is a **source-based risk of
  losing the unavailable identity on later save**, not a reproduced GUI defect.
- `ConverterController::convertFile` creates a new project for each output;
  batch output does not provide a same-project export-then-save operation.

Future GUI case: create a controlled missing-resource MSCZ, open a copy, observe
warning/mixer, play/export, Save As a new MSCZ in the same process, close/reopen,
inspect stored identity/state, restore an explicitly licensed test plugin or
SoundFont, and verify original assignment recovery. Do not call this covered by
this CLI test. MuseSampler missing and missing FX need separate scenarios.

## Local preparation checks

`preparation-checks.json`: six checks passed using the real Linux-reference CC0
native score, no application launch: ZIP-only JSON mutation, wrong track ID
refusal before output, non-Windows guard refusal without output, workflow YAML,
byte-identical reused WAV inspector, log-delta behavior. PowerShell parser for
Restore-CombinedStage and the workflow script blocks passed. Native Windows
runtime is pending; no binary has been downloaded into this preparation folder.

Publish only this namespace and `.github/workflows/cadence-missing-audio-qa.yml`
to the authorized `cadence-studio/windows-build` branch. Commit message must
include `[cadence-packaging-only]` to avoid the legacy full build. `main` and the
Android project must stay unchanged. GitHub Actions artifacts are temporary and
may require an account; none is a final gift link.
