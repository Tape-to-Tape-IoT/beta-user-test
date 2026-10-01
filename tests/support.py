"""Shared helpers for the tests."""

import os
import socket
import tempfile
from unittest import mock

from challenge import pi_info

VALID_TOML = """\
port = {port}
api_key = "{api_key}"
discord_username = "yourname"
pi_model = "Pi 4 Model B"
display_cols = 64
display_rows = 32
nhl_team = "mtl"
"""


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


class FakePi:
    """Point pi_info at fake /proc files. Use as a context manager."""

    def __init__(self, model="Raspberry Pi 4 Model B Rev 1.4", boot_id="a1b2c3d4-0000-0000"):
        self.dir = tempfile.TemporaryDirectory()
        d = self.dir.name
        self.model_path = os.path.join(d, "model")
        self.boot_path = os.path.join(d, "boot_id")
        if model is not None:
            with open(self.model_path, "wb") as f:
                f.write(model.encode() + b"\x00")
        write(self.boot_path, boot_id + "\n")
        uptime = write(os.path.join(d, "uptime"), "41.20 80.00\n")
        release = write(os.path.join(d, "os-release"),
                        'PRETTY_NAME="Debian GNU/Linux 12 (bookworm)"\nID=debian\n')
        self.patches = [
            mock.patch.object(pi_info, "MODEL_PATH", self.model_path),
            mock.patch.object(pi_info, "BOOT_ID_PATH", self.boot_path),
            mock.patch.object(pi_info, "UPTIME_PATH", uptime),
            mock.patch.object(pi_info, "OS_RELEASE_PATH", release),
        ]

    def set_boot_id(self, boot_id):
        write(self.boot_path, boot_id + "\n")

    def __enter__(self):
        for p in self.patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in self.patches:
            p.stop()
        self.dir.cleanup()
