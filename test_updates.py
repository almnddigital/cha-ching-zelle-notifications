import unittest

import updates


class UpdateTests(unittest.TestCase):
    def test_version_comparison(self):
        self.assertGreater(updates._version_tuple("v1.2.0"), updates._version_tuple("1.1.9"))
        self.assertEqual(updates._version_tuple("release"), (0,))

    def test_update_url_must_be_from_repository_release(self):
        with self.assertRaises(RuntimeError):
            updates.install_update({"download_url": "https://example.com/ChaChing.exe"})


if __name__ == "__main__":
    unittest.main()
