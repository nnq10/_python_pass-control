import hashlib
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from app.services.auth import (HASH_ALGORITHM, PERMISSION_AUDIT, PERMISSION_PRINT,
                  PERMISSION_SCANNER, PERMISSION_USERS, authenticate, delete_user,
                  has_permission, list_users, load_users, upsert_user, verify_password)


def _record_for(password):
    salt = bytes.fromhex("00112233445566778899aabbccddeeff")
    iterations = 1_000
    return {
        "name": "Test User",
        "role": "admin",
        "algorithm": HASH_ALGORITHM,
        "iterations": iterations,
        "salt": salt.hex(),
        "password_hash": hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
        ).hex(),
    }


class AuthTests(unittest.TestCase):
    def test_verify_password_accepts_matching_hash(self):
        record = _record_for("secret")
        self.assertTrue(verify_password("secret", record))

    def test_verify_password_rejects_wrong_password(self):
        record = _record_for("secret")
        self.assertFalse(verify_password("bad", record))

    def test_authenticate_returns_user_role(self):
        users = {"admin": _record_for("secret")}
        with patch("app.services.auth.load_users", return_value=users):
            user = authenticate("admin", "secret")
        self.assertEqual(user["username"], "admin")
        self.assertEqual(user["role"], "admin")
        self.assertTrue(has_permission(user, PERMISSION_USERS))
        self.assertTrue(has_permission(user, PERMISSION_AUDIT))

    def test_authenticate_rejects_unknown_user(self):
        with patch("app.services.auth.load_users", return_value={}):
            self.assertIsNone(authenticate("missing", "secret"))

    def test_upsert_and_delete_user(self):
        with tempfile.TemporaryDirectory() as tmp:
            users_file = Path(tmp) / "users.json"
            with patch("app.services.auth.USERS_FILE", users_file):
                upsert_user("admin", "Admin", "admin", "secret1")
                upsert_user("operator", "Operator", "guard", "secret1")
                users = load_users()
                self.assertIn("operator", users)
                self.assertTrue(verify_password("secret1", users["operator"]))

                upsert_user("operator", "Senior Operator", "admin", None)
                listed = list_users()
                operator = next(user for user in listed if user["username"] == "operator")
                self.assertEqual(operator["name"], "Senior Operator")
                self.assertEqual(operator["role"], "admin")
                self.assertTrue(has_permission(operator, PERMISSION_USERS))

                self.assertTrue(delete_user("operator"))
                users = load_users()
                self.assertIn("admin", users)
                self.assertNotIn("operator", users)

    def test_delete_last_user_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            users_file = Path(tmp) / "users.json"
            with patch("app.services.auth.USERS_FILE", users_file):
                upsert_user("admin", "Admin", "admin", "secret1")
                with self.assertRaises(ValueError):
                    delete_user("admin")

    def test_delete_last_admin_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            users_file = Path(tmp) / "users.json"
            with patch("app.services.auth.USERS_FILE", users_file):
                upsert_user("admin", "Admin", "admin", "secret1")
                upsert_user("guard", "Guard", "guard", "secret1")
                with self.assertRaises(ValueError):
                    delete_user("admin")

    def test_demote_last_admin_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            users_file = Path(tmp) / "users.json"
            with patch("app.services.auth.USERS_FILE", users_file):
                upsert_user("admin", "Admin", "admin", "secret1")
                upsert_user("guard", "Guard", "guard", "secret1")
                with self.assertRaises(ValueError):
                    upsert_user("admin", "Admin", "guard", None)

    def test_custom_permissions_are_saved_and_returned_on_authenticate(self):
        with tempfile.TemporaryDirectory() as tmp:
            users_file = Path(tmp) / "users.json"
            with patch("app.services.auth.USERS_FILE", users_file):
                upsert_user(
                    "printer",
                    "Print Operator",
                    "guard",
                    "secret1",
                    permissions=[PERMISSION_SCANNER, PERMISSION_PRINT],
                )
                users = load_users()
                self.assertEqual(users["printer"]["permissions"], [PERMISSION_SCANNER, PERMISSION_PRINT])
                user = authenticate("printer", "secret1")
                self.assertTrue(has_permission(user, PERMISSION_SCANNER))
                self.assertTrue(has_permission(user, PERMISSION_PRINT))
                self.assertFalse(has_permission(user, PERMISSION_AUDIT))


if __name__ == "__main__":
    unittest.main()
