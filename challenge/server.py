"""HTTP endpoints: /health, /card and a minimal / page."""

import base64
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import log


class AppState:
    """What the server needs to know. Holds no secrets."""

    def __init__(self, card_path=None, username=None, problems=()):
        self.card_path = card_path
        self.username = username
        self.problems = list(problems)

    def card_bytes(self):
        if not self.card_path:
            return None
        try:
            with open(self.card_path, "rb") as f:
                return f.read()
        except OSError:
            return None


def make_server(port, state):
    class Handler(BaseHTTPRequestHandler):
        server_version = "beta-challenge"

        def log_message(self, format, *args):  # silence default request logging
            pass

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/health":
                self._health()
            elif path == "/card":
                self._card()
            elif path == "/":
                self._index()
            else:
                self._send(404, "text/plain; charset=utf-8", b"not found\n")

        def _send(self, status, ctype, body, headers=()):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for name, value in headers:
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def _health(self):
            if state.card_path:
                self._send(200, "text/plain; charset=utf-8", b"ok\n")
            else:
                msg = "config error: %d problem(s), see log\n" % len(state.problems)
                self._send(503, "text/plain; charset=utf-8", msg.encode())

        def _card(self):
            data = state.card_bytes()
            if data is None:
                self._send(404, "text/plain; charset=utf-8", b"no card\n")
                return
            filename = "profile_card_%s.png" % state.username
            self._send(200, "image/png", data, [
                ("Content-Disposition", 'attachment; filename="%s"' % filename)])
            log.info("Card downloaded by %s" % self.client_address[0])

        def _index(self):
            self._send(200, "text/html; charset=utf-8", render_index(state).encode("utf-8"))

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    server.daemon_threads = True
    return server


def render_index(state):
    data = state.card_bytes()
    if data is not None:
        # Inline the image so viewing the page doesn't count as a download.
        src = "data:image/png;base64," + base64.b64encode(data).decode("ascii")
        body = ('<img src="%s" alt="Profile card" width="1200" height="450">\n'
                '<p><a href="/card">Download profile card</a></p>' % src)
    else:
        items = "\n".join("<li>%s</li>" % html.escape(p) for p in state.problems)
        body = ("<h2>No card generated</h2>\n<ul>\n%s\n</ul>\n"
                "<p>Fix config.toml, then run: "
                "<code>sudo supervisorctl restart app</code></p>" % items)
    return ("<!doctype html>\n<html><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            "<title>Beta challenge</title>"
            "<style>body{font-family:sans-serif;background:#14171C;color:#fff;margin:24px}"
            "img{max-width:100%%;height:auto}a{color:#F4B400}</style>"
            "</head><body>\n%s\n</body></html>\n" % body)
