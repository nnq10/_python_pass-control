import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.integrity import check_database_integrity
from app.services.pass_db import create_pass, init_db


def _empty_totals(_files):
    return {"count": 0, "bytes": 0, "photos": 0, "qrcodes": 0}


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        init_db(self.db)

    def tearDown(self):
        self.db.close()

    def _patched_files(self, qr_dir):
        return (
            patch("app.services.integrity.qr_code_path", side_effect=lambda qr: qr_dir / f"{qr}.png"),
            patch("app.services.integrity.app_path", side_effect=lambda value: Path(value)),
            patch("app.services.integrity.find_orphan_files", return_value=[]),
            patch("app.services.integrity.cleanup_totals", side_effect=_empty_totals),
        )

    def test_integrity_report_is_clean_for_valid_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            qr_dir = base / "qrcodes"
            qr_dir.mkdir()
            photo = base / "photo.jpg"
            photo.write_bytes(b"photo")
            (qr_dir / "QR1.png").write_bytes(b"qr")
            create_pass(self.db, {
                "qr_code": "QR1",
                "district": "Север",
                "unit": "12345",
                "last_name": "Иванов",
                "issued_date": "2026-01-01",
                "days_count": 30,
                "photo_path": str(photo),
            })

            patches = self._patched_files(qr_dir)
            with patches[0], patches[1], patches[2], patches[3]:
                report = check_database_integrity(self.db)

        self.assertTrue(report["ok"])
        self.assertEqual(report["errors"], 0)
        self.assertEqual(report["warnings"], 0)

    def test_integrity_report_warns_about_broken_pass_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            qr_dir = base / "qrcodes"
            qr_dir.mkdir()
            create_pass(self.db, {
                "qr_code": "QR-MISSING",
                "issued_date": "not-a-date",
                "days_count": 0,
                "photo_path": str(base / "missing.jpg"),
            })

            patches = self._patched_files(qr_dir)
            with patches[0], patches[1], patches[2], patches[3]:
                report = check_database_integrity(self.db)

        messages = "\n".join(row["message"] for row in report["rows"])
        self.assertTrue(report["ok"])
        self.assertEqual(report["errors"], 0)
        self.assertGreaterEqual(report["warnings"], 5)
        self.assertIn("обязательными", messages)
        self.assertIn("Фото", messages)
        self.assertIn("QR", messages)
        self.assertIn("даты", messages)
        self.assertIn("сроки", messages)


if __name__ == "__main__":
    unittest.main()
