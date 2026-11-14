# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""The non-Steam games an account added to Steam (its shortcuts.vdf), so they can get a case when they already have art of their own."""
import os
import struct

from engine import safefile

MAX_SHORTCUTS = 8 * 1024 * 1024               # a shortcuts.vdf is a few KB; anything bigger is not ours


def _cstr(data, i):
    j = data.index(b"\x00", i)                # ValueError when the file ends inside a string
    return data[i:j].decode("utf-8", "replace"), j + 1


def _walk(data, i, depth=0):
    """The body of one binary VDF map, from `i` to its end marker: (dict with lower-case keys, index after it). Raises when the file is cut or odd."""
    if depth > 8:
        raise ValueError("nested too deep")
    out = {}
    while True:
        kind = data[i]                        # IndexError at the end of a cut file
        i += 1
        if kind == 8:
            return out, i
        key, i = _cstr(data, i)
        key = key.lower()                     # Steam has written both AppName and appname
        if kind == 0:
            out[key], i = _walk(data, i, depth + 1)
        elif kind == 1:
            out[key], i = _cstr(data, i)
        elif kind == 2:
            out[key] = struct.unpack_from("<i", data, i)[0]
            i += 4
        else:
            raise ValueError("unknown kind %d" % kind)


def _parse(data):
    """{unsigned app id: name} of the complete entries; a cut or garbled file gives the entries before the damage. Steam names the art
    `<unsigned id>p.png`, so the signed number stored in the file is turned into an unsigned one. An entry with no `appid` is left out:
    Steam computes the id of those itself, and a wrong guess would put a case on the wrong art."""
    found = {}
    try:
        if data[:1] != b"\x00":
            return found
        _, i = _cstr(data, 1)                 # the "shortcuts" map
        while data[i] == 0:                   # one map per shortcut
            _, i = _cstr(data, i + 1)
            entry, i = _walk(data, i)
            appid, name = entry.get("appid"), entry.get("appname")
            if isinstance(appid, int) and appid & 0xFFFFFFFF and isinstance(name, str) and name:
                found[appid & 0xFFFFFFFF] = name
    except (ValueError, IndexError, struct.error):
        pass
    return found


def read_shortcuts(steam, user=None):
    """{app id: name} of the account's non-Steam shortcuts. Anything unreadable (no account, no file, a link to something else, too big, garbled) gives {}."""
    from engine import steamcase as sc        # here, not at the top: steamcase uses this module too
    try:
        path = os.path.join(steam, "userdata", sc.pick_account(steam, user), "config", "shortcuts.vdf")
        return _parse(safefile.read_small_file(path, MAX_SHORTCUTS, follow_links=True))
    except (OSError, sc.SteamcaseError):
        return {}


def add_non_steam(games, found_art, shortcuts):
    """Put the shortcuts that have art of their own into `games` (a Steam game keeps its name) and return that art: {app id: path}.
    A shortcut without art is left out of both: there is nothing to put in a case."""
    added = {}
    for appid, name in shortcuts.items():
        if appid in found_art:
            games.setdefault(appid, name)
            added[appid] = found_art[appid]
    return added
