# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A challenge app that beta candidates clone onto their own Raspberry Pi, configure, and run under
supervisord. It renders a 1200×450 profile card (`output/profile_card.png`) and serves it on
port 8081. The candidate then posts the card and the tail of their supervisord log in a GitHub issue
(`.github/ISSUE_TEMPLATE/beta-application.yml`).

- `PLAN.md` is the build spec and the source of truth for behavior, log wording, card layout and
  config rules. Implement what it says and don't add features it doesn't list.
- `README.md` is the candidate-facing sheet. Changes to behavior that candidates see (log lines,
  endpoints, config keys) usually need a matching edit there.
- `README.md` "Implementation choices" records every place the spec left a detail open. When you
  make a new judgment call like that, add it there.

## Commands

```bash
python3 -m unittest                                   # all tests, from repo root
python3 -m unittest tests.test_config                 # one module
python3 -m unittest tests.test_card.HeadlineTests.test_fits   # one test
CHALLENGE_DEV=1 python3 app.py                        # run off-Pi; skips the Pi check, stamps "DEV MODE"
```

There's no linter or build step. The only dependencies are `Pillow` and, on Python < 3.11,
`tomli` (see `requirements.txt`).

## Compatibility constraints (easy to break)

The code has to run unchanged on everything from a Pi Zero 2 W to a Pi 5, 32- or 64-bit, on
Bullseye through Trixie:

- **Python 3.9 syntax only**: no `match`, no `X | Y` type unions, no other syntax added after 3.9.
- **Pillow 8.1 through latest**: use `textbbox`/`getbbox`, never `getsize`. Get resampling via
  `getattr(Image, "Resampling", Image).LANCZOS`.
- **Standard library only** beyond Pillow/tomli. The server is `http.server.ThreadingHTTPServer`.
- **Memory**: card generation must stay well under 100 MB on a 512 MB Pi. Large templates are
  shrunk with `draft()`/`thumbnail` before `exif_transpose`.
- **Paths**: resolve every path from `__file__`, never from the working directory.
- Fonts are bundled in `fonts/` (Anton, Inter static TTFs). Don't use system fonts.

## Architecture

`app.py` runs startup as numbered steps that mirror PLAN.md's "Startup sequence". `start()`
returns a bound but not-yet-serving server, so tests can drive the whole startup without
blocking. `main()` installs SIGTERM/SIGINT handlers that raise `Stop`, which exits with code 0.

Modules in `challenge/`:
- `config.py`: loads TOML (`tomllib`, falling back to `tomli`) into a `Config` holding `values`,
  `errors` and `warnings`. It collects **all** errors in one pass. Per-key rules live in the
  `_RULES` dict. `NHL_TEAMS` is the single list of team codes.
- `pi_info.py`: reads `/proc` and `/etc` through module-level path constants (`MODEL_PATH`,
  `BOOT_ID_PATH`, `UPTIME_PATH`, `OS_RELEASE_PATH`). Tests patch those constants. Also handles
  supervisord detection (`SUPERVISOR_ENABLED`) and model normalization/matching.
- `state.py`: the start counter and the last boot id in `state/`. Writes go to a temp file and
  are then renamed, so they're atomic.
- `card.py`: renders the card. The renderer only receives fields named in the `CARD_FIELDS`
  allowlist. That's what keeps `api_key` off the card.
- `server.py`: `AppState` plus the endpoints `/health` (200 or 503), `/card` (the one request
  that gets logged) and `/` (card inlined as a data URI). Default request logging is off.
- `log.py`: timestamped stdout-only logging. `add_secret()` registers `api_key` so it's masked
  in every line as a second safety net.

Invariants to keep:
- **The app never exits because of a bad config.** Config errors are logged as `ERROR:` lines,
  no card is generated, and the server still runs, with `/health` returning 503. Exiting would
  make supervisord restart-loop the app into `FATAL`. The only non-signal exits are "port in
  use" and an unexpected crash (both exit 1).
- **A clean stop exits 0.** Candidates have to configure `autorestart=true`, and the `kill`
  test in README.md only passes with it.
- **The `api_key` value never reaches the log, the card, or the `/` page.** Log it only as
  `api_key=set` / `api_key=missing`. `tests/test_app.py` checks this with a marker key.
- A normal start logs about 10 lines. Log wording is spec'd in PLAN.md, and candidates read
  these lines to troubleshoot.

## Tests

Tests run off-Pi. `tests/support.py` provides `FakePi` (a context manager that points
`pi_info`'s path constants at temp files), `VALID_TOML`, and `free_port()`. The directories
`config.toml`, `output/*` and `state/*` are gitignored; the `.gitkeep` files in them must stay.
