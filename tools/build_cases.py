#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Maintainers only: draw assets/cases/<platform>.png (600x900, a transparent art window) and assets/cases/cases.json (the window of each).
PLACEHOLDER ART: plain coloured cases with the platform's name, so the whole feature can be built and tested. The real cases and logos replace this
(see docs/superpowers/plans/2026-10-31-platform-cases.md, task 11). Needs Pillow only. Users of steamcase.py do NOT need this: the files are committed."""
import json, os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "assets", "cases")
FONT = os.path.join(HERE, "src", "fonts", "NunitoSans.ttf")
SIZE = (600, 900)
RADIUS = 36
SIDE = 16                                   # the case's border left and right of the art, and under it
# platform: (label, banner colour, banner height); the art window starts under the banner
CASES = {"ps3": ("PlayStation 3", (20, 20, 24), 90), "ps4": ("PlayStation 4", (0, 67, 156), 90), "ps5": ("PlayStation 5", (245, 245, 250), 90),
         "xbox360": ("Xbox 360", (108, 178, 30), 90), "xboxone": ("Xbox One", (16, 124, 16), 90),
         "xboxseries": ("Xbox Series X|S", (16, 124, 16), 90), "switch": ("Nintendo Switch", (230, 0, 18), 110),
         "switch2": ("Nintendo Switch 2", (230, 0, 18), 110)}


def draw_case(label, colour, banner):
    ss = 2                                  # drawn twice as large, then shrunk: smooth corners
    big = Image.new("RGBA", (SIZE[0] * ss, SIZE[1] * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    d.rounded_rectangle((0, 0, big.width - 1, big.height - 1), RADIUS * ss, fill=colour + (255,))
    window = (SIDE, banner, SIZE[0] - SIDE, SIZE[1] - SIDE)
    d.rectangle([v * ss for v in window], fill=(0, 0, 0, 0))
    light = sum(colour) > 600
    font = ImageFont.truetype(FONT, 40 * ss)
    d.text((SIZE[0] * ss // 2, banner * ss // 2), label, font=font, fill=(20, 20, 24, 255) if light else (255, 255, 255, 255), anchor="mm")
    return big.resize(SIZE, Image.BOX), window          # BOX: an exact 2:1 shrink, so the window's edge stays sharp


def main():
    os.makedirs(OUT, exist_ok=True)
    windows = {}
    for key, (label, colour, banner) in CASES.items():
        frame, window = draw_case(label, colour, banner)
        frame.save(os.path.join(OUT, key + ".png"), format="PNG", optimize=True)
        windows[key] = {"window": list(window)}
    with open(os.path.join(OUT, "cases.json"), "w", encoding="utf-8") as f:
        json.dump(windows, f, indent=1, sort_keys=True)
        f.write("\n")
    print("wrote", len(CASES), "cases to", os.path.normpath(OUT))


if __name__ == "__main__":
    main()
