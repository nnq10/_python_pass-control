import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from app.core.config import CFG
from app.services.sounds import (CONFIG_ALLOWED_SOUND, DENIED_SOUND_NAMES,
                                 default_scan_sound_path,
                                 ensure_sounds_hint_file, import_sound_file,
                                 list_available_sounds, scan_sound_path)


def write_test_wav(path):
    with wave.open(str(path), "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(8000)
        file.writeframes(b"\x00\x00" * 16)


class SoundTests(unittest.TestCase):
    def test_scan_sound_path_prefers_custom_allowed_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            sounds_dir = Path(tmp)
            expected = sounds_dir / "scan_allowed.wav"
            write_test_wav(expected)

            with patch("app.services.sounds.SOUNDS_DIR", sounds_dir):
                self.assertEqual(scan_sound_path(True), expected)

    def test_scan_sound_path_prefers_custom_denied_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            sounds_dir = Path(tmp)
            expected = sounds_dir / DENIED_SOUND_NAMES[0]
            write_test_wav(expected)
            fallback = sounds_dir / "scan_denied.wav"
            write_test_wav(fallback)

            with patch("app.services.sounds.SOUNDS_DIR", sounds_dir):
                self.assertEqual(scan_sound_path(False), expected)

    def test_scan_sound_path_uses_legacy_denied_name_when_primary_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            sounds_dir = Path(tmp)
            expected = sounds_dir / "scan_denied.wav"
            write_test_wav(expected)

            with patch("app.services.sounds.SOUNDS_DIR", sounds_dir):
                self.assertEqual(scan_sound_path(False), expected)

    def test_scan_sound_path_skips_renamed_non_wav_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            sounds_dir = Path(tmp)
            bad_file = sounds_dir / "scan_allowed.wav"
            bad_file.write_bytes(b"not really wav")

            with patch("app.services.sounds.SOUNDS_DIR", sounds_dir):
                self.assertIsNone(scan_sound_path(True))

    def test_scan_sound_path_accepts_mp3_with_wav_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            sounds_dir = Path(tmp)
            mp3_file = sounds_dir / DENIED_SOUND_NAMES[0]
            mp3_file.write_bytes(b"ID3\x03\x00\x00\x00\x00\x00\x10fake mp3 data")

            with patch("app.services.sounds.SOUNDS_DIR", sounds_dir):
                self.assertEqual(scan_sound_path(False), mp3_file)

    def test_scan_sound_path_prefers_configured_allowed_sound(self):
        with tempfile.TemporaryDirectory() as tmp:
            sounds_dir = Path(tmp)
            configured = sounds_dir / "custom_allowed.wav"
            fallback = sounds_dir / "scan_allowed.wav"
            write_test_wav(configured)
            write_test_wav(fallback)

            with patch("app.services.sounds.SOUNDS_DIR", sounds_dir), \
                 patch.dict(CFG, {CONFIG_ALLOWED_SOUND: configured.name}, clear=False):
                self.assertEqual(scan_sound_path(True), configured)

    def test_list_available_sounds_returns_supported_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            sounds_dir = Path(tmp)
            write_test_wav(sounds_dir / "b.wav")
            (sounds_dir / "a.mp3").write_bytes(b"ID3\x03\x00\x00\x00\x00\x00\x10fake mp3 data")
            (sounds_dir / "bad.wav").write_bytes(b"bad")
            (sounds_dir / "note.txt").write_text("ignore", encoding="utf-8")

            with patch("app.services.sounds.SOUNDS_DIR", sounds_dir):
                self.assertEqual(list_available_sounds(), ["a.mp3", "b.wav"])

    def test_import_sound_file_copies_supported_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.wav"
            sounds_dir = root / "sounds"
            write_test_wav(source)

            with patch("app.services.sounds.SOUNDS_DIR", sounds_dir):
                target = import_sound_file(source)

            self.assertEqual(target.name, source.name)
            self.assertTrue(target.exists())

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

    def test_ensure_sounds_hint_file_writes_active_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            sounds_dir = Path(tmp)
            with patch("app.services.sounds.SOUNDS_DIR", sounds_dir):
                ensure_sounds_hint_file()

            hint = sounds_dir / "README_sounds.txt"
            self.assertTrue(hint.exists())
            text = hint.read_text(encoding="utf-8")
            self.assertIn(str(sounds_dir), text)
            self.assertIn(DENIED_SOUND_NAMES[0], text)


if __name__ == "__main__":
    unittest.main()
