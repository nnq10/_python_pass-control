import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.file_cleanup import cleanup_orphan_files, cleanup_totals, find_orphan_files
from app.services.pass_db import create_pass, init_db


class FileCleanupTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        init_db(self.db)

    def tearDown(self):
        self.db.close()

    def test_find_orphan_files_keeps_referenced_photo_and_qr(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            photos = root / "photos"
            qrcodes = root / "qrcodes"
            photos.mkdir()
            qrcodes.mkdir()
            keep_photo = photos / "EMP-1.jpg"
            orphan_photo = photos / "old.jpg"
            keep_qr = qrcodes / "EMP-1.png"
            orphan_qr = qrcodes / "old.png"
            keep_photo.write_bytes(b"photo")
            orphan_photo.write_bytes(b"old-photo")
            keep_qr.write_bytes(b"qr")
            orphan_qr.write_bytes(b"old-qr")
            create_pass(self.db, {"qr_code": "EMP-1", "photo_path": str(keep_photo)})

            with patch("app.services.file_cleanup.PHOTOS_DIR", photos), \
                 patch("app.services.file_cleanup.QRCODES_DIR", qrcodes), \
                 patch("app.services.file_cleanup.MEDIA_DIRS", {"photos": photos, "qrcodes": qrcodes}):
                orphans = find_orphan_files(self.db)

            self.assertEqual({item["name"] for item in orphans}, {"old.jpg", "old.png"})
            self.assertEqual(cleanup_totals(orphans)["count"], 2)

    def test_cleanup_orphan_files_deletes_only_orphans(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            photos = root / "photos"
            qrcodes = root / "qrcodes"
            photos.mkdir()
            qrcodes.mkdir()
            keep_photo = photos / "EMP-1.jpg"
            orphan_photo = photos / "old.jpg"
            keep_qr = qrcodes / "EMP-1.png"
            orphan_qr = qrcodes / "old.png"
            for path in [keep_photo, orphan_photo, keep_qr, orphan_qr]:
                path.write_bytes(path.name.encode("utf-8"))
            create_pass(self.db, {"qr_code": "EMP-1", "photo_path": str(keep_photo)})

            with patch("app.services.file_cleanup.PHOTOS_DIR", photos), \
                 patch("app.services.file_cleanup.QRCODES_DIR", qrcodes), \
                 patch("app.services.file_cleanup.MEDIA_DIRS", {"photos": photos, "qrcodes": qrcodes}):
                result = cleanup_orphan_files(self.db)

            self.assertEqual(len(result["deleted"]), 2)
            self.assertEqual(result["errors"], [])
            self.assertTrue(keep_photo.exists())
            self.assertTrue(keep_qr.exists())
            self.assertFalse(orphan_photo.exists())
            self.assertFalse(orphan_qr.exists())

    def test_relative_photo_path_is_resolved_inside_photos_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            photos = root / "photos"
            qrcodes = root / "qrcodes"
            photos.mkdir()
            qrcodes.mkdir()
            nested = photos / "nested"
            nested.mkdir()
            keep_photo = nested / "EMP-2.jpg"
            keep_photo.write_bytes(b"photo")
            create_pass(self.db, {"qr_code": "EMP-2", "photo_path": "nested/EMP-2.jpg"})

            with patch("app.services.file_cleanup.PHOTOS_DIR", photos), \
                 patch("app.services.file_cleanup.QRCODES_DIR", qrcodes), \
                 patch("app.services.file_cleanup.MEDIA_DIRS", {"photos": photos, "qrcodes": qrcodes}):
                orphans = find_orphan_files(self.db)

            self.assertNotIn("EMP-2.jpg", {item["name"] for item in orphans})


if __name__ == "__main__":
    unittest.main()
