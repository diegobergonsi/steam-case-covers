#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Maintainers only: render assets/family_corner.png, the overlay for games from the Steam Family library:
a green triangle in the top-left corner with a white three-person icon on it, transparent everywhere else.
The app lays it over the (possibly recoloured) frame, so the corner stays green in every case colour.
frame.png itself is never rewritten (covers made with it must stay recognisable). Needs rsvg-convert (librsvg) and Pillow."""
import os, subprocess, tempfile
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "assets", "family_corner.png")

GREEN = "#2e7d32"       # white on it: 5.1:1
LEG = 205               # triangle legs, in cover pixels
# The icon is drawn in a 720x640 box (after Steam's Family icon: two people behind, a smaller one in front with a gap around it).
# The transform puts its 62x54 box at (26, 26), so the gap to both legs and to the diagonal is the same.
ICON = f'''<g transform="translate(57 53) scale(.1) translate(-358 -318)">
  <g fill="#fff">
   <circle cx="185" cy="135" r="88"/><circle cx="532" cy="135" r="88"/>
   <path d="M48 550 L48 410 Q48 280 180 280 L260 280 L260 550 Z"/>
   <path d="M669 550 L669 410 Q669 280 537 280 L457 280 L457 550 Z"/>
  </g>
  <g fill="#fff" stroke="{GREEN}" stroke-width="110" paint-order="stroke">
   <circle cx="358" cy="320" r="78"/>
   <path d="M222 590 Q222 455 358 455 Q495 455 495 590 Z"/>
  </g>
</g>'''

svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="600" height="900" viewBox="0 0 600 900">
<defs><clipPath id="case"><rect width="600" height="900" rx="20"/></clipPath></defs>
<g clip-path="url(#case)"><path d="M0 0 L{LEG} 0 L0 {LEG} Z" fill="{GREEN}"/></g>
<path d="M{LEG} 0 L0 {LEG}" stroke="#fff" stroke-width="4" fill="none"/>
{ICON}
</svg>'''

with tempfile.TemporaryDirectory() as tmp:
    src, png = os.path.join(tmp, "family.svg"), os.path.join(tmp, "family.png")
    with open(src, "w") as f:
        f.write(svg)
    subprocess.run(["rsvg-convert", "-w", "600", "-h", "900", "-o", png, src], check=True)
    Image.open(png).convert("RGBA").save(OUT, format="PNG", optimize=True)
print("wrote", os.path.normpath(OUT))
