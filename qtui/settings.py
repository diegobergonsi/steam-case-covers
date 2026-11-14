# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""The seven switches the window remembers between sessions. Nothing else is ever saved: no account, no path."""
import json
import os
import uuid

from engine import safefile
from qtui import i18n
from engine import steamcase as sc

SETTING_KEYS = ("skip_auto_art", "include_software", "include_non_steam", "use_custom_art", "installed_only", "restart_steam", "reduce_effects")
DEFAULTS = {"skip_auto_art": False, "include_software": False, "include_non_steam": False, "use_custom_art": False, "installed_only": False, "restart_steam": True, "reduce_effects": False}
MAX_SETTINGS = 64 * 1024                  # a settings file is a few dozen bytes; anything bigger is not ours


def settings_path():
    """<app data>/steamcase/settings.json, next to the covers folder."""
    return os.path.join(os.path.dirname(sc.default_covers_dir()), "settings.json")


LANGUAGE_CODES = tuple(i18n.LANGUAGES)     # the languages of the window (see qtui/i18n.py)
LIBRARY_FILE = "library.txt"              # the path of the game list the user used last, next to settings.json (only the path: the file stays where it is)
LANGUAGE_FILE = "language.txt"            # the one word of the language the user chose, next to settings.json


def language_path(path=None):
    return os.path.join(os.path.dirname(path or settings_path()), LANGUAGE_FILE)


def library_path(path=None):
    return os.path.join(os.path.dirname(path or settings_path()), LIBRARY_FILE)


def load_library(path=None):
    """The path of the game list used last, or "" when there is none or the note is not a plain absolute path."""
    try:
        text = safefile.read_small_file(library_path(path), 4096, follow_links=True).decode("utf-8").strip()
    except (OSError, ValueError):
        return ""
    return text if text and "\0" not in text and os.path.isabs(text) else ""


def save_library(value, path=None):
    """Remember the game list in use, atomically. True when written, False for something that is not a path or a folder that is not writable."""
    if not isinstance(value, str) or not value or "\0" in value or not os.path.isabs(value):
        return False
    target = library_path(path)
    tmp = "%s.%s.tmp" % (target, uuid.uuid4().hex[:8])
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(value)
        os.replace(tmp, target)
        return True
    except OSError:
        return False


def forget_library(path=None):
    """Forget the game list used last: remove only our own note of its path (the game list file stays where it is)."""
    try:
        os.remove(library_path(path))
    except OSError:
        pass


def load_language(path=None):
    """The language the user chose last ("en" or "pt-BR"), or None when there is no choice yet (the system's language is then used)."""
    try:
        code = safefile.read_small_file(language_path(path), 32, follow_links=True).decode("utf-8").strip()
    except (OSError, ValueError):
        return None
    return code if code in LANGUAGE_CODES else None


def save_language(code, path=None):
    """Remember the language, atomically. True when written, False for a language we do not have or a folder that is not writable."""
    if code not in LANGUAGE_CODES:
        return False
    target = language_path(path)
    tmp = "%s.%s.tmp" % (target, uuid.uuid4().hex[:8])
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(code)
        os.replace(tmp, target)
        return True
    except OSError:
        return False


def load_settings(path=None):
    """All seven switches. A missing, unreadable, oversized or garbled file gives the defaults, and a value that is not a true/false
    gives the default of that switch only; unknown keys are ignored."""
    try:
        path = path or settings_path()
        data = json.loads(safefile.read_small_file(path, MAX_SETTINGS, follow_links=True))
    except (OSError, ValueError, RecursionError, MemoryError):
        data = None
    if not isinstance(data, dict):
        data = {}
    return {k: data[k] if isinstance(data.get(k), bool) else DEFAULTS[k] for k in SETTING_KEYS}


def save_settings(values, path=None):
    """Write the seven switches (missing ones take the default, other keys are dropped). Atomic. True when written, False if the folder is not writable."""
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
