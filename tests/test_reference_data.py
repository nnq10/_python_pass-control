import sqlite3
import unittest

from app.services.pass_db import create_pass, init_db, update_pass
from app.services.reference_data import (add_reference_value, delete_reference_value,
                                         list_reference_values,
                                         sync_reference_values_from_passes)


class ReferenceDataTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        init_db(self.db)

    def tearDown(self):
        self.db.close()

    def test_create_and_update_pass_remember_reference_values(self):
        create_pass(self.db, {
            "qr_code": "REF-1",
            "district": "Центральный округ",
            "unit": "12345",
            "rank": "Сержант",
        })

        self.assertEqual(list_reference_values(self.db, "district"), ["Центральный округ"])
        self.assertEqual(list_reference_values(self.db, "unit"), ["12345"])
        self.assertEqual(list_reference_values(self.db, "rank"), ["Сержант"])

        update_pass(self.db, "REF-1", {
            "district": "Северный округ",
            "unit": "98765",
            "rank": "Капитан",
        })

        self.assertIn("Северный округ", list_reference_values(self.db, "district"))
        self.assertIn("98765", list_reference_values(self.db, "unit"))
        self.assertIn("Капитан", list_reference_values(self.db, "rank"))

    def test_manual_reference_add_delete_and_sync_from_existing_passes(self):
        self.db.execute(
            """INSERT INTO passes(qr_code,district,unit,rank,last_name)
               VALUES ('REF-RAW','Южный округ','55555','Майор','Иванов')"""
        )
        self.db.commit()

        sync_reference_values_from_passes(self.db)
        self.assertIn("Южный округ", list_reference_values(self.db, "district"))
        self.assertTrue(add_reference_value(self.db, "rank", "Полковник"))
        self.assertIn("Полковник", list_reference_values(self.db, "rank"))
        self.assertTrue(delete_reference_value(self.db, "rank", "Полковник"))
        self.assertNotIn("Полковник", list_reference_values(self.db, "rank"))

    def test_reference_values_can_be_filtered(self):
        add_reference_value(self.db, "district", "Центральный")
        add_reference_value(self.db, "district", "Северный")

        self.assertEqual(list_reference_values(self.db, "district", "центр"), ["Центральный"])


if __name__ == "__main__":
    unittest.main()
