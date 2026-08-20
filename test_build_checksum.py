import hashlib
import tempfile
import unittest
from pathlib import Path

import build_checksum


class BuildChecksumTests(unittest.TestCase):
    def test_writes_sha256_release_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            executable = Path(temp_dir) / "ChaChing.exe"
            checksum = Path(temp_dir) / "ChaChing.exe.sha256"
            executable.write_bytes(b"windows executable")

            build_checksum.write_checksum(executable, checksum)

            expected = hashlib.sha256(b"windows executable").hexdigest()
            self.assertEqual(checksum.read_text(encoding="ascii"), f"{expected}  ChaChing.exe")


if __name__ == "__main__":
    unittest.main()
