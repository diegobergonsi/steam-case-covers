# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Notices a file the user saves from the browser, once it is finished."""
import os
import stat


class DownloadWatcher:
    """Looks in `folder` for files whose name starts with `prefix` (any case) and ends with one of `suffixes`.
    A file counts when it is a regular file (not a link) of at most `max_size` bytes, that is new or changed since the watcher started
    (what lay there before is stale; this does not depend on the clock, which may step back), and that has the same signature on two polls
    in a row, which means the browser has finished writing it. The signature is (size, modification time in ns, file id), so a replacement
    of the same size and time is still noticed. Each version of a file is handed over once."""

    def __init__(self, folder, prefix, suffixes, max_size):
        self.folder, self.prefix, self.suffixes = folder, prefix.lower(), tuple(s.lower() for s in suffixes)
        self.max_size = max_size
        self._seen = {}                  # path -> signature at the last poll
        self._given = {}                 # path -> signature already handed over
        self._before = dict(self._scan())    # path -> signature of what was there at the start

    def _scan(self):
        """[(path, signature)] of every file that matches the name and is a regular file of an allowed size. Never raises."""
        try:
            names = os.listdir(self.folder)
        except OSError:
            return []
        out = []
        for name in names:
            low = name.lower()
            if not (low.startswith(self.prefix) and low.endswith(self.suffixes)):
                continue
            path = os.path.join(self.folder, name)
            try:
                st = os.lstat(path)
            except OSError:
                continue
            if stat.S_ISREG(st.st_mode) and st.st_size <= self.max_size:
                out.append((path, (st.st_size, st.st_mtime_ns, st.st_ino)))
        return out

    def poll(self):
        """[(path, signature)] of the files that just became finished, in name order. Never raises."""
        found = []
        for path, sig in self._scan():
            if self._before.get(path) == sig:
                continue                                 # already there when the app started and not touched since
            if self._seen.get(path) == sig and self._given.get(path) != sig:
                self._given[path] = sig
                found.append((path, sig))
            self._seen[path] = sig
        return sorted(found)

    def forget(self, path):
        """Hand this file over again on the next poll (if it is still finished)."""
        self._given.pop(path, None)
