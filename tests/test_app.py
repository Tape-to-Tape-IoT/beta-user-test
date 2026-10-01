import contextlib
import io
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest import mock

import app
from challenge import card, log

from .support import VALID_TOML, FakePi, free_port, write

MARKER = "MARKER-7c1e9a3f-do-not-leak"
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get(port, path):
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d%s" % (port, path), timeout=5) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


class StartupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app_dir = self.tmp.name
        os.mkdir(os.path.join(self.app_dir, "templates"))
        self.port = free_port()
        self.pi = FakePi()
        self.pi.__enter__()
        # Disable log redaction so these tests prove the key is never written at all.
        self.no_redact = mock.patch.object(log, "add_secret", lambda value: None)
        self.no_redact.start()

    def tearDown(self):
        self.no_redact.stop()
        self.pi.__exit__()
        self.tmp.cleanup()

    def write_config(self, text):
        write(os.path.join(self.app_dir, "config.toml"), text)

    @contextlib.contextmanager
    def running(self, environ=None):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), \
                mock.patch.object(card, "render_card", wraps=card.render_card) as render:
            httpd = app.start(self.app_dir, environ or {}, checkin_url="")
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                yield out, render
            finally:
                httpd.shutdown()
                httpd.server_close()

    def test_no_key_leak(self):
        self.write_config(VALID_TOML.format(port=self.port, api_key=MARKER))
        with self.running({"SUPERVISOR_ENABLED": "1", "SUPERVISOR_PROCESS_NAME": "app"}) \
                as (out, render):
            status, page = get(self.port, "/")
            self.assertEqual(get(self.port, "/health"), (200, "ok\n"))
            self.assertEqual(get(self.port, "/card")[0], 200)
        stdout = out.getvalue()
        self.assertEqual(status, 200)
        self.assertIn("Config OK:", stdout)
        self.assertIn("api_key=set", stdout)
        self.assertNotIn(MARKER, stdout)
        self.assertNotIn(MARKER, page)
        self.assertEqual(render.call_count, 1)
        fields = render.call_args[0][0]
        self.assertEqual(set(fields), set(card.CARD_FIELDS))
        self.assertNotIn(MARKER, repr(render.call_args))

    def test_no_key_leak_with_errors(self):
        self.write_config(VALID_TOML.format(port=self.port, api_key=MARKER)
                          .replace('"mtl"', '"MON"'))
        with self.running() as (out, render):
            status, page = get(self.port, "/")
        self.assertIn("MON", page)
        self.assertNotIn(MARKER, page)
        self.assertNotIn(MARKER, out.getvalue())
        self.assertEqual(render.call_count, 0)

    def test_normal_start_log(self):
        self.write_config(VALID_TOML.format(port=self.port, api_key="k-123456"))
        with self.running({"SUPERVISOR_ENABLED": "1", "SUPERVISOR_PROCESS_NAME": "app"}) as (out, _):
            pass
        lines = out.getvalue().splitlines()
        self.assertLessEqual(len(lines), 10)
        body = "\n".join(lines)
        self.assertIn("==== beta-challenge v1.0 starting ====", body)
        self.assertIn('Start #1 (launched by supervisord, process "app")', body)
        self.assertIn("Boot a1b2c3d4, first start since boot, system up 41 s", body)
        self.assertIn("Detected: Raspberry Pi 4 Model B Rev 1.4 | Debian GNU/Linux 12 (bookworm)", body)
        self.assertIn("Config OK: discord=yourname, pi_model=Pi 4 Model B, display=64x32, "
                      "team=MTL, api_key=set", body)
        self.assertIn("Profile card saved to output/profile_card.png", body)
        self.assertIn("Serving on port %d (GET /card to download)" % self.port, body)
        self.assertIn("Check-in: disabled", body)
        self.assertNotIn("ERROR", body)
        for line in lines:
            self.assertRegex(line, r"^\[\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\] ")

    def test_second_start_same_boot(self):
        self.write_config(VALID_TOML.format(port=self.port, api_key="k-123456"))
        with self.running():
            pass
        with self.running() as (out, _):
            pass
        self.assertIn("Start #2 (NOT launched by supervisord)", out.getvalue())
        self.assertIn("Boot a1b2c3d4, system up", out.getvalue())
        self.assertNotIn("first start since boot", out.getvalue())

    def test_config_errors_keep_serving(self):
        with open(os.path.join(REPO, "config.example.toml"), encoding="utf-8") as f:
            self.write_config(f.read().replace("port = 8081", "port = %d" % self.port))
        with self.running() as (out, _):
            self.assertEqual(get(self.port, "/health")[0], 503)
        self.assertEqual(out.getvalue().count("ERROR:"), 6)
        self.assertIn("No card generated: fix config.toml, then run: "
                      "sudo supervisorctl restart app", out.getvalue())

    def test_health_503_on_errors(self):
        self.write_config(VALID_TOML.format(port=self.port, api_key="PASTE_YOUR_KEY_HERE")
                          .replace("display_cols = 64", 'display_cols = "64"'))
        with self.running():
            self.assertEqual(get(self.port, "/health"),
                             (503, "config error: 2 problem(s), see log\n"))
            self.assertEqual(get(self.port, "/card")[0], 404)
            self.assertEqual(get(self.port, "/nope")[0], 404)

    def test_model_mismatch_is_warning(self):
        self.write_config(VALID_TOML.format(port=self.port, api_key="k-123456")
                          .replace("Pi 4 Model B", "Pi 3B+"))
        with self.running() as (out, render):
            self.assertEqual(get(self.port, "/health")[0], 200)
        self.assertIn('WARNING: pi_model "Pi 3B+" does not match detected '
                      '"Raspberry Pi 4 Model B Rev 1.4"', out.getvalue())
        self.assertEqual(render.call_args[1]["detected"], "Raspberry Pi 4 Model B Rev 1.4")

    def test_not_a_pi(self):
        self.write_config(VALID_TOML.format(port=self.port, api_key="k-123456"))
        os.remove(self.pi.model_path)
        with self.running() as (out, render):
            self.assertEqual(get(self.port, "/health")[0], 503)
        self.assertIn("ERROR: Not a Raspberry Pi", out.getvalue())
        with self.running({"CHALLENGE_DEV": "1"}) as (out, render):
            self.assertEqual(get(self.port, "/health")[0], 200)
        self.assertTrue(render.call_args[1]["dev_mode"])

    def test_port_in_use_exits_1(self):
        self.write_config(VALID_TOML.format(port=self.port, api_key="k-123456"))
        with self.running():
            with contextlib.redirect_stdout(io.StringIO()) as out:
                with self.assertRaises(SystemExit) as ctx:
                    app.start(self.app_dir, {}, checkin_url="")
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("ERROR: Port %d is already in use" % self.port, out.getvalue())


class ProcessTests(unittest.TestCase):
    """Run app.py as a real process from a copy of the repo."""

    def test_sigterm_exits_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("challenge", "fonts"):
                shutil.copytree(os.path.join(REPO, name), os.path.join(tmp, name),
                                ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copy(os.path.join(REPO, "app.py"), tmp)
            port = free_port()
            write(os.path.join(tmp, "config.toml"), VALID_TOML.format(port=port, api_key=MARKER))
            env = dict(os.environ, CHALLENGE_DEV="1")
            proc = subprocess.Popen([sys.executable, "app.py"], cwd=tmp, env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            try:
                for _ in range(100):
                    time.sleep(0.1)
                    try:
                        if get(port, "/health")[0] == 200:
                            break
                    except OSError:
                        pass
                proc.send_signal(signal.SIGTERM)
                output = proc.communicate(timeout=10)[0].decode()
            finally:
                if proc.poll() is None:
                    proc.kill()
            self.assertEqual(proc.returncode, 0, output)
            self.assertIn("Stopping (received SIGTERM)", output)
            self.assertIn("DEV MODE", output)
            self.assertNotIn(MARKER, output)
            self.assertTrue(os.path.exists(os.path.join(tmp, "output", "profile_card.png")))


if __name__ == "__main__":
    unittest.main()
