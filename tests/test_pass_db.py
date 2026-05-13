import sqlite3
import unittest
from datetime import datetime, timedelta

from app.services.pass_db import (CI, PASS_TYPE_SEMIANNUAL, clear_trash, create_pass, fetch_pass_by_qr, init_db,
                     list_trash_file_refs, log_scan, logs_for_day, pass_status,
                     restore_pass, search_passes, soft_delete_pass,
                     stats_summary, trash_counts, update_pass)


def _row(db, qr):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM passes WHERE qr_code=?", (qr,))
    return cursor.fetchone()


class PassDbTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        init_db(self.db)

    def tearDown(self):
        self.db.close()

    def _insert_pass(self, qr, issued_date, days_count=30, active=1):
        self.db.execute(
            """INSERT INTO passes
               (qr_code, issued_date, days_count, active, deleted)
               VALUES (?, ?, ?, ?, 0)""",
            (qr, issued_date, days_count, active),
        )
        self.db.commit()
        return _row(self.db, qr)

    def test_active_pass_reports_days_left(self):
        issued = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
        row = self._insert_pass("ACTIVE", issued, days_count=10)
        active, days_left, expires = pass_status(self.db, row)
        self.assertTrue(active)
        self.assertGreaterEqual(days_left, 7)
        self.assertIsNotNone(expires)

    def test_expired_pass_is_marked_inactive(self):
        issued = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d")
        row = self._insert_pass("EXPIRED", issued, days_count=5, active=1)
        active, days_left, _ = pass_status(self.db, row)
        refreshed = _row(self.db, "EXPIRED")
        self.assertFalse(active)
        self.assertLess(days_left, 0)
        self.assertEqual(refreshed[CI["active"]], 0)

    def test_missing_issued_date_keeps_current_active_state(self):
        row = self._insert_pass("NO_DATE", None, active=1)
        active, days_left, expires = pass_status(self.db, row)
        self.assertTrue(active)
        self.assertIsNone(days_left)
        self.assertIsNone(expires)

    def test_fetch_and_search_passes_skip_deleted_by_default(self):
        active = self._insert_pass("VISIBLE", "2026-01-01", active=1)
        deleted = self._insert_pass("HIDDEN", "2026-01-01", active=1)
        soft_delete_pass(self.db, deleted[CI["qr"]])

        self.assertIsNotNone(fetch_pass_by_qr(self.db, "VISIBLE"))
        self.assertIsNone(fetch_pass_by_qr(self.db, "HIDDEN"))
        self.assertEqual([row[CI["qr"]] for row in search_passes(self.db)], ["VISIBLE"])

    def test_search_passes_can_filter_semiannual_passes(self):
        create_pass(self.db, {"qr_code": "MONTH", "last_name": "Month", "issued_date": "2026-01-01"})
        create_pass(self.db, {
            "qr_code": "HALF",
            "last_name": "Half",
            "issued_date": "2026-01-01",
            "days_count": 180,
            "pass_type": PASS_TYPE_SEMIANNUAL,
        })

        self.assertEqual([row[CI["qr"]] for row in search_passes(self.db)], ["MONTH"])
        self.assertEqual([row[CI["qr"]] for row in search_passes(self.db, pass_type=PASS_TYPE_SEMIANNUAL)], ["HALF"])
        self.assertEqual({row[CI["qr"]] for row in search_passes(self.db, pass_type=None)}, {"MONTH", "HALF"})

    def test_search_passes_matches_extra_fields_and_all_terms(self):
        create_pass(self.db, {
            "qr_code": "QR-A",
            "district": "Север",
            "unit": "12345",
            "rank": "Сержант",
            "last_name": "Иванов",
            "first_name": "Иван",
            "middle_name": "Петрович",
            "phone": "+7 999 111",
            "issued_date": "2026-01-01",
        })
        create_pass(self.db, {
            "qr_code": "QR-B",
            "district": "Юг",
            "unit": "99999",
            "rank": "Рядовой",
            "last_name": "Петров",
            "first_name": "Петр",
            "middle_name": "Иванович",
            "phone": "+7 222 333",
            "issued_date": "2026-02-01",
        })

        def qrs(search):
            return [row[CI["qr"]] for row in search_passes(self.db, search)]

        self.assertEqual(qrs("Петрович"), ["QR-A"])
        self.assertEqual(qrs("Сержант"), ["QR-A"])
        self.assertEqual(qrs("999 111"), ["QR-A"])
        self.assertEqual(qrs("Иванов 12345"), ["QR-A"])
        self.assertEqual(qrs("Сержант 99999"), [])

    def test_soft_delete_restore_and_trash_counts(self):
        row = self._insert_pass("TRASH", "2026-01-01", active=1)
        soft_delete_pass(self.db, row[CI["qr"]])
        self.assertEqual(trash_counts(self.db), (1, 0))

        restore_pass(self.db, row[CI["qr"]])
        self.assertEqual(trash_counts(self.db), (0, 0))

    def test_clear_trash_removes_deleted_and_expired(self):
        deleted = self._insert_pass("DELETED", "2026-01-01", active=1)
        expired = self._insert_pass("EXPIRED_INACTIVE", "2026-01-01", active=0)
        soft_delete_pass(self.db, deleted[CI["qr"]])

        refs = list_trash_file_refs(self.db)
        self.assertEqual({row[0] for row in refs}, {"DELETED", "EXPIRED_INACTIVE"})
        clear_trash(self.db)
        self.assertEqual(trash_counts(self.db), (0, 0))
        self.assertIsNone(fetch_pass_by_qr(self.db, "DELETED", include_deleted=True))
        self.assertIsNone(fetch_pass_by_qr(self.db, "EXPIRED_INACTIVE", include_deleted=True))

    def test_log_scan_writes_log_row(self):
        log_scan(self.db, "QR1", "Person", True)
        row = self.db.execute("SELECT qr_code, full_name, granted FROM logs").fetchone()
        self.assertEqual(row, ("QR1", "Person", 1))

    def test_create_and_update_pass(self):
        create_pass(self.db, {
            "qr_code": "NEW",
            "last_name": "Old",
            "issued_date": "2026-01-01",
            "days_count": 30,
        })
        update_pass(self.db, "NEW", {
            "last_name": "New",
            "first_name": "Name",
            "issued_date": "2026-01-02",
            "days_count": 10,
            "active": 1,
        })
        row = fetch_pass_by_qr(self.db, "NEW")
        self.assertEqual(row[CI["ln"]], "New")
        self.assertEqual(row[CI["fn"]], "Name")
        self.assertEqual(row[CI["days"]], 10)

    def test_stats_summary_and_logs_for_day(self):
        create_pass(self.db, {"qr_code": "A", "last_name": "A", "active": 1})
        create_pass(self.db, {"qr_code": "B", "last_name": "B", "active": 1})
        self.db.execute("UPDATE passes SET active=0 WHERE qr_code='B'")
        self.db.commit()
        log_scan(self.db, "A", "Allowed", True)
        log_scan(self.db, "B", "Denied", False)
        today = datetime.now().strftime("%Y-%m-%d")

        summary = stats_summary(self.db, today)
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["active"], 1)
        self.assertEqual(summary["inactive"], 1)
        self.assertEqual(summary["granted_today"], 1)
        self.assertEqual(summary["denied_today"], 1)

        logs = logs_for_day(self.db, today, descending=False)
        self.assertEqual(len(logs), 2)


if __name__ == "__main__":
    unittest.main()
