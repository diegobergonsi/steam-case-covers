# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""completion: find out which games are at 100% achievements, from your saved Steam games page.

The page ("Webpage, Complete" from your browser) is only read as text. Nothing but whole numbers
ever leaves read_games_page: no page text, no script content, no token (the page holds one).
"""
import os, re

import safefile

_t = lambda text: text                 # the window replaces this with its own tr(), so a message is in its language; the command line stays English

MAX_GAMES_PAGE = 40 * 1024 * 1024        # the real page is a few MB; anything bigger is not it

_ROW = re.compile(r'<a href="https://store\.steampowered\.com/app/(\d{1,10})"')     # a game row links to its store page
# the achievements link of a row, then its "unlocked/total" counter; the label in between is in the user's language
_PROGRESS = re.compile(r'href="https://steamcommunity\.com/(?:id|profiles)/[^/"]{1,200}/achievements/(\d{1,10})"[^>]{0,500}>[^<]{0,200}</a><span[^>]{0,500}>(\d{1,9})/(\d{1,9})</span>')


class PageError(ValueError):
    """The file cannot be used. The message is plain English for the user."""


def read_games_page(path):
    """{app id: (unlocked, total)} for every game row that shows achievement progress."""
    try:
        text = safefile.read_small_file(path, MAX_GAMES_PAGE).decode("utf-8", errors="replace")
    except safefile.NotRegularFile:
        raise PageError(_t("That is not a plain file. Pick the .html file you saved."))
    except safefile.FileTooBig:
        raise PageError(_t("That file is too big to be your Steam games page."))
    except OSError:
        raise PageError(_t("That file could not be opened. (%s)") % os.path.basename(path))
    if not _ROW.search(text):
        if "rgRecentlyPlayedGames" in text:
            raise PageError(_t("This page was saved without its game list. Save it again as 'Webpage, Complete', not 'HTML only'."))
        raise PageError(_t("That file does not look like your Steam games page. Open your games page on steamcommunity.com, then save it with Ctrl+S as 'Webpage, Complete'."))
    found = {int(m.group(1)): (int(m.group(2)), int(m.group(3))) for m in _PROGRESS.finditer(text)}
    if not found:
        raise PageError(_t("No game shows achievement progress on this page. Save it again after the page has finished loading, as 'Webpage, Complete'."))
    return found


def completed_apps(progress):
    """The app ids at 100%: every achievement unlocked, and the game has some."""
    return {a for a, (done, total) in progress.items() if total > 0 and done == total}
