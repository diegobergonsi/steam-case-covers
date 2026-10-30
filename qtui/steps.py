# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Which steps of the window are open, done, active or locked."""

STEPS = ("home", "game_list", "look", "hundred", "make", "add")
LABELS = {"home": "Home", "game_list": "1  Game list", "look": "2  Look", "hundred": "3  100% games", "make": "4  Make", "add": "5  Add to Steam"}

HINTS = {"hundred": "(optional)"}                  # a small line under the name of a step
LOCKED = {"look": "finish step 1 first", "hundred": "finish step 2 first", "make": "finish step 3 first", "add": "make the covers first"}      # why a step is locked


def hint(key, state):
    """The small line under a step's name: what it is ("(optional)") and, while it is locked, what unlocks it."""
    parts = [HINTS.get(key, "")] + ([LOCKED.get(key, "")] if state == "locked" else [])
    return " \u00b7 ".join(p for p in parts if p)


def step_states(ready, look_done, hundred_done, covers_made, applied):
    """{step: "open" | "done" | "active" | "locked"}. Home is always "open". A step is done only when its own fact is true AND the step before it is done,
    so an inconsistent state (covers made but no game list) never unlocks a later step; the active step is the first one that is not done.
    `ready`: a game list is loaded or installed-only is on. `look_done`: the user went on from Look. `hundred_done`: went on from (or skipped) 100% games."""
    facts = (ready, look_done, hundred_done, covers_made, applied)
    out = {"home": "open"}
    before = True                                   # the step before is done (Home counts as done)
    for key, fact in zip(STEPS[1:], facts):
        if before and fact:
            out[key] = "done"
        elif before:
            out[key] = "active"
            before = False
        else:
            out[key] = "locked"
    return out
