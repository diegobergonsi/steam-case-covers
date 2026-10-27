#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Maintainers only: render assets/completion_overlay.png, the marks of a game with every achievement unlocked:
a rosette on top of the Linux and Windows badges (top right) and a blue ribbon with cut ends saying "100% Complete"
across the bottom of the art, transparent everywhere else. The app lays it over the finished cover.
The rosette is our own drawing in the colours of Steam's old achievement ribbon, not Valve's artwork.
frame.png itself is never rewritten. Drawn with Pillow at 3x, then scaled down for smooth edges."""
import math, os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "assets", "completion_overlay.png")
FONT = os.path.join(HERE, "src", "fonts", "NunitoSans.ttf")

W, H, K = 600, 900, 3                   # cover size and supersampling
OUTLINE, FILL, TAIL = (38, 100, 170, 255), (111, 180, 240, 255), (88, 158, 226, 255)   # #2664aa, #6fb4f0, the legs' inner blue
DISC, RIM = (255, 207, 10, 255), (245, 160, 20, 255)                                   # #ffcf0a, #f5a014
BAND, ENDS, FOLD = (26, 159, 255, 255), (20, 120, 220, 255), (14, 86, 165, 255)        # #1a9fff, #1478dc, #0e56a5


def font(size):
    f = ImageFont.truetype(FONT, size * K)
    try:
        f.set_variation_by_name("ExtraBold")
    except Exception:                    # an older FreeType without variable fonts: the regular weight
        pass
    return f


def _scaled(pts, c, f):
    return [(c[0] + (x - c[0]) * f, c[1] + (y - c[1]) * f) for x, y in pts]


def rosette(d, cx, cy, r):
    """12-point starburst with a dark-blue outline, light-blue fill and a gold disc, over two swallow-tail legs."""
    for sgn in (-1, 1):                                       # legs first, so the starburst sits on top; they splay outwards
        ang = math.radians(sgn * 22)
        w, L, notch = .72 * r, 1.12 * r, .30 * r
        local = [(-w / 2, 0), (w / 2, 0), (w / 2, L), (0, L - notch), (-w / 2, L)]
        ax, ay = cx + sgn * .30 * r, cy + .30 * r             # where the leg starts, under the starburst
        t = [(ax + x * math.cos(ang) + y * math.sin(ang), ay + y * math.cos(ang) - x * math.sin(ang)) for x, y in local]
        c = (sum(p[0] for p in t) / 5, sum(p[1] for p in t) / 5)
        d.polygon(t, fill=OUTLINE)
        d.polygon(_scaled(t, c, .78), fill=TAIL)
    pts = []
    for i in range(24):
        a = math.radians(90 + i * 15)
        rad = r if i % 2 == 0 else r * .80
        pts.append((cx + rad * math.cos(a), cy + rad * math.sin(a)))
    d.polygon(pts, fill=OUTLINE)
    d.polygon(_scaled(pts, (cx, cy), .86), fill=FILL)
    d.ellipse([cx - r * .55, cy - r * .55, cx + r * .55, cy + r * .55], fill=RIM)
    d.ellipse([cx - r * .50, cy - r * .50, cx + r * .50, cy + r * .50], fill=DISC)


def ribbon(d):
    """The band across the bottom of the art, its ends cut in a V at the art's edges and folded behind it."""
    k = K
    d.polygon([(14 * k, 806 * k), (70 * k, 806 * k), (70 * k, 866 * k), (14 * k, 866 * k), (40 * k, 836 * k)], fill=ENDS)
    d.polygon([(586 * k, 806 * k), (530 * k, 806 * k), (530 * k, 866 * k), (586 * k, 866 * k), (560 * k, 836 * k)], fill=ENDS)
    d.polygon([(54 * k, 850 * k), (70 * k, 850 * k), (70 * k, 866 * k)], fill=FOLD)
    d.polygon([(546 * k, 850 * k), (530 * k, 850 * k), (530 * k, 866 * k)], fill=FOLD)
    d.rectangle([54 * k, 790 * k, 546 * k, 850 * k], fill=BAND)
    d.text((300 * k, 820 * k), "100% Complete", font=font(40), fill=(255, 255, 255, 255), anchor="mm")


im = Image.new("RGBA", (W * K, H * K), (0, 0, 0, 0))
d = ImageDraw.Draw(im)
rosette(d, 526 * K, 66 * K, 62 * K)
ribbon(d)
im.resize((W, H), Image.LANCZOS).save(OUT, format="PNG", optimize=True)
print("wrote", os.path.normpath(OUT))
