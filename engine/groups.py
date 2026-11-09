# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Groups of covers made by hand: a name, a case and the games in it, kept in groups.json in the covers folder.
A group is {"id", "name", "case", "games"}: "case" is {"platform": one of steamcase.PLATFORMS, or steamcase.CUSTOM} (a console case, or the user's own) or {"tone": [hue, sat, val]} (the Steam case
in that colour; gold is the tone of steamcase.GOLD_HUE). A game is in one group only. The file may be damaged or edited: load() never raises, it keeps what is good."""
import json, os, re, uuid

from engine import safefile
from engine import steamcase as sc

FILE = "groups.json"
MAX_NAME = 40
MAX_BYTES = 2 * 1024 * 1024            # a real file is a few kilobytes; anything bigger is not ours
MAX_GROUPS = 1000
_ID = sc.GROUP_ID


def _whole(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _name(value):
    """The name trimmed, or None if it is not text of 1 to MAX_NAME characters without control characters."""
    if not isinstance(value, str):
        return None
    name = value.strip()
    if not name or len(name) > MAX_NAME or any(ord(c) < 32 or ord(c) == 127 for c in name):
        return None
    return name


def _case(value):
    """The case as the file keeps it, or None if it is not a console case or a tone in range."""
    if not isinstance(value, dict) or len(value) != 1:
        return None
    if "platform" in value:
        return {"platform": value["platform"]} if value["platform"] in sc.PLATFORMS or value["platform"] == sc.CUSTOM else None
    tone = value.get("tone")
    if isinstance(tone, (list, tuple)) and len(tone) == 3 and all(_whole(v) for v in tone) and 0 <= tone[0] < 360 and 0 <= tone[1] <= 100 and 0 <= tone[2] <= 100:
        return {"tone": list(tone)}
    return None


def _games(values):
    """The games as appids (whole numbers above 0) in order, each once."""
    seen, order = set(), []
    for v in values if isinstance(values, (list, tuple)) else ():
        if _whole(v) and v > 0 and v not in seen:
            seen.add(v)
            order.append(v)
            if len(order) >= sc.MAX_APPS:                # more than a library can hold: the rest is not read
                break
    return order


def _read(path):
    """The JSON in the file, or None: the file must be a regular file of at most MAX_BYTES (see safefile), and one too deeply nested to decode counts as damaged."""
    try:
        return json.loads(safefile.read_small_file(path, MAX_BYTES).decode("utf-8"))
    except (OSError, ValueError, RecursionError, MemoryError):
        return None


def load(covers_dir):
    """The saved groups. A missing, unreadable or damaged file gives none; an entry that is not good (see the module) is dropped, and a name, id or game
    that comes twice stays with its first group."""
    data = _read(os.path.join(covers_dir, FILE))
    entries = data.get("groups") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return []
    out, names, ids, games = [], set(), set(), set()
    for e in entries[:MAX_GROUPS]:
        if not isinstance(e, dict):
            continue
        gid, name, case = e.get("id"), _name(e.get("name")), _case(e.get("case"))
        if not (isinstance(gid, str) and _ID.fullmatch(gid)) or name is None or case is None:
            continue
        mine = [g for g in _games(e.get("games")) if g not in games]
        if not mine or gid in ids or name.lower() in names:
            continue
        out.append({"id": gid, "name": name, "case": case, "games": mine})
        ids.add(gid)
        names.add(name.lower())
        games.update(mine)
    return out


def save(covers_dir, groups):
    """Write the groups: to a temporary file first and then over the old one, so a failure leaves the old file as it was."""
    os.makedirs(covers_dir, exist_ok=True)
    path = os.path.join(covers_dir, FILE)
    tmp = sc._tmp(path)
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"groups": groups}, f, indent=1, ensure_ascii=False)
        sc._replace(tmp, path)                                  # retried: on Windows an antivirus can hold the file for a moment
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def assign(groups, name, case, appids):
    """(groups, id): `groups` with the games put in the group called `name` (compared without regard to capitals), made if there is none. The games leave
    any other group, and a group left without games goes. ValueError, in words, if the name, the case or the games are not valid, or if the group exists with
    another case. The list given is not changed."""
    clean = _name(name)
    if clean is None:
        raise ValueError("A group name has 1 to %d letters, with no line breaks." % MAX_NAME)
    case_ok = _case(case)
    if case_ok is None:
        raise ValueError("That case is not one the app has.")
    games = _games(appids)
    if not games or any(not (_whole(a) and a > 0) for a in appids):
        raise ValueError("Pick at least one game.")
    out = [dict(g, games=[a for a in g["games"] if a not in games]) for g in groups]
    target = next((g for g in out if g["name"].lower() == clean.lower()), None)
    if target is None:
        target = {"id": "g" + uuid.uuid4().hex[:8], "name": clean, "case": case_ok, "games": []}
        out.append(target)
    elif target["case"] != case_ok:
        raise ValueError("The group “%s” already exists with another case." % target["name"])
    target["games"] += games
    return [g for g in out if g["games"]], target["id"]


def rename(groups, group_id, name):
    """`groups` with the group `group_id` called `name`. ValueError, in words, if the name is not valid, if another group has it (compared without regard to
    capitals; the group's own name in other capitals is fine) or if there is no such group. The list given is not changed."""
    clean = _name(name)
    if clean is None:
        raise ValueError("A group name has 1 to %d letters, with no line breaks." % MAX_NAME)
    if not any(g["id"] == group_id for g in groups):
        raise ValueError("That group is not there any more.")
    other = next((g for g in groups if g["id"] != group_id and g["name"].lower() == clean.lower()), None)
    if other is not None:
        raise ValueError("There is already a group called \u201c%s\u201d." % other["name"])
    return [dict(g, name=clean) if g["id"] == group_id else dict(g) for g in groups]


def add_games(groups, group_id, appids):
    """`groups` with these games moved into the group with this id (each once, in order, after the games it has). They leave any other group, and a group left
    without games goes. ValueError, in words, if there is no such group or no valid game. The list given is not changed."""
    games = _games(appids)
    if not games or any(not (_whole(a) and a > 0) for a in appids):
        raise ValueError("Pick at least one game.")
    if not any(g["id"] == group_id for g in groups):
        raise ValueError("That group is not there any more.")
    out = [dict(g, games=[a for a in g["games"] if g["id"] == group_id or a not in games]) for g in groups]
    target = next(g for g in out if g["id"] == group_id)
    target["games"] += [a for a in games if a not in target["games"]]
    return [g for g in out if g["games"]]


def delete(groups, group_id):
    """`groups` without the group with this id."""
    return [dict(g) for g in groups if g["id"] != group_id]


def members(groups, ids):
    """The appids of the groups with these ids."""
    return {a for g in groups if g["id"] in set(ids) for a in g["games"]}


def drop_games(groups, appids):
    """`groups` without these games; a group left without games goes."""
    gone = set(appids)
    out = [dict(g, games=[a for a in g["games"] if a not in gone]) for g in groups]
    return [g for g in out if g["games"]]
