#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Maintainers only: draw assets/cases/<platform>.png (600x900, a transparent art window) and assets/cases/cases.json (the window of each).
A case is a rounded shell in the console's colour with a banner on top: the console's logo on the left, its model on the right.
The logos are in tools/src/cases/ (Simple Icons, CC0; see SOURCES.txt there). Where Simple Icons has no mark for a model (Xbox 360, Xbox One, Xbox Series X|S,
Switch 2) the console's mark is drawn with the model typeset in Nunito Sans, not the official wordmark.
Needs Pillow and rsvg-convert (librsvg). Users of steamcase.py do NOT need this: the files are committed."""
import io, json, os, subprocess
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "assets", "cases")
SRC = os.path.join(HERE, "src", "cases")
FONT = os.path.join(HERE, "src", "fonts", "NunitoSans.ttf")
SIZE = (600, 900)
RADIUS = 36
SIDE = 16                                   # the shell left, right and under the art
CONTENT = (190, 440)                        # the part of the banner the family corner and the 100% rosette leave free (x range)
MARK, WORDMARK, GAP = 46, 130, 14            # the console's mark (a square box), the PlayStation wordmark's box and the space between them
SS = 2                                      # drawn twice as large, then shrunk: smooth corners and edges
WHITE, BLACK = (255, 255, 255), (16, 20, 28)
# platform: banner colour, ink (logos and text), banner height, logo on the left, what is on the right: ("svg", file) or ("text", words)
CASES = {
    "ps3": {"shell": (22, 22, 26), "ink": WHITE, "banner": 90, "left": "playstation.svg", "right": ("svg", "playstation3.svg")},
    "ps4": {"shell": (0, 55, 145), "ink": WHITE, "banner": 90, "left": "playstation.svg", "right": ("svg", "playstation4.svg")},
    "ps5": {"shell": (244, 246, 250), "ink": (0, 55, 145), "banner": 90, "left": "playstation.svg", "right": ("svg", "playstation5.svg")},
    "xbox360": {"shell": (110, 190, 20), "ink": WHITE, "banner": 90, "left": "xbox.svg", "right": ("text", "360")},
    "xboxone": {"shell": (16, 124, 16), "ink": WHITE, "banner": 90, "left": "xbox.svg", "right": ("text", "ONE")},
    "xboxseries": {"shell": (16, 124, 16), "ink": WHITE, "banner": 90, "left": "xbox.svg", "right": ("text", "SERIES X|S")},
    "switch": {"shell": (230, 0, 18), "ink": WHITE, "banner": 100, "left": "nintendoswitch.svg", "right": ("text", "Nintendo Switch")},
    "switch2": {"shell": (230, 0, 18), "ink": WHITE, "banner": 100, "left": "nintendoswitch.svg", "right": ("text", "Nintendo Switch 2")},
}


def logo(name, box, ink):
    """A Simple Icons mark in a square `box` pixels wide (times SS), painted in `ink`. The marks sit in a 24 x 24 square: the wordmarks are wide and short."""
    with open(os.path.join(SRC, name), encoding="utf-8") as f:
        svg = f.read().replace("<path ", '<path fill="#%02x%02x%02x" ' % ink, 1)
    png = subprocess.run(["rsvg-convert", "-f", "png", "-w", str(box * SS), "-h", str(box * SS)], input=svg.encode(), check=True, capture_output=True).stdout
    return Image.open(io.BytesIO(png)).convert("RGBA")


def trimmed(im):
    """The picture cut to what is drawn (the marks sit in a square with room around them)."""
    return im.crop(im.getchannel("A").getbbox())


def draw_case(spec):
    big = Image.new("RGBA", (SIZE[0] * SS, SIZE[1] * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    d.rounded_rectangle((0, 0, big.width - 1, big.height - 1), RADIUS * SS, fill=spec["shell"] + (255,))
    banner = spec["banner"]
    window = (SIDE, banner, SIZE[0] - SIDE, SIZE[1] - SIDE)
    d.rectangle([v * SS for v in window], fill=(0, 0, 0, 0))
    mid = banner * SS // 2
    mark = trimmed(logo(spec["left"], MARK, spec["ink"]))
    kind, what = spec["right"]
    room = (CONTENT[1] - CONTENT[0]) * SS - mark.width - GAP * SS                  # what is left of the banner's middle part for the model
    if kind == "svg":
        word = trimmed(logo(what, WORDMARK, spec["ink"]))
    else:                                   # the model typeset: as large as fits, up to the banner's height
        size = 40 * SS
        while True:
            font = ImageFont.truetype(FONT, size)
            box = d.textbbox((0, 0), what, font=font, stroke_width=SS)
            if box[2] - box[0] <= room or size <= 10 * SS:
                break
            size -= SS
        word = Image.new("RGBA", (box[2] - box[0] + 2 * SS, box[3] - box[1] + 2 * SS), (0, 0, 0, 0))
        ImageDraw.Draw(word).text((SS - box[0], SS - box[1]), what, font=font, fill=spec["ink"] + (255,), stroke_width=SS, stroke_fill=spec["ink"] + (255,))
    total = mark.width + GAP * SS + word.width                                       # the mark and the model, together, in the middle of the banner:
    left = (CONTENT[0] + CONTENT[1]) * SS // 2 - total // 2                          # the family corner (left) and the 100% rosette (right) never cover them
    big.alpha_composite(mark, (left, mid - mark.height // 2))
    big.alpha_composite(word, (left + mark.width + GAP * SS, mid - word.height // 2))
    return big.resize(SIZE, Image.BOX), window          # BOX: an exact 2:1 shrink, so the window's edge stays sharp


def main():
    os.makedirs(OUT, exist_ok=True)
    windows = {}
    for key, spec in CASES.items():
        frame, window = draw_case(spec)
        frame.save(os.path.join(OUT, key + ".png"), format="PNG", optimize=True)
        windows[key] = {"window": list(window)}
    with open(os.path.join(OUT, "cases.json"), "w", encoding="utf-8") as f:
        json.dump(windows, f, indent=1, sort_keys=True)
        f.write("\n")
    print("wrote", len(CASES), "cases to", os.path.normpath(OUT))


if __name__ == "__main__":
    main()
