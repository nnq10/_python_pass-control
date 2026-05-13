import sqlite3
from datetime import datetime, timedelta

from app.core.logging import get_logger
from app.core.paths import DB_FILE, ensure_data_dirs


logger = get_logger(__name__)

PASS_TYPE_REGULAR = "regular"
PASS_TYPE_SEMIANNUAL = "semiannual"
PASS_TYPE_TEMPORARY = "temporary"

CI = dict(
    id=0,
    qr=1,
    district=2,
    unit=3,
    rank=4,
    ln=5,
    fn=6,
    mn=7,
    phone=8,
    issued=9,
    days=10,
    photo=11,
    active=12,
    deleted=13,
    type=14,
    temp_status=15,
)


def connect_db(path=DB_FILE):
    ensure_data_dirs()
    return sqlite3.connect(path)


def _columns(db, table):
    cursor = db.cursor()
    cursor.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cursor.fetchall()}


def _ensure_column(db, table, name, definition):
    if name not in _columns(db, table):
        db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def init_db(db):
    cursor = db.cursor()
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS passes (
            id INTEGER PRIMARY KEY,
            qr_code     TEXT UNIQUE,
            district    TEXT,
            unit        TEXT,
            rank        TEXT,
            last_name   TEXT,
            first_name  TEXT,
            middle_name TEXT,
            phone       TEXT,
            issued_date TEXT,
            days_count  INTEGER DEFAULT 30,
            photo_path  TEXT,
            active      INTEGER DEFAULT 1,
            deleted     INTEGER DEFAULT 0,
            pass_type   TEXT DEFAULT 'regular',
            temp_status TEXT DEFAULT ''
        )"""
    )
    _ensure_column(db, "passes", "pass_type", "TEXT DEFAULT 'regular'")
    _ensure_column(db, "passes", "temp_status", "TEXT DEFAULT ''")
    cursor.execute("UPDATE passes SET pass_type='regular' WHERE pass_type IS NULL OR pass_type=''")
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY,
            qr_code TEXT, full_name TEXT,
            timestamp TEXT, granted INTEGER
        )"""
    )
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY,
            timestamp   TEXT NOT NULL,
            username    TEXT,
            role        TEXT,
            action      TEXT NOT NULL,
            entity_type TEXT,
            entity_id   TEXT,
            details     TEXT
        )"""
    )
    db.commit()


def fetch_pass_by_qr(db, qr_code, include_deleted=False):
    cursor = db.cursor()
    if include_deleted:
        cursor.execute("SELECT * FROM passes WHERE qr_code=?", (qr_code,))
    else:
        cursor.execute("SELECT * FROM passes WHERE qr_code=? AND deleted=0", (qr_code,))
    return cursor.fetchone()


def search_passes(db, search="", deleted=0, active=None, pass_type=PASS_TYPE_REGULAR):
    cursor = db.cursor()
    clauses = ["deleted=?"]
    params = [deleted]
    if pass_type is not None:
        clauses.append("pass_type=?")
        params.append(pass_type)
    if active is not None:
        clauses.append("active=?")
        params.append(active)
    if search:
        searchable_columns = [
            "qr_code",
            "district",
            "unit",
            "rank",
            "last_name",
            "first_name",
            "middle_name",
            "phone",
            "issued_date",
        ]
        for term in str(search).split():
            like = f"%{term}%"
            clauses.append("(" + " OR ".join(f"{column} LIKE ?" for column in searchable_columns) + ")")
            params.extend([like] * len(searchable_columns))
    cursor.execute(f"SELECT * FROM passes WHERE {' AND '.join(clauses)}", params)
    return cursor.fetchall()


def log_scan(db, qr_code, full_name, granted):
    db.execute(
        "INSERT INTO logs (qr_code,full_name,timestamp,granted) VALUES (?,?,?,?)",
        (qr_code, full_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), int(granted)),
    )
    db.commit()


def soft_delete_pass(db, qr_code):
    db.execute("UPDATE passes SET deleted=1 WHERE qr_code=?", (qr_code,))
    db.commit()


def restore_pass(db, qr_code):
    db.execute("UPDATE passes SET deleted=0,active=1 WHERE qr_code=?", (qr_code,))
    db.commit()


def get_photo_path(db, qr_code):
    cursor = db.cursor()
    cursor.execute("SELECT photo_path FROM passes WHERE qr_code=?", (qr_code,))
    row = cursor.fetchone()
    return row[0] if row else None


def delete_pass_forever(db, qr_code):
    db.execute("DELETE FROM passes WHERE qr_code=?", (qr_code,))
    db.commit()


def trash_counts(db):
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) FROM passes WHERE pass_type!=? AND deleted=1", (PASS_TYPE_TEMPORARY,))
    deleted = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM passes WHERE pass_type!=? AND deleted=0 AND active=0", (PASS_TYPE_TEMPORARY,))
    expired = cursor.fetchone()[0]
    return deleted, expired


def list_trash_file_refs(db):
    cursor = db.cursor()
    cursor.execute("SELECT qr_code,photo_path FROM passes WHERE pass_type!=? AND (deleted=1 OR active=0)", (PASS_TYPE_TEMPORARY,))
    return cursor.fetchall()


def clear_trash(db):
    db.execute("DELETE FROM passes WHERE pass_type!=? AND deleted=1", (PASS_TYPE_TEMPORARY,))
    db.execute("DELETE FROM passes WHERE pass_type!=? AND deleted=0 AND active=0", (PASS_TYPE_TEMPORARY,))
    db.commit()


def create_pass(db, data):
    db.execute(
        """INSERT INTO passes
           (qr_code,district,unit,rank,last_name,first_name,middle_name,
            phone,issued_date,days_count,photo_path,active,deleted,pass_type,temp_status)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            data["qr_code"],
            data.get("district", ""),
            data.get("unit", ""),
            data.get("rank", ""),
            data.get("last_name", ""),
            data.get("first_name", ""),
            data.get("middle_name", ""),
            data.get("phone", ""),
            data.get("issued_date", ""),
            data.get("days_count", 30),
            data.get("photo_path"),
            int(data.get("active", 1)),
            int(data.get("deleted", 0)),
            data.get("pass_type", PASS_TYPE_REGULAR),
            data.get("temp_status", ""),
        ),
    )
    db.commit()


def insert_pass_ignore(db, data):
    cursor = db.cursor()
    cursor.execute(
        """INSERT OR IGNORE INTO passes
           (qr_code,district,unit,rank,last_name,first_name,middle_name,
            phone,issued_date,days_count,active,deleted,pass_type,temp_status)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            data["qr_code"],
            data.get("district", ""),
            data.get("unit", ""),
            data.get("rank", ""),
            data.get("last_name", ""),
            data.get("first_name", ""),
            data.get("middle_name", ""),
            data.get("phone", ""),
            data.get("issued_date", ""),
            data.get("days_count", 30),
            int(data.get("active", 1)),
            int(data.get("deleted", 0)),
            data.get("pass_type", PASS_TYPE_REGULAR),
            data.get("temp_status", ""),
        ),
    )
    db.commit()
    return cursor.rowcount > 0


def update_pass(db, qr_code, data):
    db.execute(
        """UPDATE passes SET district=?,unit=?,rank=?,
           last_name=?,first_name=?,middle_name=?,phone=?,
           issued_date=?,days_count=?,photo_path=?,active=? WHERE qr_code=?""",
        (
            data.get("district", ""),
            data.get("unit", ""),
            data.get("rank", ""),
            data.get("last_name", ""),
            data.get("first_name", ""),
            data.get("middle_name", ""),
            data.get("phone", ""),
            data.get("issued_date", ""),
            data.get("days_count", 30),
            data.get("photo_path"),
            int(data.get("active", 1)),
            qr_code,
        ),
    )
    db.commit()


def stats_summary(db, day):
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) FROM passes WHERE pass_type!=? AND deleted=0", (PASS_TYPE_TEMPORARY,))
    total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM passes WHERE pass_type!=? AND deleted=0 AND active=1", (PASS_TYPE_TEMPORARY,))
    active = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM passes WHERE pass_type!=? AND deleted=0 AND active=0", (PASS_TYPE_TEMPORARY,))
    inactive = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM logs WHERE granted=1 AND timestamp LIKE ?", (f"{day}%",))
    granted_today = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM logs WHERE granted=0 AND timestamp LIKE ?", (f"{day}%",))
    denied_today = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM logs WHERE granted=1")
    granted_total = cursor.fetchone()[0]
    return {
        "total": total,
        "active": active,
        "inactive": inactive,
        "granted_today": granted_today,
        "denied_today": denied_today,
        "granted_total": granted_total,
    }


def logs_for_day(db, day, descending=True):
    order = "DESC" if descending else "ASC"
    cursor = db.cursor()
    cursor.execute(
        f"SELECT timestamp,full_name,qr_code,granted FROM logs WHERE timestamp LIKE ? ORDER BY id {order}",
        (f"{day}%",),
    )
    return cursor.fetchall()


def pass_status(db, row):
    issued_str = row[CI["issued"]]
    days = row[CI["days"]] or 30
    active = bool(row[CI["active"]])
    if not issued_str:
        return active, None, None

    try:
        issued = datetime.strptime(issued_str[:10], "%Y-%m-%d")
        expires = issued + timedelta(days=int(days))
        left = (expires.date() - datetime.now().date()).days
        if left < 0 and active:
            db.cursor().execute(
                "UPDATE passes SET active=0 WHERE qr_code=?",
                (row[CI["qr"]],),
            )
            db.commit()
            active = False
        return active, left, expires
    except Exception:
        logger.exception("Failed to calculate pass status for qr=%s", row[CI["qr"]])
        return active, None, None
