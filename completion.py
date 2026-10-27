# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""completion: find out which games are at 100% achievements, from your saved Steam games page.

The page ("Webpage, Complete" from your browser) is only read as text. Nothing but whole numbers
ever leaves read_games_page: no page text, no script content, no token (the page holds one).
"""
import errno, os, re, stat

MAX_GAMES_PAGE = 40 * 1024 * 1024        # the real page is a few MB; anything bigger is not it

_ROW = re.compile(r'<a href="https://store\.steampowered\.com/app/(\d{1,10})"')     # a game row links to its store page
# the achievements link of a row, then its "unlocked/total" counter; the label in between is in the user's language
_PROGRESS = re.compile(r'href="https://steamcommunity\.com/(?:id|profiles)/[^/"]{1,200}/achievements/(\d{1,10})"[^>]{0,500}>[^<]{0,200}</a><span[^>]{0,500}>(\d{1,9})/(\d{1,9})</span>')


class PageError(ValueError):
    """The file cannot be used. The message is plain English for the user."""


def read_games_page(path):
    """{app id: (unlocked, total)} for every game row that shows achievement progress."""
    name = os.path.basename(path)
    try:
        st = os.lstat(path)
    except OSError:
        raise PageError("That file could not be opened. (%s)" % name)
    if not stat.S_ISREG(st.st_mode):
        raise PageError("That is not a plain file. Pick the .html file you saved.")
    try:
        # the checks above can go stale before the open: no link is followed now, and the descriptor is checked again
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
    except OSError as e:
        if e.errno == errno.ELOOP:
            raise PageError("That is not a plain file. Pick the .html file you saved.")
        raise PageError("That file could not be opened. (%s)" % name)
    try:
        with os.fdopen(fd, "rb") as f:
            st = os.fstat(f.fileno())
            if not stat.S_ISREG(st.st_mode):
                raise PageError("That is not a plain file. Pick the .html file you saved.")
            if st.st_size > MAX_GAMES_PAGE:
                raise PageError("That file is too big to be your Steam games page.")
            text = f.read(MAX_GAMES_PAGE + 1).decode("utf-8", errors="replace")
    except OSError:
        raise PageError("That file could not be read.")
    if not _ROW.search(text):
        if "rgRecentlyPlayedGames" in text:
            raise PageError("This page was saved without its game list. Save it again as 'Webpage, Complete', not 'HTML only'.")
        raise PageError("That file does not look like your Steam games page. Open your games page on steamcommunity.com, then save it with Ctrl+S as 'Webpage, Complete'.")
    found = {int(m.group(1)): (int(m.group(2)), int(m.group(3))) for m in _PROGRESS.finditer(text)}
    if not found:
        raise PageError("No game shows achievement progress on this page. Save it again after the page has finished loading, as 'Webpage, Complete'.")
    return found


def completed_apps(progress):
    """The app ids at 100%: every achievement unlocked, and the game has some."""
    return {a for a, (done, total) in progress.items() if total > 0 and done == total}
