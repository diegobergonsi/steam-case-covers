# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""The case colour as the Look screen needs it: names (in words), hints, swatches and the colours of the sliders' tracks. No Qt in here."""
import math

import steamcase as sc
from qtui.i18n import N_, tr

ORIGINAL = (0, 100, 100)
HUE_NAMES = {0: N_("Original"), 42: N_("Violet"), 84: N_("Magenta"), 134: N_("Red"), 176: N_("Orange"), 276: N_("Green")}       # by the degrees of sc.HUE_SWATCHES
GREY_HINT = N_("Colour has no effect on grey or black.")


def clamp_tone(hue, sat, val):
    """(hue 0..359, colourfulness 0..100, brightness 0..100) as whole numbers; the hue wraps around, the others are limited.
    Anything that is not a finite number gives the original tone."""
    try:
        h, s, v = (float(x) for x in (hue, sat, val))
    except (TypeError, ValueError):
        return ORIGINAL
    if not all(math.isfinite(x) for x in (h, s, v)):
        return ORIGINAL
    return int(round(h)) % 360, min(max(int(round(s)), 0), 100), min(max(int(round(v)), 0), 100)


ORIGINAL_ANGLE = 210                                  # the original blue, in degrees on a colour wheel: the hue slider turns the case from there
BANDS = ((15, N_("red")), (40, N_("orange")), (65, N_("yellow")), (90, N_("lime")), (150, N_("green")), (175, N_("teal")), (200, N_("cyan")), (245, N_("blue")), (285, N_("violet")),
         (320, N_("magenta")), (340, N_("pink")), (360, N_("red")))   # the colour family up to each angle on the wheel
NEUTRAL_NAMES = (N_("Black"), N_("Graphite"), N_("Silver"))                 # the names sc.NEUTRAL_SWATCHES carries, so they get translated
DARK, PALE, GREY_AT = 45, 45, 8                       # brightness up to DARK is "dark", colourfulness up to PALE is "pale", up to GREY_AT is no colour at all


def tone_name(hue, sat, val):
    """A name for the case colour, in words: "Original", the ready-made names ("Red", "Silver"...), or the colour family with "Dark" or "Pale" ("Dark magenta").
    Never numbers: the sliders show those."""
    hue, sat, val = clamp_tone(hue, sat, val)
    key = sc.tone_key(hue, sat, val)
    if key == sc.tone_key(0):
        return tr("Original")
    for grey, s, v in sc.NEUTRAL_SWATCHES:
        if key == sc.tone_key(0, s, v):
            return tr(grey)
    for h in sc.HUE_SWATCHES:
        if key == sc.tone_key(h):
            return tr(HUE_NAMES[h])
    if sat <= GREY_AT or val <= 10:                    # no colour to speak of: a grey
        return tr("Black") if val <= 10 else tr("Dark grey") if val < 30 else tr("Grey") if val < 60 else tr("Light grey")
    angle = (ORIGINAL_ANGLE + hue) % 360
    word = tr(next(name for top, name in BANDS if angle < top))      # the colour family, in lower case: "blue"
    text = tr("Dark %s") % word if val <= DARK else tr("Pale %s") % word if sat <= PALE else word
    return text[:1].upper() + text[1:]


def tone_hint(hue, sat, val):
    """Without colour or light the Colour slider does nothing: say so."""
    _, sat, val = clamp_tone(hue, sat, val)
    return tr(GREY_HINT) if sat == 0 or val == 0 else ""


def swatches():
    """The nine ready-made tones: six colours at full tone, then three greys, as [{"name", "color", "hue", "sat", "val"}]."""
    out = [{"name": tr(HUE_NAMES[h]) if h in HUE_NAMES else tr("Colour %d°") % h, "color": sc.case_color(h), "hue": h, "sat": 100, "val": 100} for h in sc.HUE_SWATCHES]
    out += [{"name": tr(n), "color": sc.case_color(0, s, v), "hue": 0, "sat": s, "val": v} for n, s, v in sc.NEUTRAL_SWATCHES]
    return out


def same_tone(a, b):
    """True when two (hue, sat, val) tones look the same (a grey or black has no hue)."""
    return sc.tone_key(*clamp_tone(*a)) == sc.tone_key(*clamp_tone(*b))


def track_colors(hue, sat, val, which):
    """The colours at the two ends of the colourfulness ("sat") or brightness ("val") slider in the current colour: what moving it does to the case."""
    hue, sat, val = clamp_tone(hue, sat, val)
    if which == "sat":
        return sc.case_color(hue, 0, val), sc.case_color(hue, 100, val)
    if which == "val":
        return sc.case_color(hue, sat, 0), sc.case_color(hue, sat, 100)
    raise ValueError("unknown slider: %r" % (which,))


def hue_colors(steps=36):
    """The hue slider's gradient: the case colour at `steps` evenly spaced hues, starting at the original blue."""
    return [sc.case_color(round(i * 360 / steps) % 360) for i in range(steps)]


def track_gradient(hue, sat, val, which, steps=24):
    """The case colour along the whole colourfulness ("sat") or brightness ("val") slider, `steps` colours from one end to the other: what the track should look like."""
    hue, sat, val = clamp_tone(hue, sat, val)
    if which not in ("sat", "val"):
        raise ValueError("unknown slider: %r" % (which,))
    return [sc.case_color(hue, round(i * 100 / (steps - 1)), val) if which == "sat" else sc.case_color(hue, sat, round(i * 100 / (steps - 1))) for i in range(steps)]
