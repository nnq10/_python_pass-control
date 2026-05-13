import json
import sqlite3
import unittest

from app.services.audit import action_title, list_actions, list_entity_actions, record_action
from app.services.pass_db import init_db


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        init_db(self.db)

    def tearDown(self):
        self.db.close()

    def test_record_action_writes_actor_action_and_details(self):
        user = {"username": "admin", "role": "admin"}
        record_action(
            self.db,
            user,
            "pass.create",
            "pass",
            "EMP-1",
            {"name": "Иванов Иван", "unit": "12345"},
        )

        rows = list_actions(self.db)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row[1], "admin")
        self.assertEqual(row[2], "admin")
        self.assertEqual(row[3], "pass.create")
        self.assertEqual(row[4], "pass")
        self.assertEqual(row[5], "EMP-1")
        self.assertEqual(json.loads(row[6])["unit"], "12345")

    def test_record_action_uses_system_actor_without_user(self):
        record_action(self.db, None, "backup.auto", "backup", "auto.zip")

        row = list_actions(self.db)[0]
        self.assertEqual(row[1], "system")
        self.assertEqual(row[2], "system")

    def test_list_actions_searches_action_entity_and_details(self):
        user = {"username": "admin", "role": "admin"}
        record_action(self.db, user, "pass.create", "pass", "EMP-1", {"name": "Иванов"})
        record_action(self.db, user, "user.delete", "user", "guard", {"name": "Guard"})

        self.assertEqual(len(list_actions(self.db, search="EMP-1")), 1)
        self.assertEqual(len(list_actions(self.db, search="Guard")), 1)
        self.assertEqual(len(list_actions(self.db, search="missing")), 0)

    def test_list_entity_actions_returns_history_for_one_pass(self):
        user = {"username": "admin", "role": "admin"}
        record_action(self.db, user, "pass.create", "pass", "EMP-1", {"name": "Иванов"})
        record_action(self.db, user, "user.delete", "user", "guard", {"name": "Guard"})

        rows = list_entity_actions(self.db, "pass", "EMP-1")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][3], "pass.create")
        self.assertEqual(rows[0][5], "EMP-1")

    def test_action_title_returns_russian_label(self):
        self.assertEqual(action_title("pass.create"), "Пропуск создан")
        self.assertEqual(action_title("unknown.action"), "unknown.action")


if __name__ == "__main__":
    unittest.main()
