# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Small facts about the computer the window runs on."""
import os
import re
import sys

SAVE_KEY = "Cmd+S" if sys.platform == "darwin" else "Ctrl+S"      # the shortcut that saves a web page


def start_size(avail_w, avail_h, min_height):
    """The size the window opens at: 70% of the free screen width and 75% of the height, never below 900 wide and `min_height` (the shortest the window may be) tall, never above 1280x900."""
    return max(900, min(1280, int(avail_w * 0.7))), max(min_height, min(900, int(avail_h * 0.75)))


def restore_child_env():
    """Packaged Linux app: PyInstaller points LD_LIBRARY_PATH at its bundled libraries (Qt, OpenSSL...). Programs we launch (a browser through xdg-open,
    Steam, the file chooser) would load those and crash, so undo it. This does not touch the libraries this process has found already."""
    if getattr(sys, "frozen", False) and sys.platform.startswith("linux"):
        orig = os.environ.get("LD_LIBRARY_PATH_ORIG")
        if orig is None:
            os.environ.pop("LD_LIBRARY_PATH", None)
        else:
            os.environ["LD_LIBRARY_PATH"] = orig


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
PAGE_HELP_TEMPLATE = ("How to save the page: open it with the button and log in if asked. Wait until your games have loaded, press %s and save it as "
             "“Webpage, Complete” (Chrome or Firefox), named games.html. Your browser also saves a folder next to it.\n\n"
             "The saved file contains a temporary login token for your Steam account. This app only reads which games are at 100%%: "
             "it does not use or keep the token. You can delete the file and its folder afterwards.")
PAGE_HELP = PAGE_HELP_TEMPLATE % SAVE_KEY


def page_help():
    """The help of the games page in the language in use. The template is what gets translated; the key of this computer is put in after."""
    from qtui import i18n
    return i18n.tr(PAGE_HELP_TEMPLATE) % SAVE_KEY
