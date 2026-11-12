#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Build only two pinned VSCO CE CC0 mappings as native PCM16 SoundFont 2.1.

This is a bounded derivative builder, not a general SFZ interpreter. It uses
the Python standard library. Each original WAV is verified by its Git blob ID
and size, held in memory, then discarded after writing its SoundFont samples.
No plugin, application or installer is loaded or executed.
"""
from __future__ import annotations
import argparse
from array import array
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import struct
import sys
import urllib.parse
import urllib.request

COMMIT = "28092772094b2d9f1148d84cea97f4545b8c687d"
MAX_WAV_BYTES = 4_000_000
MAX_OUTPUT_BYTES = 150_000_000
# The retained app's FluidSynth 2.3.3 fluid_defsfont.c applies the historical
# EMU_ATTENUATION_FACTOR 0.4 to generator48 (not to modulators). Therefore 25
# raw generator units, rather than 10, produce one audible dB in THIS engine.
ATTENUATION_UNITS_PER_DB = 25
INSTRUMENTS = {"flute": ("FluteSusVib.sfz", 13, 73, "Cadence-VSCO-Flute"),
               "violin": ("SViolinVib.sfz", 30, 40, "Cadence-VSCO-Violin")}
LIMITATIONS = [
    "Only the exact sustain-vibrato flute/solo-violin mappings are accepted; no general SFZ opcode support.",
    "PCM24/32 integer recordings are deterministically truncated to signed PCM16; stereo channels are retained and linked.",
    "Positive SFZ region gains are normalized by one documented common headroom per bank; relative gains remain unchanged.",
    "Gain generators target Cadence's FluidSynth EMU attenuation factor 0.4 (25 raw units/dB); other engines may interpret gain differently.",
    "Attack/release are fixed SoundFont timecents. Live ampeg_dynamic is not implemented; default SoundFont velocity response remains active.",
    "Only an original forward infinite WAV smpl loop is enabled, continuously through release. No loop or articulation is invented.",
    "No recorded legato/staccato, original sfizz equivalence, human listening or GUI manager integration is claimed.",
]


def digest(raw): return hashlib.sha256(raw).hexdigest()


def verify_source(raw, pin):
    if len(raw) != pin["bytes"] or hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() != pin["git_blob_sha1"]:
        raise ValueError("Pinned source size/Git blob differs: " + pin["path"])


@dataclass(frozen=True)
class Region:
    sample: str
    low: int
    high: int
    root: int
    velocity_low: int
    velocity_high: int
    volume_db: float
    fine_tune: int = 0


def parse_mapping(raw, *, expected_releases=(0.7, 0.8), expected_group=None):
    """Accept the small explicit opcode vocabulary actually in these mappings."""
    sections = {"control": {}, "global": {}, "group": {}}
    regions = []
    current = None
    for original in raw.decode("utf-8-sig").splitlines():
        line = original.split("//", 1)[0].strip()
        if not line: continue
        match = re.fullmatch(r"<(control|global|group|region)>", line)
        if match:
            kind = match[1]
            if kind == "region":
                current = {}; regions.append(current)
            else:
                if sections[kind]: raise ValueError("Repeated nonempty SFZ header refused")
                current = sections[kind]
            continue
        if current is None or "=" not in line: raise ValueError("Unsupported SFZ syntax")
        key, value = line.split("=", 1)
        if key in current: raise ValueError("Duplicate SFZ opcode")
        current[key] = value
    if set(sections["control"]) != {"default_path"} or sections["group"] != (expected_group or {}):
        raise ValueError("Exact audited control/default path and static group metadata required")
    global_ = sections["global"]
    if (set(global_) != {"ampeg_attack", "ampeg_release", "ampeg_dynamic", "volume"}
            or global_["ampeg_dynamic"] != "1" or float(global_["volume"]) != 0
            or float(global_["ampeg_attack"]) != 0.001
            or float(global_["ampeg_release"]) not in expected_releases):
        raise ValueError("Unsupported global envelope/gain mapping")
    default = sections["control"]["default_path"].replace("\\", "/")
    result = []
    required = {"sample", "lokey", "hikey", "pitch_keycenter", "lovel", "hivel", "volume"}
    for row in regions:
        if not required <= row.keys() or set(row) - required - {"tune"}: raise ValueError("Unsupported region opcode")
        sample = default + row["sample"]
        path = PurePosixPath(sample)
        if path.is_absolute() or ".." in path.parts or any(c in sample for c in "\\:\0"):
            raise ValueError("Unsafe sample path")
        region = Region(sample, int(row["lokey"]), int(row["hikey"]), int(row["pitch_keycenter"]),
                        int(row["lovel"]), int(row["hivel"]), float(row["volume"]), int(row.get("tune", 0)))
        if (not 0 <= region.low <= region.high <= 127 or not 0 <= region.root <= 127
                or not 0 <= region.velocity_low <= region.velocity_high <= 127
                or not -99 <= region.fine_tune <= 99 or not math.isfinite(region.volume_db)
                or not -60 <= region.volume_db <= 24):
            raise ValueError("Invalid mapped note/velocity/gain/tuning range")
        result.append(region)
    # Every playable key/velocity pair must select exactly one source layer.
    for key in range(min(r.low for r in result), max(r.high for r in result) + 1):
        for velocity in range(128):
            if sum(r.low <= key <= r.high and r.velocity_low <= velocity <= r.velocity_high for r in result) != 1:
                raise ValueError("Mapping has an overlapping or missing key/velocity layer")
    return result, float(global_["ampeg_attack"]), float(global_["ampeg_release"])


def decode_wav(raw):
    """Read bounded little-endian integer PCM and an optional forward smpl loop."""
    if len(raw) > MAX_WAV_BYTES or raw[:4] != b"RIFF" or raw[8:12] != b"WAVE" or len(raw) < 44:
        raise ValueError("Bounded RIFF/WAVE expected")
    if struct.unpack_from("<I", raw, 4)[0] + 8 != len(raw): raise ValueError("WAV RIFF length mismatch")
    chunks = {}; offset = 12
    while offset < len(raw):
        if offset + 8 > len(raw): raise ValueError("Truncated WAV chunk")
        tag, size = struct.unpack_from("<4sI", raw, offset); end = offset + 8 + size
        if end > len(raw): raise ValueError("WAV chunk escapes RIFF")
        if tag in (b"fmt ", b"data", b"smpl"):
            if tag in chunks: raise ValueError("Duplicate semantic WAV chunk")
            chunks[tag] = raw[offset + 8:end]
        offset = end + (size & 1)
    if offset != len(raw) or b"fmt " not in chunks or b"data" not in chunks: raise ValueError("Invalid WAV chunks")
    fmt = chunks[b"fmt "]
    if len(fmt) < 16: raise ValueError("Short WAV format")
    code, channels, rate, byte_rate, align, bits = struct.unpack_from("<HHIIHH", fmt)
    if code == 0xfffe:
        if len(fmt) < 40 or fmt[24:40] != bytes.fromhex("0100000000001000800000aa00389b71") or struct.unpack_from("<H", fmt, 18)[0] != bits:
            raise ValueError("Only integer PCM extensible WAV with equal valid/container bits is supported")
        code = 1
    data = chunks[b"data"]
    if (code != 1 or channels not in (1, 2) or bits not in (16, 24, 32) or not 22050 <= rate <= 192000
            or align != channels * bits // 8 or byte_rate != rate * align or len(data) % align):
        raise ValueError("Unsupported or inconsistent PCM WAV")
    frames = len(data) // align
    if not 100 <= frames <= rate * 60: raise ValueError("WAV frame bound exceeded")
    loop = None
    if b"smpl" in chunks:
        smpl = chunks[b"smpl"]
        if len(smpl) < 36: raise ValueError("Short WAV smpl header")
        loop_count = struct.unpack_from("<I", smpl, 28)[0]
        if loop_count > 1 or len(smpl) < 36 + loop_count * 24: raise ValueError("Unsupported WAV loop count")
        if loop_count:
            _, kind, start, inclusive_end, fraction, plays = struct.unpack_from("<6I", smpl, 36)
            if kind != 0 or fraction or plays or not 0 <= start < inclusive_end < frames or inclusive_end + 1 - start < 8:
                raise ValueError("Only a valid forward infinite integer WAV loop is supported")
            loop = (start, inclusive_end + 1)  # SF2 loop end is exclusive.
    values = array("h")
    if bits == 16:
        values.frombytes(data)
        if sys.byteorder != "little": values.byteswap()
    elif bits == 24:
        # Keep the high signed 16 bits: deterministic, bounded <1 PCM16 LSB error.
        for i in range(0, len(data), 3):
            value = data[i + 1] | data[i + 2] << 8
            values.append(value - 65536 if value & 32768 else value)
    else:
        values = array("h", (value[0] >> 16 for value in struct.iter_unpack("<i", data)))
    separated = []
    for channel in range(channels):
        channel_data = values[channel::channels]
        if sys.byteorder != "little": channel_data.byteswap()
        separated.append(channel_data.tobytes())
    return {"channels": channels, "sample_rate": rate, "source_bits": bits, "frames": frames,
            "loop": loop, "pcm16": separated}


def chunk(tag, payload): return tag + struct.pack("<I", len(payload)) + payload + (b"\0" if len(payload) & 1 else b"")
def listed(kind, payload): return chunk(b"LIST", kind + payload)
def text_chunk(tag, text):
    # SoundFont INFO text requires an even DECLARED length, including NULs.
    payload = text.encode("ascii") + b"\0"
    return chunk(tag, payload + (b"\0" if len(payload) & 1 else b""))
def name20(name): return name.encode("ascii")[:19].ljust(20, b"\0")
def gen(operator, amount): return struct.pack("<HH", operator, amount & 65535)
def timecents(seconds): return max(-12000, min(8000, round(1200 * math.log2(seconds))))


def build_bank(path, regions, provider, *, title, program, attack, release, preset_name=None):
    """Stream samples directly into the final new bank, never a second PCM file."""
    if path.exists(): raise ValueError("A new SoundFont output is required")
    preset_title = title if preset_name is None else preset_name
    if not isinstance(preset_title, str) or not 1 <= len(preset_title.encode("ascii")) <= 19:
        if preset_name is not None: raise ValueError("New preset names must fit the SoundFont 19-byte bound")
    headroom = max(0.0, max(r.volume_db for r in regions))
    headers = []; zones = []; receipts = []; sample_point = 0
    info = listed(b"INFO", chunk(b"ifil", struct.pack("<HH", 2, 1)) + text_chunk(b"isng", "EMU8000")
                  + text_chunk(b"INAM", title)
                  + text_chunk(b"ICOP", "VSCO CE samples and mappings: CC0-1.0. Builder code: GPL-3.0-only.")
                  + text_chunk(b"ICMT", "Pinned VSCO CE " + COMMIT + "; fixed envelopes; no dynamic ampeg; source gain normalized by " + str(headroom) + " dB."))
    with path.open("xb+") as stream:
        stream.write(b"RIFF\0\0\0\0sfbk" + info)
        sdta_position = stream.tell();stream.write(b"LIST\0\0\0\0sdtasmpl\0\0\0\0")
        pcm_position = stream.tell()
        for source_index, region in enumerate(regions):
            raw, identity = provider(region.sample)
            wav = decode_wav(raw);receipt = {**identity, **{k: v for k, v in wav.items() if k != "pcm16"}}
            receipts.append(receipt)
            first_header = len(headers)
            for channel, pcm in enumerate(wav["pcm16"]):
                start = sample_point;end = start + wav["frames"]
                loop_start, loop_end = (start + wav["loop"][0], start + wav["loop"][1]) if wav["loop"] else (start, end)
                stereo = wav["channels"] == 2
                link = first_header + 1 - channel if stereo else 0
                sample_type = (4 if channel == 0 else 2) if stereo else 1
                headers.append(struct.pack("<20sIIIIIBbHH", name20("s%02d%s" % (source_index, "L" if channel == 0 else "R")),
                                           start, end, loop_start, loop_end, wav["sample_rate"], region.root, 0, link, sample_type))
                stream.write(pcm);stream.write(b"\0" * 92);sample_point = end + 46
                attenuation = round((headroom - region.volume_db) * ATTENUATION_UNITS_PER_DB)
                zone = (gen(43, region.low | region.high << 8) + gen(44, region.velocity_low | region.velocity_high << 8)
                        + gen(17, (-500 if channel == 0 else 500) if stereo else 0)
                        + gen(33, -12000) + gen(34, timecents(attack)) + gen(35, -12000)
                        + gen(36, -12000) + gen(37, 0) + gen(38, timecents(release))
                        + gen(48, attenuation) + gen(52, region.fine_tune) + gen(54, 1 if wav["loop"] else 0)
                        + gen(56, 100) + gen(58, region.root) + gen(53, len(headers) - 1))
                zones.append(zone)
            if stream.tell() > MAX_OUTPUT_BYTES: raise ValueError("SoundFont size bound exceeded")
        pcm_end = stream.tell();pcm_size = pcm_end - pcm_position
        stream.seek(sdta_position + 4);stream.write(struct.pack("<I", 12 + pcm_size))
        stream.seek(sdta_position + 16);stream.write(struct.pack("<I", pcm_size));stream.seek(pcm_end)
        ibag = bytearray();igen = bytearray()
        for zone in zones:
            ibag += struct.pack("<HH", len(igen) // 4, 0);igen += zone
        ibag += struct.pack("<HH", len(igen) // 4, 0);igen += gen(0, 0)
        phdr = (struct.pack("<20sHHHIII", name20(preset_title), program, 0, 0, 0, 0, 0)
                + struct.pack("<20sHHHIII", name20("EOP"), 0, 0, 1, 0, 0, 0))
        terminal_header = struct.pack("<20sIIIIIBbHH", name20("EOS"), sample_point, sample_point, sample_point, sample_point, 0, 0, 0, 0, 0)
        pdta = listed(b"pdta", chunk(b"phdr", phdr) + chunk(b"pbag", struct.pack("<4H", 0, 0, 1, 0))
                      + chunk(b"pmod", bytes(10)) + chunk(b"pgen", gen(41, 0) + gen(0, 0))
                      + chunk(b"inst", struct.pack("<20sH", name20(preset_title), 0) + struct.pack("<20sH", name20("EOI"), len(zones)))
                      + chunk(b"ibag", ibag) + chunk(b"imod", bytes(10)) + chunk(b"igen", igen)
                      + chunk(b"shdr", b"".join(headers) + terminal_header))
        stream.write(pdta);size = stream.tell();stream.seek(4);stream.write(struct.pack("<I", size - 8));stream.flush()
    return {"regions": len(regions), "zones": len(zones), "sample_headers": len(headers), "program": program,
            "bank": 0, "headroom_db": headroom, "attack_seconds": attack, "release_seconds": release,
            "original_waveforms": receipts, "loops_enabled": sum(bool(r["loop"]) for r in receipts),
            "output_pcm_bits": 16, "stereo_preserved": True,
            "raw_attenuation_units_per_db": ATTENUATION_UNITS_PER_DB}


def sf2_chunks(path):
    """Inspect RIFF directories only; PCM is not duplicated into memory."""
    result = {}
    with path.open("rb") as stream:
        header = stream.read(12)
        if header[:4] != b"RIFF" or header[8:] != b"sfbk" or struct.unpack_from("<I", header, 4)[0] + 8 != path.stat().st_size:
            raise ValueError("Invalid SoundFont RIFF header")
        end = path.stat().st_size
        while stream.tell() < end:
            tag, size = struct.unpack("<4sI", stream.read(8));payload = stream.tell()
            if tag != b"LIST" or payload + size > end: raise ValueError("Invalid SoundFont list")
            kind = stream.read(4)
            while stream.tell() < payload + size:
                child, length = struct.unpack("<4sI", stream.read(8));start = stream.tell()
                if start + length > payload + size or (kind, child) in result: raise ValueError("Invalid/duplicate SoundFont chunk")
                result[kind, child] = (start, length);stream.seek(start + length + (length & 1))
            if stream.tell() != payload + size: raise ValueError("SoundFont child alignment mismatch")
    return result


def attenuate_bank(source, target, decibels=18):
    import shutil
    if target.exists(): raise ValueError("New attenuated output required")
    with source.open("rb") as src, target.open("xb") as dst: shutil.copyfileobj(src, dst, 1 << 20)
    start, length = sf2_chunks(target)[b"pdta", b"igen"]
    changed = 0
    with target.open("r+b") as stream:
        for offset in range(start, start + length, 4):
            stream.seek(offset);operator, amount = struct.unpack("<HH", stream.read(4))
            if operator == 48:
                adjusted = amount + round(decibels * ATTENUATION_UNITS_PER_DB)
                if not 0 <= adjusted <= 1440: raise ValueError("SoundFont attenuation exceeds range")
                stream.seek(offset + 2);stream.write(struct.pack("<H", adjusted));changed += 1
    if not changed: raise ValueError("No region attenuations found")
    return changed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--download", action="store_true")
    source.add_argument("--source-root", type=Path)
    args = parser.parse_args(argv)
    here = Path(__file__).resolve().parent
    manifest = json.loads((here / "asset-source-manifest.json").read_text())
    if manifest["commit"] != COMMIT or len(manifest["files"]) != 46 or manifest["total_source_bytes"] != 99534068:
        raise ValueError("Exact VSCO two-mapping source selection required")
    pins = {row["path"]: row for row in manifest["files"]}
    license_bytes = (here / "VSCO-CC0-LICENSE.txt").read_bytes();verify_source(license_bytes, pins["LICENSE"])
    parsed = {}
    for instrument, (mapping, count, program, title) in INSTRUMENTS.items():
        raw = (here / "mappings" / mapping).read_bytes();verify_source(raw, pins[mapping])
        regions, attack, release = parse_mapping(raw)
        if len(regions) != count or any(r.sample not in pins for r in regions): raise ValueError("Original mapping selection differs")
        parsed[instrument] = regions, attack, release
    if args.output.exists(): raise ValueError("Output directory must be new")
    args.output.mkdir(parents=True)
    def provider(name):
        pin = pins[name]
        if pin["bytes"] > MAX_WAV_BYTES: raise ValueError("Source WAV exceeds bound")
        if args.download:
            url = "https://raw.githubusercontent.com/sgossner/VSCO-2-CE/" + COMMIT + "/" + urllib.parse.quote(name, safe="/")
            with urllib.request.urlopen(url, timeout=60) as response: raw = response.read(pin["bytes"] + 1)
        else:
            path = args.source_root.joinpath(*PurePosixPath(name).parts)
            if path.is_symlink() or path.stat().st_size != pin["bytes"]: raise ValueError("Invalid local source file")
            raw = path.read_bytes()
        verify_source(raw, pin)
        return raw, {"file": name, "bytes": len(raw), "sha256": digest(raw), "git_blob_sha1": pin["git_blob_sha1"]}
    report = {"schema_version": 1, "status": "building", "source_commit": COMMIT, "sounds_license": "CC0-1.0",
              "code_license": "GPL-3.0-only", "banks": [], "limitations": LIMITATIONS,
              "original_samples_cached_on_disk": False, "application_executed": False, "windows_qualified": False}
    for instrument, (_, _, program, title) in INSTRUMENTS.items():
        regions, attack, release = parsed[instrument];path = args.output / (title + ".sf2")
        details = build_bank(path, regions, provider, title=title, program=program, attack=attack, release=release)
        sf2_chunks(path)
        with path.open("rb") as stream: checksum = hashlib.file_digest(stream, "sha256").hexdigest()
        report["banks"].append({"file": path.name, "bytes": path.stat().st_size, "sha256": checksum,
                                "soundfont_name": title, "resource_id": title + "\\0\\" + str(program),
                                "bank": 0, "program": program, "gain_delta_db": 0, "instrument": instrument, **details})
    flute = args.output / "Cadence-VSCO-Flute.sf2";quiet = args.output / "Cadence-VSCO-Flute-minus18.sf2"
    changed = attenuate_bank(flute, quiet)
    with quiet.open("rb") as stream: checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    report["banks"].append({"file": quiet.name, "bytes": quiet.stat().st_size, "sha256": checksum,
                            "soundfont_name": quiet.stem, "resource_id": quiet.stem + "\\0\\73", "bank": 0,
                            "program": 73, "gain_delta_db": -18, "instrument": "flute", "changed_zone_attenuations": changed})
    (args.output / "VSCO-CC0-LICENSE.txt").write_bytes(license_bytes)
    total = sum(path.stat().st_size for path in args.output.iterdir())
    if total > MAX_OUTPUT_BYTES: raise ValueError("Combined derivative bank data exceeds 150 MB bound")
    report["status"] = "built-pinned-vsco-sf2";report["total_output_bytes"] = total
    (args.output / "banks-manifest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "total_output_bytes": total,
                      "banks": [{key: row[key] for key in ("file", "bytes", "sha256", "resource_id")} for row in report["banks"]]}))
    return 0


if __name__ == "__main__": raise SystemExit(main())
