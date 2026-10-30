# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""What the packaged app proves about the engine inside its bundle (`--selftest`): the same checks the Tk window made. No Qt in here."""
import os
import sys
import tempfile

import steamcase as sc
from qtui import system


def engine_problems():
    """A list of sentences, empty when the engine in this bundle works: the pictures are there, secure connections have certificates, a cover is built
    and recognised, the case colour can be changed, and the programs we start do not inherit the bundled libraries."""
    problems = []
    for what, path in (("frame image", sc.FRAME), ("icon", os.path.join(sc.HERE, "assets", "icon.png")), ("Discord icon", os.path.join(sc.HERE, "assets", "discord.png")),
                       ("Halloween overlay", sc.HALLOWEEN_OVERLAY), ("family corner image", sc.FAMILY_CORNER), ("completion overlay", sc.COMPLETION_OVERLAY), ("default art", sc.DEFAULT_ART)):
        if not os.path.exists(path):
            problems.append("%s missing: %s" % (what, path))
    system.restore_child_env()
    try:
        if sc._ssl_context().cert_store_stats()["x509_ca"] <= 0:
            problems.append("no trusted certificates loaded: secure connections to Steam would fail")
    except Exception as e:
        problems.append("secure connections cannot be set up: %s" % e)
    if getattr(sys, "frozen", False) and sys.platform.startswith("linux") and getattr(sys, "_MEIPASS", "\0") in os.environ.get("LD_LIBRARY_PATH", ""):
        problems.append("child programs would inherit the bundled libraries")
    try:
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            src, out = os.path.join(d, "p.png"), os.path.join(d, "c.png")
            Image.new("RGB", (600, 900), (200, 60, 60)).save(src)
            sc.build_cover(src, out, Image.open(sc.FRAME).convert("RGBA"))
            im = Image.open(out)
            if im.size != (600, 900):
                problems.append("a cover has the wrong size %s" % (im.size,))
            elif im.getpixel((300, 500))[:3] != (200, 60, 60):
                problems.append("the art window of a cover is not filled")
            if sc.cover_colour(out) != (0, 100, 100):
                problems.append("the cover does not record its colour")
            blue = sc.preview_cover(0).getpixel((7, 450))
            turned = sc.preview_cover(134)
            if not (turned.size == (600, 900) and turned.getpixel((7, 450)) != blue):
                problems.append("the case colour cannot be changed")
            if sc.preview_cover(0, sat=0, val=14).getpixel((7, 450)) == blue:
                problems.append("the case cannot be made black")
            for label, kwargs, frame in (("a black cover", {"sat": 0, "val": 14}, sc.load_frame(0, sat=0, val=14)), ("a 100% cover", {"treatment": "ribbon"}, sc.load_frame(0)),
                                         ("a rosette-only cover", {"treatment": "rosette"}, sc.load_frame(0)),
                                         ("a Halloween cover", {"treatment": "rosette", "theme": "halloween"}, sc.load_frame(0))):
                path = os.path.join(d, label.replace(" ", "_") + ".png")
                sc.build_cover(src, path, frame, **kwargs)
                if not sc.is_steamcase_cover(path):
                    problems.append("%s is not recognised as ours" % label)
                if "treatment" in kwargs and sc.cover_treatment(path) != kwargs["treatment"]:
                    problems.append("%s does not record its style" % label)
    except Exception as e:
        problems.append("a cover could not be built: %s" % e)
    return problems
