#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Maintainers only: render assets/halloween_overlay.png from tools/src/halloween.svg: the decorations of the Halloween case theme
(a cobweb with a spider in the bottom-left corner, a pumpkin in the bottom-right corner and a spider hanging from the top centre),
600 x 900 and transparent everywhere else. The app lays it over the finished case. The drawing is original artwork.
Needs rsvg-convert (librsvg). frame.png itself is never rewritten."""
import os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
SVG = os.path.join(HERE, "src", "halloween.svg")
OUT = os.path.join(HERE, "..", "assets", "halloween_overlay.png")

subprocess.run(["rsvg-convert", "-w", "600", "-h", "900", "-o", OUT, SVG], check=True)
print("wrote", os.path.normpath(OUT))
