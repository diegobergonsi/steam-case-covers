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


class Collection(NamedTuple):
    id: str                                      # the key in Steam's file
    name: str
    appids: frozenset                            # `added` without `removed`


def _app_id(value):
    """The app id a list item stands for, or None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isascii() and value.isdigit():
        return int(value)
    return None


def _ids(value):
    return {i for i in map(_app_id, value) if i is not None} if isinstance(value, list) else set()


def _collection(key, entry):
    """The Collection of one pair of the file, or None when it is not a plain, named, live collection."""
    if not (isinstance(key, str) and key.startswith(_KEY) and isinstance(entry, dict)) or entry.get("is_deleted"):
        return None
    try:
        value = json.loads(entry["value"])
    except (KeyError, TypeError, ValueError):
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
    except (OSError, ValueError):
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
