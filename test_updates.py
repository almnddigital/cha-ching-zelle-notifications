import io
import json
import unittest
from unittest.mock import patch

import updates


class UpdateTests(unittest.TestCase):
    def test_version_comparison(self):
        self.assertGreater(updates._version_tuple("v1.2.0"), updates._version_tuple("1.1.9"))
        self.assertEqual(updates._version_tuple("release"), (0,))

    def test_update_url_must_be_from_repository_release(self):
        with self.assertRaises(RuntimeError):
            updates.install_update(
                {
                    "download_url": "https://example.com/ChaChing.exe",
                    "checksum_url": "https://example.com/ChaChing.exe.sha256",
                }
            )

    def test_update_requires_executable_and_checksum_assets(self):
        release = {
            "tag_name": "v1.4.0",
            "draft": False,
            "prerelease": False,
            "assets": [
                {
                    "name": "ChaChing.exe",
                    "browser_download_url": "https://github.com/almnddigital/cha-ching-zelle-notifications/releases/download/v1.4.0/ChaChing.exe",
                }
            ],
        }
        response = io.BytesIO(json.dumps(release).encode("utf-8"))

        with patch.object(updates.urllib.request, "urlopen", return_value=response):
            self.assertIsNone(updates.check_for_update())

    def test_update_returns_verified_release_assets(self):
        base = "https://github.com/almnddigital/cha-ching-zelle-notifications/releases/download/v1.4.0/"
        release = {
            "tag_name": "v1.4.0",
            "draft": False,
            "prerelease": False,
            "assets": [
                {"name": "ChaChing.exe", "browser_download_url": base + "ChaChing.exe"},
                {
                    "name": "ChaChing.exe.sha256",
                    "browser_download_url": base + "ChaChing.exe.sha256",
                },
            ],
        }
        response = io.BytesIO(json.dumps(release).encode("utf-8"))

        with patch.object(updates.urllib.request, "urlopen", return_value=response):
            result = updates.check_for_update()

        self.assertEqual(result["version"], "1.4.0")
        self.assertEqual(result["checksum_url"], base + "ChaChing.exe.sha256")


if __name__ == "__main__":
    unittest.main()
