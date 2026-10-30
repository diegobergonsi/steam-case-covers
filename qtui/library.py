# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Step 1 of the window: the game list. The saved userdata.json is noticed by itself, checked, and unlocks the next step."""
import os
import stat
import threading

from PySide6.QtCore import Property, QDir, QObject, QUrl, Signal, Slot
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
    failed = Signal(str, str)               # a title and the words of an error, for a box: a file the user chose is not a game list
    needDialog = Signal(str)                # the desktop has no file chooser of its own: show Qt's, starting in this folder
    _picked = Signal(object)                # the answer of the file chooser, which runs on another thread

    def __init__(self, shell, downloads, parent=None):
        super().__init__(parent)
        self._shell = shell
        self._downloads = downloads
        self._watcher = DownloadWatcher(downloads, "userdata", (".json",), sc.MAX_LIBRARY_FILE)
        self._path = ""
        self._count = 0
        self._choosing = False              # a file chooser is open
        self._why = ""                      # why the last file was refused
        self._picked.connect(self._on_picked)
        self._reported = {}                 # path -> signature of the version whose error is already on screen
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
            if not stat.S_ISREG(os.stat(os.path.expanduser(path)).st_mode):         # a named pipe or a device would block the read for ever
                return 0, "Could not read %s as a game list (not a regular file)." % os.path.basename(path)
        except OSError:
            pass                                                                      # missing or unreadable: the engine words it
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
        self._why = why
        if why:
            text = "That file doesn't look right: %s" % why
            if self._path:                                      # say what is still in use: the old pop-up left that text on screen
                text += " Still using %s." % os.path.basename(self._path)
            elif self._installed:
                text += " Still using installed games only."
            self._set_status(text, "error")
            return False
        self._accept(path, count)
        return True

    @Slot(str, result=bool)
    def useFileUrl(self, url):
        """The answer of Qt's file dialog (a file: URL)."""
        return self._chosen(QDir.toNativeSeparators(QUrl(url).toLocalFile()))      # Qt answers C:/Users/x on Windows, the rest of the app uses C:\\Users\\x

    def _chosen(self, path):
        """A file the user picked (Browse, or Qt's dialog): a bad one gets a box as well as the status line. The watcher uses useFile and stays quiet."""
        ok = self.useFile(path)
        if not ok:
            self.failed.emit("That file doesn't look right", self._why)
        return ok

    @Slot()
    def poll(self):
        """One look at the Downloads folder (call it every 1.5 s). Stops looking once a list is loaded. A finished file that is not a game list
        is explained once per version of that file, and read again on the next look, because it may only have been busy."""
        if self._path:
            return
        for path, sig in self._watcher.poll():
            count, why = self._check(path)
            if not why:
                self._accept(path, count)
                return
            self._watcher.forget(path)                  # look again next time: the file may only have been busy for a moment (antivirus, the browser)
            if self._reported.get(path) != sig:         # but say why it is refused once per version, not again over another message
                self._reported[path] = sig
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
        """Open the desktop's file chooser on another thread, so the window keeps painting while it is open."""
        if self._choosing:
            return
        self._choosing = True

        def ask():
            try:
                path = pick_file("Choose your userdata.json", self._downloads)
            except Exception:
                path = None                                     # no chooser worked: Qt's own dialog
            self._picked.emit(path)
        threading.Thread(target=ask, daemon=True).start()

    def _on_picked(self, path):
        self._choosing = False
        if path is None:
            self.needDialog.emit(self._downloads)
        elif path:
            self._chosen(path)
