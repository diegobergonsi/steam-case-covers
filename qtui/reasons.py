# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""The sentences of the question "replace the covers you made?": why Make covers would rebuild covers that are already in the folder.
The words are those the app has always used, covered by tests in tests/test_steamcase.py (ReplaceReason). Also the names the Look and 100% games steps show for
a case, its marks and a theme (STYLES, MARKS, THEME_LABELS)."""

from engine import steamcase as sc
from qtui.i18n import N_, tr, trn

STYLES = [("gold-case", N_("Gold case")), ("gold-border", N_("Gold border")), ("ribbon", N_("Normal case")), ("none", N_("No special case"))]    # values: sc.CASES, or "none"
MARKS = [("full", N_("Rosette and ribbon")), ("rosette", N_("Rosette only")), ("none", N_("No marks"))]                    # values: sc.MARKS


THEME_LABELS = {"classic": N_("Classic"), "christmas": N_("Christmas")}


def theme_label(key):
    """The name of a theme in the language in use (a test keeps THEME_LABELS in step with the engine's themes)."""
    return tr(THEME_LABELS[key])


def platform_replace_reason(covers_dir, platforms, tone, treatment, completed, tones=None, groups=None, custom_art=sc.KEEP):
    """(title, sentence) for the question of the manual flow, or None when no cover already made would be rebuilt. `platforms`, `tone`, `treatment`,
    `completed`, `tones`, `groups` and `custom_art` are what make_covers gets (see sc.covers_in_other_case)."""
    n = sc.covers_in_other_case(covers_dir, platforms, tone, treatment, completed, tones, groups, custom_art)
    if not n:
        return None
    return tr("Replace the covers you made?"), trn("This replaces %n cover you already made with a new one in the case you picked.|"
                                                    "This replaces %n covers you already made with new ones in the cases you picked.", n)


def own_case_reason(covers_dir, own, treatment=None, completed=None, custom_art=sc.KEEP):
    """(title, sentence) for the question of the Look step's "My own case" switch, or None when no cover already made would be rebuilt. `own`: the switch is on."""
    if own:
        n = sc.covers_in_other_case(covers_dir, {appid: sc.CUSTOM for appid, _ in sc.scan_covers(covers_dir)}, treatment=treatment, completed=completed, custom_art=custom_art)
        return None if not n else (tr("Draw your covers again?"), trn("This replaces %n cover you already made with a new one in your own case.|"
                                                                    "This replaces %n covers you already made with new ones in your own case.", n))
    n = len(sc.covers_in_own_case(covers_dir))
    return None if not n else (tr("Go back to the Steam case?"), trn("This replaces %n cover in your own case with a new one in the Steam case.|"
                                                                   "This replaces %n covers in your own case with new ones in the Steam case.", n))


def group_repaint_reason(groups):
    """(title, sentence) for the groups ticked to be repainted (a list of {"name", "games": [appids]}), one line each, or None when there are none."""
    if not groups:
        return None
    lines = []
    for g in groups:
        n = len(g["games"])
        lines.append(trn("The group \u201c%s\u201d (%n game) will be repainted and deleted.|The group \u201c%s\u201d (%n games) will be repainted and deleted.", n) % g["name"])
    return tr("Repaint your groups?"), " ".join(lines)


def look_label(treatment):
    """How a treatment (one of sc.TREATMENTS) is named in the question: its case, then its marks, so a change of marks alone reads as one."""
    case, marks = sc.split_treatment(treatment)
    return "%s, %s" % (tr(dict(STYLES)[case]), tr(dict(MARKS)[marks]).lower())


def replace_reason(covers_dir, tone, completed, treatment, theme=None, custom_art=sc.KEEP, games=None):
    """(title, sentence) for the question, or None when nothing is rebuilt. `custom_art` is what make_covers gets ({} when the option is off);
    sc.KEEP leaves the art of existing covers out of it. `games`: the appids the run will make covers for (None: all)."""
    look = _look_reason(covers_dir, tone, completed, treatment, theme)
    if custom_art == sc.KEEP or not sc.covers_with_other_art(covers_dir, custom_art, games):
        return look
    if custom_art:
        title, extra = tr("Use your own art?"), tr("The covers you already made for games with your own art are made again with that art inside.")
    else:
        title, extra = tr("Go back to Steam's art?"), tr("The covers you made with your own art are made again with Steam's own art.")
    if look is None:
        return title, tr("This replaces covers you already made. ") + extra
    return look[0], look[1] + " " + extra


def _look_reason(covers_dir, tone, completed, treatment, theme=None):
    """The colour, 100% highlight and theme part of replace_reason; None when none of them rebuilds a cover."""
    if not sc.covers_in_other_look(covers_dir, *tone, completed=completed, treatment=treatment, theme=theme):
        return None
    if not sc.covers_in_other_look(covers_dir, *tone, completed=completed, treatment=treatment, theme=theme, drawing=False):       # only how they were drawn is old
        return tr("Draw your covers again?"), tr("Your covers were made by an earlier version, which cut part of the art to fit the case. They are made again with the whole art stretched to fit.")
    colour = sc.covers_in_other_colour(covers_dir, *tone)
    marks_note = ""                                          # what a theme does to full-marks 100% covers when no games page decides their look
    if theme and completed is None and sc.covers_with_marks(covers_dir, "full"):
        marks_note = (tr(" The covers of your 100%% games lose their ribbon: the %s case shows the rosette only. To get it back later, choose the Classic case, "
                  "load your games page and pick “Rosette and ribbon”.") % theme_label(theme))
    if theme and completed is None and sc.covers_with_marks(covers_dir, "none"):          # and to the ones with no marks: the theme gives them its rosette
        marks_note += tr(" The covers of your 100%% games with no marks get the rosette: the %s case shows the rosette only.") % theme_label(theme)
    tail = ""                                            # the theme every cover is made in, when it changes
    if sc.covers_in_other_theme(covers_dir, theme):
        tail = tr("the %s theme") % theme_label(theme) if theme else tr("the Classic case")
    styles, changed = set(), False                       # the treatments in the folder, and whether any cover gets another one
    if completed is not None:
        for appid, _, notes in sc.usual_covers(covers_dir):                # covers by hand are left alone: they change nothing here
            have = notes.treatment or None
            styles.add(have)
            changed = changed or have != (treatment if appid in completed else None)
    if tail and not changed:
        if colour:
            return tr("Change your covers?"), tr("This replaces the covers you already made in another colour or theme.%s") % marks_note
        return tr("Change the theme of your covers?"), tr("This replaces the covers you already made with new ones in %s.%s") % (tail, marks_note)
    if colour and not changed:
        return tr("Change the colour of your covers?"), tr("This replaces the covers you already made in another colour.")
    styles &= set(sc.TREATMENTS)
    label = look_label(treatment) if treatment else None
    if treatment is None:
        what = tr("the covers of your 100% games are made again as normal covers")
        title, one = tr("Remove the 100% highlight?"), tr("You chose no highlight for your 100%% games (“No special case”, or “No marks” on the normal case): %s.") % what
    elif not completed:
        what = tr("the covers with a highlight lose it, as no game on your page is at 100%")
        title, one = tr("Remove the 100% highlight?"), tr("No game on your page is at 100%, so the covers you made with a highlight lose it and are made again as normal covers.")
    elif styles - {treatment}:
        what = tr("the covers of your 100%% games made with another look are made again as “%s”") % label
        title, one = tr("Change the look of your 100% games?"), tr("This replaces the covers of your 100%% games made with another look with “%s”.") % label
    elif not styles:
        what = tr("your 100%% games get highlighted covers (“%s”)") % label
        title, one = tr("Highlight your 100% games?"), tr("This replaces the covers of your 100%% games with highlighted ones (“%s”).") % label
    else:
        what = tr("your 100% covers are updated to match your games page")
        title, one = tr("Update your 100% covers?"), (tr("Some covers you already made are made again to match your games page: "
                                                  "games you finished get the highlight, games no longer at 100% lose it."))
    if colour:
        return tr("Change your covers?"), tr("This replaces the covers you already made in another colour, and %s.%s") % (what, tr(" All your covers are also made in %s.") % tail if tail else "")
    if tail:
        return tr("Change your covers?"), tr("%s All your covers are also made in %s.") % (one, tail)
    return title, one
