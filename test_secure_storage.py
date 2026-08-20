import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch

import secure_storage


class FakeWin32Crypt:
    @staticmethod
    def CryptProtectData(data, description, entropy, reserved, prompt, flags):
        return b"encrypted"

    @staticmethod
    def CryptUnprotectData(data, entropy, reserved, prompt, flags):
        return "Cha-Ching", b"plain"


class SecureStorageTests(unittest.TestCase):
    def test_protect_returns_encrypted_bytes(self):
        with patch.object(secure_storage, "_win32crypt", return_value=FakeWin32Crypt):
            self.assertEqual(secure_storage._protect("plain"), b"encrypted")

    def test_unprotect_returns_plaintext(self):
        with patch.object(secure_storage, "_win32crypt", return_value=FakeWin32Crypt):
            self.assertEqual(secure_storage._unprotect(b"encrypted"), "plain")

    def test_save_keeps_previous_file_as_backup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = str(Path(temp_dir) / "data.json")
            secure_storage.save_json(path, {"version": 1})
            secure_storage.save_json(path, {"version": 2})

            self.assertEqual(secure_storage.load_json(path), {"version": 2})
            self.assertEqual(secure_storage.load_json(path + ".bak"), {"version": 1})

    def test_plaintext_migration_does_not_leave_plaintext_backup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "data.json"
            path.write_text(json.dumps({"secret": "value"}), encoding="utf-8")

            with patch.object(secure_storage.os, "name", "nt"), patch.object(
                secure_storage,
                "_win32crypt",
                return_value=FakeWin32Crypt,
            ):
                self.assertEqual(secure_storage.load_json(str(path)), {"secret": "value"})

            self.assertFalse(Path(str(path) + ".bak").exists())


if __name__ == "__main__":
    unittest.main()
