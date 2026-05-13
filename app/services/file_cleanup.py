from pathlib import Path

from app.core.paths import PHOTOS_DIR, QRCODES_DIR, app_path


MEDIA_DIRS = {
    "photos": PHOTOS_DIR,
    "qrcodes": QRCODES_DIR,
}


def _resolved(path):
    return Path(path).resolve()


def _is_inside(path, root):
    try:
        _resolved(path).relative_to(_resolved(root))
        return True
    except ValueError:
        return False


def _photo_ref_path(photo_path):
    if not photo_path:
        return None
    path = Path(photo_path)
    candidates = [path] if path.is_absolute() else [app_path(path), PHOTOS_DIR / path, PHOTOS_DIR / path.name]
    for candidate in candidates:
        if _is_inside(candidate, PHOTOS_DIR):
            return _resolved(candidate)
    return None


def _qr_ref_path(qr_code):
    if not qr_code:
        return None
    return _resolved(QRCODES_DIR / f"{qr_code}.png")


def _referenced_files(db):
    refs = {"photos": set(), "qrcodes": set()}
    cursor = db.cursor()
    cursor.execute("SELECT qr_code, photo_path FROM passes")
    for qr_code, photo_path in cursor.fetchall():
        photo_ref = _photo_ref_path(photo_path)
        qr_ref = _qr_ref_path(qr_code)
        if photo_ref:
            refs["photos"].add(photo_ref)
        if qr_ref:
            refs["qrcodes"].add(qr_ref)
    return refs


def _file_item(kind, path):
    stat = path.stat()
    return {
        "kind": kind,
        "path": path,
        "name": path.name,
        "size": stat.st_size,
    }


def find_orphan_files(db):
    for root in MEDIA_DIRS.values():
        root.mkdir(parents=True, exist_ok=True)

    refs = _referenced_files(db)
    orphans = []
    for kind, root in MEDIA_DIRS.items():
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if _resolved(path) not in refs[kind]:
                orphans.append(_file_item(kind, path))
    return sorted(orphans, key=lambda item: (item["kind"], item["name"].lower()))


def cleanup_orphan_files(db):
    orphans = find_orphan_files(db)
    deleted = []
    errors = []
    for item in orphans:
        root = MEDIA_DIRS[item["kind"]]
        path = item["path"]
        if not _is_inside(path, root):
            errors.append({"path": str(path), "error": "file is outside media directory"})
            continue
        try:
            path.unlink()
            deleted.append(item)
        except Exception as exc:
            errors.append({"path": str(path), "error": str(exc)})
    return {
        "deleted": deleted,
        "errors": errors,
        "bytes": sum(item["size"] for item in deleted),
    }


def cleanup_totals(files):
    return {
        "count": len(files),
        "photos": sum(1 for item in files if item["kind"] == "photos"),
        "qrcodes": sum(1 for item in files if item["kind"] == "qrcodes"),
        "bytes": sum(item["size"] for item in files),
    }
