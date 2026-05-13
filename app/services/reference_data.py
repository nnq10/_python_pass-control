from datetime import datetime


REFERENCE_FIELDS = {
    "district": "district",
    "unit": "unit",
    "rank": "rank",
}

REFERENCE_TITLES = {
    "district": "Округа",
    "unit": "Подразделения",
    "rank": "Звания",
}


def _clean(value):
    return " ".join(str(value or "").strip().split())


def _require_kind(kind):
    if kind not in REFERENCE_FIELDS:
        raise ValueError(f"unknown reference kind: {kind}")
    return kind


def ensure_reference_table(db):
    db.execute(
        """CREATE TABLE IF NOT EXISTS reference_values (
            id INTEGER PRIMARY KEY,
            kind TEXT NOT NULL,
            value TEXT NOT NULL,
            uses INTEGER DEFAULT 0,
            last_used TEXT DEFAULT '',
            UNIQUE(kind, value)
        )"""
    )
    db.commit()


def sync_reference_values_from_passes(db):
    ensure_reference_table(db)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for kind, column in REFERENCE_FIELDS.items():
        rows = db.execute(
            f"""SELECT {column}, COUNT(*)
                FROM passes
                WHERE TRIM(COALESCE({column}, '')) != ''
                GROUP BY {column}"""
        ).fetchall()
        for value, uses in rows:
            value = _clean(value)
            if not value:
                continue
            db.execute(
                """INSERT INTO reference_values(kind,value,uses,last_used)
                   VALUES (?,?,?,?)
                   ON CONFLICT(kind,value) DO UPDATE SET
                       uses=CASE WHEN excluded.uses > reference_values.uses
                                 THEN excluded.uses ELSE reference_values.uses END""",
                (kind, value, int(uses or 0), stamp),
            )
    db.commit()


def list_reference_values(db, kind, search=""):
    kind = _require_kind(kind)
    ensure_reference_table(db)
    search = _clean(search)
    rows = db.execute(
        """SELECT value
           FROM reference_values
           WHERE kind=?
           ORDER BY uses DESC, value COLLATE NOCASE ASC""",
        (kind,),
    ).fetchall()
    values = [row[0] for row in rows]
    if search:
        needle = search.casefold()
        values = [value for value in values if needle in value.casefold()]
    return values


def add_reference_value(db, kind, value, uses=0):
    kind = _require_kind(kind)
    ensure_reference_table(db)
    value = _clean(value)
    if not value:
        return False
    cursor = db.cursor()
    cursor.execute(
        """INSERT OR IGNORE INTO reference_values(kind,value,uses,last_used)
           VALUES (?,?,?,?)""",
        (kind, value, int(uses or 0), ""),
    )
    db.commit()
    return cursor.rowcount > 0


def delete_reference_value(db, kind, value):
    kind = _require_kind(kind)
    ensure_reference_table(db)
    cursor = db.cursor()
    cursor.execute(
        "DELETE FROM reference_values WHERE kind=? AND value=?",
        (kind, _clean(value)),
    )
    db.commit()
    return cursor.rowcount > 0


def remember_reference_values(db, data):
    ensure_reference_table(db)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for kind, field in REFERENCE_FIELDS.items():
        value = _clean(data.get(field, ""))
        if not value:
            continue
        db.execute(
            """INSERT INTO reference_values(kind,value,uses,last_used)
               VALUES (?,?,1,?)
               ON CONFLICT(kind,value) DO UPDATE SET
                   uses=reference_values.uses + 1,
                   last_used=excluded.last_used""",
            (kind, value, stamp),
        )
    db.commit()
