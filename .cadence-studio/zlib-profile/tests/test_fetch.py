"""The fetcher must reject altered sources and preserve existing directories."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CMAKE = os.environ.get("CADENCE_CMAKE", shutil.which("cmake") or "cmake")


class SourceIntegrityTests(unittest.TestCase):
    def test_tampered_archive_never_creates_source_directory(self):
        with tempfile.TemporaryDirectory(prefix="zlib integrity ") as tmp:
            work = Path(tmp)
            archive = work / "tampered.tar.gz"
            archive.write_bytes(b"This is not the pinned upstream archive")
            output = work / "sources"
            result = subprocess.run([CMAKE, f"-DZLIB_SOURCE_OUTPUT={output}",
                                     f"-DZLIB_SOURCE_ARCHIVE={archive}", "-P", str(ROOT / "FetchSource.cmake")],
                                    text=True, capture_output=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SHA-256 mismatch", result.stdout + result.stderr)
            self.assertFalse(output.exists())

    def test_existing_directory_is_preserved(self):
        with tempfile.TemporaryDirectory(prefix="zlib existing ") as tmp:
            output = Path(tmp) / "sources"
            output.mkdir()
            marker = output / "keep.txt"
            marker.write_bytes(b"Existing user files must never be replaced")
            result = subprocess.run([CMAKE, f"-DZLIB_SOURCE_OUTPUT={output}",
                                     "-P", str(ROOT / "FetchSource.cmake")],
                                    text=True, capture_output=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("new absolute directory", result.stdout + result.stderr)
            self.assertEqual(marker.read_bytes(), b"Existing user files must never be replaced")


if __name__ == "__main__":
    unittest.main()
