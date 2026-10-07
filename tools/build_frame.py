#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Maintainers only: render assets/frame.png (600x900, transparent art window) from SVG.
Needs rsvg-convert (librsvg). Users of steamcase.py do NOT need this: frame.png is committed."""
import os, re, base64, subprocess, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")
OUT = os.path.join(HERE, "..", "assets", "frame.png")

W, H = 600, 900
L, R, T, B = 14, 586, 14, 872   # art+banner box
BAR = 78
AT = T + BAR + 4                # art window top  (window = L..R x AT..B)

svg_logo = open(os.path.join(SRC, "steam_logo.svg")).read()
DISC, MARK = re.findall(r'<path d="([^"]+)"', svg_logo)[:2]
TUX = base64.b64encode(open(os.path.join(SRC, "tux.svg"), "rb").read()).decode()
cy = T + BAR / 2

svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<defs>
 <linearGradient id="case" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2f5fe8"/><stop offset=".5" stop-color="#1636c8"/><stop offset="1" stop-color="#0a1e90"/></linearGradient>
 <linearGradient id="bar" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0d3a82"/><stop offset="1" stop-color="#051c4d"/></linearGradient>
 <linearGradient id="gloss" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".13"/><stop offset=".3" stop-color="#fff" stop-opacity="0"/></linearGradient>
 <linearGradient id="fade" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
 <mask id="dm"><rect x="{L}" y="{T}" width="190" height="{BAR}" fill="url(#fade)"/></mask>
 <mask id="hole"><rect width="{W}" height="{H}" fill="#fff"/><rect x="{L}" y="{AT}" width="{R-L}" height="{B-AT}" fill="#000"/></mask>
 <pattern id="dots" width="12" height="12" patternUnits="userSpaceOnUse"><circle cx="6" cy="6" r="2.4" fill="#5d8fd6" opacity=".55"/></pattern>
 <clipPath id="ban"><rect x="{L}" y="{T}" width="{R-L}" height="{BAR}" rx="4"/></clipPath>
 <filter id="white"><feColorMatrix type="matrix" values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 1 0"/></filter>
</defs>
<g mask="url(#hole)">
 <rect x="0" y="0" width="{W}" height="{H}" rx="20" fill="url(#case)"/>
 <rect x="1.5" y="1.5" width="{W-3}" height="{H-3}" rx="19" fill="none" stroke="#8fb2ff" stroke-opacity=".55" stroke-width="2"/>
 <rect x="14" y="{B+2}" width="{R-L}" height="12" rx="3" fill="#0b2bb5"/>
 <rect x="14" y="{B+2}" width="{R-L}" height="2.5" fill="#4d7cf2" opacity=".8"/>
 <rect x="30" y="{B+10}" width="{R-L-32}" height="2" fill="#061a78" opacity=".8"/>
 <g clip-path="url(#ban)">
  <rect x="{L}" y="{T}" width="{R-L}" height="{BAR}" fill="url(#bar)"/>
  <rect x="{L}" y="{T}" width="190" height="{BAR}" fill="url(#dots)" mask="url(#dm)"/>
 </g>
 <rect x="{L}" y="{T+BAR}" width="{R-L}" height="4" fill="#2e86e6"/>
 <rect x="{L}" y="{T+BAR}" width="{R-L}" height="1.2" fill="#7fc0ff" opacity=".8"/>
 <g transform="translate(196,{cy-24}) scale({48/32})"><path d="{DISC}" fill="#fff"/><path d="{MARK}" fill="#0a2a66"/></g>
 <text x="252" y="{cy+13}" font-family="Nunito Sans, sans-serif" font-weight="bold" font-size="40" letter-spacing="4" fill="#fff" stroke="#fff" stroke-width="1.8" stroke-linejoin="round">STEAM</text>
 <image href="data:image/svg+xml;base64,{TUX}" x="484" y="{cy-27}" width="28" height="28" filter="url(#white)"/>
 <text x="498" y="{cy+19}" text-anchor="middle" font-family="Nunito Sans, sans-serif" font-size="12" fill="#cfe0ff">Linux</text>
 <g fill="#fff" transform="translate(541,{cy-22})"><rect width="11" height="11"/><rect x="13" width="11" height="11"/><rect y="13" width="11" height="11"/><rect x="13" y="13" width="11" height="11"/></g>
 <text x="553" y="{cy+19}" text-anchor="middle" font-family="Nunito Sans, sans-serif" font-size="12" fill="#cfe0ff">Windows</text>
</g>
<!-- gloss over everything, art window included -->
<rect x="0" y="0" width="{W}" height="{H}" rx="20" fill="url(#gloss)"/>
</svg>'''

with tempfile.TemporaryDirectory() as tmp:
    p = os.path.join(tmp, "frame.svg"); open(p, "w").write(svg)
    conf = os.path.join(tmp, "fc.conf")
    open(conf, "w").write(f'<?xml version="1.0"?><fontconfig><include ignore_missing="yes">/etc/fonts/fonts.conf</include><dir>{SRC}/fonts</dir></fontconfig>')
    subprocess.run(["rsvg-convert", "-w", str(W), "-h", str(H), "-o", OUT, p], check=True, env={**os.environ, "FONTCONFIG_FILE": conf}, stderr=subprocess.DEVNULL)
print("wrote", os.path.normpath(OUT), "| art window:", (L, AT, R, B))
