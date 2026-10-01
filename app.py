#!/usr/bin/env python3
"""Beta challenge app. Run from the app folder: python3 app.py"""

import errno
import json
import os
import signal
import sys
import threading
import urllib.request
from datetime import datetime

from challenge import VERSION, card, config, log, pi_info, server, state

# Optional check-in endpoint. Empty = disabled.
CHECKIN_URL = ""

APP_DIR = os.path.dirname(os.path.abspath(__file__))


class Stop(Exception):
    def __init__(self, signame):
        super().__init__(signame)
        self.signame = signame


def start(app_dir=APP_DIR, environ=None, checkin_url=None):
    """Run startup steps 1-7 and return the bound (not yet serving) HTTP server."""
    environ = os.environ if environ is None else environ
    checkin_url = CHECKIN_URL if checkin_url is None else checkin_url
    dev_mode = environ.get("CHALLENGE_DEV") == "1"
    state_dir = os.path.join(app_dir, "state")
    output_dir = os.path.join(app_dir, "output")
    os.makedirs(state_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    # 1-3: banner, start counter, environment
    log.info("==== beta-challenge v%s starting ====" % VERSION)
    start_count = state.next_start_count(state_dir)
    env = pi_info.Environment(environ)
    if env.supervised:
        log.info('Start #%d (launched by supervisord, process "%s")'
                 % (start_count, env.process_name))
    else:
        log.info("Start #%d (NOT launched by supervisord)" % start_count)
    first_boot = state.check_boot(state_dir, env.boot_id)
    log.info("Boot %s, %ssystem up %s" % (
        env.boot_id, "first start since boot, " if first_boot else "",
        pi_info.format_uptime(env.uptime)))
    log.info("Detected: %s | %s | %s" % (env.model or "not a Raspberry Pi", env.os_name, env.arch))

    problems = []
    if env.model is None:
        if dev_mode:
            log.warning("DEV MODE (CHALLENGE_DEV=1): Raspberry Pi check skipped")
        else:
            problems.append("Not a Raspberry Pi: %s not found" % pi_info.MODEL_PATH)
            log.error(problems[-1])

    # 4: config
    cfg = config.load(os.path.join(app_dir, "config.toml"))
    log.add_secret(cfg.api_key)
    for message in cfg.errors:
        log.error(message)
    for message in cfg.warnings:
        log.warning(message)
    problems += cfg.errors

    detected_note = None
    typed_model = cfg.values.get("pi_model")
    if typed_model and env.model and not pi_info.model_matches(typed_model, env.model):
        log.warning('pi_model "%s" does not match detected "%s"' % (typed_model, env.model))
        detected_note = env.model

    if cfg.ok:
        v = cfg.values
        log.info("Config OK: discord=%s, pi_model=%s, display=%dx%d, team=%s, api_key=%s" % (
            v["discord_username"], v["pi_model"], v["display_cols"], v["display_rows"],
            v["nhl_team"], cfg.api_key_state))

    # 5: card
    card_path = None
    if not problems:
        card_path = os.path.join(output_dir, "profile_card.png")
        fields = {key: cfg.values[key] for key in card.CARD_FIELDS}
        make_card(app_dir, fields, card_path, start_count, env.boot_id, detected_note, dev_mode)
        log.info("Profile card saved to %s" % os.path.relpath(card_path, app_dir))
    elif cfg.errors:
        log.info("No card generated: fix config.toml, then run: sudo supervisorctl restart app")
    else:
        log.info("No card generated: the app must run on a Raspberry Pi")

    # 6: HTTP server
    port = cfg.port
    app_state = server.AppState(card_path, cfg.values.get("discord_username"), problems)
    try:
        httpd = server.make_server(port, app_state)
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            log.error("Port %d is already in use. Is another copy of the app running? "
                      "Check with: sudo supervisorctl status" % port)
        else:
            log.error("Cannot listen on port %d: %s" % (port, exc.strerror or exc))
        raise SystemExit(1)
    if card_path:
        log.info("Serving on port %d (GET /card to download)" % port)
    else:
        log.info("Serving on port %d (config errors, /health returns 503)" % port)

    # 7: optional check-in
    if not checkin_url:
        log.info("Check-in: disabled")
    elif not cfg.api_key:
        log.warning("Check-in skipped: api_key missing")
    else:
        payload = checkin_payload(cfg, env, start_count, card_path is not None)
        threading.Thread(target=checkin, args=(checkin_url, cfg.api_key, payload),
                         daemon=True).start()
    return httpd


def make_card(app_dir, fields, card_path, start_count, boot_id, detected_note, dev_mode):
    template = card.pick_template(os.path.join(app_dir, "templates"))
    panel = None
    if template is None:
        log.warning("templates/ has no .jpg or .png images; using a plain gradient")
    else:
        log.info("Template: %s" % os.path.relpath(template, app_dir))
        try:
            panel = card.load_template(template)
        except Exception as exc:
            log.warning("Could not open %s (%s); using a plain gradient"
                        % (os.path.relpath(template, app_dir), exc))
    if panel is None:
        panel = card.placeholder_panel()
    image = card.render_card(fields, panel, start_count, boot_id, datetime.now(),
                             detected=detected_note, dev_mode=dev_mode)
    card.save_card(image, card_path)


def checkin_payload(cfg, env, start_count, card_ok):
    v = cfg.values
    display = ("%dx%d" % (v["display_cols"], v["display_rows"])
               if "display_cols" in v and "display_rows" in v else None)
    return {
        "discord_username": v.get("discord_username"),
        "pi_model": v.get("pi_model"),
        "detected_model": env.model,
        "os": env.os_name,
        "arch": env.arch,
        "display": display,
        "nhl_team": v.get("nhl_team"),
        "start_count": start_count,
        "boot_id": env.boot_id,
        "under_supervisord": env.supervised,
        "card_ok": card_ok,
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def checkin(url, api_key, payload):
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer %s" % api_key})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            log.info("Check-in: sent (HTTP %d)" % response.status)
    except Exception as exc:
        log.warning("Check-in failed: %s" % exc)


def _raise_stop(signum, frame):
    raise Stop(signal.Signals(signum).name)


def main():
    sys.stdout.reconfigure(line_buffering=True, errors="backslashreplace")
    signal.signal(signal.SIGTERM, _raise_stop)
    signal.signal(signal.SIGINT, _raise_stop)
    httpd = None
    try:
        httpd = start()
        httpd.serve_forever()
    except Stop as stop:
        log.info("Stopping (received %s)" % stop.signame)
        return 0
    except Exception as exc:
        log.crash(exc)
        return 1
    finally:
        if httpd is not None:
            httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
