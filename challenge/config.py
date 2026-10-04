"""Load config.toml and validate it, collecting every problem in one pass."""

import re

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.9-3.10 (Bullseye)
    import tomli as tomllib

DEFAULT_PORT = 8081

NHL_TEAMS = (
    "ANA", "BOS", "BUF", "CAR", "CBJ", "CGY", "CHI", "COL",
    "DAL", "DET", "EDM", "FLA", "LAK", "MIN", "MTL", "NJD",
    "NSH", "NYI", "NYR", "OTT", "PHI", "PIT", "SEA", "SJS",
    "STL", "TBL", "TOR", "UTA", "VAN", "VGK", "WPG", "WSH",
)

KEY_PLACEHOLDER = "PASTE_YOUR_KEY_HERE"
TEXT_PLACEHOLDER = "CHANGE_ME"

# Order matters: errors are reported in this order.
KNOWN_KEYS = (
    "port", "api_key", "discord_username", "pi_model",
    "display_cols", "display_rows", "nhl_team",
)
INT_KEYS = ("port", "display_cols", "display_rows")

# Example value shown in "missing key" and "needs quotes" hints.
EXAMPLES = {
    "port": "8081",
    "api_key": '"<the key we sent you>"',
    "discord_username": '"yourname"',
    "pi_model": '"Pi 4 Model B"',
    "display_cols": "64",
    "display_rows": "32",
    "nhl_team": '"MTL"',
}

DISCORD_RE = re.compile(r"^[A-Za-z0-9_.]{2,32}$")
QUOTE_HINT = 'Text values need double quotes, e.g. nhl_team = "MTL"'


class Config:
    """Result of loading config.toml.

    `values` holds the validated values (api_key excluded), `api_key` the key
    itself (or None). Never log or render the key; use `api_key_state`.
    """

    def __init__(self):
        self.values = {}
        self.api_key = None
        self.errors = []
        self.warnings = []

    @property
    def ok(self):
        return not self.errors

    @property
    def api_key_state(self):
        return "set" if self.api_key else "missing"

    @property
    def port(self):
        return self.values.get("port", DEFAULT_PORT)

    def __repr__(self):
        return "Config(values=%r, api_key=%s, errors=%r)" % (
            self.values, self.api_key_state, self.errors)


def show(value, limit=40):
    """Render a value roughly the way it would look in TOML."""
    if isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, str):
        text = '"%s"' % value
    elif isinstance(value, dict):
        text = "a table"
    elif isinstance(value, list):
        text = "a list"
    else:
        text = str(value)
    if len(text) > limit:
        text = text[:limit - 1] + "…"
    return text


def load(path, toml=tomllib):
    """Read and validate `path`. `toml` is the parser module (tomllib or tomli)."""
    cfg = Config()
    try:
        with open(path, "rb") as f:
            data = toml.load(f)
    except FileNotFoundError:
        cfg.errors.append(
            "config.toml not found. Copy the example first: "
            "cp config.example.toml config.toml")
        return cfg
    except UnicodeDecodeError:
        cfg.errors.append("config.toml: the file is not valid UTF-8 text")
        return cfg
    except toml.TOMLDecodeError as exc:
        cfg.errors.append("config.toml: %s. %s" % (exc, QUOTE_HINT))
        return cfg
    validate(data, cfg)
    return cfg


def validate(data, cfg=None):
    cfg = cfg or Config()
    for key, value in data.items():
        if key in KNOWN_KEYS:
            continue
        if isinstance(value, dict):
            cfg.warnings.append(
                "config.toml: table [%s] ignored; all keys go at the top level, "
                "above any [section] line" % key)
        else:
            cfg.warnings.append('config.toml: unknown key "%s" ignored' % key)

    for key in KNOWN_KEYS:
        if key not in data:
            if key == "port":
                cfg.values["port"] = DEFAULT_PORT
                continue
            cfg.errors.append("%s: missing; add a line like %s = %s"
                              % (key, key, EXAMPLES[key]))
            continue
        value = data[key]
        problem = (_check_int if key in INT_KEYS else _check_text)(key, value)
        if problem is None:
            problem, value = _RULES[key](value)
        if problem:
            cfg.errors.append("%s: %s" % (key, problem))
        elif key == "api_key":
            cfg.api_key = value
        else:
            cfg.values[key] = value
    return cfg


def _check_int(key, value):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return "%s is not a whole number; write it like %s = %s" % (
            show(value), key, EXAMPLES[key])
    if isinstance(value, str):
        return "%s is text; write it as a number without quotes" % show(value)
    return None


def _check_text(key, value):
    if isinstance(value, str):
        return None
    if key == "api_key":  # never echo the key, even when mistyped
        return "must be text in double quotes"
    return "%s is not text; put it in double quotes, e.g. %s = %s" % (
        show(value), key, EXAMPLES[key])


def _placeholder(value):
    return "%s is the placeholder from the example; replace it" % show(value)


def _rule_port(value):
    if not 1024 <= value <= 65535:
        return ("%s is out of range; use a number from 1024 to 65535 "
                "(using %d for now)" % (value, DEFAULT_PORT)), None
    return None, value


def _rule_api_key(value):
    value = value.strip()
    if not value:
        return "is empty; paste the key we sent you", None
    if value == KEY_PLACEHOLDER:
        return "still the placeholder; paste the key we sent you", None
    return None, value


def _rule_discord(value):
    if value == TEXT_PLACEHOLDER:
        return _placeholder(value), None
    if not DISCORD_RE.match(value) or ".." in value:
        return ('%s is not a valid Discord username. Expected 2-32 characters: '
                'letters, digits, _ and . (no "..")' % show(value)), None
    return None, value


def _rule_pi_model(value):
    value = value.strip()
    if value == TEXT_PLACEHOLDER:
        return _placeholder(value), None
    if not value:
        return 'is empty; write your model, e.g. pi_model = "Pi 4 Model B"', None
    if len(value) > 60:
        return "%s is too long (max 60 characters)" % show(value), None
    return None, value


def _rule_display(value):
    if not 1 <= value <= 4096:
        return "%s is out of range; use a whole number from 1 to 4096" % value, None
    return None, value


def _rule_nhl(value):
    code = value.strip().upper()
    if code not in NHL_TEAMS:
        if value == TEXT_PLACEHOLDER:
            return _placeholder(value), None
        return ("%s is not a valid team code. Valid codes: %s"
                % (show(value), ", ".join(NHL_TEAMS))), None
    return None, code


_RULES = {
    "port": _rule_port,
    "api_key": _rule_api_key,
    "discord_username": _rule_discord,
    "pi_model": _rule_pi_model,
    "display_cols": _rule_display,
    "display_rows": _rule_display,
    "nhl_team": _rule_nhl,
}
