#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Maintainers only: draw assets/flag_us.png and assets/flag_br.png (72 x 48, shown at 24 x 16 in the window) for the language buttons.
Simple drawings made for this project with Pillow, no font or file needed: the stripes and the canton of the United States, and the green field, yellow
diamond and blue circle with its white band of Brazil (no stars or lettering at this size)."""
import math, os
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "assets")
W, H, K = 72, 48, 8                        # final size, and the scale of the drawing before it is shrunk (smooth edges)


def us():
    im = Image.new("RGB", (W * K, H * K), (255, 255, 255))
    d = ImageDraw.Draw(im)
    stripe = H * K / 13
    for i in range(0, 13, 2):
        d.rectangle([0, round(i * stripe), W * K, round((i + 1) * stripe) - 1], fill=(178, 34, 52))
    d.rectangle([0, 0, round(W * K * 0.4), round(7 * stripe) - 1], fill=(60, 59, 110))
    for row in range(5):                    # a small grid of white dots in the canton stands for the stars
        for col in range(6):
            x = (col + 0.7) * W * K * 0.4 / 6.4 + (0.5 if row % 2 else 0) * W * K * 0.4 / 13
            y = (row + 0.7) * 7 * stripe / 5.4
            d.ellipse([x - 5, y - 5, x + 5, y + 5], fill=(255, 255, 255))
    return im.resize((W, H), Image.LANCZOS)


def br():
    im = Image.new("RGB", (W * K, H * K), (0, 156, 59))
    d = ImageDraw.Draw(im)
    cx, cy = W * K / 2, H * K / 2
    d.polygon([(cx, H * K * 0.08), (W * K * 0.92, cy), (cx, H * K * 0.92), (W * K * 0.08, cy)], fill=(255, 223, 0))
    r = H * K * 0.30
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(0, 39, 118))
    band = []                              # the white band across the circle: an arc, drawn as a thick curve
    for i in range(0, 101):
        t = i / 100
        x = cx - r * 0.95 + t * r * 1.9
        y = cy + r * 0.12 - math.sin(t * math.pi) * r * 0.42
        band.append((x, y))
    d.line(band, fill=(255, 255, 255), width=round(r * 0.14))
    return im.resize((W, H), Image.LANCZOS)


if __name__ == "__main__":
    for name, draw in (("flag_us.png", us), ("flag_br.png", br)):
        path = os.path.join(OUT, name)
        draw().save(path, optimize=True)
        print("wrote", os.path.normpath(path))
