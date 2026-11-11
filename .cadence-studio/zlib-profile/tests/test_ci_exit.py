"""Exercise the real guard script under the GitHub Actions PowerShell wrapper."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PWSH = os.environ.get("CADENCE_PWSH") or shutil.which("pwsh")


@unittest.skipUnless(PWSH, "PowerShell 7 is needed for the CI exit propagation regression")
class CiExitPropagationTests(unittest.TestCase):
    def invoke_guard(self, root):
        with tempfile.TemporaryDirectory(prefix="zlib actions shell ") as tmp:
            step = Path(tmp) / "actions step.ps1"
            guard = (root / "tests/Test-ToolPaths.ps1").as_posix().replace("'", "''")
            # The runner's pwsh shell adds ErrorActionPreference=Stop and the
            # LASTEXITCODE tail. A bare pwsh -File guard.ps1 does not test this.
            step.write_text(
                "$ErrorActionPreference = 'Stop'\n"
                "$global:LASTEXITCODE = 0\n"
                f"& '{guard}'\n"
                'Write-Host "CALLER_NATIVE_EXIT=$LASTEXITCODE"\n'
                "if (Test-Path -LiteralPath variable:\\LASTEXITCODE) { exit $LASTEXITCODE }\n",
                encoding="utf-8",
            )
            quoted = step.as_posix().replace("'", "''")
            return subprocess.run([PWSH, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", f". '{quoted}'"],
                                  text=True, capture_output=True, timeout=60)

    def test_successful_negative_tests_preserve_caller_zero_exit(self):
        result = self.invoke_guard(ROOT)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS: actual Native/ToolPath AST", result.stdout)
        self.assertIn("CALLER_NATIVE_EXIT=0", result.stdout)

    def test_actual_guard_failure_is_still_fatal(self):
        with tempfile.TemporaryDirectory(prefix="zlib broken tool resolution ") as tmp:
            root = Path(tmp)
            (root / "tests").mkdir()
            shutil.copyfile(ROOT / "tests/Test-ToolPaths.ps1", root / "tests/Test-ToolPaths.ps1")
            source = (ROOT / "Build-Windows.ps1").read_text(encoding="utf-8")
            self.assertIn("Select-Object -First 1", source)
            # Reintroduce a real wrong-tool selection into the temporary
            # production function; no application or source checkout is changed.
            (root / "Build-Windows.ps1").write_text(
                source.replace("Select-Object -First 1", "Select-Object -Last 1"), encoding="utf-8")
            result = self.invoke_guard(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Tool resolution", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
