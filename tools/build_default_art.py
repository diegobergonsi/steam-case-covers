#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Maintainers only: render assets/default_art.png (600x900) from tools/src/default_art.svg.
The window uses this original artwork to preview the case colour before any game's art has been downloaded.
Needs rsvg-convert (librsvg) and Pillow. Users of steamcase.py do NOT need this: default_art.png is committed."""
import os, subprocess, tempfile
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")
OUT = os.path.join(HERE, "..", "assets", "default_art.png")

with tempfile.TemporaryDirectory() as tmp:
    conf = os.path.join(tmp, "fc.conf")
    with open(conf, "w") as f:
        f.write(f'<?xml version="1.0"?><fontconfig><include ignore_missing="yes">/etc/fonts/fonts.conf</include><dir>{SRC}/fonts</dir></fontconfig>')
    png = os.path.join(tmp, "art.png")
    subprocess.run(["rsvg-convert", "-w", "600", "-h", "900", "-o", png, os.path.join(SRC, "default_art.svg")], check=True,
                   env={**os.environ, "FONTCONFIG_FILE": conf}, stderr=subprocess.DEVNULL)
    Image.open(png).convert("RGB").save(OUT, format="PNG", optimize=True)
print("wrote", os.path.normpath(OUT))
