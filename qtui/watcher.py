# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Notices a file the user saves from the browser, once it is finished."""
import os
import stat


class DownloadWatcher:
    """Looks in `folder` for files whose name starts with `prefix` (any case) and ends with one of `suffixes`.
    A file counts when it is a regular file (not a link), was saved after `started`, is at most `max_size` bytes, and has the same (size, time)
    on two polls in a row, which means the browser has finished writing it. Each version of a file is handed over once."""

    def __init__(self, folder, prefix, suffixes, started, max_size):
        self.folder, self.prefix, self.suffixes = folder, prefix.lower(), tuple(s.lower() for s in suffixes)
        self.started, self.max_size = started, max_size
        self._seen = {}                  # path -> signature at the last poll
        self._given = {}                 # path -> signature already handed over

    def poll(self):
        """[(path, (size, mtime))] of the files that just became finished. Never raises."""
        try:
            names = os.listdir(self.folder)
        except OSError:
            return []
        found = []
        for name in sorted(names):
            low = name.lower()
            if not (low.startswith(self.prefix) and low.endswith(self.suffixes)):
                continue
            path = os.path.join(self.folder, name)
            try:
                st = os.lstat(path)
            except OSError:
                continue
            if not stat.S_ISREG(st.st_mode) or st.st_mtime < self.started or st.st_size > self.max_size:
                continue
            sig = (st.st_size, st.st_mtime)
            if self._seen.get(path) == sig and self._given.get(path) != sig:
                self._given[path] = sig
                found.append((path, sig))
            self._seen[path] = sig
        return found

    def forget(self, path):
        """Hand this file over again on the next poll (if it is still finished)."""
        self._given.pop(path, None)
