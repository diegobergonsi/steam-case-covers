#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Maintainers only: render assets/preview.png (the README header and GitHub social preview, 1280x640).

    python tools/build_preview.py COVERS_DIR [OUT.png] [APPID x5, left to right]

COVERS_DIR holds covers made by the app (files named Game_Name_<appid>.png). The default five games are
SnowRunner, Coral Island, Clair Obscur: Expedition 33, Fallout 4 and V Rising; the middle one is drawn on top."""
import glob, os, sys
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = os.path.join(HERE, "src", "fonts", "NunitoSans.ttf")
DEFAULT_IDS = ["1465360", "1158160", "1903340", "377160", "1604030"]
W, H = 1280, 640
TITLE = "Steam Case Covers"


def font(size, weight):
    f = ImageFont.truetype(FONT, size)
    try:
        f.set_variation_by_name(weight)
    except Exception:
        pass
    return f


def main(covers_dir, out, ids):
    bg = Image.new("RGB", (W, H))
    px = bg.load()
    for y in range(H):
        for x in range(W):
            t = (x / W) * 0.6 + (y / H) * 0.4
            px[x, y] = (int(23 + 11 * (1 - t) + 6 * t), int(26 + 36 * (1 - t) * 0.9), int(33 + 63 * (1 - t) * 0.9 + 6 * t))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((620, 60, 1320, 760), fill=(102, 192, 244, 70))
    bg = Image.alpha_composite(bg.convert("RGBA"), glow.filter(ImageFilter.GaussianBlur(110)))

    angles, xs, h = [14, 7, 0, -7, -14], [780, 850, 920, 990, 1060], 380
    for i in [0, 4, 1, 3, 2]:                                   # outer cards first, the middle one last (on top)
        found = glob.glob(os.path.join(covers_dir, "*_%s.png" % ids[i]))
        if not found:
            sys.exit("No cover for app %s in %s" % (ids[i], covers_dir))
        im = Image.open(found[0]).convert("RGBA")
        im = im.resize((round(im.width * h / im.height), h), Image.LANCZOS).rotate(angles[i], resample=Image.BICUBIC, expand=True)
        pad = 50                                                # room for the blur, or it is cut off in a hard edge
        alpha = Image.new("L", (im.width + 2 * pad, im.height + 2 * pad), 0)
        alpha.paste(im.getchannel("A").point(lambda a: int(a * 0.4)), (pad, pad))
        shadow = Image.merge("RGBA", (Image.new("L", alpha.size, 0),) * 3 + (alpha,)).filter(ImageFilter.GaussianBlur(14))
        pos = (xs[i] + 40 - im.width // 2, 295 + abs(angles[i]) * 2 - im.height // 2)
        bg.alpha_composite(shadow, (pos[0] - 8 - pad, pos[1] + 14 - pad))
        bg.alpha_composite(im, pos)

    d = ImageDraw.Draw(bg)
    title_font = font(58, "ExtraBold")
    if d.textlength(TITLE, font=title_font) > 560:
        sys.exit("Title too wide for the layout; lower the font size.")
    d.text((70, 160), TITLE, font=title_font, fill="white")
    d.rectangle((72, 240, 232, 245), fill=(102, 192, 244))
    sub = font(35, "Regular")
    d.text((72, 275), "Give every game in your Steam", font=sub, fill=(199, 213, 224))
    d.text((72, 322), "library a physical case cover.", font=sub, fill=(199, 213, 224))
    d.text((72, 410), "Local  ·  No API key  ·  No uploads", font=font(28, "SemiBold"), fill=(102, 192, 244))
    d.text((72, 470), "Windows · macOS · Linux · Steam Deck", font=font(22, "Regular"), fill=(138, 160, 178))
    bg.convert("RGB").save(out, optimize=True)
    print("wrote", out, os.path.getsize(out), "bytes")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    ids = sys.argv[3:8] if len(sys.argv) >= 8 else DEFAULT_IDS
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..", "assets", "preview.png"), ids)
