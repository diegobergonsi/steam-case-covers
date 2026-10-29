#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Maintainers only: render assets/discord.png (96 x 96, Discord's blurple on transparency) from tools/src/discord.svg,
the Discord mark of Simple Icons (CC0). It is shown as a button in the window's header and only links to the project's server.
Needs rsvg-convert (librsvg)."""
import os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
SVG = os.path.join(HERE, "src", "discord.svg")
OUT = os.path.join(HERE, "..", "assets", "discord.png")

subprocess.run(["rsvg-convert", "-w", "96", "-h", "96", "-o", OUT, SVG], check=True)
print("wrote", os.path.normpath(OUT))
