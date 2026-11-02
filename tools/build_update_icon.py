#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Maintainers only: render assets/update.png (96 x 96, the window's muted text colour on transparency) from tools/src/update.svg,
a refresh mark drawn for this project. It is shown beside "Check for updates" in the window's navigation.
Needs rsvg-convert (librsvg)."""
import os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
SVG = os.path.join(HERE, "src", "update.svg")
OUT = os.path.join(HERE, "..", "assets", "update.png")

subprocess.run(["rsvg-convert", "-w", "96", "-h", "96", "-o", OUT, SVG], check=True)
print("wrote", os.path.normpath(OUT))
