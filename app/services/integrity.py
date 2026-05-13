from datetime import datetime

from app.core.paths import app_path, qr_code_path
from app.services.file_cleanup import cleanup_totals, find_orphan_files
from app.services.pass_db import CI, PASS_TYPE_SEMIANNUAL
from app.services.temporary_passes import TEMP_STATUS_FREE, is_temporary_pass, temporary_status


def _ok(message):
    return {"level": "ok", "message": message}


def _warn(message):
    return {"level": "warning", "message": message}


def _error(message):
    return {"level": "error", "message": message}


def _valid_date(value):
    if not value:
        return True
    try:
        datetime.strptime(str(value)[:10], "%Y-%m-%d")
        return True
    except ValueError:
        return False


def check_database_integrity(db):
    rows = []
    cursor = db.cursor()

    try:
        result = cursor.execute("PRAGMA integrity_check").fetchone()
        if result and result[0] == "ok":
            rows.append(_ok("SQLite integrity_check: ok"))
        else:
            rows.append(_error(f"SQLite integrity_check: {result[0] if result else 'нет ответа'}"))
    except Exception as exc:
        rows.append(_error(f"SQLite integrity_check не выполнен: {exc}"))

    passes = cursor.execute("SELECT * FROM passes").fetchall()
    rows.append(_ok(f"Пропусков в базе: {len(passes)}"))

    missing_photos = []
    missing_qrs = []
    bad_dates = []
    bad_days = []
    empty_required = []

    for row in passes:
        qr = row[CI["qr"]]
        temp_blank_allowed = is_temporary_pass(row) and temporary_status(row) == TEMP_STATUS_FREE
        if not temp_blank_allowed and (not qr or not row[CI["district"]] or not row[CI["unit"]] or not row[CI["ln"]]):
            empty_required.append(qr or f"id={row[CI['id']]}")

        photo_path = row[CI["photo"]]
        if row[CI["type"]] == PASS_TYPE_SEMIANNUAL and not photo_path:
            missing_photos.append(qr)
        elif photo_path and not app_path(photo_path).exists():
            missing_photos.append(qr)

        if qr and not qr_code_path(qr).exists():
            missing_qrs.append(qr)

        if not _valid_date(row[CI["issued"]]):
            bad_dates.append(qr)

        try:
            raw_days = row[CI["days"]]
            days = 30 if raw_days in (None, "") else int(raw_days)
            if days <= 0:
                bad_days.append(qr)
        except (TypeError, ValueError):
            bad_days.append(qr)

    if empty_required:
        rows.append(_warn(f"Пропусков с пустыми обязательными полями: {len(empty_required)}"))
    else:
        rows.append(_ok("Обязательные поля заполнены"))

    if missing_photos:
        rows.append(_warn(f"Фото не найдены у пропусков: {len(missing_photos)}"))
    else:
        rows.append(_ok("Ссылки на фото корректны"))

    if missing_qrs:
        rows.append(_warn(f"QR-файлы не найдены у пропусков: {len(missing_qrs)}"))
    else:
        rows.append(_ok("QR-файлы на месте"))

    if bad_dates:
        rows.append(_warn(f"Некорректные даты выдачи: {len(bad_dates)}"))
    else:
        rows.append(_ok("Даты выдачи корректны"))

    if bad_days:
        rows.append(_warn(f"Некорректные сроки действия: {len(bad_days)}"))
    else:
        rows.append(_ok("Сроки действия корректны"))

    orphans = find_orphan_files(db)
    totals = cleanup_totals(orphans)
    if totals["count"]:
        rows.append(_warn(f"Лишние файлы: {totals['count']} ({totals['photos']} фото, {totals['qrcodes']} QR)"))
    else:
        rows.append(_ok("Лишних файлов не найдено"))

    errors = sum(1 for row in rows if row["level"] == "error")
    warnings = sum(1 for row in rows if row["level"] == "warning")
    return {
        "ok": errors == 0,
        "errors": errors,
        "warnings": warnings,
        "rows": rows,
    }
