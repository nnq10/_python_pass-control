import math
import shutil
import struct
import sys
import threading
import time
import wave
from pathlib import Path

from app.core.logging import get_logger
from app.core.paths import SOUNDS_DIR


logger = get_logger(__name__)

ALLOWED_SOUND_NAMES = ("scan_allowed.wav", "allowed.wav", "ok.wav")
DENIED_SOUND_NAMES = (
    "Звук_неправильного_ответа_сто_к_одному.wav",
    "scan_denied.wav",
    "denied.wav",
    "fail.wav",
)
DEFAULT_ALLOWED_SOUND = "_default_scan_allowed.wav"
DEFAULT_DENIED_SOUND = "_default_scan_denied.wav"
SOUNDS_HELP_FILE = "README_sounds.txt"
CONFIG_ALLOWED_SOUND = "scan_sound_allowed"
CONFIG_DENIED_SOUND = "scan_sound_denied"
SOUND_FILE_EXTENSIONS = (".wav", ".mp3")
SAMPLE_RATE = 44100


def _sound_help_text():
    allowed_names = "\n".join(f"- {name}" for name in ALLOWED_SOUND_NAMES)
    denied_names = "\n".join(f"- {name}" for name in DENIED_SOUND_NAMES)
    return (
        "PassControl scanner sounds\n"
        "==========================\n\n"
        f"Active sounds folder:\n{SOUNDS_DIR}\n\n"
        "Allowed pass sound file names, by priority:\n"
        f"{allowed_names}\n"
        f"- {DEFAULT_ALLOWED_SOUND}\n\n"
        "Denied pass sound file names, by priority:\n"
        f"{denied_names}\n"
        f"- {DEFAULT_DENIED_SOUND}\n\n"
        "Important:\n"
        "- Use real WAV files with PCM audio.\n"
        "- MP3 files are supported on Windows.\n"
        "- You can choose uploaded sounds in Settings.\n"
        "- If the app is installed to C:\\PassControl, replace files in C:\\PassControl\\data\\sounds.\n"
        "- If you run dist\\PassControl\\PassControl.exe, replace files in dist\\PassControl\\data\\sounds.\n"
    )


def ensure_sounds_hint_file():
    path = SOUNDS_DIR / SOUNDS_HELP_FILE
    try:
        SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
        text = _sound_help_text()
        if not path.exists() or path.read_text(encoding="utf-8", errors="ignore") != text:
            path.write_text(text, encoding="utf-8")
    except Exception:
        logger.exception("Failed to write scanner sounds help file: %s", path)


def _file_header(path, size=16):
    try:
        with open(path, "rb") as file:
            return file.read(size)
    except OSError:
        return b""


def _is_mp3_header(header):
    return header.startswith(b"ID3") or (len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0)


def _sound_file_kind(path):
    if not path:
        return None
    header = _file_header(path, 16)
    if _is_mp3_header(header):
        return "mp3"
    if not (header.startswith(b"RIFF") and header[8:12] == b"WAVE"):
        logger.warning("Scanner sound has unsupported audio header: %s", path)
        return None
    try:
        with wave.open(str(path), "rb") as file:
            if file.getnchannels() not in (1, 2):
                return None
            if file.getsampwidth() not in (1, 2, 3, 4):
                return None
            if file.getframerate() > 0 and file.getnframes() > 0:
                return "wav"
    except (wave.Error, EOFError, OSError):
        logger.warning("Scanner sound is not a playable PCM WAV file: %s", path)
    return None


def _is_supported_sound(path):
    return _sound_file_kind(path) in ("wav", "mp3")


def _config_sound_key(granted):
    return CONFIG_ALLOWED_SOUND if granted else CONFIG_DENIED_SOUND


def _safe_sound_name(name):
    if not name:
        return ""
    return Path(str(name)).name


def _configured_sound_path(granted):
    try:
        from app.core.config import CFG

        name = _safe_sound_name(CFG.get(_config_sound_key(granted), ""))
    except Exception:
        logger.exception("Failed to read selected scanner sound setting")
        name = ""
    if not name:
        return None
    path = SOUNDS_DIR / name
    if path.exists() and _is_supported_sound(path):
        logger.debug("Using selected scanner sound: %s", path)
        return path
    logger.warning("Selected scanner sound is missing or unsupported: %s", path)
    return None


def scan_sound_path(granted):
    ensure_sounds_hint_file()
    selected = _configured_sound_path(granted)
    if selected:
        return selected
    names = ALLOWED_SOUND_NAMES if granted else DENIED_SOUND_NAMES
    for name in names:
        path = SOUNDS_DIR / name
        if path.exists() and _is_supported_sound(path):
            logger.debug("Using custom scanner sound: %s", path)
            return path
    return None


def list_available_sounds():
    ensure_sounds_hint_file()
    sounds = []
    try:
        for path in SOUNDS_DIR.iterdir():
            if not path.is_file() or path.name == SOUNDS_HELP_FILE:
                continue
            if path.suffix.lower() not in SOUND_FILE_EXTENSIONS:
                continue
            if _is_supported_sound(path):
                sounds.append(path.name)
    except Exception:
        logger.exception("Failed to list scanner sounds in %s", SOUNDS_DIR)
    return sorted(set(sounds), key=str.casefold)


def sound_path_by_name(name):
    name = _safe_sound_name(name)
    if not name:
        return None
    path = SOUNDS_DIR / name
    if path.exists() and _is_supported_sound(path):
        return path
    return None


def import_sound_file(source):
    ensure_sounds_hint_file()
    source = Path(source)
    if not source.exists() or not source.is_file():
        raise ValueError("Файл звука не найден")
    if source.suffix.lower() not in SOUND_FILE_EXTENSIONS:
        raise ValueError("Поддерживаются только WAV и MP3")
    if not _is_supported_sound(source):
        raise ValueError("Файл не похож на поддерживаемый WAV или MP3")

    SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
    target = SOUNDS_DIR / source.name
    try:
        if source.resolve() == target.resolve():
            return target
    except OSError:
        pass

    if target.exists():
        stem = target.stem
        suffix = target.suffix
        index = 2
        while True:
            candidate = SOUNDS_DIR / f"{stem}_{index}{suffix}"
            if not candidate.exists():
                target = candidate
                break
            index += 1
    shutil.copy2(source, target)
    return target


def _tone(frequency, seconds, volume=0.45, harmonics=()):
    total = max(1, int(SAMPLE_RATE * seconds))
    fade = max(1, int(SAMPLE_RATE * 0.012))
    samples = []
    for index in range(total):
        t = index / SAMPLE_RATE
        value = math.sin(2 * math.pi * frequency * t)
        weight = 1.0
        for multiplier, gain in harmonics:
            value += gain * math.sin(2 * math.pi * frequency * multiplier * t)
            weight += gain
        value /= weight
        envelope = min(1.0, index / fade, (total - index - 1) / fade)
        samples.append(int(32767 * volume * envelope * value))
    return samples


def _silence(seconds):
    return [0] * max(1, int(SAMPLE_RATE * seconds))


def _write_wav(path, samples):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(SAMPLE_RATE)
        file.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))


def _default_samples(granted):
    if granted:
        return (
            _tone(659.25, 0.075, 0.38, harmonics=((2, 0.12),))
            + _silence(0.025)
            + _tone(987.77, 0.095, 0.42, harmonics=((2, 0.10),))
            + _silence(0.03)
            + _tone(1318.51, 0.16, 0.35, harmonics=((2, 0.08),))
        )
    return (
        _tone(185.0, 0.16, 0.58, harmonics=((2, 0.65), (3, 0.35), (5, 0.18)))
        + _silence(0.045)
        + _tone(145.0, 0.18, 0.60, harmonics=((2, 0.70), (3, 0.40), (5, 0.20)))
        + _silence(0.04)
        + _tone(110.0, 0.24, 0.62, harmonics=((2, 0.72), (3, 0.42), (5, 0.22)))
    )


def default_scan_sound_path(granted):
    ensure_sounds_hint_file()
    path = SOUNDS_DIR / (DEFAULT_ALLOWED_SOUND if granted else DEFAULT_DENIED_SOUND)
    if path.exists() and _sound_file_kind(path) == "wav":
        return path
    try:
        _write_wav(path, _default_samples(granted))
        return path
    except Exception:
        logger.exception("Failed to create default scanner sound: %s", path)
        return None


def _beep_sequence(granted):
    sequence = [(784, 70), (1046, 80), (1568, 150)] if granted else [(220, 180), (170, 180), (120, 260)]
    try:
        if sys.platform.startswith("win"):
            import winsound

            for frequency, duration in sequence:
                winsound.Beep(frequency, duration)
                time.sleep(0.04)
        else:
            print("\a", end="", flush=True)
    except Exception:
        logger.exception("Failed to play scanner beep")


def _mci_error_message(winmm, code):
    try:
        import ctypes

        buffer = ctypes.create_unicode_buffer(256)
        if winmm.mciGetErrorStringW(code, buffer, len(buffer)):
            return buffer.value
    except Exception:
        logger.debug("Failed to read MCI error text", exc_info=True)
    return f"MCI error {code}"


def _mci_send(winmm, command, buffer=None):
    code = winmm.mciSendStringW(command, buffer, len(buffer) if buffer is not None else 0, None)
    if code:
        raise RuntimeError(_mci_error_message(winmm, code))


def _play_windows_mci_mp3(path):
    def worker():
        try:
            import ctypes

            winmm = ctypes.WinDLL("winmm")
            alias = f"passcontrol_scan_{time.time_ns()}"
            opened = False
            try:
                try:
                    _mci_send(winmm, f'open "{path}" type mpegvideo alias {alias}')
                except Exception:
                    _mci_send(winmm, f'open "{path}" alias {alias}')
                opened = True
                length_buffer = ctypes.create_unicode_buffer(64)
                try:
                    _mci_send(winmm, f"status {alias} length", length_buffer)
                    length_ms = max(1, int(length_buffer.value or "0"))
                except Exception:
                    length_ms = 2500
                _mci_send(winmm, f"play {alias} from 0")
                time.sleep((length_ms + 250) / 1000)
            finally:
                if opened:
                    try:
                        winmm.mciSendStringW(f"close {alias}", None, 0, None)
                    except Exception:
                        logger.debug("Failed to close MCI scanner sound", exc_info=True)
        except Exception:
            logger.exception("Failed to play scanner MP3 sound file: %s", path)

    threading.Thread(target=worker, daemon=True).start()


def play_sound_file(path, granted=True):
    path = Path(path) if path else None
    try:
        if path and sys.platform.startswith("win"):
            kind = _sound_file_kind(path)
            if kind == "wav":
                import winsound

                winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
                return
            if kind == "mp3":
                _play_windows_mci_mp3(str(path))
                return
    except Exception:
        logger.exception("Failed to play scanner sound file: %s", path)
    threading.Thread(target=_beep_sequence, args=(granted,), daemon=True).start()


def play_scan_sound(granted):
    path = scan_sound_path(granted) or default_scan_sound_path(granted)
    play_sound_file(path, granted)
