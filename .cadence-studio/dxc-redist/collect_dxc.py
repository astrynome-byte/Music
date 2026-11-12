#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Collect one pinned official DXC package as DATA on hosted Ubuntu CI.

Only the x64 compiler/validator DLL pair and original package legal texts are
extracted. No DLL, compiler executable, application, Office or installer is run.
Two optional official Microsoft legal-document downloads are independent of the
required DXC archive. Their failure is explicit and never substitutes an older
DXC or a Windows-SDK license for CRT terms.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
from html.parser import HTMLParser
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

TAG = "v1.8.2505.1"
COMMIT = "b106a961d09221b3c5bdb37be45b679257da08b8"
ASSET_ID = 272848549
ARCHIVE_NAME = "dxc_2025_07_14.zip"
ARCHIVE_BYTES = 26505604
ARCHIVE_SHA = "9ad895a6b039e3a8f8c22a1009f866800b840a74b50db9218d13319e215ea8a4"
ARCHIVE_URL = "https://github.com/microsoft/DirectXShaderCompiler/releases/download/" + TAG + "/" + ARCHIVE_NAME
RELEASE_API = "https://api.github.com/repos/microsoft/DirectXShaderCompiler/releases/tags/" + TAG
REF_API = "https://api.github.com/repos/microsoft/DirectXShaderCompiler/git/ref/tags/" + TAG
TARGETS = {"bin/x64/dxcompiler.dll", "bin/x64/dxil.dll"}
MAX_CONSOLE = 512 * 1024
MAX_OPTIONAL = 1024 * 1024
GITHUB_HOSTS = {"github.com", "api.github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}
MICROSOFT_HOSTS = {"go.microsoft.com", "www.microsoft.com", "learn.microsoft.com", "docs.microsoft.com",
                   "download.microsoft.com", "visualstudio.microsoft.com", "msdn.microsoft.com",
                   "download.visualstudio.microsoft.com", "aka.ms"}
OPTIONAL = [
    ("SDK-REDIST-Link524842.original", "https://go.microsoft.com/fwlink/?LinkId=524842", "SDK referenced REDIST list; applicability still needs inspection"),
    ("Visual-C-Runtime-2015-2022-License-1.docx", "https://visualstudio.microsoft.com/wp-content/uploads/2021/09/Visual-C-Runtime-2015-2022-License-1.docx", "Original Visual C++ runtime terms, independent from SDK terms"),
]
BEGIN, END = "CADENCE_DXC_OFFICIAL_DATA_V1_BEGIN", "CADENCE_DXC_OFFICIAL_DATA_V1_END"


def digest(raw): return hashlib.sha256(raw).hexdigest()


def plain(path, kind=None):
    if not path.is_absolute() or ".." in path.parts: raise ValueError("Absolute plain path required")
    for item in (path, *path.parents):
        try: info = item.lstat()
        except FileNotFoundError: continue
        if stat.S_ISLNK(info.st_mode) or not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
            raise ValueError("Links/special paths refused")
        if stat.S_ISREG(info.st_mode) and info.st_nlink != 1: raise ValueError("Hard-linked source/output refused")
    if kind == "file" and not path.is_file(): raise ValueError("Ordinary file required")
    if kind == "directory" and not path.is_dir(): raise ValueError("Ordinary directory required")


def safe_member(info):
    raw = info.filename
    if getattr(info, "orig_filename", raw) != raw or not raw or len(raw) > 512:
        raise ValueError("Invalid ZIP name")
    name = raw[:-1] if info.is_dir() else raw
    path = PurePosixPath(name)
    if (path.is_absolute() or not path.parts or str(path) != name or any(c in name for c in '\\:*?"<>|')
            or any(ord(c) < 32 for c in name) or any(part in (".", "..") for part in path.parts)):
        raise ValueError("Unsafe ZIP path")
    for part in path.parts:
        if (part.endswith((".", " ")) or re.fullmatch(r"(?i)(con|prn|aux|nul|conin\$|conout\$|clock\$|com[0-9¹²³]|lpt[0-9¹²³])",
                                                       part.split(".", 1)[0].rstrip(" "))):
            raise ValueError("Ambiguous Windows ZIP component")
    mode = stat.S_IFMT(info.external_attr >> 16)
    expected = stat.S_IFDIR if info.is_dir() else stat.S_IFREG
    if mode not in (0, expected) or info.external_attr & 0x400 or info.flag_bits & 1:
        raise ValueError("Linked, special or encrypted ZIP entry refused")
    if info.file_size < 0 or (info.is_dir() and info.file_size): raise ValueError("Invalid ZIP entry size")
    return name


def zip_inventory(archive, *, maximum_entries=4096, maximum_file=128 * 1024**2, maximum_total=1024**3):
    rows = archive.infolist()
    if len(rows) > maximum_entries: raise ValueError("ZIP entry count bound exceeded")
    result = [];seen = {};total = 0
    for info in rows:
        name = safe_member(info);folded = name.casefold()
        if folded in seen or info.file_size > maximum_file: raise ValueError("Duplicate/case-colliding or oversized ZIP entry")
        total += info.file_size
        if total > maximum_total: raise ValueError("ZIP expanded byte bound exceeded")
        seen[folded] = info.is_dir()
        result.append((name, info))
    for name, _ in result:
        if any(seen.get(str(parent).casefold()) is False for parent in PurePosixPath(name).parents if str(parent) != "."):
            raise ValueError("ZIP file/directory collision")
    return result


def read_member(archive, info, limit):
    if info.file_size > limit: raise ValueError("Selected ZIP file exceeds its bound")
    with archive.open(info) as stream: raw = stream.read(limit + 1)
    if len(raw) != info.file_size or len(raw) > limit: raise ValueError("Selected ZIP stream differs from bounded directory")
    return raw  # ZipFile verifies the original CRC while reading to EOF.


def pe_x64_dll(raw):
    if len(raw) < 128 or raw[:2] != b"MZ": raise ValueError("Selected DLL lacks a bounded DOS header")
    offset = struct.unpack_from("<I", raw, 60)[0]
    if offset < 64 or offset + 26 > len(raw) or raw[offset:offset + 4] != b"PE\0\0":
        raise ValueError("Selected DLL lacks a bounded PE header")
    machine = struct.unpack_from("<H", raw, offset + 4)[0]
    characteristics = struct.unpack_from("<H", raw, offset + 22)[0]
    magic = struct.unpack_from("<H", raw, offset + 24)[0]
    if machine != 0x8664 or magic != 0x20b or not characteristics & 0x2000:
        raise ValueError("Selected file is not an AMD64 PE32+ DLL")
    return {"machine": "AMD64", "PE32_plus": True, "DLL_characteristic": True,
            "header_inspected_as_data_only": True, "DLL_loaded": False}


def legal_name(name):
    base = PurePosixPath(name).name.casefold()
    return ((base.startswith("license") and ("." not in base or base.endswith((".txt", ".md", ".rtf"))))
            or base.startswith("releasenotes") and base.endswith((".txt", ".md", ".rtf")))


def extract_selected(archive_path, output):
    selected = [];inventory = [];found = set();legal_count = legal_bytes = 0
    with zipfile.ZipFile(archive_path) as archive:
        rows = zip_inventory(archive)
        for name, info in rows:
            folded = name.casefold()
            chosen = not info.is_dir() and (folded in TARGETS or legal_name(name))
            inventory.append({"path": name, "directory": info.is_dir(), "bytes": info.file_size,
                              "compressed_bytes": info.compress_size, "crc32": "%08x" % info.CRC,
                              "selected": chosen, "sha256": None})
            if not chosen: continue
            dll = folded in TARGETS
            if not dll:
                legal_count += 1;legal_bytes += info.file_size
                if legal_count > 32 or legal_bytes > 4 * 1024**2: raise ValueError("Package legal text bounds exceeded")
            raw = read_member(archive, info, 64 * 1024**2 if dll else 512 * 1024)
            relative = folded if dll else "original-package-texts/" + name
            target = output.joinpath(*PurePosixPath(relative).parts);target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream: stream.write(raw)
            row = {"zip_path": name, "retained_path": relative, "bytes": len(raw), "sha256": digest(raw),
                   "kind": "x64-DLL-data" if dll else "original-package-legal-text", "original_bytes_retained": True}
            if dll: row["PE_header"] = pe_x64_dll(raw);found.add(folded)
            selected.append(row);inventory[-1]["sha256"] = row["sha256"]
    if found != TARGETS: raise ValueError("The exact x64 compiler/validator pair is absent from this package")
    names = {PurePosixPath(row["zip_path"]).name.casefold() for row in selected if row["kind"] != "x64-DLL-data"}
    return {"inventory": inventory, "selected": selected, "missing_expected_package_texts": sorted({"license-llvm.txt", "license-mit.txt"} - names),
            "package_ReleaseNotes_present": any(name.startswith("releasenotes") for name in names),
            "unselected_members_not_extracted_or_executed": True}


def safe_url(url, allowed):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in allowed or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("Redirect leaves the explicit official HTTPS host set")


def public_url(url):
    parsed = urllib.parse.urlsplit(url)
    host = parsed.hostname or ""
    try:
        if parsed.port not in (None, 443): host += ":" + str(parsed.port)
    except ValueError:
        host += ":invalid-port"
    return urllib.parse.urlunsplit((parsed.scheme, host, parsed.path, "", ""))


class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed): self.allowed = allowed;self.chain = []
    def redirect_request(self, request, response, code, message, headers, newurl):
        try: safe_url(newurl, self.allowed)
        except ValueError as error:
            raise ValueError("Official redirect refused: " + public_url(newurl)) from error
        self.chain.append(public_url(newurl))
        return super().redirect_request(request, response, code, message, headers, newurl)


def fetch(url, limit, allowed):
    safe_url(url, allowed);redirect = OfficialRedirect(allowed)
    opener = urllib.request.build_opener(redirect)
    request = urllib.request.Request(url, headers={"User-Agent": "Cadence-official-redist-data-collector/1"})
    with opener.open(request, timeout=60) as response:
        safe_url(response.url, allowed)
        raw = response.read(limit + 1)
        if response.status != 200 or len(raw) > limit: raise ValueError("Official response is failed/oversized")
        return raw, {"requested_url": url, "final_url_without_query": public_url(response.url),
                     "redirects_without_queries": redirect.chain, "content_type": response.headers.get("Content-Type"),
                     "bytes": len(raw), "sha256": digest(raw)}


def docx_text(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        rows = zip_inventory(archive, maximum_entries=256, maximum_file=2 * 1024**2, maximum_total=8 * 1024**2)
        match = [info for name, info in rows if name == "word/document.xml"]
        if len(match) != 1: raise ValueError("DOCX lacks exactly one main XML document")
        xml = read_member(archive, match[0], 2 * 1024**2)
        if re.search(br"<!DOCTYPE|<!ENTITY", xml, re.I): raise ValueError("DTD/entity declarations in optional document refused")
        document = ET.fromstring(xml)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        text = "\n".join("".join(node.itertext()) for paragraph in document.findall(".//w:p", ns)
                         for node in [paragraph] if node is not None)
        if len(text.encode()) > 256 * 1024: raise ValueError("DOCX text view exceeds bound")
        return text


class HtmlText(HTMLParser):
    def __init__(self): super().__init__(convert_charrefs=True);self.parts = [];self.hidden = 0
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"): self.hidden += 1
        if tag in ("p", "li", "br", "tr", "h1", "h2", "h3"): self.parts.append("\n")
    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.hidden: self.hidden -= 1
    def handle_data(self, data):
        if not self.hidden: self.parts.append(data)


def optional_documents(output):
    rows = []
    for filename, url, purpose in OPTIONAL:
        row = {"file": "optional-microsoft/" + filename, "requested_url": url, "purpose": purpose,
               "status": "failed-optional", "required_for_DXC_archive_collection": False}
        try:
            raw, receipt = fetch(url, MAX_OPTIONAL, MICROSOFT_HOSTS);row.update(receipt)
            path = output / row["file"];path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream: stream.write(raw)
            row["status"] = "original-retained"
            try:
                if filename.endswith(".docx"): text = docx_text(raw)
                else:
                    text = raw.decode("utf-8-sig")
                    if "html" in (receipt["content_type"] or "").lower():
                        parser = HtmlText();parser.feed(text);text = "".join(parser.parts)
                if len(text.encode()) > 256 * 1024: raise ValueError("Optional text view exceeds bound")
                view = row["file"] + ".text-view.txt"
                (output / view).write_text(text, encoding="utf-8")
                row["text_view"] = view;row["text_view_sha256"] = digest(text.encode())
                row["text_view_bytes"] = len(text.encode())
                row["text_view_is_original_bytes"] = False
            except (ValueError, UnicodeError, ET.ParseError, zipfile.BadZipFile) as error:
                row["text_view_error"] = type(error).__name__ + ": " + str(error)[:300]
        except Exception as error:
            row["error"] = type(error).__name__ + ": " + str(error)[:300]
        rows.append(row)
    return rows


def fit_console(report, output):
    legal = [row for row in report.get("package", {}).get("selected", []) if row["kind"] == "original-package-legal-text"]
    legal.sort(key=lambda row: (PurePosixPath(row["zip_path"]).name.casefold() != "license-llvm.txt", row["zip_path"]))
    candidates = [(row["retained_path"], row["bytes"], row["sha256"]) for row in legal]
    candidates += [(row["file"], row["bytes"], row["sha256"]) for row in report.get("optional_microsoft_documents", []) if row["status"] == "original-retained"]
    report["console_originals"] = []
    for path, size, checksum in candidates:
        row = {"path": path, "bytes": size, "sha256": checksum, "printed": False}
        report["console_originals"].append(row)
        if size <= 256 * 1024:
            raw = (output / path).read_bytes()
            row.update(encoding="base64", data_base64=base64.b64encode(raw).decode("ascii"), printed=True)
            if len(json.dumps(report, ensure_ascii=True).encode()) + len(BEGIN) + len(END) + 4 <= MAX_CONSOLE - 4096:
                continue
            del row["encoding"];del row["data_base64"];row["printed"] = False
        row["reason"] = "Original retained in evidence artifact; per-file/global console budget"
    # Derived plain views are supplementary; original bytes and their identities
    # remain authoritative. Never execute Office or silently truncate a document.
    for row in report.get("optional_microsoft_documents", []):
        if "text_view" not in row: continue
        if row["text_view_bytes"] <= 64 * 1024:
            row["inspectable_text_view"] = (output / row["text_view"]).read_text(encoding="utf-8")
            if len(json.dumps(report, ensure_ascii=True).encode()) + len(BEGIN) + len(END) + 4 <= MAX_CONSOLE:
                continue
            del row["inspectable_text_view"]
        row["text_view_console_omitted"] = "Full derived view remains in artifact; per-file/global console budget"
    raw = json.dumps(report, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("ascii")
    if len(raw) + len(BEGIN) + len(END) + 4 > MAX_CONSOLE: raise ValueError("Even bounded evidence metadata exceeds console limit")
    return raw


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if (sys.platform != "linux" or os.environ.get("CI") != "true" or os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted" or os.environ.get("RUNNER_OS") != "Linux"):
        raise ValueError("Only hosted Ubuntu CI may fetch the real package; no local archive download")
    temporary = Path(os.environ["RUNNER_TEMP"]);plain(temporary, "directory");plain(args.output)
    if temporary not in args.output.parents or args.output.exists(): raise ValueError("New output strictly below RUNNER_TEMP required")
    plain(args.output.parent, "directory")
    args.output.mkdir()
    report = {"schema_version": 1, "status": "collecting", "tag": TAG, "commit": COMMIT, "asset_id": ASSET_ID,
              "archive_name": ARCHIVE_NAME, "expected_archive_bytes": ARCHIVE_BYTES, "expected_archive_sha256": ARCHIVE_SHA,
              "application_executed": False, "DLL_loaded": False, "dxc_exe_extracted_or_executed": False,
              "ARM_or_x86_executable_extracted": False, "stage_or_product_modified": False, "integration_qualified": False,
              "redistribution_approved": False, "older_LICENSE_MS_2407_imported": False, "errors": [],
              "license_policy_from_pinned_source_notes": {"LICENSE-MIT.txt": "d3d12shader.h only", "LICENSE-LLVM.txt": "all other files"},
              "console_limit_bytes": MAX_CONSOLE}
    try:
        metadata_bytes, metadata_receipt = fetch(RELEASE_API, 512 * 1024, GITHUB_HOSTS)
        metadata = json.loads(metadata_bytes)
        assets = [row for row in metadata.get("assets", []) if row.get("id") == ASSET_ID]
        if (metadata.get("tag_name") != TAG or metadata.get("draft") is not False
                or metadata.get("prerelease") is not False or len(assets) != 1 or assets[0].get("name") != ARCHIVE_NAME
                or assets[0].get("size") != ARCHIVE_BYTES or assets[0].get("digest") != "sha256:" + ARCHIVE_SHA
                or assets[0].get("browser_download_url") != ARCHIVE_URL):
            raise ValueError("Official release API no longer matches the exact reviewed asset")
        report["release_API_receipt"] = metadata_receipt
        ref_bytes, ref_receipt = fetch(REF_API, 65536, GITHUB_HOSTS)
        ref = json.loads(ref_bytes)
        if ref.get("object", {}).get("type") != "commit" or ref["object"].get("sha") != COMMIT:
            raise ValueError("Official tag no longer resolves to the exact reviewed source commit")
        report["tag_commit_API_receipt"] = ref_receipt
        raw, receipt = fetch(ARCHIVE_URL, ARCHIVE_BYTES, GITHUB_HOSTS)
        if len(raw) != ARCHIVE_BYTES or digest(raw) != ARCHIVE_SHA: raise ValueError("Original DXC archive size/hash mismatch")
        report["actual_archive"] = receipt
        # The full ZIP is data in memory only; never install/extract dxc.exe or
        # unrelated architectures and do not retain a second package on disk.
        report["package"] = extract_selected(io.BytesIO(raw), args.output)
        report["status"] = "official-package-collected-as-data-not-integrated"
    except Exception as error:
        report["status"] = "failed-required-DXC-collection";report["errors"].append(type(error).__name__ + ": " + str(error)[:500])
    report["optional_microsoft_documents"] = optional_documents(args.output)
    # Keep a complete metadata checkpoint even if an unexpected real inventory
    # later exceeds the bounded console envelope. No binary/PCM is in this JSON.
    with (args.output / "collection-metadata.json").open("xb") as stream:
        stream.write(json.dumps(report, ensure_ascii=True, indent=2, allow_nan=False).encode("ascii") + b"\n")
    data = fit_console(report, args.output)
    with (args.output / "dxc-collection.json").open("xb") as stream: stream.write(data + b"\n")
    print(BEGIN);print(data.decode("ascii"));print(END)
    return 1 if report["errors"] else 0


if __name__ == "__main__": raise SystemExit(main())
