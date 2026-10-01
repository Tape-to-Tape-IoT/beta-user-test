"""Start counter and last boot id, kept in state/ and written atomically."""

import os


def atomic_write(path, data):
    """Write bytes to a temp file next to `path`, then rename over it."""
    tmp = "%s.tmp" % path
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _read_text(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except (OSError, ValueError):
        return ""


def next_start_count(state_dir):
    """Increment state/start_count and return the new value."""
    path = os.path.join(state_dir, "start_count")
    try:
        count = int(_read_text(path))
    except ValueError:
        count = 0
    count += 1
    atomic_write(path, b"%d\n" % count)
    return count


def check_boot(state_dir, boot_id):
    """Return True when `boot_id` differs from the saved one, and save it."""
    path = os.path.join(state_dir, "last_boot_id")
    first = _read_text(path) != boot_id
    if first:
        atomic_write(path, boot_id.encode("utf-8") + b"\n")
    return first
