import math
import struct
import sys
import threading
import time
import wave

from app.core.logging import get_logger
from app.core.paths import SOUNDS_DIR


logger = get_logger(__name__)

ALLOWED_SOUND_NAMES = ("scan_allowed.wav", "allowed.wav", "ok.wav")
DENIED_SOUND_NAMES = ("scan_denied.wav", "denied.wav", "fail.wav")
DEFAULT_ALLOWED_SOUND = "_default_scan_allowed.wav"
DEFAULT_DENIED_SOUND = "_default_scan_denied.wav"
SAMPLE_RATE = 44100


def scan_sound_path(granted):
    names = ALLOWED_SOUND_NAMES if granted else DENIED_SOUND_NAMES
    for name in names:
        path = SOUNDS_DIR / name
        if path.exists():
            return path
    return None


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
    path = SOUNDS_DIR / (DEFAULT_ALLOWED_SOUND if granted else DEFAULT_DENIED_SOUND)
    if path.exists():
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


def play_scan_sound(granted):
    path = scan_sound_path(granted) or default_scan_sound_path(granted)
    try:
        if path and sys.platform.startswith("win"):
            import winsound

            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
            return
    except Exception:
        logger.exception("Failed to play scanner sound file: %s", path)

    threading.Thread(target=_beep_sequence, args=(granted,), daemon=True).start()
