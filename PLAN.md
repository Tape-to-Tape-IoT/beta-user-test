# Beta Challenge App — Build Spec

Sep 30, 2026 · @Mighty Jay Jay

## Purpose

Build a small challenge app that beta candidates install on their own Raspberry Pi, configure from the CLI, run under supervisord, and prove it with a generated profile card plus their app log in a GitHub issue.

**For Claude (the builder):** implement everything in this spec. Where the spec leaves a detail open, pick the simplest option that works on every Raspberry Pi model and note the choice in the README. Do not add features that are not listed here.

What the challenge tests, in the order the candidate meets it:

1. Access a Raspberry Pi (SSH or keyboard and screen, both fine) and clone a GitHub repo.
2. Install a Python dependency on a modern Pi OS.
3. Copy and edit a config file from the CLI.
4. Write a supervisord program entry from scratch: autostart, autorestart, log file.
5. Recover from mistakes by reading the app log.
6. Get a file off the Pi and open a well-formed GitHub issue with the image and the log.

## Tech constraints

The app must run unchanged on any Raspberry Pi from a Zero 2 W to a Pi 5, 32- or 64-bit, on Raspberry Pi OS Bullseye, Bookworm or Trixie.

* **Python 3.9 or newer.** Bullseye ships 3.9, so no `match` statements and no syntax newer than 3.9.
* **Pillow is the main third-party dependency.** Code must work with Pillow 8.1 (the Bullseye apt version) up to the latest. Use `ImageDraw.textbbox` and `ImageFont.getbbox`, never `getsize` (removed in Pillow 10). For resampling use `getattr(Image, "Resampling", Image).LANCZOS`. Use `ImageOps.exif\_transpose` so phone photos are not rotated.
* **Everything else from the standard library, plus `tomli` on old Python.** The config is TOML, read with `tomllib` (standard library since Python 3.11). On Python 3.9–3.10 (Bullseye), fall back to the `tomli` package, which has the same API. Web server = `http.server.ThreadingHTTPServer`.
* **No root needed by the app.** It runs as the candidate's normal user. Only installing supervisor and creating the log folder need `sudo`.
* **Paths are relative to the app folder,** resolved from `\_\_file\_\_`, so the app works wherever it is cloned.
* **Low memory.** Card generation must stay well under 100 MB on a 512 MB Pi.
* **Fonts are bundled, not system fonts.** Headline: [Anton](https://fonts.google.com/specimen/Anton) (free Impact look-alike, SIL OFL). Body: [Inter](https://fonts.google.com/specimen/Inter) (SIL OFL). Ship both `.ttf` files in `fonts/` with `OFL.txt`. Do not bundle Impact itself: it belongs to Microsoft.
* **No network needed** except the optional check-in.

## Repo layout

One public repo, for example `beta-challenge`. Candidates clone it; `config.toml` is never committed.

```
beta-challenge/
├── app.py                  # entry point: python3 app.py
├── challenge/
│   ├── \_\_init\_\_.py
│   ├── config.py           # TOML loading + validation
│   ├── pi\_info.py          # Pi model, boot id, supervisord detection
│   ├── card.py             # profile card rendering
│   ├── server.py           # HTTP endpoints
│   └── state.py            # start counter
├── config.example.toml     # candidates copy this to config.toml
├── templates/              # template images you provide (.jpg / .png)
├── fonts/
│   ├── Anton-Regular.ttf
│   ├── Inter-Regular.ttf
│   ├── Inter-SemiBold.ttf
│   └── OFL.txt
├── requirements.txt        # Pillow, plus tomli on Python < 3.11
├── README.md               # the candidate task sheet
├── .github/ISSUE\_TEMPLATE/beta-application.yml
├── tests/
├── output/                 # generated card (gitignored, keep .gitkeep)
└── state/                  # start counter (gitignored, keep .gitkeep)
```

`.gitignore` covers `config.toml`, `output/\*`, `state/\*`, `venv/`, `\_\_pycache\_\_/`.

If `templates/` is empty, the app generates a plain gradient placeholder so it still works, and logs a warning.

## Configuration

Candidates run `cp config.example.toml config.toml` and edit it. The placeholders in the example are deliberately invalid, so an unedited config fails with clear log messages.

```toml
# config.example.toml
port = 8081
api\_key = "PASTE\_YOUR\_KEY\_HERE"
discord\_username = "CHANGE\_ME"
pi\_model = "CHANGE\_ME"
display\_cols = 0
display\_rows = 0
nhl\_team = "CHANGE\_ME"
```

|Key|Type|Rule|On card|In log|
|-|-|-|-|-|
|`port`|integer|1024–65535, default 8081 if missing|no|yes|
|`api\_key`|text|required, not empty, not the placeholder|**never**|only `set` / `missing`|
|`discord\_username`|text|2–32 chars; lowercase letters, digits, `\_` and `.`; no `..`|yes|yes|
|`pi\_model`|text|not empty, max 60 chars; compared with the detected model (warning only)|yes|yes|
|`display\_cols`|integer|1–4096|yes|yes|
|`display\_rows`|integer|1–4096|yes|yes|
|`nhl\_team`|text|one of the 32 codes below, case-insensitive, stored uppercase|yes|yes|

**Valid NHL codes:** ANA, BOS, BUF, CAR, CBJ, CGY, CHI, COL, DAL, DET, EDM, FLA, LAK, MIN, MTL, NJD, NSH, NYI, NYR, OTT, PHI, PIT, SEA, SJS, STL, TBL, TOR, UTA, VAN, VGK, WPG, WSH. Keep the list in one constant so it is easy to update.

### Reading the TOML

* Load with `tomllib.load()` on a file opened in binary mode: `try: import tomllib` / `except ModuleNotFoundError: import tomli as tomllib`.
* `requirements.txt` holds two lines: `Pillow>=8.1` and `tomli>=1.1; python\_version < "3.11"`.
* All keys are top-level; no `\[tables]` are needed. A table or an unknown key → warning, ignored. A missing key → error.
* Syntax error (this also covers duplicate keys) → one `ERROR:` line with the parser's message and line number, plus the hint that text values need double quotes, e.g. `nhl\_team = "MTL"`. Validation is skipped until the file parses.
* Wrong type → error with a fix hint. Example: `display\_cols = "64"` → `display\_cols: "64" is text; write it as a number without quotes`.
* Missing `config.toml` → error telling them to copy `config.example.toml`.

### Validation output

* Collect **all** errors in one pass, then log each on its own line with the key, the bad value and what is expected. Example: `nhl\_team: "MON" is not a valid team code. Valid codes: ANA, BOS, …`
* Never echo the `api\_key` value, even in an error.
* Any error → no card is generated (see runtime behavior).

### Pi model matching

The detected model comes from `/proc/device-tree/model` (strip the trailing null byte). Normalize both strings: lowercase, cut everything from `rev` onward, remove the words `raspberry`, `pi` and `model`, then remove everything that is not a letter or digit. It matches when the detected value starts with the candidate's value.

|Candidate wrote|Detected|Normalized|Result|
|-|-|-|-|
|Pi 4 Model B|Raspberry Pi 4 Model B Rev 1.4|`4b` vs `4b`|match|
|Raspberry Pi 5|Raspberry Pi 5 Model B Rev 1.0|`5` vs `5b`|match|
|Zero 2 W|Raspberry Pi Zero 2 W Rev 1.0|`zero2w` vs `zero2w`|match|
|Pi 3B+|Raspberry Pi 4 Model B Rev 1.2|`3b` vs `4b`|warning|

A mismatch is a **warning**, not an error: the card is still made, with a small "Detected: …" note, and the log says so.

## Runtime behavior

The app is a long-running web service, started with `python3 app.py` from the app folder. It generates the card once at startup, then keeps serving until stopped. It must never exit just because the config is wrong: a script that exits would be restarted in a loop by supervisord and end up `FATAL`, hiding the real problem.

### Startup sequence

1. Log the start banner.
2. Increment the start counter in `state/start\_count`. Write to a temp file, then rename, so a crash never corrupts it.
3. Detect the environment:

   * **Pi model** from `/proc/device-tree/model`. Missing file = not a Raspberry Pi → error, no card. For development only, `CHALLENGE\_DEV=1` skips this check and stamps "DEV MODE" on the card.
   * **Boot id**: first 8 characters of `/proc/sys/kernel/random/boot\_id`. Compare with the value saved in `state/last\_boot\_id`; if different, log "first start since boot", then save the new one. This is the reboot proof.
   * **System uptime** from `/proc/uptime`.
   * **Supervisord**: launched by supervisord when the env var `SUPERVISOR\_ENABLED` is `1`. Also log `SUPERVISOR\_PROCESS\_NAME`.
   * **OS and arch**: `PRETTY\_NAME` from `/etc/os-release`, `platform.machine()`.
4. Load and validate the config (see Configuration).
5. If valid: pick a random template from `templates/`, render the card, save `output/profile\_card.png` (temp file then rename), log the path.
6. Start the HTTP server on `0.0.0.0:<port>` (8081 if the port is invalid). If the port is already in use, log a clear error and exit with code 1.
7. Run the optional check-in in a background thread.
8. Serve until SIGTERM or SIGINT.

When the config has errors, the app still starts the server and waits. The candidate fixes the config and runs `sudo supervisorctl restart app`. There is no hot reload.

### Endpoints

|Path|Returns|
|-|-|
|`GET /health`|`200 ok` when the card was generated; `503 config error: N problem(s), see log` otherwise|
|`GET /card`|The PNG, with `Content-Disposition: attachment; filename="profile\_card\_<discord\_username>.png"`; 404 if no card|
|`GET /`|Minimal HTML page: the card and a download link, or the list of config errors (never the api key)|
|anything else|404|

Default `http.server` request logging is switched off. Only `/card` downloads get one log line each.

### Stopping

On SIGTERM or SIGINT: log `Stopping (received SIGTERM)` and exit with code 0.

This is intentional. Supervisord's default `autorestart=unexpected` treats exit code 0 as expected and does not restart, so the candidate's `kill <pid>` test only passes with `autorestart=true`.

### Optional check-in

`CHECKIN\_URL` is a constant at the top of `app.py`, empty by default. Empty → log `Check-in: disabled` and skip.

When set, POST JSON with `urllib` (5 s timeout) and the header `Authorization: Bearer <api\_key>`:

```json
{
  "discord\_username": "yourname",
  "pi\_model": "Pi 4 Model B",
  "detected\_model": "Raspberry Pi 4 Model B Rev 1.4",
  "os": "Debian GNU/Linux 12 (bookworm)",
  "arch": "aarch64",
  "display": "64x32",
  "nhl\_team": "MTL",
  "start\_count": 3,
  "boot\_id": "a1b2c3d4",
  "under\_supervisord": true,
  "card\_ok": true,
  "timestamp": "2026-10-01T19:42:11-04:00"
}
```

Failure = one warning line in the log, never fatal.

## Profile card

A 1200 × 450 px PNG: the template image fills the left quarter, the headline and the candidate's parameters fill the right three quarters.

```
0        300                                                    1200
┌─────────┬──────────────────────────────────────────────────────┐
│         │  YOURNAME, STANDING BY          ← Anton, white, black │
│         │                                   outline, fit width  │
│template │  Discord         yourname                             │
│ image   │  Raspberry Pi    Pi 4 Model B                         │
│ (cover  │  Display         64 cols × 32 rows                    │
│  crop)  │  Favorite team   MTL                                  │
│         │  Detected: Raspberry Pi 4 Model B Rev 1.4  (if mismatch)
│         │                   start #3 · boot a1b2c3d4 · 2026-10-01│
└─────────┴──────────────────────────────────────────────────────┘ 450
```

### Left panel (x 0–300)

* Random image from `templates/` (`.jpg`, `.jpeg`, `.png`, case-insensitive), a new pick on every start.
* Apply `exif\_transpose`, convert to RGB, scale to cover 300 × 450 and center-crop. Never stretch.

### Right panel (x 300–1200)

* Background `#14171C`. Padding 48 px left and right, 36 px top. Usable text width: 804 px.

**Headline**

* Text: `<discord\_username>, standing by`, uppercased (constant `HEADLINE\_UPPERCASE = True`).
* Anton, fill `#FFFFFF`, outline `#000000`, `stroke\_width = max(2, round(size \* 0.06))`. Measure with `textbbox(..., stroke\_width=...)` so the outline counts.
* Fit: start at 72 px and step down 2 px until it fits in 804 px; minimum 40 px.
* Still too wide at 40 px → two lines, `YOURNAME,` / `STANDING BY`, fitted again from 60 px down to 32 px.
* Still too wide → truncate the username with `…` until it fits. Line spacing 1.05 × font size.

**Parameter list** (24 px below the headline)

|Label|Value|Source|
|-|-|-|
|Discord|`yourname`|`discord\_username`|
|Raspberry Pi|as typed|`pi\_model`|
|Display|`64 cols × 32 rows`|`display\_cols`, `display\_rows`|
|Favorite team|`MTL`|`nhl\_team`|

* Labels: Inter SemiBold 24 px, `#9AA4B2`, column 220 px wide. Values: Inter Regular 26 px, `#FFFFFF`. Row height 42 px.
* A value too wide for its column shrinks to 20 px, then truncates with `…`.
* The card is built from an allowlist constant, `CARD\_FIELDS`. The render function receives only a dict built from that list, so `api\_key` can never reach the card.

**Extras**

* Model mismatch: `Detected: <detected model>` under the list, Inter 18 px, amber `#F4B400`.
* Footer, bottom right, Inter 14 px, `#5C6573`: `start #<n> · boot <boot id> · <YYYY-MM-DD HH:MM>`. This ties the card to the log.
* Dev mode: `DEV MODE` in red, bottom left of the right panel.

Saved as `output/profile\_card.png`, overwritten on every start.

## Log

The app logs to **stdout only**, and the candidate's supervisord config sends it to `/var/log/app/app.log`. The candidate copies the log from the terminal and pastes it into the issue, so every start must be short, readable and free of secrets.

### Rules

* Call `sys.stdout.reconfigure(line\_buffering=True)` at startup so lines appear immediately under supervisord.
* Format: `\[YYYY-MM-DD HH:MM:SS] message`, local time. Problems start with `ERROR:` or `WARNING:`.
* At most about 10 lines per start when everything is fine.
* The `api\_key` value is never written, not even in errors or tracebacks. Log `api\_key=set` or `api\_key=missing`.
* An unexpected crash logs one `ERROR:` summary line, then the traceback, then exits with code 1.

### Normal start

```
\[2026-10-01 19:42:10] ==== beta-challenge v1.0 starting ====
\[2026-10-01 19:42:10] Start #3 (launched by supervisord, process "app")
\[2026-10-01 19:42:10] Boot a1b2c3d4, first start since boot, system up 41 s
\[2026-10-01 19:42:10] Detected: Raspberry Pi 4 Model B Rev 1.4 | Debian GNU/Linux 12 (bookworm) | aarch64
\[2026-10-01 19:42:10] Config OK: discord=yourname, pi\_model=Pi 4 Model B, display=64x32, team=MTL, api\_key=set
\[2026-10-01 19:42:11] Template: templates/rink.jpg
\[2026-10-01 19:42:11] Profile card saved to output/profile\_card.png
\[2026-10-01 19:42:11] Serving on port 8081 (GET /card to download)
\[2026-10-01 19:42:11] Check-in: disabled
```

### Start with problems

```
\[2026-10-01 19:30:02] Start #1 (NOT launched by supervisord)
\[2026-10-01 19:30:02] ERROR: nhl\_team: "MON" is not a valid team code. Valid codes: ANA, BOS, BUF, …
\[2026-10-01 19:30:02] ERROR: display\_cols: "64" is text; write it as a number without quotes
\[2026-10-01 19:30:02] WARNING: pi\_model "Pi 3B+" does not match detected "Raspberry Pi 4 Model B Rev 1.4"
\[2026-10-01 19:30:02] No card generated: fix config.toml, then run: sudo supervisorctl restart app
\[2026-10-01 19:30:02] Serving on port 8081 (config errors, /health returns 503)
```

A syntax error looks like this, and no other config checks run until it is fixed:

```
\[2026-10-01 19:25:40] ERROR: config.toml: Invalid value (at line 8, column 12). Text values need double quotes, e.g. nhl\_team = "MTL"
```

### Other lines

* Card download: `Card downloaded by 192.168.1.20`.
* Stop: `Stopping (received SIGTERM)`.

## Candidate task sheet (README.md)

Ship this text as `README.md`. It says what to achieve, not which commands to type: finding the commands is part of the test.

```markdown
# Beta challenge

Thanks for applying! This takes about an hour. Searching the web is allowed and expected.

\*\*You need:\*\* a Raspberry Pi running Raspberry Pi OS with internet access, a GitHub account,
and the personal API key we sent you. Work over SSH or with a keyboard and screen, your choice.

\*\*Never post your API key anywhere\*\*, including in your issue.

## Steps

1. Clone this repository into `\~/app` on your Pi.
2. Install the dependencies listed in `requirements.txt`. Recent Raspberry Pi OS versions block
   system-wide `pip install`; pick an approach that works.
3. Copy `config.example.toml` to `config.toml` and fill in, from the command line:
   - `api\_key`: the key we sent you
   - `discord\_username`: your Discord username
   - `pi\_model`: your Raspberry Pi model
   - `display\_cols` and `display\_rows`: your display size
   - `nhl\_team`: your favorite NHL team's abbreviation (e.g. MTL)
4. Run the app once by hand with `python3 app.py` from `\~/app`. Read what it prints,
   fix anything it complains about, then stop it with Ctrl+C.
5. Install supervisor and create a program named `app` that:
   - runs the app as your user, from `\~/app`
   - starts automatically when the Pi boots
   - restarts whenever the app process stops
   - writes all its output to `/var/log/app/app.log`
6. Check that `curl localhost:8081/health` returns `ok`.
7. Prove it recovers:
   - find the app's process ID and `kill` it; confirm it comes back
   - reboot the Pi; confirm it comes back
8. Get `output/profile\_card.png` onto the computer you use for GitHub (any method).
9. Open an issue in this repo using the \*\*Beta application\*\* form.
   Attach your profile card and paste the full app log, copied from your terminal.

## Done when

- \[ ] Your issue shows your profile card
- \[ ] Your log shows at least 3 starts, including one after a reboot
- \[ ] No API key appears anywhere in your issue

## Cleaning up (optional)

Stop and remove the `app` program from supervisor, uninstall supervisor if you
don't need it, and delete `\~/app` and `/var/log/app`.
```

## GitHub issue form

Use a GitHub issue form (YAML), not a Markdown template: fields can be required, and `render: text` wraps the pasted log in a code block automatically. Create the `beta-application` label in the repo first.

```yaml
# .github/ISSUE\_TEMPLATE/beta-application.yml
name: Beta application
description: Submit your beta challenge result
title: "\[Beta] <your Discord username>"
labels: \["beta-application"]
body:
  - type: markdown
    attributes:
      value: |
        Thanks for doing the challenge! Make sure your API key appears nowhere below.
  - type: input
    id: discord
    attributes:
      label: Discord username
    validations:
      required: true
  - type: textarea
    id: card
    attributes:
      label: Profile card
      description: Drag and drop your profile\_card.png here.
    validations:
      required: true
  - type: textarea
    id: log
    attributes:
      label: App log
      description: Paste the full contents of /var/log/app/app.log, copied from your terminal.
      render: text
    validations:
      required: true
  - type: textarea
    id: notes
    attributes:
      label: Anything confusing or broken?
      description: Optional. Unclear instructions, problems on your Pi model, anything.
  - type: checkboxes
    id: checks
    attributes:
      label: Before submitting
      options:
        - label: My API key does not appear anywhere in this issue
          required: true
```

Also add `.github/ISSUE\_TEMPLATE/config.yml` with `blank\_issues\_enabled: false` so candidates can't skip the form.

## Grading checklist

A candidate passes when every required row checks out; the bonus rows help you pick between passing candidates.

|Check|Where to look|Pass looks like|
|-|-|-|
|Runs on a real Pi|Log `Detected:` line, card|A Raspberry Pi model is detected, no `DEV MODE` on the card|
|Config edited correctly|Card, `Config OK` line|Valid values, username matches the issue|
|Supervisord set up|`Start #` lines|`launched by supervisord, process "app"`|
|Autorestart after kill|Log|`Stopping (received SIGTERM)` followed by a new start|
|Autostart after reboot|Log|A later start with `first start since boot`|
|Card matches log|Card footer vs log|Same start number and boot id|
|Log copied correctly|Issue|Full log, readable, inside the code block|
|No secrets|Whole issue|API key absent|
|**Bonus:** recovered from mistakes|Log|Early `ERROR:` lines, then a clean start|
|**Bonus:** useful feedback|Notes field|Concrete problems reported, e.g. unclear step or a Pi-model issue|

If a candidate leaks their API key, revoke it and issue a new one. Whether that fails them is your call.

## Tests and acceptance

The build is done when the unit tests pass off-Pi and the full candidate flow passes on at least one real Pi.

### Unit tests

Standard library `unittest` only, run with `python3 -m unittest` from the repo root. `CHALLENGE\_DEV=1` lets them run on a laptop.

* **Parser:** TOML syntax error with its line number, duplicate key, number written in quotes, missing key, unknown key, missing file; runs with both tomllib and tomli.
* **Validation:** every rule in the Configuration table, including the unedited `config.example.toml` failing on every field; all errors reported in one pass.
* **NHL codes:** `mtl` accepted and stored as `MTL`; `MON` rejected.
* **Pi model matching:** every row of the matching table.
* **Headline fit:** 2-char, 16-char and 32-char usernames all fit within 804 px; the 32-char one may wrap to two lines.
* **No key leak:** run a full startup with `api\_key` set to a unique marker string; assert the marker is absent from captured stdout, the `/` page, and the dict passed to the card renderer.
* **Card:** output is exactly 1200 × 450; wide, tall and EXIF-rotated templates are cropped, not stretched; empty `templates/` produces a placeholder.
* **Start counter:** increments across runs; boot id change is detected.

### Acceptance on a real Pi

Follow `README.md` exactly as a candidate would.

* \[ ] Unedited config: clear `ERROR:` lines, `/health` returns 503, app keeps running
* \[ ] Fixed config + `supervisorctl restart app`: card generated, `/health` returns `ok`
* \[ ] `kill <pid>` with `autorestart=true`: app comes back
* \[ ] `kill <pid>` with the default `autorestart=unexpected`: app stays down (confirms the test is meaningful)
* \[ ] Reboot: app comes back, log shows `first start since boot`
* \[ ] Card downloads from a laptop browser at `http://<pi-ip>:8081/`
* \[ ] Log copied from the terminal pastes cleanly into the issue form
* \[ ] Tested on a 64-bit Pi OS and, if possible, a 32-bit one

## Open decisions

The spec uses the defaults below; change any of them before building.

|Decision|Default in this spec|
|-|-|
|Meaning of `display\_cols` / `display\_rows`|Your project's display dimensions (e.g. a 64 × 32 LED matrix); only whole numbers 1–4096 are checked|
|Headline case|Uppercase, classic meme style|
|Discord username rules|Current Discord format only (lowercase, digits, `\_`, `.`); old `name#1234` tags rejected|
|Check-in endpoint|Off; `api\_key` is still required so candidates practise handling a secret|
|Card colors|Dark panel `#14171C`, white text, grey labels|
|Template images|You supply them in `templates/`; a gradient placeholder is used if the folder is empty|