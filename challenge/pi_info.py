"""Detect the Pi model, boot id, uptime, OS and whether supervisord launched us."""

import platform
import re

# Module-level so tests can point them at fake files.
MODEL_PATH = "/proc/device-tree/model"
BOOT_ID_PATH = "/proc/sys/kernel/random/boot_id"
UPTIME_PATH = "/proc/uptime"
OS_RELEASE_PATH = "/etc/os-release"


class Environment:
    def __init__(self, environ):
        self.model = read_model()
        self.boot_id = read_boot_id()
        self.uptime = read_uptime()
        self.os_name = read_os_name()
        self.arch = platform.machine() or "unknown"
        self.supervised = environ.get("SUPERVISOR_ENABLED") == "1"
        self.process_name = environ.get("SUPERVISOR_PROCESS_NAME", "")


def _read(path):
    try:
        with open(path, "rb") as f:
            return f.read().decode("utf-8", "replace")
    except OSError:
        return None


def read_model():
    """The model string, or None when this is not a Raspberry Pi."""
    text = _read(MODEL_PATH)
    if text is None:
        return None
    return text.rstrip("\x00").strip() or None


def read_boot_id():
    text = _read(BOOT_ID_PATH)
    return text.strip()[:8] if text and text.strip() else "unknown"


def read_uptime():
    """Seconds since boot, or None if unknown."""
    text = _read(UPTIME_PATH)
    try:
        return float(text.split()[0])
    except (AttributeError, IndexError, ValueError):
        return None


def read_os_name():
    text = _read(OS_RELEASE_PATH) or ""
    for line in text.splitlines():
        if line.startswith("PRETTY_NAME="):
            return line.split("=", 1)[1].strip().strip('"\'')
    return platform.system() or "unknown"


def format_uptime(seconds):
    if seconds is None:
        return "unknown"
    seconds = int(seconds)
    if seconds < 120:
        return "%d s" % seconds
    minutes = seconds // 60
    if minutes < 120:
        return "%d min" % minutes
    hours = minutes // 60
    if hours < 48:
        return "%d h %d min" % (hours, minutes % 60)
    return "%d d %d h" % (hours // 24, hours % 24)


def normalize_model(text):
    """'Raspberry Pi 4 Model B Rev 1.4' -> '4b', 'Pi 3B+' -> '3b'."""
    text = text.lower()
    rev = text.find("rev")
    if rev != -1:
        text = text[:rev]
    for word in ("raspberry", "pi", "model"):
        text = text.replace(word, "")
    return re.sub(r"[^a-z0-9]", "", text)


def model_matches(typed, detected):
    typed_n = normalize_model(typed)
    return bool(typed_n) and normalize_model(detected).startswith(typed_n)
