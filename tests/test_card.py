import os
import tempfile
import unittest
from datetime import datetime

from PIL import Image

from challenge import card

FIELDS = {"discord_username": "yourname", "pi_model": "Pi 4 Model B",
          "display_cols": 64, "display_rows": 32, "nhl_team": "MTL"}
RED, GREEN, BLUE = (220, 30, 30), (30, 220, 30), (30, 30, 220)


def bands(size, colors, vertical):
    """An image split into equal colored bands (top-to-bottom if vertical)."""
    w, h = size
    img = Image.new("RGB", size)
    n = len(colors)
    for i, color in enumerate(colors):
        box = (0, h * i // n, w, h * (i + 1) // n) if vertical else (w * i // n, 0, w * (i + 1) // n, h)
        img.paste(color, box)
    return img


def dominant(pixel):
    return "RGB"[max(range(3), key=lambda i: pixel[i])]


class HeadlineTests(unittest.TestCase):
    def test_fits(self):
        for name in ("ab", "sixteen_chars_ab", "w" * 32, "m" * 32, "abcdefghijklmnopqrstuvwxyz.01234"):
            with self.subTest(name=name):
                lines, size = card.fit_headline(name)
                self.assertGreaterEqual(size, 32)
                for line in lines:
                    width = card.text_width(line, card.anton(size), card.stroke_for(size))
                    self.assertLessEqual(width, card.TEXT_W)
                self.assertIn(len(lines), (1, 2))

    def test_short_name_one_line_uppercase(self):
        lines, size = card.fit_headline("ab")
        self.assertEqual(lines, ["AB, STANDING BY"])
        self.assertEqual(size, 72)

    def test_32_chars_wraps(self):
        lines, _ = card.fit_headline("w" * 32)
        self.assertEqual(lines, ["W" * 32 + ",", "STANDING BY"])


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def render(self, panel, **kw):
        return card.render_card(FIELDS, panel, 3, "a1b2c3d4", datetime(2026, 10, 1, 19, 42), **kw)

    def template(self, name, img, **save_kw):
        path = os.path.join(self.tmp.name, name)
        img.save(path, **save_kw)
        return path

    def test_size(self):
        out = self.render(card.placeholder_panel(), detected="Raspberry Pi 4 Model B Rev 1.4",
                          dev_mode=True)
        self.assertEqual(out.size, (1200, 450))
        self.assertEqual(out.mode, "RGB")

    def test_long_values_do_not_crash(self):
        fields = dict(FIELDS, pi_model="W" * 60, display_cols=4096, display_rows=4096)
        out = card.render_card(fields, card.placeholder_panel(), 1, "x", datetime.now())
        self.assertEqual(out.size, (1200, 450))

    def test_wide_template_is_cropped(self):
        path = self.template("wide.png", bands((900, 300), [RED, GREEN, BLUE], vertical=False))
        panel = card.load_template(path)
        self.assertEqual(panel.size, (300, 450))
        # Cover-cropped: only the green middle band is visible. Stretching would show red/blue.
        for x in (5, 150, 294):
            self.assertEqual(dominant(panel.getpixel((x, 225))), "G")

    def test_tall_template_is_cropped(self):
        path = self.template("tall.jpg", bands((300, 1350), [RED, GREEN, BLUE], vertical=True),
                             quality=95)
        panel = card.load_template(path)
        self.assertEqual(panel.size, (300, 450))
        for y in (5, 225, 444):
            self.assertEqual(dominant(panel.getpixel((150, y))), "G")

    def test_exif_rotated_template(self):
        upright = bands((300, 900), [RED, GREEN, BLUE], vertical=True)
        stored = upright.rotate(90, expand=True)  # what the camera wrote: 900 x 300
        exif = Image.Exif()
        exif[0x0112] = 6  # orientation: rotate 90 CW to display
        path = self.template("phone.jpg", stored, exif=exif.tobytes(), quality=95)
        panel = card.load_template(path)
        self.assertEqual(panel.size, (300, 450))
        # Upright 300x900 cropped to the middle 450 rows: red top, green middle, blue bottom.
        self.assertEqual(dominant(panel.getpixel((150, 10))), "R")
        self.assertEqual(dominant(panel.getpixel((150, 225))), "G")
        self.assertEqual(dominant(panel.getpixel((150, 440))), "B")

    def test_empty_templates_gives_placeholder(self):
        self.assertIsNone(card.pick_template(self.tmp.name))
        self.assertIsNone(card.pick_template(os.path.join(self.tmp.name, "missing")))
        self.assertEqual(card.placeholder_panel().size, (300, 450))

    def test_pick_template_extensions(self):
        for name in ("a.JPG", "b.jpeg", "c.png", "notes.txt", "d.gif"):
            open(os.path.join(self.tmp.name, name), "w").close()
        picks = {os.path.basename(card.pick_template(self.tmp.name)) for _ in range(50)}
        self.assertEqual(picks, {"a.JPG", "b.jpeg", "c.png"})

    def test_save_card(self):
        path = os.path.join(self.tmp.name, "profile_card.png")
        card.save_card(self.render(card.placeholder_panel()), path)
        with Image.open(path) as img:
            self.assertEqual(img.size, (1200, 450))


if __name__ == "__main__":
    unittest.main()
