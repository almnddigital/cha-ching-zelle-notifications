import unittest
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


if __name__ == "__main__":
    unittest.main()
