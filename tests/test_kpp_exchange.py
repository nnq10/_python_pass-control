import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app.services.kpp_exchange import (export_kpp_package, import_kpp_package,
                                       inspect_kpp_package)
from app.services.pass_db import (CI, PASS_TYPE_REGULAR, PASS_TYPE_SEMIANNUAL,
                                  PASS_TYPE_TEMPORARY, create_pass,
                                  fetch_pass_by_qr, init_db)


class KppExchangeTests(unittest.TestCase):
    def setUp(self):
        self.source = sqlite3.connect(":memory:")
        self.target = sqlite3.connect(":memory:")
        init_db(self.source)
        init_db(self.target)

    def tearDown(self):
        self.source.close()
        self.target.close()

    def _patch_paths(self, root):
        photos = root / "photos"
        qrcodes = root / "qrcodes"
        backups = root / "backups"
        patches = [
            patch("app.core.paths.PHOTOS_DIR", photos),
            patch("app.core.paths.QRCODES_DIR", qrcodes),
            patch("app.core.paths.BACKUPS_DIR", backups),
            patch("app.services.kpp_exchange.PHOTOS_DIR", photos),
            patch("app.services.kpp_exchange.QRCODES_DIR", qrcodes),
        ]
        return patches

    def _create_photo(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (30, 40), "blue").save(path)
        return path

    def test_export_and_import_monthly_and_semiannual_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            patches = self._patch_paths(root)
            for item in patches:
                item.start()
            self.addCleanup(lambda: [item.stop() for item in reversed(patches)])

            photo = self._create_photo(root / "photos" / "HALF.jpg")
            create_pass(self.source, {
                "qr_code": "MONTH-001",
                "district": "Север",
                "unit": "12345",
                "rank": "Рядовой",
                "last_name": "Иванов",
                "issued_date": "2026-05-01",
                "days_count": 30,
                "pass_type": PASS_TYPE_REGULAR,
            })
            create_pass(self.source, {
                "qr_code": "HALF-001",
                "district": "Юг",
                "unit": "99999",
                "rank": "Сержант",
                "last_name": "Петров",
                "issued_date": "2026-05-01",
                "days_count": 180,
                "photo_path": str(photo),
                "pass_type": PASS_TYPE_SEMIANNUAL,
            })
            create_pass(self.source, {
                "qr_code": "TMP-B001-0001",
                "district": "Не надо",
                "unit": "Не надо",
                "last_name": "Разовый",
                "issued_date": "2026-05-01",
                "days_count": 1,
                "pass_type": PASS_TYPE_TEMPORARY,
            })

            package = root / "exchange.pcpkg"
            exported = export_kpp_package(self.source, package, created_by="admin")
            info = inspect_kpp_package(package)

            self.assertEqual(exported["count"], 2)
            self.assertEqual(info["counts"][PASS_TYPE_REGULAR], 1)
            self.assertEqual(info["counts"][PASS_TYPE_SEMIANNUAL], 1)

            with patch("app.services.kpp_exchange.create_backup", return_value=root / "backup.zip"):
                result = import_kpp_package(self.target, package)

            self.assertEqual(result["stats"]["created"], 2)
            self.assertEqual(result["stats"]["updated"], 0)
            self.assertEqual(result["stats"]["errors"], 0)
            self.assertIsNotNone(fetch_pass_by_qr(self.target, "MONTH-001"))
            imported_half = fetch_pass_by_qr(self.target, "HALF-001")
            self.assertEqual(imported_half[CI["type"]], PASS_TYPE_SEMIANNUAL)
            self.assertTrue(Path(imported_half[CI["photo"]]).exists())
            self.assertIsNone(fetch_pass_by_qr(self.target, "TMP-B001-0001"))

    def test_import_updates_existing_pass_by_qr(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            patches = self._patch_paths(root)
            for item in patches:
                item.start()
            self.addCleanup(lambda: [item.stop() for item in reversed(patches)])

            create_pass(self.source, {
                "qr_code": "MONTH-EDIT",
                "district": "Новый",
                "unit": "22222",
                "last_name": "Новая",
                "issued_date": "2026-05-01",
                "days_count": 30,
            })
            create_pass(self.target, {
                "qr_code": "MONTH-EDIT",
                "district": "Старый",
                "unit": "11111",
                "last_name": "Старая",
                "issued_date": "2026-04-01",
                "days_count": 30,
            })

            package = root / "exchange.pcpkg"
            export_kpp_package(self.source, package)
            with patch("app.services.kpp_exchange.create_backup", return_value=root / "backup.zip"):
                result = import_kpp_package(self.target, package)

            row = fetch_pass_by_qr(self.target, "MONTH-EDIT")
            self.assertEqual(result["stats"]["created"], 0)
            self.assertEqual(result["stats"]["updated"], 1)
            self.assertEqual(row[CI["district"]], "Новый")
            self.assertEqual(row[CI["ln"]], "Новая")


if __name__ == "__main__":
    unittest.main()
