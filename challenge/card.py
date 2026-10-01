"""Render the 1200 x 450 profile card."""

import io
import os
import random
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .state import atomic_write

FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts")
TEMPLATE_EXTS = (".jpg", ".jpeg", ".png")
LANCZOS = getattr(Image, "Resampling", Image).LANCZOS

# Only these config keys ever reach the renderer.
CARD_FIELDS = ("discord_username", "pi_model", "display_cols", "display_rows", "nhl_team")

HEADLINE_UPPERCASE = True

WIDTH, HEIGHT = 1200, 450
PANEL_W = 300
PAD_X, PAD_TOP = 48, 36
TEXT_X = PANEL_W + PAD_X
TEXT_W = WIDTH - PANEL_W - 2 * PAD_X  # 804

BG = "#14171C"
WHITE = "#FFFFFF"
BLACK = "#000000"
LABEL = "#9AA4B2"
AMBER = "#F4B400"
FOOTER = "#5C6573"
RED = "#E53935"

LABEL_COL_W = 220
ROW_H = 42
ROW_BASELINE = 30
VALUE_W = TEXT_W - LABEL_COL_W
ELLIPSIS = "…"

_measure = ImageDraw.Draw(Image.new("RGB", (1, 1)))


@lru_cache(maxsize=None)
def font(name, size):
    return ImageFont.truetype(os.path.join(FONT_DIR, name), size)


def anton(size):
    return font("Anton-Regular.ttf", size)


def inter(size):
    return font("Inter-Regular.ttf", size)


def inter_semibold(size):
    return font("Inter-SemiBold.ttf", size)


def stroke_for(size):
    return max(2, round(size * 0.06))


def text_width(text, fnt, stroke=0):
    left, _, right, _ = _measure.textbbox((0, 0), text, font=fnt, stroke_width=stroke)
    return right - left


def truncate(text, fnt, max_w, stroke=0, suffix=""):
    """Shorten `text` with an ellipsis until text + suffix fits in max_w."""
    if text_width(text + suffix, fnt, stroke) <= max_w:
        return text + suffix
    while text and text_width(text + ELLIPSIS + suffix, fnt, stroke) > max_w:
        text = text[:-1]
    return text + ELLIPSIS + suffix


def fit_headline(username):
    """Return (lines, size) for the headline, fitted to TEXT_W."""
    def case(text):
        return text.upper() if HEADLINE_UPPERCASE else text

    one_line = case("%s, standing by" % username)
    for size in range(72, 39, -2):
        if text_width(one_line, anton(size), stroke_for(size)) <= TEXT_W:
            return [one_line], size

    lines = [case(username + ","), case("standing by")]
    for size in range(60, 31, -2):
        if max(text_width(l, anton(size), stroke_for(size)) for l in lines) <= TEXT_W:
            return lines, size

    size = 32
    lines[0] = truncate(case(username), anton(size), TEXT_W, stroke_for(size), ",")
    return lines, size


def fit_value(text):
    """Return (text, font) for a parameter value, fitted to VALUE_W."""
    if text_width(text, inter(26)) <= VALUE_W:
        return text, inter(26)
    return truncate(text, inter(20), VALUE_W), inter(20)


def pick_template(templates_dir):
    try:
        names = sorted(n for n in os.listdir(templates_dir)
                       if n.lower().endswith(TEMPLATE_EXTS))
    except OSError:
        return None
    return os.path.join(templates_dir, random.choice(names)) if names else None


def load_template(path):
    """Open a template and cover-crop it to the left panel, never stretching."""
    with Image.open(path) as img:
        img.draft("RGB", (HEIGHT, HEIGHT))  # decode big JPEGs at reduced size
        # Shrink in place before any copy is made, keeping just enough pixels to
        # cover the panel whichever way EXIF rotates it. thumbnail() keeps the EXIF.
        w, h = img.size
        rotated = img.getexif().get(0x0112) in (5, 6, 7, 8)
        panel_w, panel_h = (HEIGHT, PANEL_W) if rotated else (PANEL_W, HEIGHT)
        scale = max(panel_w / w, panel_h / h)
        if scale < 1:
            img.thumbnail((int(w * scale) + 1, int(h * scale) + 1), LANCZOS)
        img = ImageOps.exif_transpose(img).convert("RGB")
    return ImageOps.fit(img, (PANEL_W, HEIGHT), method=LANCZOS)


def placeholder_panel():
    gradient = Image.linear_gradient("L").resize((PANEL_W, HEIGHT), LANCZOS)
    return ImageOps.colorize(gradient, "#1F3A5F", "#0B6E4F")


def rows_for(fields):
    return [
        ("Discord", fields["discord_username"]),
        ("Raspberry Pi", fields["pi_model"]),
        ("Display", "%d cols × %d rows" % (fields["display_cols"], fields["display_rows"])),
        ("Favorite team", fields["nhl_team"]),
    ]


def render_card(fields, panel, start_count, boot_id, when, detected=None, dev_mode=False):
    """Draw the card. `fields` holds exactly the CARD_FIELDS keys."""
    card = Image.new("RGB", (WIDTH, HEIGHT), BG)
    card.paste(panel, (0, 0))
    draw = ImageDraw.Draw(card)

    lines, size = fit_headline(fields["discord_username"])
    head_font, stroke = anton(size), stroke_for(size)
    # Anton has a tall ascender; align the ink, not the ascender, to the padding.
    ink_top = _measure.textbbox((0, 0), lines[0], font=head_font, stroke_width=stroke)[1]
    bottom = PAD_TOP
    for i, line in enumerate(lines):
        y = PAD_TOP - ink_top + round(i * size * 1.05)
        left = _measure.textbbox((0, 0), line, font=head_font, stroke_width=stroke)[0]
        draw.text((TEXT_X - left, y), line, font=head_font, fill=WHITE,
                  stroke_width=stroke, stroke_fill=BLACK)
        bottom = draw.textbbox((TEXT_X - left, y), line, font=head_font,
                               stroke_width=stroke)[3]

    top = bottom + 24
    for i, (label, value) in enumerate(rows_for(fields)):
        baseline = top + i * ROW_H + ROW_BASELINE
        draw.text((TEXT_X, baseline), label, font=inter_semibold(24), fill=LABEL, anchor="ls")
        text, value_font = fit_value(str(value))
        draw.text((TEXT_X + LABEL_COL_W, baseline), text, font=value_font,
                  fill=WHITE, anchor="ls")

    if detected:
        note = truncate("Detected: %s" % detected, inter(18), TEXT_W)
        draw.text((TEXT_X, top + 4 * ROW_H + 8), note, font=inter(18), fill=AMBER)

    footer = "start #%d · boot %s · %s" % (start_count, boot_id, when.strftime("%Y-%m-%d %H:%M"))
    draw.text((WIDTH - PAD_X, HEIGHT - 24), footer, font=inter(14), fill=FOOTER, anchor="rs")

    if dev_mode:
        draw.text((TEXT_X, HEIGHT - 24), "DEV MODE", font=inter_semibold(18), fill=RED, anchor="ls")
    return card


def save_card(card, path):
    buf = io.BytesIO()
    card.save(buf, "PNG")
    atomic_write(path, buf.getvalue())
