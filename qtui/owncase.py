# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""The user's own case: asks for the file (the desktop's chooser, or Qt's dialog when there is none), checks it and keeps the copy (steamcase.save_custom_case).
One case at a time: picking a file replaces the one before. The Case step and the Look step both use this object."""
import threading

from PySide6.QtCore import Property, QDir, QObject, QUrl, Signal, Slot

import steamcase as sc
from qtui.filepicker import pick_file
from qtui.i18n import tr


class OwnCase(QObject):
    changed = Signal()
    failed = Signal(str, str)               # a title and the words of an error, for a box: the file is not a case
    needDialog = Signal(str)                # the desktop has no file chooser of its own: show Qt's, starting in this folder
    finished = Signal(bool)                 # a pick ended: True when a case file was accepted, False when it was cancelled or refused
    _picked = Signal(object)                # the answer of the file chooser, which runs on another thread

    def __init__(self, covers_dir, downloads, parent=None):
        super().__init__(parent)
        self._covers, self._downloads = covers_dir, downloads
        self._choosing, self._error, self._serial = False, "", 0
        self._picked.connect(self._on_picked)
        try:                                # the copy kept by an earlier run is the case again
            sc.use_custom_case(covers_dir)
        except sc.SteamcaseError as e:
            self._error = str(e)

    @Property(bool, notify=changed)
    def available(self):
        return sc.custom_case_digest() is not None

    @Property(bool, notify=changed)
    def choosing(self):
        return self._choosing

    @Property(str, notify=changed)
    def error(self):
        return self._error

    @Property(int, notify=changed)
    def serial(self):
        """Changes with every accepted file, so a picture of the case is asked for again."""
        return self._serial

    @Property(str, constant=True)
    def downloadsUrl(self):
        return QUrl.fromLocalFile(self._downloads).toString()

    @Slot()
    def browse(self):
        """Open the desktop's file chooser on another thread, so the window keeps painting while it is open."""
        if self._choosing:
            return
        self._choosing = True
        self.changed.emit()

        def ask():
            try:
                path = pick_file(tr("Choose your case file"), self._downloads, (tr("PNG pictures"), "*.png"))
            except Exception:
                path = None                                     # no chooser worked: Qt's own dialog
            self._picked.emit(path)
        threading.Thread(target=ask, daemon=True).start()

    def _on_picked(self, path):
        self._choosing = False
        self.changed.emit()
        if path is None:
            self.needDialog.emit(self._downloads)
        elif path:
            self.use(path)
        else:
            self.finished.emit(False)                           # cancelled

    @Slot(str)
    def useFileUrl(self, url):
        """The answer of Qt's file dialog (a file: URL)."""
        self.use(QDir.toNativeSeparators(QUrl(url).toLocalFile()))

    def use(self, path):
        """Check the file and keep it as the case. A bad one leaves the old case as it was and gets a box as well as `error`."""
        try:
            sc.save_custom_case(path, self._covers)
        except sc.SteamcaseError as e:
            self._error = str(e)
            self.changed.emit()
            self.failed.emit(tr("That file can't be used as a case"), self._error)
            self.finished.emit(False)
            return
        self._error = ""
        self._serial += 1
        self.changed.emit()
        self.finished.emit(True)
