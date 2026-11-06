#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Takes the screenshots of the README: Home, Look, 100% games and Pick a case, in English and in Brazilian Portuguese (eight images).

Run it on a desktop, in a real session (a window must be shown; the offscreen platform does not draw the pages):

    python tools/take_screenshots.py OUT_DIR

Nothing real is touched: a fake home folder, a fake Steam account called "Player" and three made-up games, so the pictures never show a real account name.
The files are named like the ones in `assets/` (`screenshot-home.png`, `screenshot-home-pt.png`, ...). Look at every picture before using it."""
import argparse
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAMES = {1: "Hades", 2: "Forza Horizon 5", 3: "God of War"}            # made-up library: the covers are the sample art
PAGE = {1: (3, 3), 2: (1, 4)}                                            # the games page: game 1 at 100%, game 2 only started
SIZES = {"home": (900, 900), "look": (900, 900), "100": (900, 1000), "cases": (900, 1000)}      # window size in points; the picture is this times the scale
LANGUAGES = (("en", ""), ("pt-BR", "-pt"))


def write_games_page(folder):
    """A saved games page with a row per game in PAGE (the same shape as tests/fixtures/games_page.html)."""
    rows = []
    for appid, (unlocked, total) in PAGE.items():
        store = '<a href="https://store.steampowered.com/app/%d"' % appid
        rows.append('<div class="row">\n  %s class="img"></a>\n  %s class="name">Game</a>\n'
                    '  <a class="ach" href="https://steamcommunity.com/id/playerone/achievements/%d">ACHIEVEMENTS</a><span class="cnt">%d/%d</span>\n</div>\n'
                    % (store, store, appid, unlocked, total))
    path = os.path.join(folder, "games.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write('<!DOCTYPE html>\n<html><body><div class="list">\n' + "".join(rows) + "</div></body></html>\n")
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description="Take the README screenshots (see the top of this file).")
    ap.add_argument("out", help="the folder the eight pictures are written to")
    ap.add_argument("--scale", default="1.5", help="how much bigger than the window the pictures are (the README ones use 1.5)")
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)

    home = tempfile.mkdtemp(prefix="steamcase-shots-")                      # nothing of the real account or the real Steam folder is read
    for key in ("HOME", "USERPROFILE", "XDG_CONFIG_HOME", "XDG_DATA_HOME"):
        os.environ[key] = home
    os.environ["QT_SCALE_FACTOR"] = args.scale
    sys.path.insert(0, ROOT)

    from unittest import mock
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtGui import QGuiApplication
    from engine import steamcase as sc
    from qtui.app import create_engine
    from qtui.shell import Shell

    app = QGuiApplication(sys.argv[:1])
    downloads = os.path.join(home, "Downloads")
    os.makedirs(downloads)
    for name, value in (("steam_dir", lambda: home), ("steam_running", lambda: False), ("list_accounts", lambda steam: [("111", "Player")]),
                        ("pick_account", lambda steam, forced=None: forced or "111"), ("account_label", lambda steam, acc: "Player"),
                        ("list_backups", lambda steam, user=None: []), ("find_our_covers", lambda steam, user=None, progress=None, cancelled=None: []),
                        ("find_other_art", lambda steam, user=None, ours=(): ([], [])), ("grid_dir", lambda steam, user=None: home),
                        ("load_library", lambda steam, lib: (dict.fromkeys(GAMES), set())),
                        ("store_items", lambda ids, log=None, cancelled=None, errors=None: {i: {"type": 0, "name": GAMES[i]} for i in ids if i in GAMES})):
        mock.patch.object(sc, name, value).start()
    shell = Shell(os.path.join(home, "settings.json"), downloads=downloads, covers_dir=os.path.join(home, "covers"))
    shell.reduceEffects = True                                              # no animation: a screen is ready the moment it is shown
    shell.library.installedOnly = True                                      # the steps after the game list are open
    engine = create_engine(shell)
    root = engine.rootObjects()[0]
    root.setProperty("minimumHeight", 0)

    def settle(seconds=1.0):
        end = time.time() + seconds
        while time.time() < end:
            QCoreApplication.processEvents()
            time.sleep(0.02)

    def shot(screen, suffix):
        width, height = SIZES[screen]
        root.setWidth(width)
        root.setHeight(height)
        root.show()
        settle()
        path = os.path.join(args.out, "screenshot-%s%s.png" % (screen, suffix))
        if not root.grabWindow().save(path):
            raise SystemExit("could not write " + path)
        print(path)

    page = write_games_page(downloads)
    for code, suffix in LANGUAGES:
        shell.setLanguage(code)
        shell.picker.clearAll()
        shell.startPath("natural")
        shell.go(0)                                                         # Home, the first time: two cards
        settle()
        shot("home", suffix)
        shell.setFact("look_done", False)
        shell.go(shell.stepIndex("look"))
        shot("look", suffix)
        shell.setFact("look_done", True)
        shell.go(shell.stepIndex("hundred"))
        shell.hundred.loadPage(page)
        end = time.time() + 10
        while shell.hundred.busy and time.time() < end:
            QCoreApplication.processEvents()
        shell.hundred.style = "gold-case"
        shot("100", suffix)
        shell.startPath("manual")                                           # the other way: pick games, then a case for them
        shell.picker.load()
        end = time.time() + 10
        while shell.picker.loading and time.time() < end:
            QCoreApplication.processEvents()
        shell.picker.toggle(2)
        shell.picker.toggle(3)
        shell.go(shell.stepIndex("case"))
        shell.cases.pick("ps5")
        shot("cases", suffix)
        shell.startPath("natural")
    return 0


if __name__ == "__main__":
    sys.exit(main())
