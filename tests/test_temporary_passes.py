import sqlite3
import unittest
from datetime import datetime

from app.services.pass_db import CI, fetch_pass_by_qr, init_db, pass_status, search_passes
from app.services.temporary_passes import (
    TEMP_STATUS_FREE,
    TEMP_STATUS_ISSUED,
    TEMP_STATUS_LOST,
    TemporaryPassError,
    create_temporary_pool,
    issue_temporary_pass,
    list_temporary_passes,
    mark_temporary_lost,
    return_temporary_pass,
    temporary_counts,
    temporary_status,
)
from app.services.validation import ValidationError


class TemporaryPassTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        init_db(self.db)

    def tearDown(self):
        self.db.close()

    def _issue_data(self, days=3):
        return {
            "district": "Север",
            "unit": "12345",
            "rank": "Сержант",
            "last_name": "Иванов",
            "first_name": "Иван",
            "middle_name": "Иванович",
            "phone": "+7 999 111",
            "issued_date": datetime.now().strftime("%Y-%m-%d"),
            "days_count": days,
        }

    def test_create_temporary_pool_creates_free_qr_cards(self):
        created = create_temporary_pool(self.db, count=3, create_qr_files=False)

        self.assertEqual(created, ["TMP-0001", "TMP-0002", "TMP-0003"])
        self.assertEqual(temporary_counts(self.db)[TEMP_STATUS_FREE], 3)
        rows = list_temporary_passes(self.db)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0][CI["active"]], 0)
        self.assertEqual(temporary_status(rows[0]), TEMP_STATUS_FREE)
        self.assertIsNotNone(fetch_pass_by_qr(self.db, "TMP-0001"))

    def test_issue_temporary_pass_uses_existing_qr_without_photo(self):
        create_temporary_pool(self.db, count=1, create_qr_files=False)

        row = issue_temporary_pass(self.db, "TMP-0001", self._issue_data())
        active, _left, _expires = pass_status(self.db, row)

        self.assertTrue(active)
        self.assertEqual(temporary_status(row), TEMP_STATUS_ISSUED)
        self.assertEqual(row[CI["ln"]], "Иванов")
        self.assertIsNone(row[CI["photo"]])
        self.assertEqual(temporary_counts(self.db)[TEMP_STATUS_ISSUED], 1)

    def test_temporary_pass_rejects_month_duration(self):
        create_temporary_pool(self.db, count=1, create_qr_files=False)

        with self.assertRaises(ValidationError):
            issue_temporary_pass(self.db, "TMP-0001", self._issue_data(days=30))

    def test_return_temporary_pass_makes_qr_free_again(self):
        create_temporary_pool(self.db, count=1, create_qr_files=False)
        issue_temporary_pass(self.db, "TMP-0001", self._issue_data())

        row = return_temporary_pass(self.db, "TMP-0001")

        self.assertEqual(temporary_status(row), TEMP_STATUS_FREE)
        self.assertEqual(row[CI["active"]], 0)
        self.assertEqual(row[CI["ln"]], "")
        self.assertEqual(row[CI["issued"]], "")

    def test_mark_temporary_lost_blocks_reissue_until_returned(self):
        create_temporary_pool(self.db, count=1, create_qr_files=False)
        mark_temporary_lost(self.db, "TMP-0001")

        row = fetch_pass_by_qr(self.db, "TMP-0001", include_deleted=True)
        self.assertEqual(temporary_status(row), TEMP_STATUS_LOST)
        self.assertEqual(row[CI["active"]], 0)
        with self.assertRaises(TemporaryPassError):
            issue_temporary_pass(self.db, "TMP-0001", self._issue_data())

    def test_regular_search_excludes_temporary_pool(self):
        create_temporary_pool(self.db, count=2, create_qr_files=False)

        self.assertEqual(search_passes(self.db), [])
        self.assertEqual(len(search_passes(self.db, pass_type=None)), 2)


if __name__ == "__main__":
    unittest.main()
