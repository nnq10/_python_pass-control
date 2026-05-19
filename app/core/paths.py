import shutil
import sys
from pathlib import Path


def _base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


BASE_DIR = _base_dir()
DATA_DIR = BASE_DIR / "data"

SETTINGS_FILE = DATA_DIR / "settings.json"
USERS_FILE = DATA_DIR / "users.json"
DB_FILE = DATA_DIR / "passes.db"
LOG_FILE = DATA_DIR / "app.log"

PHOTOS_DIR = DATA_DIR / "photos"
QRCODES_DIR = DATA_DIR / "qrcodes"
BACKUPS_DIR = DATA_DIR / "backups"
TEMPLATES_DIR = DATA_DIR / "templates"
PRINTS_DIR = DATA_DIR / "prints"
SOUNDS_DIR = DATA_DIR / "sounds"
ASSETS_DIR = DATA_DIR / "assets"

LEGACY_SETTINGS_FILE = BASE_DIR / "settings.json"
LEGACY_USERS_FILE = BASE_DIR / "users.json"
LEGACY_DB_FILE = BASE_DIR / "passes.db"
LEGACY_LOG_FILE = BASE_DIR / "app.log"
LEGACY_PHOTOS_DIR = BASE_DIR / "photos"
LEGACY_QRCODES_DIR = BASE_DIR / "qrcodes"
LEGACY_BACKUPS_DIR = BASE_DIR / "backups"
LEGACY_TEMPLATES_DIR = BASE_DIR / "templates"
LEGACY_PRINTS_DIR = BASE_DIR / "prints"
LEGACY_SOUNDS_DIR = BASE_DIR / "sounds"
LEGACY_ASSETS_DIR = BASE_DIR / "assets"


def _move_file_if_needed(src, dst):
    if src.exists() and not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))


def _move_dir_contents_if_needed(src, dst):
    if not src.exists():
        return
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dst / item.name
        if target.exists():
            continue
        shutil.move(str(item), str(target))


def ensure_data_dirs():
    DATA_DIR.mkdir(exist_ok=True)
    PHOTOS_DIR.mkdir(exist_ok=True)
    QRCODES_DIR.mkdir(exist_ok=True)
    BACKUPS_DIR.mkdir(exist_ok=True)
    TEMPLATES_DIR.mkdir(exist_ok=True)
    PRINTS_DIR.mkdir(exist_ok=True)
    SOUNDS_DIR.mkdir(exist_ok=True)
    ASSETS_DIR.mkdir(exist_ok=True)
    _move_file_if_needed(LEGACY_SETTINGS_FILE, SETTINGS_FILE)
    _move_file_if_needed(LEGACY_USERS_FILE, USERS_FILE)
    _move_file_if_needed(LEGACY_DB_FILE, DB_FILE)
    _move_file_if_needed(LEGACY_LOG_FILE, LOG_FILE)
    _move_dir_contents_if_needed(LEGACY_PHOTOS_DIR, PHOTOS_DIR)
    _move_dir_contents_if_needed(LEGACY_QRCODES_DIR, QRCODES_DIR)
    _move_dir_contents_if_needed(LEGACY_BACKUPS_DIR, BACKUPS_DIR)
    _move_dir_contents_if_needed(LEGACY_TEMPLATES_DIR, TEMPLATES_DIR)
    _move_dir_contents_if_needed(LEGACY_PRINTS_DIR, PRINTS_DIR)
    _move_dir_contents_if_needed(LEGACY_SOUNDS_DIR, SOUNDS_DIR)
    _move_dir_contents_if_needed(LEGACY_ASSETS_DIR, ASSETS_DIR)


def app_path(path):
    path = Path(path)
    if path.is_absolute():
        return path
    data_path = DATA_DIR / path
    if data_path.exists():
        return data_path
    return BASE_DIR / path


def photo_file_path(qr_code, extension):
    return PHOTOS_DIR / f"{qr_code}{extension}"


def qr_code_path(qr_code):
    return QRCODES_DIR / f"{qr_code}.png"
