import sqlite3
import unittest

from app.services.pass_db import create_pass, init_db
from app.services.validation import ValidationError, validate_pass_data


def _valid_pass(**overrides):
    data = {
        "qr_code": "EMP-20260506120000000000",
        "district": "Центральный",
        "unit": "12345",
        "rank": "Сержант",
        "last_name": "Иванов",
        "first_name": "Иван",
        "middle_name": "Иванович",
        "phone": "+7 (999) 123-45-67",
        "issued_date": "2026-05-06",
        "days_count": 30,
    }
    data.update(overrides)
    return data


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        init_db(self.db)

    def tearDown(self):
        self.db.close()

    def test_validate_pass_data_normalizes_text_date_and_days(self):
        data = _valid_pass(
            district="  Центральный   округ ",
            unit="  12345 ",
            issued_date="06.05.2026",
            days_count="180.0",
        )

        cleaned = validate_pass_data(data, self.db)

        self.assertEqual(cleaned["district"], "Центральный округ")
        self.assertEqual(cleaned["unit"], "12345")
        self.assertEqual(cleaned["issued_date"], "2026-05-06")
        self.assertEqual(cleaned["days_count"], 180)

    def test_validate_pass_data_can_require_photo(self):
        with self.assertRaises(ValidationError) as caught:
            validate_pass_data(_valid_pass(photo_path=None), self.db, require_photo=True)

        self.assertIn("Фото обязательно", caught.exception.errors)

    def test_validate_pass_data_requires_core_fields(self):
        with self.assertRaises(ValidationError) as caught:
            validate_pass_data(
                _valid_pass(qr_code="", district="", unit="", last_name=""),
                self.db,
            )

        self.assertIn("QR-код обязателен", caught.exception.errors)
        self.assertIn("Округ обязателен", caught.exception.errors)
        self.assertIn("В/ч обязательна", caught.exception.errors)
        self.assertIn("Фамилия обязательна", caught.exception.errors)

    def test_validate_pass_data_rejects_invalid_formats(self):
        with self.assertRaises(ValidationError) as caught:
            validate_pass_data(
                _valid_pass(
                    qr_code="bad qr!",
                    phone="phone",
                    issued_date="06-05-2026",
                    days_count=14,
                ),
                self.db,
            )

        self.assertTrue(any("QR-код должен быть" in error for error in caught.exception.errors))
        self.assertTrue(any("Телефон может содержать" in error for error in caught.exception.errors))
        self.assertTrue(any("Дата выдачи должна быть" in error for error in caught.exception.errors))
        self.assertTrue(any("Срок пропуска должен быть" in error for error in caught.exception.errors))

    def test_validate_pass_data_rejects_duplicate_qr(self):
        create_pass(self.db, _valid_pass())

        with self.assertRaises(ValidationError) as caught:
            validate_pass_data(_valid_pass(), self.db)

        self.assertIn("Такой QR-код уже существует", caught.exception.errors)

    def test_validate_pass_data_allows_existing_qr_for_edit(self):
        data = _valid_pass()
        create_pass(self.db, data)

        cleaned = validate_pass_data(
            _valid_pass(last_name="Петров"),
            self.db,
            existing_qr=data["qr_code"],
        )

        self.assertEqual(cleaned["last_name"], "Петров")


if __name__ == "__main__":
    unittest.main()
