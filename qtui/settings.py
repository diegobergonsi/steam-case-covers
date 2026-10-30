# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""The five switches the window remembers between sessions. Nothing else is ever saved: no account, no path."""
import json
import os
import stat
import uuid

import steamcase as sc

SETTING_KEYS = ("skip_auto_art", "use_custom_art", "installed_only", "restart_steam", "reduce_effects")
DEFAULTS = {"skip_auto_art": False, "use_custom_art": False, "installed_only": False, "restart_steam": True, "reduce_effects": False}
MAX_SETTINGS = 64 * 1024                  # a settings file is a few dozen bytes; anything bigger is not ours


def settings_path():
    """<app data>/steamcase/settings.json, next to the covers folder."""
    return os.path.join(os.path.dirname(sc.default_covers_dir()), "settings.json")


def load_settings(path=None):
    """All five switches. A missing, unreadable, oversized or garbled file gives the defaults, and a value that is not a true/false
    gives the default of that switch only; unknown keys are ignored."""
    try:
        path = path or settings_path()
        if not stat.S_ISREG(os.stat(path).st_mode):         # a named pipe or a device would block open() for ever
            raise OSError("not a regular file")
        with open(path, "rb") as f:
            raw = f.read(MAX_SETTINGS + 1)
        data = json.loads(raw) if len(raw) <= MAX_SETTINGS else None
    except (OSError, ValueError, RecursionError, MemoryError):
        data = None
    if not isinstance(data, dict):
        data = {}
    return {k: data[k] if isinstance(data.get(k), bool) else DEFAULTS[k] for k in SETTING_KEYS}


def save_settings(values, path=None):
    """Write the five switches (missing ones take the default, other keys are dropped). Atomic. True when written, False if the folder is not writable."""
    path = path or settings_path()
    clean = {k: values[k] if isinstance(values.get(k), bool) else DEFAULTS[k] for k in SETTING_KEYS}
    tmp = "%s.%s.tmp" % (path, uuid.uuid4().hex[:8])
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w") as f:
            json.dump(clean, f)
        os.replace(tmp, path)
        return True
    except OSError:
        return False
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
