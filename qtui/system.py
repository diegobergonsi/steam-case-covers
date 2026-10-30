# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Small facts about the computer the window runs on."""
import os
import re
import sys

SAVE_KEY = "Cmd+S" if sys.platform == "darwin" else "Ctrl+S"      # the shortcut that saves a web page


def downloads_dir():
    """The user's Downloads folder (honours the Linux XDG setting)."""
    home = os.path.expanduser("~")
    cfg = os.path.join(home, ".config", "user-dirs.dirs")
    try:
        with open(cfg, errors="replace") as f:
            m = re.search(r'XDG_DOWNLOAD_DIR="([^"]+)"', f.read())
    except OSError:
        m = None
    if m:
        p = m.group(1).replace("$HOME", home)
        if os.path.isdir(p):
            return p
    return os.path.join(home, "Downloads")
