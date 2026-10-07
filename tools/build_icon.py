#!/usr/bin/env python3
"""Maintainers only: render assets/icon.png, icon.ico and icon.icns from tools/src/icon.svg.
Needs rsvg-convert (librsvg) and Pillow."""
import os, subprocess, tempfile
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SVG = os.path.join(HERE, "src", "icon.svg")
OUT = os.path.join(HERE, "..", "assets")

def render(size, path):
    subprocess.run(["rsvg-convert", "-w", str(size), "-h", str(size), "-o", path, SVG], check=True)

with tempfile.TemporaryDirectory() as tmp:
    big = os.path.join(tmp, "icon_1024.png")
    render(1024, big)
    master = Image.open(big).convert("RGBA")
    master.resize((256, 256), Image.LANCZOS).save(os.path.join(OUT, "icon.png"), optimize=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    frames = []
    for s in sizes:                                   # render each size from the SVG so small ones stay crisp
        p = os.path.join(tmp, "s%d.png" % s); render(s, p); frames.append(Image.open(p).convert("RGBA"))
    frames[-1].save(os.path.join(OUT, "icon.ico"), sizes=[(s, s) for s in sizes], append_images=frames[:-1])
    master.save(os.path.join(OUT, "icon.icns"))
print("wrote icon.png, icon.ico, icon.icns in", os.path.normpath(OUT))
