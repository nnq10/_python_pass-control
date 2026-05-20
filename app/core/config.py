import json
import os

import customtkinter as ctk

from app.core.logging import get_logger
from app.core.paths import SETTINGS_FILE, ensure_data_dirs


DEFAULT_CONFIG = {
    "theme": "dark",
    "scan_timeout": 8,
    "scan_sound_allowed": "",
    "scan_sound_denied": "",
}
FONT = "Segoe UI"
logger = get_logger(__name__)

THEMES = {
    "dark": {
        "bg": "#161b27",
        "panel": "#1e2535",
        "input": "#252e42",
        "border": "#2e3a52",
        "accent": "#4f8ef7",
        "green": "#2ec27e",
        "red": "#e05567",
        "yellow": "#f0a53a",
        "text": "#e2e8f5",
        "muted": "#5a6a8a",
        "mid": "#8a9bbf",
        "gg": "#162b20",
        "gr": "#2b1620",
    },
    "light": {
        "bg": "#f2f4fa",
        "panel": "#ffffff",
        "input": "#eaeef8",
        "border": "#ccd4ea",
        "accent": "#3b7de8",
        "green": "#1b9e5e",
        "red": "#d63a50",
        "yellow": "#c47a10",
        "text": "#1a2138",
        "muted": "#7a88a8",
        "mid": "#4a5878",
        "gg": "#d6f5e8",
        "gr": "#fde4e8",
    },
}


def load_config():
    ensure_data_dirs()
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, encoding="utf-8") as file:
                data = json.load(file)
            for key, value in DEFAULT_CONFIG.items():
                data.setdefault(key, value)
            return data
        except Exception:
            logger.exception("Failed to load settings from %s", SETTINGS_FILE)
    return dict(DEFAULT_CONFIG)


def save_config(settings):
    ensure_data_dirs()
    with open(SETTINGS_FILE, "w", encoding="utf-8") as file:
        json.dump(settings, file, ensure_ascii=False, indent=2)


CFG = load_config()
C = dict(THEMES[CFG["theme"]])


def apply_theme(name):
    C.update(THEMES[name])
    CFG["theme"] = name
    save_config(CFG)
    ctk.set_appearance_mode(name)


ctk.set_appearance_mode(CFG["theme"])
