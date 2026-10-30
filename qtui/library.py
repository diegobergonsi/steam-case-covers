# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Step 1 of the window: the game list. The saved userdata.json is noticed by itself, checked, and unlocks the next step."""
import os

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QGuiApplication

import steamcase as sc
from qtui.filepicker import pick_file
from qtui.system import SAVE_KEY
from qtui.watcher import DownloadWatcher

WAITING = "Waiting for userdata.json…"
INSTALLED_ONLY = "Using installed games only."


class Library(QObject):
    pathChanged = Signal()
    installedOnlyChanged = Signal()
    readyChanged = Signal()
    statusChanged = Signal()
    needDialog = Signal(str)                # the desktop has no file chooser of its own: show Qt's, starting in this folder

    def __init__(self, shell, downloads, started, parent=None):
        super().__init__(parent)
        self._shell = shell
        self._downloads = downloads
        self._watcher = DownloadWatcher(downloads, "userdata", (".json",), started, sc.MAX_LIBRARY_FILE)
        self._path = ""
        self._count = 0
        self._installed = shell.switchValue("installed_only")
        self._status, self._kind = "", "wait"
        self._show_default_status()
        self._was_ready = self.ready
        shell.setFact("ready", self.ready)

    # ----- properties -----
    @Property(str, notify=pathChanged)
    def path(self):
        return self._path

    @Property(str, constant=True)
    def downloadsUrl(self):
        """The Downloads folder as a URL, for the Qt file dialog."""
        return QUrl.fromLocalFile(self._downloads).toString()

    @Property(bool, notify=readyChanged)
    def ready(self):
        """True when a list is loaded or only the installed games are wanted: step 2 may open."""
        return self._installed or bool(self._path)

    @Property(str, notify=statusChanged)
    def status(self):
        return self._status

    @Property(str, notify=statusChanged)
    def statusKind(self):
        return self._kind

    def _get_installed(self):
        return self._installed

    def _set_installed(self, value):
        value = bool(value)
        if value != self._installed:
            self._installed = value
            self._shell.setSwitch("installed_only", value)
            self.installedOnlyChanged.emit()
            self._after_change()

    installedOnly = Property(bool, _get_installed, _set_installed, notify=installedOnlyChanged)

    # ----- behaviour -----
    def _set_status(self, text, kind):
        if (text, kind) != (self._status, self._kind):
            self._status, self._kind = text, kind
            self.statusChanged.emit()

    def _show_default_status(self):
        if self._installed:
            self._set_status(INSTALLED_ONLY, "ok")
        elif self._path:
            self._set_status("Got it: %s (%d items in your library)." % (os.path.basename(self._path), self._count), "ok")
        else:
            self._set_status(WAITING, "wait")

    def _after_change(self):
        self._show_default_status()
        if self.ready != self._was_ready:
            self._was_ready = self.ready
            self.readyChanged.emit()
        self._shell.setFact("ready", self.ready)

    @staticmethod
    def _check(path):
        """(number of items, "") for a good game list, (0, reason) otherwise."""
        try:
            return len(sc.owned_ids(path)), ""
        except sc.SteamcaseError as e:
            return 0, str(e)

    def _accept(self, path, count):
        self._path, self._count = path, count
        self.pathChanged.emit()
        if self._installed:                         # a file wins over "installed only", as before
            self._installed = False
            self._shell.setSwitch("installed_only", False)
            self.installedOnlyChanged.emit()
        self._after_change()

    @Slot(str, result=bool)
    def useFile(self, path):
        """Check a file the user chose and use it. A bad file changes nothing but the status."""
        count, why = self._check(path)
        if why:
            self._set_status("That file doesn't look right: %s" % why, "error")
            return False
        self._accept(path, count)
        return True

    @Slot(str, result=bool)
    def useFileUrl(self, url):
        """The answer of Qt's file dialog (a file: URL)."""
        return self.useFile(QUrl(url).toLocalFile())

    @Slot()
    def poll(self):
        """One look at the Downloads folder (call it every 1.5 s). Stops looking once a list is loaded. A file that is not a game list
        is explained once per version of that file."""
        if self._path:
            return
        for path, _sig in self._watcher.poll():
            count, why = self._check(path)
            if not why:
                self._accept(path, count)
                return
            self._set_status("%s: %s" % (os.path.basename(path), why), "error")

    @Slot()
    def openDownloadPage(self):
        QDesktopServices.openUrl(QUrl(sc.library_login_url()))
        # Qt cannot tell whether a browser really opened, so always show the way out
        self._set_status("Opening your browser\u2026 Log in to Steam if it asks. You'll then see a page of plain text: save it as userdata.json (%s) and I'll pick it up. "
                         "Nothing opened? Click \u201cCopy link\u201d and paste it into your browser." % SAVE_KEY, "wait")

    @Slot()
    def copyLink(self):
        QGuiApplication.clipboard().setText(sc.library_login_url())
        self._set_status("Link copied. Paste it into your browser, log in if asked, then save the page as userdata.json (%s)." % SAVE_KEY, "ok")

    @Slot()
    def browse(self):
        path = pick_file("Choose your userdata.json", self._downloads)
        if path is None:
            self.needDialog.emit(self._downloads)
        elif path:
            self.useFile(path)
