# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""The user's own case: asks for the file (the desktop's chooser, or Qt's dialog when there is none), checks it and keeps the copy (steamcase.save_custom_case).
One case at a time: picking a file replaces the one before. The Case step and the Look step both use this object."""
import threading

from PySide6.QtCore import Property, QDir, QObject, QUrl, Signal, Slot

from engine import steamcase as sc
from qtui.filepicker import pick_file
from qtui.i18n import N_, tr


class OwnCase(QObject):
    _WAIT = N_("Your case cannot be changed while covers are being made. Try again when they are done.")

    changed = Signal()
    failed = Signal(str, str)               # a title and the words of an error, for a box: the file is not a case
    needDialog = Signal(str)                # the desktop has no file chooser of its own: show Qt's, starting in this folder
    _picked = Signal(object)                # the answer of the file chooser, which runs on another thread

    def __init__(self, covers_dir, downloads, parent=None, busy=lambda: False):
        super().__init__(parent)
        self._covers, self._downloads, self._busy = covers_dir, downloads, busy      # busy(): covers are being made, and the case must not change under them
        self._choosing, self._error, self._serial = False, "", 0
        self._then = None                   # what to do once the file in question is accepted (see ask)
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

    def ask(self, then):
        """Ask for a case file; `then()` runs once, only if the file is accepted. A cancelled or refused pick runs nothing."""
        if self._choosing:
            return
        if self._busy():
            self._fail(tr("Wait for the covers"), tr(self._WAIT))
            return
        self._then = then
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
            self._then = None                                   # cancelled

    @Slot(str)
    def useFileUrl(self, url):
        """The answer of Qt's file dialog (a file: URL)."""
        self.use(QDir.toNativeSeparators(QUrl(url).toLocalFile()))

    def use(self, path):
        """Check the file and keep it as the case. A bad one leaves the old case as it was and gets a box as well as `error`."""
        try:
            if self._busy():                                    # the Qt dialog may have been open while a run began
                raise sc.SteamcaseError(tr(self._WAIT))
            sc.save_custom_case(path, self._covers)
        except Exception as e:                                  # a SteamcaseError says what is wrong; anything else must not leave the window waiting for an answer
            self._fail(tr("That file can't be used as a case"), str(e))
            return
        self._error = ""
        self._serial += 1
        self.changed.emit()
        then, self._then = self._then, None
        if then:
            then()

    def _fail(self, title, text):
        self._then, self._error = None, text
        self.changed.emit()
        self.failed.emit(title, text)
