import os
import tempfile
import unittest

from challenge import config

from .support import VALID_TOML, write

HERE = os.path.dirname(os.path.abspath(__file__))
EXAMPLE = os.path.join(os.path.dirname(HERE), "config.example.toml")

PARSERS = []
for _name in ("tomllib", "tomli"):
    try:
        PARSERS.append(__import__(_name))
    except ModuleNotFoundError:
        pass

VALID = VALID_TOML.format(port=8081, api_key="k-123456")


def error_keys(cfg):
    return [e.split(":", 1)[0] for e in cfg.errors]


class ParserTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "config.toml")

    def tearDown(self):
        self.tmp.cleanup()

    def load(self, text, toml):
        write(self.path, text)
        return config.load(self.path, toml=toml)

    def test_parsers_available(self):
        self.assertTrue(PARSERS, "need tomllib or tomli")

    def test_valid(self):
        for toml in PARSERS:
            with self.subTest(parser=toml.__name__):
                cfg = self.load(VALID, toml)
                self.assertEqual(cfg.errors, [])
                self.assertEqual(cfg.warnings, [])
                self.assertEqual(cfg.values["nhl_team"], "MTL")
                self.assertEqual(cfg.api_key, "k-123456")

    def test_syntax_error_has_line_number_and_hint(self):
        text = VALID.replace('nhl_team = "mtl"', "nhl_team = MTL")
        for toml in PARSERS:
            with self.subTest(parser=toml.__name__):
                cfg = self.load(text, toml)
                self.assertEqual(len(cfg.errors), 1)
                self.assertIn("line 7", cfg.errors[0])
                self.assertTrue(cfg.errors[0].startswith("config.toml: "))
                self.assertIn('Text values need double quotes, e.g. nhl_team = "MTL"',
                              cfg.errors[0])
                self.assertEqual(cfg.values, {})  # validation skipped

    def test_duplicate_key(self):
        for toml in PARSERS:
            with self.subTest(parser=toml.__name__):
                cfg = self.load(VALID + 'nhl_team = "BOS"\n', toml)
                self.assertEqual(len(cfg.errors), 1)
                self.assertIn("line 8", cfg.errors[0])

    def test_number_in_quotes(self):
        for toml in PARSERS:
            with self.subTest(parser=toml.__name__):
                cfg = self.load(VALID.replace("display_cols = 64", 'display_cols = "64"'), toml)
                self.assertEqual(cfg.errors, [
                    'display_cols: "64" is text; write it as a number without quotes'])

    def test_missing_key(self):
        for toml in PARSERS:
            with self.subTest(parser=toml.__name__):
                cfg = self.load(VALID.replace('nhl_team = "mtl"\n', ""), toml)
                self.assertEqual(len(cfg.errors), 1)
                self.assertTrue(cfg.errors[0].startswith("nhl_team: missing"))

    def test_unknown_key_and_table_are_warnings(self):
        for toml in PARSERS:
            with self.subTest(parser=toml.__name__):
                cfg = self.load(VALID + 'color = "red"\n[extra]\nx = 1\n', toml)
                self.assertEqual(cfg.errors, [])
                self.assertEqual(len(cfg.warnings), 2)
                self.assertIn('"color"', cfg.warnings[0])
                self.assertIn("[extra]", cfg.warnings[1])

    def test_missing_file(self):
        cfg = config.load(os.path.join(self.tmp.name, "nope.toml"))
        self.assertEqual(len(cfg.errors), 1)
        self.assertIn("cp config.example.toml config.toml", cfg.errors[0])


class ValidationTests(unittest.TestCase):
    def check(self, key, value):
        data = config.tomllib.loads(VALID)
        data[key] = value
        return config.validate(data)

    def assertValid(self, key, value, stored=None):
        cfg = self.check(key, value)
        self.assertEqual(cfg.errors, [], "%s=%r" % (key, value))
        if key != "api_key":
            self.assertEqual(cfg.values[key], value if stored is None else stored)

    def assertInvalid(self, key, value):
        cfg = self.check(key, value)
        self.assertEqual(error_keys(cfg), [key], "%s=%r" % (key, value))
        return cfg.errors[0]

    def test_port(self):
        data = config.tomllib.loads(VALID)
        del data["port"]
        cfg = config.validate(data)
        self.assertEqual(cfg.errors, [])
        self.assertEqual(cfg.port, 8081)
        for ok in (1024, 8081, 65535):
            self.assertValid("port", ok)
        for bad in (80, 1023, 65536, "8081", True, 80.5):
            self.assertInvalid("port", bad)
        self.assertEqual(self.check("port", 80).port, 8081)

    def test_api_key(self):
        self.assertValid("api_key", "abc")
        for bad in ("", "   ", "PASTE_YOUR_KEY_HERE", 12345678):
            self.assertInvalid("api_key", bad)
        data = config.tomllib.loads(VALID)
        del data["api_key"]
        cfg = config.validate(data)
        self.assertEqual(error_keys(cfg), ["api_key"])
        self.assertEqual(cfg.api_key_state, "missing")

    def test_api_key_never_echoed(self):
        for bad in (98765432, ["marker-9f8e7d"], {"k": "marker-9f8e7d"}):
            message = self.assertInvalid("api_key", bad)
            self.assertNotIn("9876", message)
            self.assertNotIn("marker", message)

    def test_discord_username(self):
        for ok in ("ab", "a" * 32, "your.name_1", "_x_", "Yourname", "YOUR.Name_1"):
            self.assertValid("discord_username", ok)
        for bad in ("a", "a" * 33, "name#1234", "a..b", "with space",
                    "", "CHANGE_ME", 42):
            self.assertInvalid("discord_username", bad)

    def test_pi_model(self):
        for ok in ("Pi 4 Model B", "x" * 60, "Anything"):
            self.assertValid("pi_model", ok)
        for bad in ("", "   ", "x" * 61, "CHANGE_ME", 4):
            self.assertInvalid("pi_model", bad)

    def test_display(self):
        for key in ("display_cols", "display_rows"):
            for ok in (1, 64, 4096):
                self.assertValid(key, ok)
            for bad in (0, -1, 4097, "64", 64.0, False):
                self.assertInvalid(key, bad)

    def test_nhl_codes(self):
        self.assertValid("nhl_team", "mtl", "MTL")
        self.assertValid("nhl_team", "Tor", "TOR")
        message = self.assertInvalid("nhl_team", "MON")
        self.assertIn('"MON" is not a valid team code. Valid codes: ANA, BOS', message)
        self.assertEqual(len(config.NHL_TEAMS), 32)

    def test_example_config_fails_on_every_field(self):
        cfg = config.load(EXAMPLE)
        self.assertEqual(sorted(error_keys(cfg)), sorted([
            "api_key", "discord_username", "pi_model",
            "display_cols", "display_rows", "nhl_team"]))
        self.assertEqual(cfg.warnings, [])

    def test_all_errors_in_one_pass(self):
        data = config.tomllib.loads(VALID)
        data.update(nhl_team="MON", display_cols="64", display_rows=0)
        cfg = config.validate(data)
        self.assertEqual(error_keys(cfg), ["display_cols", "display_rows", "nhl_team"])


if __name__ == "__main__":
    unittest.main()
