"""Timestamped stdout logging that never writes a registered secret."""

import sys
import traceback
from datetime import datetime

_secrets = set()


def add_secret(value):
    """Register a value that must be masked in every line written from now on.

    Very short values are skipped: masking them would mangle ordinary words.
    """
    if value and len(value) >= 6:
        _secrets.add(value)


def clear_secrets():
    _secrets.clear()


def redact(text):
    for secret in _secrets:
        text = text.replace(secret, "***")
    return text


def _write(text):
    sys.stdout.write(redact(text))
    sys.stdout.flush()


def info(message):
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _write("[%s] %s\n" % (stamp, message))


def warning(message):
    info("WARNING: " + message)


def error(message):
    info("ERROR: " + message)


def crash(exc):
    """One ERROR summary line, then the traceback."""
    error("Unexpected crash: %s: %s" % (type(exc).__name__, exc))
    _write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
