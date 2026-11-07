# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""collections: the Steam collections (Completed, Backlog, Favorites, Hidden...) of one account, read from a file Steam keeps on this computer.

The file is `userdata/<account>/config/cloudstorage/cloud-storage-namespace-1.json`: a list of [key, entry] pairs. A collection's key starts with
`user-collections.`; its entry holds a JSON text with `name`, `added` and `removed` (app ids). A collection that Steam fills by a rule has a
`filterSpec` and no list of its own: it is skipped. The file is only read, never written; anything odd in it means "no collections", never an error.
"""
import json
import os
from typing import NamedTuple

from engine import safefile

MAX_FILE = 8 * 1024 * 1024                       # a real file is some tens of KB; anything bigger is not it
_KEY = "user-collections."
HIDDEN = _KEY + "hidden"                         # Steam's own id of the Hidden collection (its name changes with the language)


class Collection(NamedTuple):
    id: str                                      # the key in Steam's file
    name: str
    appids: frozenset                            # `added` without `removed`


class Shown(NamedTuple):
    """A collection as the Games screen shows it: only its games that are on the screen."""
    id: str
    name: str
    games: frozenset

    @property
    def label(self):
        return "%s (%d)" % (self.name, len(self.games))


def on_list(found, on_screen):
    """[Shown] for the collections that have games among `on_screen` (a set of app ids): the most games first, then by name.
    Steam's "Hidden" is always last: it is usually the biggest and would push the player's own collections out of sight."""
    shown = [Shown(c.id, c.name, c.appids & on_screen) for c in found]
    return sorted((s for s in shown if s.games), key=lambda s: (s.id == HIDDEN, -len(s.games), s.name.casefold(), s.id))


def _app_id(value):
    """The app id a list item stands for, or None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isascii() and value.isdigit():
        try:
            return int(value)
        except ValueError:                           # a string of thousands of digits: Python refuses to convert it
            return None
    return None


def _ids(value):
    return {i for i in map(_app_id, value) if i is not None} if isinstance(value, list) else set()


def _collection(key, entry):
    """The Collection of one pair of the file, or None when it is not a plain, named, live collection."""
    if not (isinstance(key, str) and key.startswith(_KEY) and isinstance(entry, dict)) or entry.get("is_deleted"):
        return None
    try:
        value = json.loads(entry["value"])
    except (KeyError, TypeError, ValueError, RecursionError):      # RecursionError: a text nested far too deep
        return None
    if not isinstance(value, dict) or value.get("filterSpec"):
        return None
    name = value.get("name")
    if not isinstance(name, str) or not name.strip() or not isinstance(value.get("added"), list):
        return None
    return Collection(key, name, frozenset(_ids(value.get("added")) - _ids(value.get("removed"))))


def read_collections(steam, account):
    """[Collection] of this account, in the order of the file; [] when the file is missing, too big, a link or not what Steam writes."""
    path = os.path.join(steam, "userdata", str(account), "config", "cloudstorage", "cloud-storage-namespace-1.json")
    try:
        pairs = json.loads(safefile.read_small_file(path, MAX_FILE).decode("utf-8", errors="replace"))
    except (OSError, ValueError, RecursionError):
        return []
    if not isinstance(pairs, list):
        return []
    found = []
    for pair in pairs:
        if isinstance(pair, list) and len(pair) == 2:
            collection = _collection(*pair)
            if collection:
                found.append(collection)
    return found
