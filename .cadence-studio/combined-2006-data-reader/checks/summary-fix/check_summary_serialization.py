# SPDX-License-Identifier: GPL-3.0-only
"""API return-shape checks only: no actual Windows Installer or MSI file."""
import ast
import argparse
import json
from pathlib import Path
import re
import sys
from types import ModuleType, SimpleNamespace

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--original", type=Path, required=True)
parser.add_argument("--fixed", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
ORIGINAL = args.original
FIXED = args.fixed
VALUES = {"ProductVersion": "4.7.6.2006", "ProductName": "Cadence Studio",
          "ProductCode": "{11111111-1111-1111-1111-111111111111}",
          "UpgradeCode": "{319B992F-470A-465B-9A79-6B0CBFC7D6C7}",
          "Manufacturer": "Synthetic shape only", "ProductLanguage": "1033"}

class Record:
    def __init__(self, value): self.value = value
    def GetString(self, index):
        assert index == 1
        return self.value

class View:
    def __init__(self, query):
        match = re.fullmatch(r"SELECT `Value` FROM `Property` WHERE `Property`='([A-Za-z]+)'", query)
        assert match and match[1] in VALUES
        self.value = VALUES[match[1]]
    def Execute(self, argument): assert argument is None
    def Fetch(self): return Record(self.value)
    def Close(self): pass

class Database:
    def __init__(self, summary): self.summary = summary
    def OpenView(self, query): return View(query)
    def GetSummaryInformation(self, count):
        assert count == 0
        return self
    def GetProperty(self, index):
        assert index == 7
        return self.summary

def read_shape(path, summary):
    source = path.read_text()
    ast.parse(source)
    module = ModuleType("shape_check_module")
    exec(compile(source, str(path), "exec"), module.__dict__)
    module.os = SimpleNamespace(name="nt")
    def open_database(actual_path, mode):
        assert actual_path == "synthetic-not-a-file.msi" and mode == 0
        return Database(summary)
    fake = SimpleNamespace(MSIDBOPEN_READONLY=0, OpenDatabase=open_database)
    previous = sys.modules.get("_msi")
    sys.modules["_msi"] = fake
    try:
        return module.properties("synthetic-not-a-file.msi")
    finally:
        if previous is None: sys.modules.pop("_msi", None)
        else: sys.modules["_msi"] = previous

records = []
try:
    json.dumps(read_shape(ORIGINAL, b"x64;1033"))
    raise AssertionError("Original bytes serialization defect not reproduced")
except TypeError as error:
    records.append({"name": "original-bytes-json-failure-reproduced", "passed": True, "error": str(error)})
for summary in (b"x64;1033", "x64;1033"):
    result = read_shape(FIXED, summary)
    assert json.loads(json.dumps(result))["summary_template"] == "x64;1033"
    assert result["open_mode"] == 0 and result["installer_executed"] is False
    assert result["summary_template_raw_hex"] == (summary.hex() if isinstance(summary, bytes) else None)
    records.append({"name": "fixed-" + type(summary).__name__ + "-summary-json", "passed": True})
for summary in (b"x64;\xff", 7):
    try:
        read_shape(FIXED, summary)
        raise AssertionError("Invalid summary unexpectedly accepted")
    except (UnicodeDecodeError, RuntimeError):
        records.append({"name": "refused-invalid-" + type(summary).__name__, "passed": True})
receipt = {"schema_version": 1, "scope": "Synthetic _msi API return shapes and JSON serialization only",
           "checks": len(records), "records": records, "actual_windows_installer_called": False,
           "actual_msi_read": False, "application_or_installer_executed": False}
args.output.write_text(json.dumps(receipt, indent=2) + "\n")
print("PASS", len(records), "return-shape checks; no actual MSI/database/network")
