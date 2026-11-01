#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Maintainers only: write assets/cases/cases.json from the frames in assets/cases/<platform>.png (600x900, a see-through art window).
"window" is the box of the fully see-through pixels; "overlay", only if the frame still covers part of that box (the Switch's tab, the Series X's tab), is the box of
what it covers. Run it after replacing a frame. Needs Pillow. Users of steamcase.py do NOT need this: the files are committed."""
import json, os
from PIL import Image

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "cases")
PLATFORMS = ("ps3", "ps4", "ps5", "xbox360", "xboxone", "xboxseries", "switch", "switch2")


def measure(path):
    """{"window": [x0, y0, x1, y1]} and, if the frame covers part of it, "overlay": [x0, y0, x1, y1]."""
    alpha = Image.open(path).convert("RGBA").getchannel("A")
    window = alpha.point(lambda a: 255 if a == 0 else 0).getbbox()
    info = {"window": list(window)}
    tab = alpha.crop(window).point(lambda a: 255 if a else 0).getbbox()
    if tab:
        info["overlay"] = [tab[0] + window[0], tab[1] + window[1], tab[2] + window[0], tab[3] + window[1]]
    return info


if __name__ == "__main__":
    cases = {p: measure(os.path.join(OUT, p + ".png")) for p in PLATFORMS}
    with open(os.path.join(OUT, "cases.json"), "w", encoding="utf-8") as f:
        json.dump(cases, f, indent=1, sort_keys=True)
        f.write("\n")
    print(json.dumps(cases))
