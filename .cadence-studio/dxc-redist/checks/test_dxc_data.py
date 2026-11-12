# SPDX-License-Identifier: GPL-3.0-only
"""Synthetic data-only ZIP/PE-header/XML checks, not Windows qualification."""
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile

HERE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("cadence_dxc_data_fixture", HERE / "collect_dxc.py")
collector = importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(collector)


def synthetic_pe(machine=0x8664):
    raw = bytearray(256);raw[:2] = b"MZ";struct.pack_into("<I", raw, 60, 64)
    raw[64:68] = b"PE\0\0";struct.pack_into("<H", raw, 68, machine)
    struct.pack_into("<H", raw, 86, 0x2000);struct.pack_into("<H", raw, 88, 0x20b)
    return bytes(raw)  # Header fixture only: never an executable or loaded DLL.


def memory_zip(rows):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, raw in rows: archive.writestr(name, raw)
    output.seek(0);return output


class DxcDataChecks(unittest.TestCase):
    def test_only_two_x64_dll_data_and_original_legal_texts_selected(self):
        rows = [("bin/x64/dxcompiler.dll", synthetic_pe()), ("bin/x64/dxil.dll", synthetic_pe()),
                ("bin/x64/dxc.exe", b"EXCLUDED DATA"), ("bin/x86/dxcompiler.dll", b"EXCLUDED DATA"),
                ("bin/arm64/dxc.exe", b"EXCLUDED DATA"), ("LICENSE-LLVM.txt", b"SYNTHETIC LLVM notice"),
                ("LICENSE-MIT.txt", b"SYNTHETIC header notice"), ("ReleaseNotes.md", b"SYNTHETIC release notes")]
        with tempfile.TemporaryDirectory(prefix="synthetic-dxc-data-") as name:
            output = Path(name)
            result = collector.extract_selected(memory_zip(rows), output)
            self.assertEqual(len(result["selected"]), 5)
            self.assertEqual(result["missing_expected_package_texts"], [])
            self.assertTrue(result["package_ReleaseNotes_present"])
            self.assertFalse(any(path.suffix == ".exe" for path in output.rglob("*")))
            self.assertFalse((output / "bin/x86").exists())
            self.assertEqual((output / "bin/x64/dxil.dll").read_bytes(), synthetic_pe())

    def test_zip_paths_case_aliases_links_and_collisions_refused(self):
        for bad in ("../escape", "/absolute", ".", "dir\\file", "dir/../file", "dir//file", "C:stream",
                    "dir/NUL.txt", "dir/COM¹.txt", "dir/CONIN$.txt", "dir/NUL .txt", "dir/trailing.", "dir/trailing "):
            with self.subTest(name=bad), zipfile.ZipFile(memory_zip([(bad, b"x")])) as archive:
                with self.assertRaises(ValueError): collector.zip_inventory(archive)
        for rows in ([("case", b"x"), ("CASE", b"y")], [("parent", b"x"), ("parent/child", b"y")]):
            with zipfile.ZipFile(memory_zip(rows)) as archive, self.assertRaises(ValueError): collector.zip_inventory(archive)
        for attributes in ((stat.S_IFLNK | 0o777) << 16, 0x400, (stat.S_IFIFO | 0o600) << 16):
            info = zipfile.ZipInfo("link");info.external_attr = attributes
            with self.assertRaises(ValueError): collector.safe_member(info)

    def test_zip_size_count_and_architecture_bounds(self):
        with zipfile.ZipFile(memory_zip([("one", b"xx"), ("two", b"xx")])) as archive:
            for kwargs in ({"maximum_entries": 1}, {"maximum_file": 1}, {"maximum_total": 3}):
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError): collector.zip_inventory(archive, **kwargs)
        with self.assertRaises(ValueError): collector.pe_x64_dll(synthetic_pe(0x14c))
        with self.assertRaises(ValueError): collector.pe_x64_dll(b"MZ")
        with tempfile.TemporaryDirectory(prefix="synthetic-dxc-missing-") as name, self.assertRaises(ValueError):
            collector.extract_selected(memory_zip([("bin/x64/dxc.exe", b"not selected")]), Path(name))

    def test_docx_xml_is_data_and_doctype_or_traversal_refused(self):
        xml = b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>SYNTHETIC legal text</w:t></w:r></w:p></w:body></w:document>'
        self.assertEqual(collector.docx_text(memory_zip([("word/document.xml", xml)]).getvalue()), "SYNTHETIC legal text")
        with self.assertRaises(ValueError): collector.docx_text(memory_zip([("word/document.xml", b'<!DOCTYPE x>'+xml)]).getvalue())
        with self.assertRaises(ValueError): collector.docx_text(memory_zip([("../escape", b"x"), ("word/document.xml", xml)]).getvalue())

    def test_redirect_host_boundaries(self):
        collector.safe_url("https://download.microsoft.com/original", collector.MICROSOFT_HOSTS)
        collector.safe_url("https://msdn.microsoft.com/original", collector.MICROSOFT_HOSTS)
        collector.safe_url("https://download.visualstudio.microsoft.com/original", collector.MICROSOFT_HOSTS)
        for url in ("http://download.microsoft.com/file", "https://example.org/file", "https://download.microsoft.com.evil.invalid/file", "https://user:password@download.microsoft.com/file"):
            with self.subTest(url=url), self.assertRaises(ValueError): collector.safe_url(url, collector.MICROSOFT_HOSTS)
        redirect = collector.OfficialRedirect(collector.MICROSOFT_HOSTS)
        with self.assertRaisesRegex(ValueError, r'https://example.org/file$'):
            redirect.redirect_request(None, None, 302, "redirect", {}, "https://example.org/file?private=must-not-print")

    def test_console_budget_marks_omitted_originals_without_truncation(self):
        with tempfile.TemporaryDirectory(prefix="synthetic-dxc-console-") as name:
            root = Path(name);data = b"x" * 200000
            paths = ["a.txt", "b.txt", "c.txt"]
            for path in paths: (root / path).write_bytes(data)
            report = {"package": {"selected": [{"kind": "original-package-legal-text", "zip_path": p,
                        "retained_path": p, "bytes": len(data), "sha256": collector.digest(data)} for p in paths]},
                      "optional_microsoft_documents": []}
            raw = collector.fit_console(report, root)
            self.assertLessEqual(len(raw) + len(collector.BEGIN) + len(collector.END) + 4, collector.MAX_CONSOLE)
            rows = json.loads(raw)["console_originals"]
            self.assertTrue(any(row["printed"] for row in rows))
            self.assertTrue(any(not row["printed"] and "reason" in row for row in rows))

    def test_real_download_entrypoint_refuses_local_environment(self):
        with tempfile.TemporaryDirectory(prefix="synthetic-dxc-refusal-") as name:
            target = Path(name) / "untouched"
            with patch.dict(os.environ, {}, clear=True), patch.object(collector, "fetch", side_effect=AssertionError("network must not occur")):
                with self.assertRaises(ValueError): collector.main(["--output", str(target)])
            self.assertFalse(target.exists())


if __name__ == "__main__": unittest.main()
