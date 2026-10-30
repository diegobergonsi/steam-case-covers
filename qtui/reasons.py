# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""The sentences of the question "replace the covers you made?": why Make covers would rebuild covers that are already in the folder.
The words are those of the Tk window (gui.App._replace_reason); a test keeps the two equal."""
import os

import steamcase as sc
from qtui.hundred import MARKS, STYLES


def look_label(treatment):
    """How a treatment (one of sc.TREATMENTS) is named in the question: its case, then its marks, so a change of marks alone reads as one."""
    case, marks = sc.split_treatment(treatment)
    return "%s, %s" % (dict(STYLES)[case], dict(MARKS)[marks].lower())


def replace_reason(covers_dir, tone, completed, treatment, theme=None, custom_art=sc.KEEP, games=None):
    """(title, sentence) for the question, or None when nothing is rebuilt. `custom_art` is what make_covers gets ({} when the option is off);
    sc.KEEP leaves the art of existing covers out of it. `games`: the appids the run will make covers for (None: all)."""
    look = _look_reason(covers_dir, tone, completed, treatment, theme)
    if custom_art == sc.KEEP or not sc.covers_with_other_art(covers_dir, custom_art, games):
        return look
    if custom_art:
        title, extra = "Use your own art?", "The covers you already made for games with your own art are made again with that art inside."
    else:
        title, extra = "Go back to Steam's art?", "The covers you made with your own art are made again with Steam's own art."
    if look is None:
        return title, "This replaces covers you already made. " + extra
    return look[0], look[1] + " " + extra


def _look_reason(covers_dir, tone, completed, treatment, theme=None):
    """The colour, 100% highlight and theme part of replace_reason; None when none of them rebuilds a cover."""
    if not sc.covers_in_other_look(covers_dir, *tone, completed=completed, treatment=treatment, theme=theme):
        return None
    colour = sc.covers_in_other_colour(covers_dir, *tone)
    ribbon = ""                                          # what a theme does to full-marks 100% covers when no games page decides their look
    if theme and completed is None and sc.covers_with_full_marks(covers_dir):
        ribbon = (" The covers of your 100%% games lose their ribbon: the %s case shows the rosette only. To get it back later, choose the Classic case, "
                  "load your games page and pick “Rosette and ribbon”." % theme.capitalize())
    tail = ""                                            # the theme every cover is made in, when it changes
    if sc.covers_in_other_theme(covers_dir, theme):
        tail = "the %s theme" % theme.capitalize() if theme else "the Classic case"
    styles, changed = set(), False                       # the treatments in the folder, and whether any cover gets another one
    if completed is not None:
        try:
            for n in os.listdir(covers_dir):
                appid = sc.appid_of(n)
                if n.lower().endswith(".png") and appid is not None:
                    have = sc.cover_treatment(os.path.join(covers_dir, n)) or None
                    styles.add(have)
                    changed = changed or have != (treatment if int(appid) in completed else None)
        except OSError:
            pass
    if tail and not changed:
        if colour:
            return "Change your covers?", "This replaces the covers you already made in another colour or theme.%s" % ribbon
        return "Change the theme of your covers?", "This replaces the covers you already made with new ones in %s.%s" % (tail, ribbon)
    if colour and not changed:
        return "Change the colour of your covers?", "This replaces the covers you already made in another colour."
    styles &= set(sc.TREATMENTS)
    label = look_label(treatment) if treatment else None
    if treatment is None:
        what = "the covers of your 100% games are made again as normal covers"
        title, one = "Remove the 100% highlight?", "You chose “No special case”: " + what + "."
    elif not completed:
        what = "the covers with a highlight lose it, as no game on your page is at 100%"
        title, one = "Remove the 100% highlight?", "No game on your page is at 100%, so the covers you made with a highlight lose it and are made again as normal covers."
    elif styles - {treatment}:
        what = "the covers of your 100%% games made with another look are made again as “%s”" % label
        title, one = "Change the look of your 100% games?", "This replaces the covers of your 100%% games made with another look with “%s”." % label
    elif not styles:
        what = "your 100%% games get highlighted covers (“%s”)" % label
        title, one = "Highlight your 100% games?", "This replaces the covers of your 100%% games with highlighted ones (“%s”)." % label
    else:
        what = "your 100% covers are updated to match your games page"
        title, one = "Update your 100% covers?", ("Some covers you already made are made again to match your games page: "
                                                  "games you finished get the highlight, games no longer at 100% lose it.")
    if colour:
        return "Change your covers?", "This replaces the covers you already made in another colour, and %s.%s" % (what, " All your covers are also made in %s." % tail if tail else "")
    if tail:
        return "Change your covers?", "%s All your covers are also made in %s." % (one, tail)
    return title, one
