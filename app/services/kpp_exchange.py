import hashlib
import json
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from app.core.paths import PHOTOS_DIR, QRCODES_DIR, app_path, ensure_data_dirs, qr_code_path
from app.services.backups import create_backup
from app.services.pass_db import (CI, PASS_TYPE_REGULAR, PASS_TYPE_SEMIANNUAL,
                                  PASS_TYPE_TEMPORARY, fetch_pass_by_qr,
                                  search_passes)
from app.services.qr_codes import save_qr_code
from app.services.validation import ValidationError, validate_pass_data


PACKAGE_VERSION = 1
PACKAGE_EXTENSION = ".pcpkg"
PACKAGE_PASS_TYPES = (PASS_TYPE_REGULAR, PASS_TYPE_SEMIANNUAL)
PASS_TYPE_TITLES = {
    PASS_TYPE_REGULAR: "Месячные",
    PASS_TYPE_SEMIANNUAL: "Полугодовые",
}


class KppExchangeError(ValueError):
    pass


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _json_bytes(payload):
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _safe_file_part(value):
    text = str(value or "").strip()
    cleaned = "".join(char if char.isalnum() or char in "._-" else "_" for char in text)
    return cleaned.strip("._-") or "pass"


def _existing_path(value):
    if not value:
        return None
    path = Path(value)
    candidates = [path] if path.is_absolute() else [path, app_path(path)]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _photo_archive_name(qr_code, photo_path):
    suffix = Path(photo_path).suffix or ".jpg"
    return f"photos/{_safe_file_part(qr_code)}{suffix}"


def _qr_archive_name(qr_code):
    return f"qrcodes/{_safe_file_part(qr_code)}.png"


def _row_to_record(row):
    return {
        "qr_code": row[CI["qr"]] or "",
        "district": row[CI["district"]] or "",
        "unit": row[CI["unit"]] or "",
        "rank": row[CI["rank"]] or "",
        "last_name": row[CI["ln"]] or "",
        "first_name": row[CI["fn"]] or "",
        "middle_name": row[CI["mn"]] or "",
        "phone": row[CI["phone"]] or "",
        "issued_date": row[CI["issued"]] or "",
        "days_count": int(row[CI["days"]] or 30),
        "active": int(row[CI["active"]] or 0),
        "pass_type": row[CI["type"]] or PASS_TYPE_REGULAR,
        "photo_file": "",
        "qr_file": _qr_archive_name(row[CI["qr"]]),
    }


def _export_rows(db, pass_types):
    rows = []
    for pass_type in pass_types:
        rows.extend(search_passes(db, "", deleted=0, pass_type=pass_type))
    return rows


def export_kpp_package(db, path, pass_types=PACKAGE_PASS_TYPES, created_by=""):
    ensure_data_dirs()
    path = Path(path)
    if path.suffix.lower() != PACKAGE_EXTENSION:
        path = path.with_suffix(PACKAGE_EXTENSION)
    path.parent.mkdir(parents=True, exist_ok=True)

    pass_types = tuple(pass_type for pass_type in pass_types if pass_type in PACKAGE_PASS_TYPES)
    if not pass_types:
        raise KppExchangeError("Не выбраны типы пропусков для экспорта")

    rows = _export_rows(db, pass_types)
    records = []
    files = []
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_root = Path(tmp_dir)
        for row in rows:
            qr_code = row[CI["qr"]]
            record = _row_to_record(row)

            qr_path = qr_code_path(qr_code)
            if not qr_path.exists():
                qr_path = save_qr_code(qr_code)
            record["qr_file"] = _qr_archive_name(qr_code)
            files.append((qr_path, record["qr_file"]))

            photo_path = _existing_path(row[CI["photo"]])
            if photo_path:
                record["photo_file"] = _photo_archive_name(qr_code, photo_path)
                files.append((photo_path, record["photo_file"]))
            records.append(record)

        passes_payload = {"passes": records}
        passes_bytes = _json_bytes(passes_payload)
        manifest = {
            "version": PACKAGE_VERSION,
            "kind": "pass_control_kpp_exchange",
            "created_at": _now(),
            "created_by": created_by or "",
            "pass_types": list(pass_types),
            "counts": {pass_type: sum(1 for row in rows if (row[CI["type"]] or PASS_TYPE_REGULAR) == pass_type) for pass_type in pass_types},
            "passes_sha256": _sha256(passes_bytes),
        }
        tmp_package = tmp_root / path.name
        with zipfile.ZipFile(tmp_package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            archive.writestr("passes.json", passes_bytes)
            seen_names = set()
            for source, archive_name in files:
                if archive_name in seen_names:
                    continue
                seen_names.add(archive_name)
                archive.write(source, archive_name)
        tmp_package.replace(path)
    return {"path": path, "count": len(records), "counts": manifest["counts"]}


def _read_package(path):
    path = Path(path)
    if not path.exists():
        raise KppExchangeError("Файл пакета не найден")
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        if "manifest.json" not in names or "passes.json" not in names:
            raise KppExchangeError("Это не пакет обмена КПП")
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        passes_bytes = archive.read("passes.json")
        if manifest.get("passes_sha256") != _sha256(passes_bytes):
            raise KppExchangeError("Контрольная сумма пакета не совпадает")
        payload = json.loads(passes_bytes.decode("utf-8"))
    if manifest.get("kind") != "pass_control_kpp_exchange":
        raise KppExchangeError("Неверный тип пакета")
    records = payload.get("passes") or []
    if not isinstance(records, list):
        raise KppExchangeError("В пакете повреждён список пропусков")
    return manifest, records


def inspect_kpp_package(path):
    manifest, records = _read_package(path)
    counts = {PASS_TYPE_REGULAR: 0, PASS_TYPE_SEMIANNUAL: 0}
    for record in records:
        pass_type = record.get("pass_type")
        if pass_type in counts:
            counts[pass_type] += 1
    return {
        "manifest": manifest,
        "count": len(records),
        "counts": counts,
    }


def _copy_member(archive, member, destination_dir):
    if not member:
        return None
    member = str(member).replace("\\", "/")
    if member.startswith("/") or ".." in Path(member).parts:
        raise KppExchangeError("В пакете небезопасный путь файла")
    source_name = Path(member).name
    if not source_name:
        return None
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / source_name
    with archive.open(member) as source, destination.open("wb") as target:
        shutil.copyfileobj(source, target)
    return destination


def _upsert_pass(db, record, photo_path):
    pass_type = record.get("pass_type") or PASS_TYPE_REGULAR
    if pass_type not in PACKAGE_PASS_TYPES:
        raise KppExchangeError(f"Неподдерживаемый тип пропуска: {pass_type}")

    qr_code = record.get("qr_code")
    existing = fetch_pass_by_qr(db, qr_code, include_deleted=True) if qr_code else None
    if existing and existing[CI["type"]] == PASS_TYPE_TEMPORARY:
        raise KppExchangeError(f"QR {qr_code} уже занят одноразовым пропуском")

    existing_photo = existing[CI["photo"]] if existing else None
    final_photo = str(photo_path) if photo_path else existing_photo
    cleaned = validate_pass_data(
        {
            "qr_code": qr_code,
            "district": record.get("district"),
            "unit": record.get("unit"),
            "rank": record.get("rank"),
            "last_name": record.get("last_name"),
            "first_name": record.get("first_name"),
            "middle_name": record.get("middle_name"),
            "phone": record.get("phone"),
            "issued_date": record.get("issued_date"),
            "days_count": record.get("days_count"),
            "photo_path": final_photo,
            "active": record.get("active", 1),
        },
        db,
        existing_qr=qr_code,
        require_photo=pass_type == PASS_TYPE_SEMIANNUAL,
    )
    if pass_type == PASS_TYPE_REGULAR and cleaned["days_count"] != 30:
        raise KppExchangeError(f"QR {qr_code}: месячный пропуск должен быть на 30 дней")
    if pass_type == PASS_TYPE_SEMIANNUAL and cleaned["days_count"] != 180:
        raise KppExchangeError(f"QR {qr_code}: полугодовой пропуск должен быть на 180 дней")

    values = (
        cleaned["district"],
        cleaned["unit"],
        cleaned["rank"],
        cleaned["last_name"],
        cleaned["first_name"],
        cleaned["middle_name"],
        cleaned["phone"],
        cleaned["issued_date"],
        cleaned["days_count"],
        final_photo,
        int(cleaned["active"]),
        0,
        pass_type,
        "",
        qr_code,
    )
    if existing:
        db.execute(
            """UPDATE passes SET district=?,unit=?,rank=?,last_name=?,first_name=?,middle_name=?,
               phone=?,issued_date=?,days_count=?,photo_path=?,active=?,deleted=?,pass_type=?,temp_status=?
               WHERE qr_code=?""",
            values,
        )
        return "updated"
    db.execute(
        """INSERT INTO passes
           (district,unit,rank,last_name,first_name,middle_name,phone,issued_date,days_count,
            photo_path,active,deleted,pass_type,temp_status,qr_code)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        values,
    )
    return "created"


def import_kpp_package(db, path, create_backup_before=True):
    ensure_data_dirs()
    path = Path(path)
    manifest, records = _read_package(path)
    if create_backup_before:
        create_backup(db, "before_kpp_import")

    stats = {"created": 0, "updated": 0, "errors": 0, "skipped": 0}
    errors = []
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        for index, record in enumerate(records, start=1):
            try:
                photo_path = None
                if record.get("photo_file"):
                    if record["photo_file"] not in names:
                        raise KppExchangeError(f"QR {record.get('qr_code')}: фото отсутствует в пакете")
                    photo_path = _copy_member(archive, record["photo_file"], PHOTOS_DIR)
                if record.get("qr_file") and record["qr_file"] in names:
                    _copy_member(archive, record["qr_file"], QRCODES_DIR)
                else:
                    save_qr_code(record.get("qr_code"))
                result = _upsert_pass(db, record, photo_path)
                stats[result] += 1
            except (KppExchangeError, ValidationError) as ex:
                stats["errors"] += 1
                errors.append(f"Запись {index}: {ex}")
        db.commit()
    return {
        "manifest": manifest,
        "count": len(records),
        "stats": stats,
        "errors": errors,
    }
