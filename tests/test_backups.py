import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from app.services.backups import create_backup, prune_backups, restore_backup
from app.services.pass_db import init_db


class BackupTests(unittest.TestCase):
    def test_create_backup_contains_database_and_manifest(self):
        db = sqlite3.connect(":memory:")
        try:
            init_db(db)
            with tempfile.TemporaryDirectory() as tmp:
                backup_dir = Path(tmp) / "backups"
                photos_dir = Path(tmp) / "photos"
                qrcodes_dir = Path(tmp) / "qrcodes"
                backup_dir.mkdir()
                photos_dir.mkdir()
                qrcodes_dir.mkdir()
                (photos_dir / "photo.jpg").write_bytes(b"photo")
                (qrcodes_dir / "qr.png").write_bytes(b"qr")
                with patch("app.services.backups.BACKUPS_DIR", backup_dir), \
                     patch("app.services.backups.PHOTOS_DIR", photos_dir), \
                     patch("app.services.backups.QRCODES_DIR", qrcodes_dir), \
                     patch("app.services.backups.BACKUP_DIRS", {"photos": photos_dir, "qrcodes": qrcodes_dir}):
                    archive_path = create_backup(db, "unittest")
                self.assertTrue(archive_path.exists())
                with zipfile.ZipFile(archive_path) as archive:
                    names = set(archive.namelist())
                self.assertIn("passes.db", names)
                self.assertIn("manifest.json", names)
                self.assertIn("photos/photo.jpg", names)
                self.assertIn("qrcodes/qr.png", names)
        finally:
            db.close()

    def test_prune_backups_keeps_newest_archives(self):
        with tempfile.TemporaryDirectory() as tmp:
            backup_dir = Path(tmp)
            archives = []
            for index in range(5):
                archive = backup_dir / f"backup_{index}.zip"
                archive.write_text("backup", encoding="utf-8")
                archives.append(archive)
            with patch("app.services.backups.BACKUPS_DIR", backup_dir):
                removed = prune_backups(keep=2)
            self.assertEqual(len(removed), 3)
            self.assertEqual(len(list(backup_dir.glob("*.zip"))), 2)

    def test_restore_backup_restores_media_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backup_dir = root / "backups"
            photos_dir = root / "photos"
            qrcodes_dir = root / "qrcodes"
            db_file = root / "passes.db"
            backup_dir.mkdir()
            photos_dir.mkdir()
            qrcodes_dir.mkdir()

            db = sqlite3.connect(db_file)
            try:
                init_db(db)
                (photos_dir / "photo.jpg").write_bytes(b"photo")
                (qrcodes_dir / "qr.png").write_bytes(b"qr")
                with patch("app.services.backups.BACKUPS_DIR", backup_dir), \
                     patch("app.services.backups.PHOTOS_DIR", photos_dir), \
                     patch("app.services.backups.QRCODES_DIR", qrcodes_dir), \
                     patch("app.services.backups.DB_FILE", db_file), \
                     patch("app.services.backups.BACKUP_DIRS", {"photos": photos_dir, "qrcodes": qrcodes_dir}):
                    archive_path = create_backup(db, "unittest")
                    (photos_dir / "photo.jpg").unlink()
                    (qrcodes_dir / "qr.png").unlink()
                    restore_backup(archive_path)
                self.assertEqual((photos_dir / "photo.jpg").read_bytes(), b"photo")
                self.assertEqual((qrcodes_dir / "qr.png").read_bytes(), b"qr")
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
