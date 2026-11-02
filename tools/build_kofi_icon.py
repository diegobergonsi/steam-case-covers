#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Maintainers only: render assets/kofi.png (96 x 96, Ko-fi's coral on transparency) from tools/src/kofi.svg,
the Ko-fi mark of Simple Icons (CC0). It is shown as a button in the window's navigation and only links to the author's Ko-fi page.
Needs rsvg-convert (librsvg)."""
import os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
SVG = os.path.join(HERE, "src", "kofi.svg")
OUT = os.path.join(HERE, "..", "assets", "kofi.png")

subprocess.run(["rsvg-convert", "-w", "96", "-h", "96", "-o", OUT, SVG], check=True)
print("wrote", os.path.normpath(OUT))
