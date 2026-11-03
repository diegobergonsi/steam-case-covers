# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Which steps of the window are open, done, active or locked."""
from qtui.i18n import N_, tr

STEPS = ("home", "game_list", "look", "hundred", "make", "add")
LABELS = {"home": N_("Home"), "game_list": N_("1. Game list"), "look": N_("2. Look"), "hundred": N_("3. 100% games"), "make": N_("4. Make"), "add": N_("5. Add to Steam")}
STEPS_MANUAL = ("home", "game_list", "pick", "case", "hundred", "make", "add")          # the manual flow: tick games, give them a case
LABELS_MANUAL = {"home": N_("Home"), "game_list": N_("1. Game list"), "pick": N_("2. Games"), "case": N_("3. Case"), "hundred": N_("4. 100% games"), "make": N_("5. Make"), "add": N_("6. Add to Steam")}

HINTS = {"hundred": N_("(optional)")}                  # a small line under the name of a step


def hint(key, state):
    """The small line under a step's name: "(optional)" for the step that is. A locked step is only dimmed."""
    return tr(HINTS.get(key, ""))


def labels(flow):
    """The names of the steps of a flow ("natural" or "manual")."""
    return {key: tr(text) for key, text in (LABELS_MANUAL if flow == "manual" else LABELS).items()}


def _chain(keys, facts):
    """{step: state} for steps in order, each done only when its own fact is true and the step before it is done (see step_states)."""
    out = {"home": "open"}
    before = True                                   # the step before is done (Home counts as done)
    for key, fact in zip(keys[1:], facts):
        if before and fact:
            out[key] = "done"
        elif before:
            out[key] = "active"
            before = False
        else:
            out[key] = "locked"
    return out


def manual_step_states(ready, picked, assigned, hundred_done, covers_made, applied):
    """step_states for the manual flow. Games already given a case count as picked: the ticks are cleared once a case is given.
    `picked`: some games are ticked. `assigned`: some games have a case."""
    return _chain(STEPS_MANUAL, (ready, picked or assigned, assigned, hundred_done, covers_made, applied))


def step_states(ready, look_done, hundred_done, covers_made, applied):
    """{step: "open" | "done" | "active" | "locked"}. Home is always "open". A step is done only when its own fact is true AND the step before it is done,
    so an inconsistent state (covers made but no game list) never unlocks a later step; the active step is the first one that is not done.
    `ready`: a game list is loaded or installed-only is on. `look_done`: the user went on from Look. `hundred_done`: went on from (or skipped) 100% games."""
    return _chain(STEPS, (ready, look_done, hundred_done, covers_made, applied))
