#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Maintainers only: draw assets/cases/<platform>.png (600x900, a transparent art window) and assets/cases/cases.json (where the art goes, and where the
100% rosette and the Steam Family corner go so they never cover a logo). Each case follows photographs of the real cases: the Xbox 360's white banner with its
green swoosh in a green shell, the Xbox One's green bar, the PS3's black and the PS4's blue banner, the PS5's white banner in a blue shell, the Switch's red tab
in a clear case, the Switch 2's red case with a tall red banner.
The logos are in tools/src/cases/ (Simple Icons, CC0; see SOURCES.txt there). Where Simple Icons has no mark for a model (Xbox 360, Xbox One, Xbox Series X|S,
Switch 2) the console's mark is drawn with the model typeset in Nunito Sans, not the official wordmark.
Needs Pillow and rsvg-convert (librsvg). Users of steamcase.py do NOT need this: the files are committed."""
import io, json, os, subprocess
from PIL import Image, ImageChops, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "assets", "cases")
SRC = os.path.join(HERE, "src", "cases")
FONT = os.path.join(HERE, "src", "fonts", "NunitoSans.ttf")
SIZE = (600, 900)
SS = 2                                      # drawn twice as large, then shrunk: smooth corners and edges
WHITE, BLACK = (255, 255, 255), (16, 16, 18)


def box_png(name, box, ink):
    """A Simple Icons mark in a square `box` pixels wide (times SS), painted in `ink`, cut to what is drawn."""
    with open(os.path.join(SRC, name), encoding="utf-8") as f:
        svg = f.read().replace("<path ", '<path fill="#%02x%02x%02x" ' % ink, 1)
    png = subprocess.run(["rsvg-convert", "-f", "png", "-w", str(box * SS), "-h", str(box * SS)], input=svg.encode(), check=True, capture_output=True).stdout
    im = Image.open(io.BytesIO(png)).convert("RGBA")
    return im.crop(im.getchannel("A").getbbox())


def text(words, size, ink, spacing=0.0, bold=2):
    """The words in Nunito Sans as a picture cut to what is drawn; `spacing` is extra space between letters (in pixels), `bold` a faux-bold stroke."""
    font = ImageFont.truetype(FONT, int(size * SS))
    width = int(sum(font.getlength(c) + spacing * SS for c in words)) + 8 * SS
    im = Image.new("RGBA", (width, int(size * SS * 1.6)), (0, 0, 0, 0))
    d, x = ImageDraw.Draw(im), 4 * SS
    for c in words:
        d.text((x, 4 * SS), c, font=font, fill=ink + (255,), stroke_width=bold, stroke_fill=ink + (255,))
        x += font.getlength(c) + spacing * SS
    return im.crop(im.getchannel("A").getbbox())


def gradient(size, top, bottom):
    """A vertical gradient picture of `size` (already times SS)."""
    mask = Image.linear_gradient("L").resize(size)
    return Image.composite(Image.new("RGB", size, bottom), Image.new("RGB", size, top), mask).convert("RGBA")


class Canvas:
    def __init__(self):
        self.im = Image.new("RGBA", (SIZE[0] * SS, SIZE[1] * SS), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.im)

    def px(self, box):
        return tuple(int(v * SS) for v in box)

    def shell(self, colour, radius, edge=None):
        self.d.rounded_rectangle((0, 0, self.im.width - 1, self.im.height - 1), radius * SS, fill=colour + (255,), outline=edge + (255,) if edge else None, width=2 * SS)
        self.silhouette = Image.new("L", self.im.size, 0)
        ImageDraw.Draw(self.silhouette).rounded_rectangle((0, 0, self.im.width - 1, self.im.height - 1), radius * SS, fill=255)

    def fill(self, box, colour):
        x0, y0, x1, y1 = self.px(box)
        self.d.rectangle((x0, y0, x1 - 1, y1 - 1), fill=colour + (255,))          # PIL's rectangle includes its last pixel: stop one short, so the edge is exact

    def gradient(self, box, top, bottom):
        x0, y0, x1, y1 = self.px(box)
        self.im.alpha_composite(gradient((x1 - x0, y1 - y0), top, bottom), (x0, y0))

    def put(self, im, x, cy, anchor="l"):
        """Lay a picture so its vertical middle is at `cy` and its left edge (or middle with anchor "c", right edge with "r") is at `x` (all 1x numbers)."""
        left = int(x * SS) - (0 if anchor == "l" else im.width // 2 if anchor == "c" else im.width)
        self.im.alpha_composite(im, (left, int(cy * SS) - im.height // 2))

    def row(self, items, cx, cy, gap):
        """Pictures side by side, the row centred on `cx`."""
        total = sum(i.width for i in items) + gap * SS * (len(items) - 1)
        x = cx * SS - total // 2
        for i in items:
            self.im.alpha_composite(i, (int(x), int(cy * SS) - i.height // 2))
            x += i.width + gap * SS

    def poly(self, points, colour):
        self.d.polygon([(x * SS, y * SS) for x, y in points], fill=colour + (255,))

    def punch(self, window):
        self.d.rectangle(self.px(window), fill=(0, 0, 0, 0))

    def finish(self):
        self.im.putalpha(ImageChops.multiply(self.im.getchannel("A"), self.silhouette))
        return self.im.resize(SIZE, Image.BOX)           # BOX: an exact 2:1 shrink, so the window's edge stays sharp


def xbox360():
    c, t, b = Canvas(), 20, 112
    c.shell((108, 182, 36), 24)
    c.gradient((t, t, 600 - t, b), (255, 255, 255), (226, 232, 224))
    swoosh = Canvas()                                  # green stripes on the right of the banner, cut to the banner
    for x, w, col in ((352, 66, (138, 200, 50)), (422, 40, (46, 128, 28)), (466, 34, (108, 182, 36)), (504, 24, (34, 110, 26)), (532, 44, (150, 206, 56))):
        swoosh.d.polygon([(x * SS, b * SS), ((x + 46) * SS, t * SS), ((x + 46 + w) * SS, t * SS), ((x + w) * SS, b * SS)], fill=col + (255,))
    clip = Image.new("L", swoosh.im.size, 0)
    ImageDraw.Draw(clip).rectangle(c.px((t, t, 600 - t, b)), fill=255)
    swoosh.im.putalpha(ImageChops.multiply(swoosh.im.getchannel("A"), clip))
    c.im.alpha_composite(swoosh.im)
    c.put(box_png("xbox.svg", 70, (126, 132, 138)), t + 20, (t + b) // 2)
    c.put(text("XBOX 360", 42, (100, 106, 112), spacing=0.7, bold=3), t + 20 + 70 + 14, (t + b) // 2)
    window = (t, b, 600 - t, 900 - t)
    c.punch(window)
    return c, window, {"marks_dy": b}


def xboxone(model, size=46, spacing=0.6):
    c, t, b = Canvas(), 16, 96
    c.shell((16, 126, 16), 18)
    c.gradient((t, t, 600 - t, b), (24, 142, 24), (14, 118, 14))
    c.fill((t, b - 3, 600 - t, b), (8, 88, 8))
    c.row([box_png("xbox.svg", 60, WHITE), text(model, size, WHITE, spacing=spacing, bold=3)], 300, (t + b - 3) // 2, 14)
    window = (t, b, 600 - t, 900 - t)
    c.punch(window)
    return c, window, {"marks_dy": b}


def xboxseries():
    """From photographs: a thin green shell, the art up to the top edge, and a slanted tab at the top-left: the sphere on green, then a white slant with the name."""
    c, t, h = Canvas(), 16, 112
    c.shell((16, 126, 16), 18)
    window = (t, t, 600 - t, 900 - t)
    c.punch(window)
    c.poly([(t, t), (t + 336, t), (t + 288, t + h), (t, t + h)], (16, 126, 16))                  # the green tab
    c.poly([(t + 132, t), (t + 336, t), (t + 288, t + h), (t + 86, t + h)], (252, 252, 252))      # the white slant on it
    c.put(box_png("xbox.svg", 62, WHITE), t + 20, t + h // 2)
    c.put(text("Xbox Series X", 23, (72, 76, 80), bold=2), t + 148, t + h // 2)
    return c, window, {"marks_dy": 0, "corner": [t, t + h], "overlay": [t, t, t + 337, t + h + 1]}        # +1: PIL draws a polygon's last pixel too, a half pixel after the shrink


def psn():
    """"PlayStation.Network" as the PS3 covers show it, typeset (no logo file for it): a round badge and the name, in white."""
    badge = Canvas()
    d = badge.d
    d.ellipse((0, 0, 30 * SS, 30 * SS), fill=(92, 88, 204, 255))
    cx = cy = 15 * SS
    d.polygon([(cx, 4 * SS), (cx + 3 * SS, cy - 3 * SS), (26 * SS, cy), (cx + 3 * SS, cy + 3 * SS), (cx, 26 * SS), (cx - 3 * SS, cy + 3 * SS), (4 * SS, cy), (cx - 3 * SS, cy - 3 * SS)], fill=WHITE + (255,))
    icon = badge.im.crop((0, 0, 30 * SS, 30 * SS))
    name = text("PlayStation.Network", 21, WHITE, spacing=0.2, bold=1)
    out = Image.new("RGBA", (icon.width + 10 * SS + name.width, 30 * SS), (0, 0, 0, 0))
    out.alpha_composite(icon, (0, 0))
    out.alpha_composite(name, (icon.width + 10 * SS, (30 * SS - name.height) // 2))
    return out


def ps(shell, banner_top, banner_bottom, ink, wordmark, line=None, t=10, b=84, radius=14, right=None):
    """The PlayStation cases. PS3 and PS4 are printed inserts that run edge to edge (t=0): a banner with the PS mark and the model, a thin line under it."""
    c = Canvas()
    c.shell(shell, radius)
    c.gradient((t, t, 600 - t, b), banner_top, banner_bottom)
    mark, word = box_png("playstation.svg", 56, ink), box_png(wordmark, 210, ink)
    c.put(mark, 26, (t + b) // 2)
    c.put(word, 26 + mark.width / SS + 18, (t + b) // 2)
    if right:
        c.put(right, 600 - 22, (t + b) // 2, "r")
    top = b
    if line:
        c.fill((t, b, 600 - t, b + 3), line)
        top = b + 3
    window = (t, top, 600 - t, 900 - t)
    c.punch(window)
    return c, window, {"marks_dy": top}


def ps5():
    c, t, b = Canvas(), 16, 100
    c.shell((26, 80, 204), 28)
    c.fill((t, t, 600 - t, b), (253, 253, 253))
    mark, word = box_png("playstation.svg", 58, BLACK), box_png("playstation5.svg", 220, BLACK)
    c.put(mark, 30, (t + b) // 2)
    c.put(word, 30 + mark.width / SS + 18, (t + b) // 2)
    window = (t, b + 4, 600 - t, 900 - t)
    c.punch(window)
    return c, window, {"marks_dy": b + 4}


def switch():
    c, t = Canvas(), 16
    c.shell((228, 230, 234), 24, edge=(176, 180, 188))
    window = (t, t, 600 - t, 900 - t)
    c.punch(window)
    tab = (t, t, t + 150, t + 172)                      # the red tab in the corner, over the art
    c.fill(tab, (230, 0, 18))
    c.put(box_png("nintendoswitch.svg", 74, WHITE), t + 75, t + 58, "c")
    c.put(text("NINTENDO", 16, WHITE, spacing=3.6, bold=2), t + 75, t + 122, "c")
    c.put(text("SWITCH", 26, WHITE, spacing=2.8, bold=2), t + 75, t + 149, "c")
    return c, window, {"marks_dy": 0, "corner": [t, tab[3]], "overlay": list(tab)}


def switch2():
    c, t, b = Canvas(), 14, 152
    c.shell((214, 4, 24), 30)
    c.gradient((t, t, 600 - t, b), (236, 14, 30), (222, 8, 26))
    c.row([box_png("nintendoswitch.svg", 70, WHITE), text("2", 80, WHITE, bold=3)], 300, 54, 10)
    c.put(text("NINTENDO", 18, WHITE, spacing=3.8, bold=2), 300, 104, "c")
    c.put(text("SWITCH", 29, WHITE, spacing=3.0, bold=2), 300, 130, "c")
    window = (t, b, 600 - t, 900 - t)
    c.punch(window)
    return c, window, {"marks_dy": b}


CASES = {
    "ps3": lambda: ps((16, 16, 18), (74, 74, 78), (4, 4, 6), WHITE, "playstation3.svg", line=(150, 22, 44), t=0, b=76, radius=8, right=psn()),
    "ps4": lambda: ps((18, 108, 214), (22, 116, 222), (0, 70, 160), WHITE, "playstation4.svg", t=0, b=84, radius=8),
    "ps5": ps5,
    "xbox360": xbox360,
    "xboxone": lambda: xboxone("XBOX ONE"),
    "xboxseries": xboxseries,
    "switch": switch,
    "switch2": switch2,
}


def main():
    os.makedirs(OUT, exist_ok=True)
    info = {}
    for key, make in CASES.items():
        canvas, window, extra = make()
        canvas.finish().save(os.path.join(OUT, key + ".png"), format="PNG", optimize=True)
        info[key] = dict({"window": list(window)}, **extra)
    with open(os.path.join(OUT, "cases.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, indent=1, sort_keys=True)
        f.write("\n")
    print("wrote", len(CASES), "cases to", os.path.normpath(OUT))


if __name__ == "__main__":
    main()
