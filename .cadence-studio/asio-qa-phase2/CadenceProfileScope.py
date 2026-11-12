#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Own three initially absent Cadence profile roots on a disposable Windows CI VM.

SOURCE PREPARATION ONLY until a separately authorized Windows job invokes this
file. Importing it performs no Windows API calls or filesystem changes.

prepare --record NEW_JSON_BELOW_RUNNER_TEMP
verify  --record JSON_BELOW_RUNNER_TEMP
cleanup --record JSON_BELOW_RUNNER_TEMP

The caller must drain its Cadence processes (including children) before cleanup.
No process is discovered or terminated here. No registry, environment redirection,
backup, existing profile replacement, stage, DLL, score, or statistics write is
performed. The only writes outside RUNNER_TEMP are within the three owned roots.
Path and identity checks fail closed, but are not an adversarial same-user
concurrency boundary. Interrupted preparation/deletion may require inspection;
cleanup never expands its scope to recover an unmarked or substituted root.
"""
from __future__ import annotations

import argparse
import configparser
import ctypes
from contextlib import ExitStack, contextmanager
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import secrets
import stat
import sys
import uuid


SCHEMA = 1
KIND = "cadence-disposable-knownfolder-profile"
SOURCE_COMMIT = "0e05d04acbeee32f1b561f24493d7ef41c322081"
CONTRACT_SHA256 = "0023f8d7510c89429dea85cda35d803175b3434532cf14aecaf793ded5663a9e"
MARKER_NAME = ".cadence-qa-profile-owner.json"
ROOT_KEYS = ("local_org_root", "roaming_org_root", "documents_app_root")
LAYOUT_KEYS = (*ROOT_KEYS, "local_app_root", "settings_file", "log_root", "extension_root")
KNOWN_FOLDER_IDS = {
    "local": "F1B32785-6FBA-4FCF-9D55-7B8E7F157091",  # FOLDERID_LocalAppData
    "roaming": "3EB685DB-65F9-4CF6-A03A-E3EF65729F3D",  # FOLDERID_RoamingAppData
    "documents": "FDD39AD0-238F-46AF-ADB4-6C85480369C7",  # FOLDERID_Documents
    "program_data": "62AB5D82-FDC1-4DC3-A9DD-070D1D495D97",  # FOLDERID_ProgramData
}
SEED_SETTINGS = (
    "[application]\n"
    "hasCompletedFirstLaunchSetup=true\n"
    "\n[io]\n"
    "audioApi=ASIO\n"
    "outputDevice=Cadence QA Clock (silent sink)\n"
    "bufferSize=256\n"
    "sampleRate=48000\n"
).encode("utf-8")
MAX_RECORD_BYTES = 128 * 1024
MAX_SETTINGS_BYTES = 2 * 1024 * 1024
MAX_TREE_ENTRIES = 20000
MAX_TREE_DEPTH = 24
MAX_FILE_BYTES = 512 * 1024 * 1024
MAX_TREE_BYTES = 2 * 1024 * 1024 * 1024
REPARSE_ATTRIBUTE = 0x400
READONLY_ATTRIBUTE = 0x1


class ScopeError(RuntimeError):
    """Refusal which must not broaden the owned profile scope."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode("utf-8")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ScopeError("Duplicate JSON key refused")
        result[key] = value
    return result


def _decode_json(data: bytes) -> dict:
    try:
        result = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object)
    except (ValueError, UnicodeError) as exc:
        raise ScopeError("Invalid scope JSON") from exc
    if not isinstance(result, dict):
        raise ScopeError("Scope JSON must be an object")
    return result


def windows_path(value: str) -> str:
    """Pure lexical guard; this is not a Windows filesystem validation."""
    if (not isinstance(value, str) or not value or len(value) > 1024
            or any(ord(c) < 32 for c in value)):
        raise ScopeError("Invalid Windows path")
    path = PureWindowsPath(value)
    if (not path.is_absolute() or not re.fullmatch(r"[A-Za-z]:", path.drive)
            or value.startswith(("\\\\", "//")) or "/" in value):
        raise ScopeError("Only absolute local drive paths are permitted")
    # Refuse DOS devices, ADS, ambiguous Win32 trailing characters and dot paths.
    components = value.split("\\")[1:]
    if any(not part or part in (".", "..") or part.endswith((".", " "))
           or any(c in part for c in ':*?"<>|')
           or re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|CLOCK\$|COM[0-9¹²³]|LPT[0-9¹²³])",
                           part.split(".", 1)[0].rstrip(" "))
           for part in components):
        raise ScopeError("Ambiguous or special Windows path refused")
    if str(path) != value:
        raise ScopeError("Canonical Windows path spelling required")
    return str(path)


def layout_for_known_folders(known: dict[str, str]) -> dict[str, str]:
    """Derive the exact source-backed scope; never accept roots from a record."""
    if set(known) != set(KNOWN_FOLDER_IDS):
        raise ScopeError("Exact KnownFolder set required")
    base = {key: PureWindowsPath(windows_path(value)) for key, value in known.items()}
    local = base["local"] / "CadenceStudio"
    roaming = base["roaming"] / "CadenceStudio"
    documents = base["documents"] / "CadenceStudio4"
    app = local / "CadenceStudio4"
    layout = {
        "local_org_root": str(local), "local_app_root": str(app),
        "roaming_org_root": str(roaming), "settings_file": str(roaming / "CadenceStudio4.ini"),
        "documents_app_root": str(documents), "log_root": str(app / "logs"),
        "extension_root": str(app / "extensions"),
    }
    roots = [PureWindowsPath(layout[key]) for key in ROOT_KEYS]
    for index, left in enumerate(roots):
        for right in roots[index + 1:]:
            if left == right or left in right.parents or right in left.parents:
                raise ScopeError("Overlapping KnownFolder profile roots refused")
    return layout


def fallback_settings_paths(known: dict[str, str]) -> list[str]:
    layout_for_known_folders(known)
    roaming = PureWindowsPath(known["roaming"])
    machine = PureWindowsPath(known["program_data"])
    return [str(roaming / "CadenceStudio.ini"), str(machine / "CadenceStudio.ini"),
            str(machine / "CadenceStudio" / "CadenceStudio4.ini")]


def validate_audio_settings(data: bytes) -> None:
    """Check mutable QSettings semantically; the initial hash is provenance only."""
    if len(data) > MAX_SETTINGS_BYTES:
        raise ScopeError("Settings file is too large")
    parser = configparser.ConfigParser(interpolation=None, delimiters=("=",), strict=True)
    parser.optionxform = str
    try:
        parser.read_string(data.decode("utf-8-sig"))
        if parser.defaults():
            raise ScopeError("ConfigParser DEFAULT inheritance is not QSettings syntax")
        sections = set()
        targets = {"io/audioapi": "audioApi", "io/outputdevice": "outputDevice"}
        for section in parser.sections():
            folded = section.casefold()
            if folded in sections:
                raise ScopeError("Case-ambiguous INI sections refused")
            sections.add(folded)
            options = set()
            for option in parser.options(section):
                if option.casefold() in options:
                    raise ScopeError("Case-ambiguous INI keys refused")
                options.add(option.casefold())
                # QSettings decodes percent escapes in key/group names and
                # uses backslashes for nested groups. Refuse alternate spellings
                # that could shadow either canonical audio selection key.
                group = "" if section.casefold() == "general" else _ini_name(section)
                effective = (group + "/" + _ini_name(option)).lstrip("/").casefold()
                if effective in targets and (section != "io" or option != targets[effective]):
                    raise ScopeError("Alternate spelling of an audio selection key refused")
        if (parser.get("io", "audioApi", raw=True) != "ASIO"
                or parser.get("io", "outputDevice", raw=True) != "Cadence QA Clock (silent sink)"):
            raise ScopeError("Cadence settings no longer select the exact ASIO QA endpoint")
    except (configparser.Error, UnicodeError) as exc:
        raise ScopeError("Invalid Cadence INI settings") from exc


def _ini_name(value: str) -> str:
    """Decode QSettings key-name escapes solely to reject target-key aliases."""
    return re.sub(r"%U([a-fA-F0-9]{4})|%([a-fA-F0-9]{2})",
                  lambda match: chr(int(match.group(1) or match.group(2), 16)),
                  value).replace("\\", "/")


def _known_folder_paths() -> dict[str, str]:
    """Use the same official KnownFolder API as Qt; never trust APPDATA alone."""
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

    shell = ctypes.WinDLL("shell32", use_last_error=True)
    ole = ctypes.WinDLL("ole32", use_last_error=True)
    shell.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(GUID), wintypes.DWORD,
                                           wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
    shell.SHGetKnownFolderPath.restype = ctypes.c_long
    ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    result = {}
    for name, identifier in KNOWN_FOLDER_IDS.items():
        guid = GUID.from_buffer_copy(uuid.UUID(identifier).bytes_le)
        pointer = ctypes.c_void_p()
        hr = shell.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(pointer))
        try:
            if hr < 0 or not pointer.value:
                raise ScopeError(f"SHGetKnownFolderPath failed for {name}")
            result[name] = windows_path(ctypes.wstring_at(pointer))
        finally:
            if pointer.value:
                ole.CoTaskMemFree(pointer)
    return result


def _windows_identity() -> dict:
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.IsWow64Process2.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.WORD),
                                      ctypes.POINTER(wintypes.WORD)]
    kernel.IsWow64Process2.restype = wintypes.BOOL
    process_machine, native_machine = wintypes.WORD(), wintypes.WORD()
    if (not kernel.IsWow64Process2(kernel.GetCurrentProcess(), ctypes.byref(process_machine),
                                  ctypes.byref(native_machine))
            or process_machine.value != 0 or native_machine.value != 0x8664
            or ctypes.sizeof(ctypes.c_void_p) != 8):
        raise ScopeError("Native Windows x64 Python and OS required")
    advapi.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    advapi.OpenProcessToken.restype = wintypes.BOOL
    advapi.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                         wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    advapi.GetTokenInformation.restype = wintypes.BOOL
    advapi.GetSidSubAuthorityCount.argtypes = [ctypes.c_void_p]
    advapi.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
    advapi.GetSidSubAuthority.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    advapi.GetSidSubAuthority.restype = ctypes.POINTER(wintypes.DWORD)
    advapi.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    advapi.ConvertSidToStringSidW.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    token = wintypes.HANDLE()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
        raise ScopeError("Cannot inspect process token")
    try:
        def token_info(kind):
            needed = wintypes.DWORD()
            advapi.GetTokenInformation(token, kind, None, 0, ctypes.byref(needed))
            if not 0 < needed.value <= 65536:
                raise ScopeError("Invalid process token information size")
            buffer = ctypes.create_string_buffer(needed.value)
            if not advapi.GetTokenInformation(token, kind, buffer, needed.value, ctypes.byref(needed)):
                raise ScopeError("Cannot read process token information")
            return buffer

        integrity = token_info(25)  # TOKEN_MANDATORY_LABEL starts with SID_AND_ATTRIBUTES.
        sid = ctypes.cast(integrity, ctypes.POINTER(ctypes.c_void_p))[0]
        count_pointer = advapi.GetSidSubAuthorityCount(sid)
        if not count_pointer or count_pointer[0] == 0:
            raise ScopeError("Invalid token integrity SID")
        level = advapi.GetSidSubAuthority(sid, count_pointer[0] - 1)[0]
        if level < 0x2000:  # SECURITY_MANDATORY_MEDIUM_RID; reject low/untrusted.
            raise ScopeError("Low-integrity or untrusted process refused")
        user = token_info(1)  # TOKEN_USER starts with SID_AND_ATTRIBUTES.
        user_sid = ctypes.cast(user, ctypes.POINTER(ctypes.c_void_p))[0]
        text = ctypes.c_void_p()
        if not advapi.ConvertSidToStringSidW(user_sid, ctypes.byref(text)):
            raise ScopeError("Cannot identify token owner")
        try:
            return {"user_sid": ctypes.wstring_at(text), "integrity_rid": int(level)}
        finally:
            kernel.LocalFree(text)
    finally:
        kernel.CloseHandle(token)


def _lstat_plain(path: Path, expected_kind: str | None = None):
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & REPARSE_ATTRIBUTE:
        raise ScopeError(f"Reparse point or link refused: {path}")
    kind = "directory" if stat.S_ISDIR(info.st_mode) else "file" if stat.S_ISREG(info.st_mode) else "other"
    if kind == "other" or (expected_kind and kind != expected_kind):
        raise ScopeError(f"Unexpected filesystem object: {path}")
    if kind == "file" and info.st_nlink != 1:
        raise ScopeError(f"Hard-linked file refused: {path}")
    return info


def _identity(info) -> dict:
    if info.st_ino <= 0:
        raise ScopeError("Filesystem does not expose a usable object identity")
    return {"device": int(info.st_dev), "inode": int(info.st_ino)}


def _plain_ancestors(path: Path) -> None:
    # lstat every existing component, including the volume root, without resolve().
    for current in reversed((path, *path.parents)):
        try:
            info = _lstat_plain(current)
        except FileNotFoundError:
            continue
        if current != path and not stat.S_ISDIR(info.st_mode):
            raise ScopeError("Non-directory path ancestor refused")


def _exists(path: Path) -> bool:
    try:
        path.lstat()
        return True
    except FileNotFoundError:
        return False


def _runtime_context() -> dict:
    if (os.name != "nt" or os.environ.get("CI") != "true"
            or os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"):
        raise ScopeError("Only disposable Windows x64 GitHub-hosted CI is permitted")
    identity = _windows_identity()
    run = {key: os.environ.get(key, "") for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_JOB")}
    if (not run["GITHUB_RUN_ID"].isdigit() or not run["GITHUB_RUN_ATTEMPT"].isdigit()
            or not run["GITHUB_JOB"] or len(run["GITHUB_JOB"]) > 256):
        raise ScopeError("GitHub job identity required")
    temporary = Path(windows_path(os.environ.get("RUNNER_TEMP", "")))
    _plain_ancestors(temporary)
    _lstat_plain(temporary, "directory")
    known = _known_folder_paths()
    for value in known.values():
        path = Path(value)
        _plain_ancestors(path)
        _lstat_plain(path, "directory")
    layout = layout_for_known_folders(known)
    for key in ROOT_KEYS:
        root = PureWindowsPath(layout[key])
        temp = PureWindowsPath(str(temporary))
        if root == temp or root in temp.parents or temp in root.parents:
            raise ScopeError("RUNNER_TEMP and owned profile roots must be disjoint")
    contract = Path(__file__).with_name("profile-source-contract.json")
    if _sha(_read_regular(contract, MAX_RECORD_BYTES)) != CONTRACT_SHA256:
        raise ScopeError("Pinned profile source contract differs")
    return {"identity": {**identity, **run}, "temporary": str(temporary),
            "known_folders": known, "layout": layout}


def _record_path(path: Path, context: dict, *, must_exist: bool) -> Path:
    path = Path(windows_path(str(path)))
    temporary = PureWindowsPath(context["temporary"])
    if temporary not in PureWindowsPath(str(path)).parents or path.suffix.lower() != ".json":
        raise ScopeError("Record must be a JSON file strictly below RUNNER_TEMP")
    _plain_ancestors(path)
    _lstat_plain(path.parent, "directory")
    if must_exist:
        _lstat_plain(path, "file")
    elif _exists(path):
        raise ScopeError("New record required; existing records are never overwritten by prepare")
    return path


def _read_regular(path: Path, limit: int) -> bytes:
    _plain_ancestors(path)
    before = _lstat_plain(path, "file")
    if before.st_size > limit:
        raise ScopeError(f"File exceeds its bounded read: {path}")
    with path.open("rb") as stream:
        if _identity(os.fstat(stream.fileno())) != _identity(before):
            raise ScopeError("File was substituted before read")
        data = stream.read(limit + 1)
    after = _lstat_plain(path, "file")
    if (len(data) > limit or _identity(after) != _identity(before)
            or before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns):
        raise ScopeError("File changed during bounded read")
    return data


def _write_record(path: Path, record: dict, *, new=False) -> None:
    _plain_ancestors(path)
    if new:
        with path.open("xb") as stream:
            stream.write(_json_bytes(record))
            stream.flush()
            os.fsync(stream.fileno())
        return
    _lstat_plain(path, "file")
    temporary = path.with_name(path.name + ".pending-" + secrets.token_hex(16))
    created = False
    try:
        with temporary.open("xb") as stream:
            created = True
            stream.write(_json_bytes(record))
            stream.flush()
            os.fsync(stream.fileno())
        _plain_ancestors(path)
        _lstat_plain(path, "file")
        os.replace(temporary, path)
    finally:
        if created and _exists(temporary):
            _lstat_plain(temporary, "file")
            temporary.unlink()


def _marker_bytes(record: dict, key: str, spec: dict) -> bytes:
    return _json_bytes({"schema_version": SCHEMA, "kind": KIND, "owner": record["owner"],
                        "root_key": key, "root_path": record[key], "root_identity": spec["identity"],
                        "record_path": record["record_path"], "nonce": spec["nonce"]})


def _valid_identity(value) -> bool:
    return (isinstance(value, dict) and set(value) == {"device", "inode"}
            and all(type(value[key]) is int and value[key] >= (1 if key == "inode" else 0)
                    for key in value))


def validate_record_manifest(record: dict, expected_context: dict, record_path: str) -> None:
    """Pure manifest checks; expected_context must come from fresh runtime APIs."""
    expected_keys = {"schema_version", "kind", "source_commit", "source_contract_sha256", "owner",
                     "status", "record_path", "runtime_identity", "known_folders", "runner_temp",
                     "roots_initially_absent", "seed_settings_sha256", "root_markers", "error", *LAYOUT_KEYS}
    if (set(record) != expected_keys or type(record["schema_version"]) is not int
            or record["schema_version"] != SCHEMA or record["kind"] != KIND):
        raise ScopeError("Unexpected profile record schema")
    try:
        if str(uuid.UUID(record["owner"])) != record["owner"]:
            raise ValueError("owner")
    except (ValueError, TypeError, AttributeError) as exc:
        raise ScopeError("Invalid profile owner") from exc
    if (record["source_commit"] != SOURCE_COMMIT or record["source_contract_sha256"] != CONTRACT_SHA256
            or record["roots_initially_absent"] is not True or record["record_path"] != record_path
            or record["runner_temp"] != expected_context["temporary"]
            or record["runtime_identity"] != expected_context["identity"]
            or record["known_folders"] != expected_context["known_folders"]
            or record["seed_settings_sha256"] != _sha(SEED_SETTINGS)
            or record["status"] not in ("preparing", "prepare-failed", "prepared", "cleaning", "cleanup-failed", "cleaned")):
        raise ScopeError("Profile record context or provenance differs")
    if any(record[key] != expected_context["layout"][key] for key in LAYOUT_KEYS):
        raise ScopeError("Record paths do not match the current KnownFolders")
    markers = record["root_markers"]
    if not isinstance(markers, dict) or not set(markers).issubset(ROOT_KEYS):
        raise ScopeError("Unexpected owned root list")
    if record["status"] == "prepared" and set(markers) != set(ROOT_KEYS):
        raise ScopeError("Prepared record lacks an owned root")
    for key, spec in markers.items():
        if (not isinstance(spec, dict)
                or set(spec) != {"identity", "nonce", "marker_identity", "marker_sha256", "state"}
                or not _valid_identity(spec["identity"]) or not _valid_identity(spec["marker_identity"])
                or not isinstance(spec["nonce"], str) or not re.fullmatch("[a-f0-9]{64}", spec["nonce"])
                or spec["state"] not in ("present", "removed")
                or spec["marker_sha256"] != _sha(_marker_bytes(record, key, spec))):
            raise ScopeError("Invalid owned marker manifest")
        if record["status"] == "prepared" and spec["state"] != "present":
            raise ScopeError("Prepared record has a removed root")
    if record["status"] == "cleaned" and any(spec["state"] != "removed" for spec in markers.values()):
        raise ScopeError("Cleaned record retains owned roots")


def _assert_fallbacks_absent(context: dict) -> None:
    for name in fallback_settings_paths(context["known_folders"]):
        path = Path(name)
        _plain_ancestors(path)
        if _exists(path):
            raise ScopeError(f"Preexisting fallback QSettings file refused: {path}")


@contextmanager
def _hold_root(path: Path):
    """Deny root rename/deletion while inspecting or deleting its descendants."""
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                   ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    # FILE_READ_ATTRIBUTES; SHARE_READ|SHARE_WRITE, deliberately no SHARE_DELETE.
    handle = kernel.CreateFileW(str(path), 0x80, 0x3, None, 3, 0x02200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ScopeError(f"Cannot hold owned directory against replacement: {path}")
    try:
        _lstat_plain(path, "directory")
        yield
    finally:
        kernel.CloseHandle(handle)


def _assert_marker(record: dict, key: str) -> None:
    root = Path(record[key])
    spec = record["root_markers"][key]
    _plain_ancestors(root)
    if _identity(_lstat_plain(root, "directory")) != spec["identity"]:
        raise ScopeError("Owned root identity changed")
    marker = root / MARKER_NAME
    info = _lstat_plain(marker, "file")
    if (not getattr(info, "st_file_attributes", 0) & READONLY_ATTRIBUTE
            or _identity(info) != spec["marker_identity"]
            or _read_regular(marker, 4096) != _marker_bytes(record, key, spec)):
        raise ScopeError("Owned root marker changed or lost its read-only attribute")


def scan_plain_tree(root: Path) -> list[tuple[Path, dict, str]]:
    """Bounded lstat-only walk. Portable fixtures test this without Windows claims."""
    result = []
    total = 0
    pending = [(root, 0)]
    seen = set()
    while pending:
        directory, depth = pending.pop()
        _lstat_plain(directory, "directory")
        if depth > MAX_TREE_DEPTH:
            raise ScopeError("Owned profile exceeds maximum depth")
        with os.scandir(directory) as iterator:
            for entry in iterator:
                path = Path(entry.path)
                if os.name == "nt":
                    windows_path(str(path))
                folded = str(path).casefold()
                if folded in seen:
                    raise ScopeError("Ambiguous case-folded profile path")
                seen.add(folded)
                info = _lstat_plain(path)
                if len(result) >= MAX_TREE_ENTRIES:
                    raise ScopeError("Owned profile exceeds maximum entry count")
                kind = "directory" if stat.S_ISDIR(info.st_mode) else "file"
                if kind == "directory":
                    pending.append((path, depth + 1))
                else:
                    if info.st_size > MAX_FILE_BYTES:
                        raise ScopeError("Owned profile has an oversized file")
                    total += info.st_size
                    if total > MAX_TREE_BYTES:
                        raise ScopeError("Owned profile exceeds maximum total bytes")
                result.append((path, _identity(info), kind))
    return result


def _load_record(record_path: Path) -> tuple[Path, dict, dict]:
    context = _runtime_context()
    path = _record_path(record_path, context, must_exist=True)
    record = _decode_json(_read_regular(path, MAX_RECORD_BYTES))
    validate_record_manifest(record, context, str(path))
    return path, record, context


def prepare_record(record_path: Path) -> dict:
    context = _runtime_context()
    path = _record_path(record_path, context, must_exist=False)
    _assert_fallbacks_absent(context)
    for key in ROOT_KEYS:
        root = Path(context["layout"][key])
        _plain_ancestors(root)
        if _exists(root):
            raise ScopeError(f"Existing Cadence profile is never modified: {root}")
    record = {"schema_version": SCHEMA, "kind": KIND, "source_commit": SOURCE_COMMIT,
              "source_contract_sha256": CONTRACT_SHA256, "owner": str(uuid.uuid4()),
              "status": "preparing", "record_path": str(path), "runtime_identity": context["identity"],
              "known_folders": context["known_folders"], "runner_temp": context["temporary"],
              "roots_initially_absent": True, "seed_settings_sha256": _sha(SEED_SETTINGS),
              "root_markers": {}, "error": None, **context["layout"]}
    _write_record(path, record, new=True)
    try:
        for key in ROOT_KEYS:
            root = Path(record[key])
            _plain_ancestors(root)
            root.mkdir()  # Atomic absence check; no exist_ok and no parent creation.
            root_identity = _identity(_lstat_plain(root, "directory"))
            spec = {"identity": root_identity, "nonce": secrets.token_hex(32),
                    "marker_identity": {}, "marker_sha256": "", "state": "present"}
            marker = root / MARKER_NAME
            try:
                with marker.open("xb") as stream:
                    stream.write(_marker_bytes(record, key, spec))
                    stream.flush()
                    os.fsync(stream.fileno())
                os.chmod(marker, stat.S_IREAD)
                spec["marker_identity"] = _identity(_lstat_plain(marker, "file"))
                spec["marker_sha256"] = _sha(_marker_bytes(record, key, spec))
                record["root_markers"][key] = spec
                _write_record(path, record)
            except BaseException:
                # An unmarked/nonempty root is deliberately left for inspection.
                if (_identity(_lstat_plain(root, "directory")) == root_identity
                        and not any(root.iterdir())):
                    root.rmdir()
                raise
        with ExitStack() as stack:
            for key in ROOT_KEYS:
                stack.enter_context(_hold_root(Path(record[key])))
                _assert_marker(record, key)
            Path(record["local_app_root"]).mkdir()
            Path(record["log_root"]).mkdir()
            Path(record["extension_root"]).mkdir()
            with Path(record["settings_file"]).open("xb") as stream:
                stream.write(SEED_SETTINGS)
                stream.flush()
                os.fsync(stream.fileno())
            _assert_fallbacks_absent(context)
            for key in ROOT_KEYS:
                _assert_marker(record, key)
                scan_plain_tree(Path(record[key]))
            validate_audio_settings(_read_regular(Path(record["settings_file"]), MAX_SETTINGS_BYTES))
        record["status"] = "prepared"
        _write_record(path, record)
        return record
    except BaseException as exc:
        record["status"] = "prepare-failed"
        record["error"] = type(exc).__name__ + ": " + str(exc)
        _write_record(path, record)
        raise


def verify_record(record_path: Path) -> dict:
    """Public runner API: fresh KnownFolders/identity, markers and exact ASIO INI."""
    _, record, context = _load_record(record_path)
    if record["status"] != "prepared":
        raise ScopeError("Only a prepared profile may be used by the GUI runner")
    _assert_fallbacks_absent(context)
    with ExitStack() as stack:
        for key in ROOT_KEYS:
            stack.enter_context(_hold_root(Path(record[key])))
            _assert_marker(record, key)
            scan_plain_tree(Path(record[key]))
        settings = _read_regular(Path(record["settings_file"]), MAX_SETTINGS_BYTES)
        validate_audio_settings(settings)
    return {**record, "verification": {"required_audio_settings": True,
                                      "current_settings_sha256": _sha(settings)}}


def cleanup_record(record_path: Path) -> dict:
    """Caller must already have drained its owned Cadence process tree."""
    path, record, _ = _load_record(record_path)
    # Validate every remaining root before deleting the first descendant.
    trees = {}
    with ExitStack() as stack:
        for key in ROOT_KEYS:
            root = Path(record[key])
            spec = record["root_markers"].get(key)
            if spec is None or spec["state"] == "removed":
                if _exists(root):
                    raise ScopeError("Unowned or previously removed root now exists; cleanup refused")
                continue
            if not _exists(root):
                # Safe recovery after deletion completed but record update was interrupted.
                spec["state"] = "removed"
                continue
            stack.enter_context(_hold_root(root))
            _assert_marker(record, key)
            trees[key] = scan_plain_tree(root)
        try:
            record["status"] = "cleaning"
            record["error"] = None
            _write_record(path, record)
            for key, tree in trees.items():
                root = Path(record[key])
                marker = root / MARKER_NAME
                _assert_marker(record, key)
                for node, expected, kind in sorted(tree, key=lambda row: len(row[0].parts), reverse=True):
                    if node == marker:
                        continue
                    _plain_ancestors(node)
                    if _identity(_lstat_plain(node, kind)) != expected:
                        raise ScopeError("Profile entry changed before deletion")
                    if kind == "directory":
                        node.rmdir()
                    else:
                        os.chmod(node, stat.S_IREAD | stat.S_IWRITE)
                        node.unlink()
                _assert_marker(record, key)
                if [entry.name for entry in root.iterdir()] != [MARKER_NAME]:
                    raise ScopeError("Unexpected entry appeared before final root removal")
        except BaseException as exc:
            record["status"] = "cleanup-failed"
            record["error"] = type(exc).__name__ + ": " + str(exc)
            _write_record(path, record)
            raise
    # Root locks must close before rmdir. Recheck identities/markers immediately.
    try:
        for key in trees:
            root = Path(record[key])
            _assert_marker(record, key)
            if [entry.name for entry in root.iterdir()] != [MARKER_NAME]:
                raise ScopeError("Unexpected entry appeared before final marker removal")
            marker = root / MARKER_NAME
            os.chmod(marker, stat.S_IREAD | stat.S_IWRITE)
            marker.unlink()
            if _identity(_lstat_plain(root, "directory")) != record["root_markers"][key]["identity"]:
                raise ScopeError("Owned root changed before rmdir")
            root.rmdir()
            record["root_markers"][key]["state"] = "removed"
            _write_record(path, record)
        for key in ROOT_KEYS:
            if _exists(Path(record[key])):
                raise ScopeError("An owned profile root remains after cleanup")
        record["status"] = "cleaned"
        record["error"] = None
        _write_record(path, record)
        return record
    except BaseException as exc:
        record["status"] = "cleanup-failed"
        record["error"] = type(exc).__name__ + ": " + str(exc)
        _write_record(path, record)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "verify", "cleanup"))
    parser.add_argument("--record", type=Path, required=True)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    action = {"prepare": prepare_record, "verify": verify_record, "cleanup": cleanup_record}[args.command]
    try:
        result = action(args.record)
    except (ScopeError, OSError, ValueError) as exc:
        print(f"Cadence profile scope refused: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
