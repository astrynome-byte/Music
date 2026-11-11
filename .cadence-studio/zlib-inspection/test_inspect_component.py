"""Verify source-only transport repair using the actual pinned source archive."""
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from inspect_component import verified_hash_reader

ARCHIVE = Path(os.environ.get("ZLIB_TEST_SOURCE_ARCHIVE", Path(__file__).resolve().parents[1] / "evidence/zlib-1.3.2.tar.gz"))


@unittest.skipUnless(ARCHIVE.is_file(), "The official pinned zlib archive is required")
class TransportRepairTests(unittest.TestCase):
    def test_hidden_source_recovered_and_non_source_never_invented(self):
        with tempfile.TemporaryDirectory(prefix="zlib archive reader ") as tmp:
            root = Path(tmp)
            (root / "sources").mkdir()
            shutil.copyfile(ARCHIVE, root / "sources/zlib-1.3.2.tar.gz")
            with verified_hash_reader(root) as (digest, recovered):
                value = digest("sources/unmodified/zlib-1.3.2/.cmake-format.yaml")
                self.assertEqual(value, "986f0fdc53be34f931d66c1a6fa4935d84991da14f059c7df567ede7cd32b68f")
                self.assertEqual(len(recovered), 1)
                self.assertFalse((root / "sources/unmodified").exists())
                with self.assertRaisesRegex(ValueError, "Missing retained non-source"):
                    digest("stage/lib/zs.lib")
                with self.assertRaisesRegex(ValueError, "Unsafe"):
                    digest("sources/unmodified/zlib-1.3.2/../../secret")

    def test_altered_archive_rejected_before_recovery(self):
        with tempfile.TemporaryDirectory(prefix="zlib bad archive ") as tmp:
            root = Path(tmp)
            (root / "sources").mkdir()
            (root / "sources/zlib-1.3.2.tar.gz").write_bytes(b"tampered source archive")
            with self.assertRaisesRegex(ValueError, "source archive changed"):
                with verified_hash_reader(root):
                    self.fail("An altered archive was accepted")


if __name__ == "__main__":
    unittest.main()
