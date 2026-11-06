#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Maintainers only: write assets/cases/cases.json from the frames in assets/cases/<platform>.png (600x900, a see-through art window).
"window" is the see-through part joined to the middle of the picture; "overlay", only if a tab of the frame still covers part of it (the Switch's tab, the Series X's tab),
is the box of that tab: the same measure the app uses for a case a user brings (steamcase.check_case_file, engine/caseframe.py). Run it after replacing a frame. Needs Pillow.
Users of steamcase.py do NOT need this: the files are committed."""
import json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from engine import steamcase as sc

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "cases")


if __name__ == "__main__":
    cases = {p: sc.check_case_file(os.path.join(OUT, p + ".png")) for p in sc.PLATFORMS}
    with open(os.path.join(OUT, "cases.json"), "w", encoding="utf-8") as f:
        json.dump(cases, f, indent=1, sort_keys=True)
        f.write("\n")
    print(json.dumps(cases))
