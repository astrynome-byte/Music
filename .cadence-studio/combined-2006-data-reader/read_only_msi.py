# SPDX-License-Identifier: GPL-3.0-only
"""Read a Windows Installer database in mode 0; never install or run any action."""
import os
import re

def properties(path):
    if os.name != "nt":
        return {"status": "unavailable-non-Windows", "database_opened_readonly": False, "installer_executed": False}
    import _msi
    database = _msi.OpenDatabase(str(path), _msi.MSIDBOPEN_READONLY)
    result = {}
    for name in ("ProductVersion", "ProductName", "ProductCode", "UpgradeCode", "Manufacturer", "ProductLanguage"):
        # Constants only. Execute here means a SELECT view, not an MSI action.
        view = database.OpenView("SELECT `Value` FROM `Property` WHERE `Property`='" + name + "'")
        try:
            view.Execute(None)
            record = view.Fetch()
            if record is None: raise RuntimeError("Required MSI property missing: " + name)
            value = record.GetString(1)
            if not value or len(value) > 512: raise RuntimeError("Empty/oversized MSI property")
            result[name] = value
        finally:
            view.Close()
    summary = database.GetSummaryInformation(0).GetProperty(7)
    return {"status": "read-actual-Property-table", "database_opened_readonly": True,
            "open_mode": int(_msi.MSIDBOPEN_READONLY), "properties": result, "summary_template": summary,
            "version_matches_expected_family": bool(re.fullmatch(r"4\.7\.6(?:\.\d+)?", result["ProductVersion"])),
            "upgrade_matches_cadence_identity": result["UpgradeCode"].upper() == "{319B992F-470A-465B-9A79-6B0CBFC7D6C7}",
            "installer_executed": False}
