# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""The two links of the navigation: "Check for updates" (asks GitHub only when clicked, installs nothing) and "Discord". The words are those of the Tk window.
Every answer is a `message` for the window's dialog: a title, paragraphs, the label of the OK button, the label of Cancel ("" = an information box) and a link to open on OK."""
import threading

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QGuiApplication

import steamcase as sc


class Updates(QObject):
    checkingChanged = Signal()
    message = Signal(str, list, str, str, str)
    _checked = Signal(object, object)               # the answer of GitHub or the words of the error (from the worker thread)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._checking = False
        self._checked.connect(self._on_checked)

    @Property(bool, notify=checkingChanged)
    def checking(self):
        return self._checking

    @Slot()
    def check(self):
        """Ask GitHub whether a newer release exists. Only on click; nothing is downloaded or installed."""
        if self._checking:
            return
        self._checking = True
        self.checkingChanged.emit()
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        result = error = None
        try:
            result = sc.check_for_update()
        except sc.SteamcaseError as e:
            error = str(e)
        except Exception as e:
            error = "Unexpected problem: %s" % e
        try:
            self._checked.emit(result, error)
        except RuntimeError:
            pass                                    # the window is closing

    def _on_checked(self, r, error):
        self._checking = False
        self.checkingChanged.emit()
        if error:
            self.message.emit("Could not check for updates", [{"text": error, "kind": "main"}], "OK", "", "")
        elif r["newer"] is False:
            self.message.emit("No update needed", [{"text": "You have the latest version (%s)." % r["current"], "kind": "main"}], "OK", "", "")
        else:
            if r["newer"]:
                head = "A newer version is available: %s (you have %s)." % (r["latest"], r["current"])
            else:
                head = "The latest version is %s. This copy has no version number (it was not installed from a release), so I cannot compare." % r["latest"]
            self.message.emit("Update available", [
                {"text": head, "kind": "main"},
                {"text": "\u201cOpen GitHub page\u201d opens this project's release page on GitHub in your web browser:\n%s" % r["url"], "kind": "muted"},
                {"text": "Nothing is downloaded or installed unless you choose to do it yourself on that page.", "kind": "muted"}],
                "Open GitHub page", "Not now", r["url"])

    @Slot(str)
    def openLink(self, url):
        """Open a web link in the browser. Anything that is not http(s) is ignored."""
        if url.startswith("https://") or url.startswith("http://"):
            QDesktopServices.openUrl(QUrl(url))

    @Slot()
    def openDiscord(self):
        """Open the project's Discord invite in the browser. If no browser opens, the link is copied and shown instead."""
        if not QDesktopServices.openUrl(QUrl(sc.DISCORD_URL)):
            QGuiApplication.clipboard().setText(sc.DISCORD_URL)
            self.message.emit("Join our Discord", [{"text": "Your browser did not open, so the invite link was copied. Paste it into your browser:\n%s" % sc.DISCORD_URL, "kind": "main"}],
                              "OK", "", "")
