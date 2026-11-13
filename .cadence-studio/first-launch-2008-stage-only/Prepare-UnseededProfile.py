#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Prepare the known owned profile, verify its seed, then remove only that INI.

No application, registry, bank, plugin or source tree is touched by this helper.
Windows execution remains pending. Importing this file performs no profile work.
"""
from contextlib import ExitStack
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
SOURCE = 'a2b7abaf045a8f3cb84ec2953d9e0e51b9e78903'


def native_file_id(handle):
    import ctypes
    from ctypes import wintypes
    class FileIdInfo(ctypes.Structure):
        _fields_ = [('volume', ctypes.c_ulonglong), ('identifier', ctypes.c_ubyte * 16)]
    api = ctypes.WinDLL('kernel32', use_last_error=True).GetFileInformationByHandleEx
    api.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    api.restype = wintypes.BOOL
    result = FileIdInfo()
    if not api(handle, 18, ctypes.byref(result), ctypes.sizeof(result)) or not any(result.identifier):
        raise RuntimeError('Native seed FileIdInfo could not be established')
    return {'volume_serial': int(result.volume), 'file_id_128_hex': bytes(result.identifier).hex()}


def delete_exact_seed_by_handle(settings, expected_data, expected_native_id):
    import ctypes
    from ctypes import wintypes
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                               wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    api.CreateFileW.restype = wintypes.HANDLE
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    api.ReadFile.restype = wintypes.BOOL
    api.GetFileSizeEx.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_longlong)]
    api.GetFileSizeEx.restype = wintypes.BOOL
    api.GetFinalPathNameByHandleW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
    api.GetFinalPathNameByHandleW.restype = wintypes.DWORD
    api.SetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    api.SetFileInformationByHandle.restype = wintypes.BOOL
    # GENERIC_READ|DELETE, SHARE_READ only, OPEN_EXISTING, OPEN_REPARSE_POINT.
    # The captured128-bit FileId and final path must match before marking this handle for deletion.
    handle = api.CreateFileW(str(settings), 0x80010000, 1, None, 3, 0x00200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise RuntimeError('Exact seed could not be locked for read and deletion')
    try:
        if native_file_id(handle) != expected_native_id:
            raise RuntimeError('Native seed FileId changed before deletion')
        final = ctypes.create_unicode_buffer(32768)
        count = api.GetFinalPathNameByHandleW(handle, final, len(final), 0)
        value = final.value[4:] if final.value.startswith('\\\\?\\') else final.value
        if not count or count >= len(final) or value.casefold() != str(settings).casefold():
            raise RuntimeError('Seed handle points outside its exact derived INI path')
        size = ctypes.c_longlong()
        if not api.GetFileSizeEx(handle, ctypes.byref(size)) or size.value != len(expected_data):
            raise RuntimeError('Seed size changed before deletion')
        buffer = ctypes.create_string_buffer(len(expected_data)); read = wintypes.DWORD()
        if not api.ReadFile(handle, buffer, len(expected_data), ctypes.byref(read), None) or read.value != len(expected_data) or buffer.raw != expected_data:
            raise RuntimeError('Seed handle bytes differ from the helper-created seed')
        # FILE_DISPOSITION_INFO.DeleteFile is BOOLEAN (one byte), not BOOL.
        disposition = ctypes.c_ubyte(1)
        if native_file_id(handle) != expected_native_id or not api.SetFileInformationByHandle(handle, 4, ctypes.byref(disposition), ctypes.sizeof(disposition)):
            raise RuntimeError('Only the locked exact seed handle may be deleted')
    finally:
        api.CloseHandle(handle)


def load_scope():
    if os.name != 'nt':
        raise RuntimeError('Disposable hosted native Windows only; nothing prepared or deleted')
    manifest = json.loads((HERE / 'source-manifest.json').read_text())
    expected = next(row for row in manifest['files'] if row['path'] == 'runtime/CadenceProfileScope.py')
    path = HERE / expected['path']
    raw = path.read_bytes()
    if len(raw) != expected['bytes'] or hashlib.sha256(raw).hexdigest() != expected['sha256']:
        raise RuntimeError('Original profile helper bytes changed')
    spec = importlib.util.spec_from_file_location('cadence_original_first_launch_scope', path)
    scope = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = scope
    spec.loader.exec_module(scope)
    return scope


def validate_unseeded(scope, record_path, receipt_path):
    _, record, context = scope._load_record(record_path)
    receipt_path = scope._record_path(receipt_path, context, must_exist=True)
    receipt = scope._decode_json(scope._read_regular(receipt_path, scope.MAX_RECORD_BYTES))
    if (receipt.get('kind') != 'owned-first-launch-no-INI' or receipt.get('source_commit') != SOURCE
            or receipt.get('owner') != record['owner'] or receipt.get('record_path') != str(record_path)
            or receipt.get('settings_file') != record['settings_file']
            or receipt.get('seed_sha256') != record['seed_settings_sha256']
            or receipt.get('seed_removed') is not True or receipt.get('profile_record_kept_unchanged') is not True
            or receipt.get('root_markers') != record['root_markers']):
        raise RuntimeError('Unseeded first-launch receipt differs from the exact owned profile')
    with ExitStack() as stack:
        for key in scope.ROOT_KEYS:
            stack.enter_context(scope._hold_root(Path(record[key])))
            scope._assert_marker(record, key)
            for path, _, kind in scope.scan_plain_tree(Path(record[key])):
                if kind == 'file' and path.suffix.casefold() == '.ini':
                    raise RuntimeError('An INI appeared before first launch')
        scope._assert_fallbacks_absent(context)
        if scope._exists(Path(record['settings_file'])):
            raise RuntimeError('Seed settings still exist or were replaced')
    return receipt


def prepare_and_remove(scope, record_path, receipt_path):
    record = scope.prepare_record(record_path)
    # Capture native stat identity immediately after the original helper creates
    # the seed, before verification, and compare it again before the sole unlink.
    _, record, context = scope._load_record(record_path)
    receipt_path = scope._record_path(receipt_path, context, must_exist=False)
    settings = Path(record['settings_file'])
    import msvcrt
    with ExitStack() as stack:
        for key in scope.ROOT_KEYS:
            stack.enter_context(scope._hold_root(Path(record[key])))
            scope._assert_marker(record, key)
        identity = scope._identity(scope._lstat_plain(settings, 'file'))
        data = scope._read_regular(settings, scope.MAX_SETTINGS_BYTES)
        if data != scope.SEED_SETTINGS or scope._sha(data) != record['seed_settings_sha256']:
            raise RuntimeError('Only the exact helper-created seed may be removed')
        with settings.open('rb') as stream:
            if scope._identity(os.fstat(stream.fileno())) != identity or stream.read(len(data) + 1) != data:
                raise RuntimeError('Seed changed before native handle identity capture')
            native_identity = native_file_id(msvcrt.get_osfhandle(stream.fileno()))
    scope.verify_record(record_path)  # The original ASIO seed is verified BEFORE removal.
    with ExitStack() as stack:
        for key in scope.ROOT_KEYS:
            stack.enter_context(scope._hold_root(Path(record[key])))
            scope._assert_marker(record, key)
        if (scope._identity(scope._lstat_plain(settings, 'file')) != identity
                or scope._read_regular(settings, scope.MAX_SETTINGS_BYTES) != data):
            raise RuntimeError('Seed identity or bytes changed before removal')
        delete_exact_seed_by_handle(settings, data, native_identity)
        if scope._exists(settings):
            raise RuntimeError('Seed removal was not observed')
        for key in scope.ROOT_KEYS:
            scope._assert_marker(record, key)
    receipt = {'schema_version': 1, 'kind': 'owned-first-launch-no-INI', 'source_commit': SOURCE,
               'owner': record['owner'], 'record_path': str(record_path),
               'settings_file': record['settings_file'], 'seed_sha256': scope._sha(data),
               'seed_file_identity': identity,
               'seed_native_file_id': native_identity,
               'seed_file_identity_kind': 'Native Windows FileIdInfo128 and stat device/file ID; delete by the same locked handle',
               'identity_captured_after_prepare_before_verify': True, 'seed_removed': True,
               'root_markers': record['root_markers'], 'profile_record_kept_unchanged': True,
               'application_started': False, 'ASIO_seed_present_after_removal': False,
               'setup_user_choices_exercised': False, 'setup_completion_qualified': False,
               'completion_flag_after_close': 'not_observed_yet', 'zero_network_claimed': False}
    scope._write_record(receipt_path, receipt, new=True)
    return validate_unseeded(scope, record_path, receipt_path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('prepare-and-remove', 'verify-before-start'))
    parser.add_argument('--record', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    scope = load_scope()
    result = (prepare_and_remove(scope, args.record, args.receipt) if args.operation == 'prepare-and-remove'
              else validate_unseeded(scope, args.record, args.receipt))
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))


if __name__ == '__main__':
    main()
