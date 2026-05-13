import hashlib
import hmac
import json
import os
import secrets

from app.core.logging import get_logger
from app.core.paths import USERS_FILE, ensure_data_dirs


logger = get_logger(__name__)
HASH_ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 200_000

PERMISSION_SCANNER = "scanner"
PERMISSION_TEMPORARY = "temporary"
PERMISSION_REGULAR = "regular"
PERMISSION_SEMIANNUAL = "semiannual"
PERMISSION_IMPORT = "import"
PERMISSION_PRINT = "print"
PERMISSION_STATS = "stats"
PERMISSION_USERS = "users"
PERMISSION_AUDIT = "audit"
PERMISSION_TRASH = "trash"
PERMISSION_SETTINGS = "settings"

PERMISSION_TITLES = {
    PERMISSION_SCANNER: "Сканер",
    PERMISSION_TEMPORARY: "Одноразовые",
    PERMISSION_REGULAR: "Временные",
    PERMISSION_SEMIANNUAL: "Полугодовые",
    PERMISSION_IMPORT: "Импорт",
    PERMISSION_PRINT: "Печать",
    PERMISSION_STATS: "Статистика",
    PERMISSION_USERS: "Пользователи",
    PERMISSION_AUDIT: "Аудит",
    PERMISSION_TRASH: "Корзина",
    PERMISSION_SETTINGS: "Настройки",
}
BASE_GUARD_PERMISSIONS = (
    PERMISSION_SCANNER,
    PERMISSION_TEMPORARY,
    PERMISSION_REGULAR,
    PERMISSION_SEMIANNUAL,
    PERMISSION_IMPORT,
    PERMISSION_PRINT,
    PERMISSION_STATS,
    PERMISSION_SETTINGS,
)
ADMIN_ONLY_PERMISSIONS = (
    PERMISSION_USERS,
    PERMISSION_AUDIT,
    PERMISSION_TRASH,
)
DEFAULT_PERMISSIONS = {
    "guard": list(BASE_GUARD_PERMISSIONS),
    "admin": list(BASE_GUARD_PERMISSIONS + ADMIN_ONLY_PERMISSIONS),
}


def permissions_for_role(role):
    return list(DEFAULT_PERMISSIONS["admin" if role == "admin" else "guard"])


def role_title(role):
    return "Администратор" if role == "admin" else "Профиль доступа"


def normalize_permissions(permissions, role="guard"):
    if permissions is None:
        values = permissions_for_role(role)
    else:
        values = []
        for permission in permissions:
            permission = str(permission or "").strip()
            if permission in PERMISSION_TITLES and permission not in values:
                values.append(permission)
    if role == "admin":
        for permission in ADMIN_ONLY_PERMISSIONS + (PERMISSION_SETTINGS,):
            if permission not in values:
                values.append(permission)
    return values


def has_permission(user, permission):
    if not user:
        return False
    permissions = normalize_permissions(user.get("permissions"), user.get("role", "guard"))
    return permission in permissions


def load_users(path=None):
    path = path or USERS_FILE
    ensure_data_dirs()
    if not os.path.exists(path):
        logger.error("Users file is missing: %s", path)
        return {}
    try:
        with open(path, encoding="utf-8") as file:
            data = json.load(file)
    except Exception:
        logger.exception("Failed to load users file: %s", path)
        return {}
    return data.get("users", {})


def save_users(users, path=None):
    path = path or USERS_FILE
    ensure_data_dirs()
    with open(path, "w", encoding="utf-8") as file:
        json.dump({"users": users}, file, ensure_ascii=False, indent=2)


def hash_password(password):
    salt = secrets.token_hex(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        ITERATIONS,
    ).hex()
    return {
        "algorithm": HASH_ALGORITHM,
        "iterations": ITERATIONS,
        "salt": salt,
        "password_hash": password_hash,
    }


def list_users():
    users = load_users()
    return [
        {
            "username": username,
            "name": record.get("name", username),
            "role": record.get("role", "guard"),
            "permissions": normalize_permissions(record.get("permissions"), record.get("role", "guard")),
        }
        for username, record in sorted(users.items())
    ]


def _admin_count(users):
    return sum(1 for record in users.values() if record.get("role") == "admin")


def upsert_user(username, name, role, password=None, permissions=None):
    username = username.strip()
    if not username:
        raise ValueError("username is required")
    if role not in ("admin", "guard"):
        raise ValueError("unsupported role")

    users = load_users()
    record = users.get(username, {})
    if record.get("role") == "admin" and role != "admin" and _admin_count(users) <= 1:
        raise ValueError("cannot demote the last admin")
    record["name"] = name.strip() or username
    record["role"] = role
    record["permissions"] = normalize_permissions(permissions, role)
    if password:
        record.update(hash_password(password))
    elif username not in users:
        raise ValueError("password is required for new user")
    users[username] = record
    save_users(users)


def delete_user(username):
    users = load_users()
    if username not in users:
        return False
    if len(users) <= 1:
        raise ValueError("cannot delete the last user")
    if users[username].get("role") == "admin" and _admin_count(users) <= 1:
        raise ValueError("cannot delete the last admin")
    del users[username]
    save_users(users)
    return True


def verify_password(password, record):
    if record.get("algorithm") != HASH_ALGORITHM:
        logger.error("Unsupported password hash algorithm: %s", record.get("algorithm"))
        return False

    try:
        salt = bytes.fromhex(record["salt"])
        expected = record["password_hash"]
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            int(record.get("iterations", ITERATIONS)),
        ).hex()
    except Exception:
        logger.exception("Failed to verify password hash")
        return False

    return hmac.compare_digest(actual, expected)


def authenticate(username, password):
    users = load_users()
    record = users.get(username)
    if not record:
        return None
    if not verify_password(password, record):
        return None
    return {
        "username": username,
        "name": record.get("name", username),
        "role": record.get("role", "guard"),
        "permissions": normalize_permissions(record.get("permissions"), record.get("role", "guard")),
    }
