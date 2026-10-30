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
            return os.path.normpath(p)
    return os.path.join(home, "Downloads")


CUSTOM_ART_HELP = ("For games where you set your own art (in Steam's menu or from SteamGridDB), your art goes inside the case instead of Steam's. "
                   "The app keeps a copy of it in its own folder and never changes your files. Games without art of your own use Steam's.")

GAMES_PAGE_URL = "https://steamcommunity.com/my/games/?tab=all&sort=achievements"     # the user's own games page, most achievements first
THEME_NOTE = "The Halloween case shows the rosette only: the ribbon would hide the pumpkin and the web."
PAGE_HELP = ("How to save the page: open it with the button and log in if asked. Wait until your games have loaded, press %s and save it as "
             "“Webpage, Complete” (Chrome or Firefox), named games.html. Your browser also saves a folder next to it.\n\n"
             "The saved file contains a temporary login token for your Steam account. This app only reads which games are at 100%%: "
             "it does not use or keep the token. You can delete the file and its folder afterwards." % SAVE_KEY)
