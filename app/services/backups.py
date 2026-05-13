import json
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from app.core.logging import get_logger
from app.core.paths import (BACKUPS_DIR, DB_FILE, PHOTOS_DIR, QRCODES_DIR, SETTINGS_FILE,
                   USERS_FILE, ensure_data_dirs)


logger = get_logger(__name__)
DEFAULT_KEEP_BACKUPS = 30
BACKUP_DIRS = {
    "photos": PHOTOS_DIR,
    "qrcodes": QRCODES_DIR,
}


def _timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def create_backup(db, reason="manual", prune=True):
    ensure_data_dirs()
    stamp = _timestamp()
    archive_path = BACKUPS_DIR / f"pass_control_{stamp}_{reason}.zip"

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_copy = f"{tmp_dir}/passes.db"
        target = sqlite3.connect(db_copy)
        try:
            db.backup(target)
        finally:
            target.close()

        manifest = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "reason": reason,
            "files": ["passes.db"],
            "dirs": [],
        }

        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(db_copy, "passes.db")
            if SETTINGS_FILE.exists():
                archive.write(SETTINGS_FILE, SETTINGS_FILE.name)
                manifest["files"].append(SETTINGS_FILE.name)
            if USERS_FILE.exists():
                archive.write(USERS_FILE, USERS_FILE.name)
                manifest["files"].append(USERS_FILE.name)
            for archive_dir, source_dir in BACKUP_DIRS.items():
                if not source_dir.exists():
                    continue
                files = [path for path in source_dir.rglob("*") if path.is_file()]
                if files:
                    manifest["dirs"].append(archive_dir)
                for path in files:
                    archive.write(path, f"{archive_dir}/{path.relative_to(source_dir).as_posix()}")
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    logger.info("Backup created: %s", archive_path)
    if prune:
        prune_backups()
    return archive_path


def create_daily_backup_if_needed(db):
    BACKUPS_DIR.mkdir(exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    if any(BACKUPS_DIR.glob(f"pass_control_{today}_*_auto.zip")):
        prune_backups()
        return None
    return create_backup(db, "auto")


def list_backups():
    ensure_data_dirs()
    rows = []
    for path in sorted(BACKUPS_DIR.glob("*.zip"), reverse=True):
        manifest = {}
        try:
            with zipfile.ZipFile(path) as archive:
                if "manifest.json" in archive.namelist():
                    manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        except Exception:
            logger.exception("Failed to read backup manifest: %s", path)
        rows.append(
            {
                "path": path,
                "name": path.name,
                "created_at": manifest.get("created_at") or datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
                "reason": manifest.get("reason", "unknown"),
                "files": manifest.get("files", []),
            }
        )
    return rows


def prune_backups(keep=DEFAULT_KEEP_BACKUPS):
    ensure_data_dirs()
    backups = sorted(BACKUPS_DIR.glob("*.zip"), key=lambda path: path.stat().st_mtime, reverse=True)
    removed = []
    for path in backups[keep:]:
        try:
            path.unlink()
            removed.append(path)
        except Exception:
            logger.exception("Failed to prune old backup: %s", path)
    return removed


def restore_backup(archive_path):
    ensure_data_dirs()
    archive_path = Path(archive_path)
    if not archive_path.is_absolute():
        archive_path = BACKUPS_DIR / archive_path
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_root = Path(tmp_dir)
        with zipfile.ZipFile(archive_path) as archive:
            names = set(archive.namelist())
            if "passes.db" not in names:
                raise ValueError("backup does not contain passes.db")
            archive.extract("passes.db", tmp_root)
            if "settings.json" in names:
                archive.extract("settings.json", tmp_root)
            if "users.json" in names:
                archive.extract("users.json", tmp_root)
            for archive_dir in BACKUP_DIRS:
                for name in names:
                    if name.startswith(f"{archive_dir}/") and not name.endswith("/"):
                        archive.extract(name, tmp_root)
        shutil.copy2(tmp_root / "passes.db", DB_FILE)
        if (tmp_root / "settings.json").exists():
            shutil.copy2(tmp_root / "settings.json", SETTINGS_FILE)
        if (tmp_root / "users.json").exists():
            shutil.copy2(tmp_root / "users.json", USERS_FILE)
        for archive_dir, target_dir in BACKUP_DIRS.items():
            restored_dir = tmp_root / archive_dir
            if not restored_dir.exists():
                continue
            if target_dir.exists():
                shutil.rmtree(target_dir)
            shutil.copytree(restored_dir, target_dir)
    logger.info("Backup restored: %s", archive_path)
