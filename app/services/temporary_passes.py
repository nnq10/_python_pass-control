from datetime import datetime

from app.services.pass_db import CI, PASS_TYPE_TEMPORARY, fetch_pass_by_qr, pass_status
from app.services.qr_codes import save_qr_code
from app.services.validation import ValidationError, validate_pass_data


TEMPORARY_TYPE = PASS_TYPE_TEMPORARY
TEMP_STATUS_FREE = "free"
TEMP_STATUS_ISSUED = "issued"
TEMP_STATUS_EXPIRED = "expired"
TEMP_STATUS_LOST = "lost"
TEMP_POOL_PREFIX = "TMP"
TEMP_POOL_SIZE = 500

TEMP_STATUS_TITLES = {
    TEMP_STATUS_FREE: "Свободен",
    TEMP_STATUS_ISSUED: "Выдан",
    TEMP_STATUS_EXPIRED: "Истёк",
    TEMP_STATUS_LOST: "Утерян",
}


class TemporaryPassError(ValueError):
    pass


def temporary_qr(index, prefix=TEMP_POOL_PREFIX):
    return f"{prefix}-{index:04d}"


def is_temporary_pass(row):
    return bool(row and len(row) > CI["type"] and row[CI["type"]] == TEMPORARY_TYPE)


def temporary_status(row):
    if not is_temporary_pass(row):
        return ""
    return row[CI["temp_status"]] or TEMP_STATUS_FREE


def temporary_status_title(status):
    return TEMP_STATUS_TITLES.get(status, status or "")


def _name(row):
    return " ".join(filter(None, [row[CI["ln"]], row[CI["fn"]], row[CI["mn"]]]))


def create_temporary_pool(db, count=TEMP_POOL_SIZE, prefix=TEMP_POOL_PREFIX, create_qr_files=True):
    created = []
    for index in range(1, count + 1):
        qr_code = temporary_qr(index, prefix)
        cursor = db.execute(
            """INSERT OR IGNORE INTO passes
               (qr_code,district,unit,rank,last_name,first_name,middle_name,phone,
                issued_date,days_count,photo_path,active,deleted,pass_type,temp_status)
               VALUES (?, '', '', '', '', '', '', '', '', 1, NULL, 0, 0, ?, ?)""",
            (qr_code, TEMPORARY_TYPE, TEMP_STATUS_FREE),
        )
        if cursor.rowcount:
            created.append(qr_code)
            if create_qr_files:
                save_qr_code(qr_code)
    db.commit()
    return created


def refresh_temporary_statuses(db):
    cursor = db.cursor()
    cursor.execute(
        "SELECT * FROM passes WHERE pass_type=? AND temp_status=? AND deleted=0",
        (TEMPORARY_TYPE, TEMP_STATUS_ISSUED),
    )
    expired = []
    for row in cursor.fetchall():
        active, _left, _expires = pass_status(db, row)
        if not active:
            expired.append(row[CI["qr"]])
    if expired:
        db.executemany(
            "UPDATE passes SET active=0,temp_status=? WHERE qr_code=?",
            [(TEMP_STATUS_EXPIRED, qr_code) for qr_code in expired],
        )
        db.commit()
    return expired


def temporary_counts(db):
    refresh_temporary_statuses(db)
    cursor = db.cursor()
    counts = {status: 0 for status in TEMP_STATUS_TITLES}
    cursor.execute("SELECT temp_status, COUNT(*) FROM passes WHERE pass_type=? GROUP BY temp_status", (TEMPORARY_TYPE,))
    for status, count in cursor.fetchall():
        counts[status or TEMP_STATUS_FREE] = count
    counts["total"] = sum(counts.values())
    return counts


def list_temporary_passes(db, search="", status="all"):
    refresh_temporary_statuses(db)
    clauses = ["pass_type=?", "deleted=0"]
    params = [TEMPORARY_TYPE]
    if status and status != "all":
        clauses.append("temp_status=?")
        params.append(status)
    if search:
        searchable = ("qr_code", "district", "unit", "rank", "last_name", "first_name", "middle_name", "phone", "issued_date")
        for term in str(search).split():
            like = f"%{term}%"
            clauses.append("(" + " OR ".join(f"{column} LIKE ?" for column in searchable) + ")")
            params.extend([like] * len(searchable))
    cursor = db.cursor()
    cursor.execute(f"SELECT * FROM passes WHERE {' AND '.join(clauses)} ORDER BY qr_code", params)
    return cursor.fetchall()


def next_free_temporary_pass(db):
    refresh_temporary_statuses(db)
    cursor = db.cursor()
    cursor.execute(
        "SELECT * FROM passes WHERE pass_type=? AND temp_status=? AND deleted=0 ORDER BY qr_code LIMIT 1",
        (TEMPORARY_TYPE, TEMP_STATUS_FREE),
    )
    return cursor.fetchone()


def _require_temporary(db, qr_code):
    row = fetch_pass_by_qr(db, qr_code, include_deleted=True)
    if not row or not is_temporary_pass(row):
        raise TemporaryPassError("Временный QR не найден")
    return row


def issue_temporary_pass(db, qr_code, data):
    row = _require_temporary(db, qr_code)
    if temporary_status(row) != TEMP_STATUS_FREE:
        raise TemporaryPassError("Этот временный QR сейчас не свободен")

    payload = dict(data)
    payload["qr_code"] = qr_code
    payload["photo_path"] = None
    payload["active"] = 1
    cleaned = validate_pass_data(payload, db, existing_qr=qr_code)
    if cleaned["days_count"] < 1 or cleaned["days_count"] > 10:
        raise ValidationError(["Срок временного пропуска должен быть от 1 до 10 суток"])

    db.execute(
        """UPDATE passes SET district=?,unit=?,rank=?,last_name=?,first_name=?,middle_name=?,
           phone=?,issued_date=?,days_count=?,photo_path=NULL,active=1,deleted=0,
           pass_type=?,temp_status=? WHERE qr_code=?""",
        (
            cleaned["district"],
            cleaned["unit"],
            cleaned["rank"],
            cleaned["last_name"],
            cleaned["first_name"],
            cleaned["middle_name"],
            cleaned["phone"],
            cleaned["issued_date"],
            cleaned["days_count"],
            TEMPORARY_TYPE,
            TEMP_STATUS_ISSUED,
            qr_code,
        ),
    )
    db.commit()
    return fetch_pass_by_qr(db, qr_code, include_deleted=True)


def return_temporary_pass(db, qr_code):
    _require_temporary(db, qr_code)
    db.execute(
        """UPDATE passes SET district='',unit='',rank='',last_name='',first_name='',middle_name='',
           phone='',issued_date='',days_count=1,photo_path=NULL,active=0,deleted=0,
           pass_type=?,temp_status=? WHERE qr_code=?""",
        (TEMPORARY_TYPE, TEMP_STATUS_FREE, qr_code),
    )
    db.commit()
    return fetch_pass_by_qr(db, qr_code, include_deleted=True)


def mark_temporary_lost(db, qr_code):
    row = _require_temporary(db, qr_code)
    db.execute(
        "UPDATE passes SET active=0,deleted=0,pass_type=?,temp_status=? WHERE qr_code=?",
        (TEMPORARY_TYPE, TEMP_STATUS_LOST, qr_code),
    )
    db.commit()
    return {"qr_code": qr_code, "name": _name(row), "status": temporary_status(row), "lost_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
