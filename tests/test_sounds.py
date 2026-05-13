import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.sounds import default_scan_sound_path, scan_sound_path


class SoundTests(unittest.TestCase):
    def test_scan_sound_path_prefers_custom_allowed_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            sounds_dir = Path(tmp)
            expected = sounds_dir / "scan_allowed.wav"
            expected.write_bytes(b"wav")

            with patch("app.services.sounds.SOUNDS_DIR", sounds_dir):
                self.assertEqual(scan_sound_path(True), expected)

    def test_scan_sound_path_prefers_custom_denied_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            sounds_dir = Path(tmp)
            expected = sounds_dir / "scan_denied.wav"
            expected.write_bytes(b"wav")

            with patch("app.services.sounds.SOUNDS_DIR", sounds_dir):
                self.assertEqual(scan_sound_path(False), expected)

    def test_scan_sound_path_returns_none_without_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("app.services.sounds.SOUNDS_DIR", Path(tmp)):
                self.assertIsNone(scan_sound_path(True))
                self.assertIsNone(scan_sound_path(False))

    def test_default_scan_sounds_are_generated_and_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("app.services.sounds.SOUNDS_DIR", Path(tmp)):
                allowed = default_scan_sound_path(True)
                denied = default_scan_sound_path(False)

                self.assertIsNotNone(allowed)
                self.assertIsNotNone(denied)
                self.assertTrue(allowed.exists())
                self.assertTrue(denied.exists())
                self.assertNotEqual(allowed.name, denied.name)
                self.assertNotEqual(allowed.read_bytes(), denied.read_bytes())


if __name__ == "__main__":
    unittest.main()
