# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Step 3 of the window: the 100% games. The saved Steam games page is read on a worker thread (only the app ids at 100% and the file's name ever
leave it: the page holds a login token), and the style of those covers follows the theme chosen in step 2."""
import os
import threading

from PySide6.QtCore import Property, QDir, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QGuiApplication

import completion
import steamcase as sc
from qtui.filepicker import pick_file
from qtui.reasons import MARKS, STYLES
from qtui.system import GAMES_PAGE_URL, SAVE_KEY, THEME_NOTE
from qtui.watcher import DownloadWatcher

WAITING = "No games page loaded. Your covers keep the look they have."


class Hundred(QObject):
    pathChanged = Signal()
    busyChanged = Signal()
    statusChanged = Signal()
    styleChanged = Signal()
    marksChanged = Signal()
    choicesChanged = Signal()               # styleEnabled and marksEnabled (they depend on the page, the case and the theme)
    themeNoteChanged = Signal()
    needDialog = Signal(str)                # the desktop has no file chooser of its own: show Qt's, starting in this folder
    _picked = Signal(object)                # the answer of the file chooser, which runs on another thread
    _read = Signal(int, str, object, object)        # request number, path, app ids at 100% or None, the error words or None (from the worker thread)

    def __init__(self, shell, downloads, parent=None):
        super().__init__(parent)
        self._shell = shell
        self._look = shell.look
        self._downloads = downloads
        self._watcher = DownloadWatcher(downloads, "games", (".html", ".htm"), completion.MAX_GAMES_PAGE)
        self._path = ""
        self._completed = None              # None: no page loaded
        self._req = 0
        self._pending = 0
        self._choosing = False
        self._style, self._marks = "ribbon", "full"
        self._marks_before = None           # the marks chosen before Halloween forced the rosette
        self._status, self._kind, self._note = WAITING, "wait", ""
        self._picked.connect(self._on_picked)
        self._read.connect(self._on_read)
        self._look.themeChanged.connect(self._theme_changed)
        self._theme_changed()               # the folder may hold Halloween covers already

    # ----- properties -----
    @Property(str, notify=pathChanged)
    def path(self):
        return self._path

    @Property(bool, notify=pathChanged)
    def loaded(self):
        return self._completed is not None

    @Property(int, notify=pathChanged)
    def count(self):
        return len(self._completed or ())

    @Property(bool, notify=busyChanged)
    def busy(self):
        """A page is being read: Make must wait for it, it must not use the page read before."""
        return self._pending > 0

    @Property(str, notify=statusChanged)
    def status(self):
        return self._status

    @Property(str, notify=statusChanged)
    def statusKind(self):
        return self._kind

    @Property(str, notify=statusChanged)
    def note(self):
        """Advice for after a page is loaded: delete the file, it holds a login token."""
        return self._note

    @Property(str, constant=True)
    def downloadsUrl(self):
        return QUrl.fromLocalFile(self._downloads).toString()

    @Property("QVariantList", constant=True)
    def styles(self):
        return [{"key": k, "label": v} for k, v in STYLES]

    @Property("QVariantList", constant=True)
    def markChoices(self):
        return [{"key": k, "label": v} for k, v in MARKS]

    @Property(bool, notify=choicesChanged)
    def styleEnabled(self):
        return self._completed is not None

    @Property(bool, notify=choicesChanged)
    def marksEnabled(self):
        """Marks can be chosen with a page loaded, a case to put them on, and the classic theme (Halloween has the rosette alone)."""
        return self._completed is not None and self._style in sc.CASES and self._look.theme == "classic"

    @Property(str, notify=themeNoteChanged)
    def themeNote(self):
        return THEME_NOTE if self._look.theme != "classic" else ""

    def _get_style(self):
        return self._style

    def _set_style(self, value):
        if value in sc.CASES or value == "none":
            if value != self._style:
                self._style = value
                self.styleChanged.emit()
                self._sync()

    style = Property(str, _get_style, _set_style, notify=styleChanged)

    def _get_marks(self):
        return self._marks

    def _set_marks(self, value):
        if value in sc.MARKS and value != self._marks and self._look.theme == "classic":      # under Halloween the choice is greyed and fixed
            self._marks = value
            self.marksChanged.emit()
            self._sync()

    marks = Property(str, _get_marks, _set_marks, notify=marksChanged)

    # ----- what Make gets -----
    def values(self):
        """(completed, treatment) for make_covers. No page loaded: (None, None), every cover keeps its look.
        "No special case": (empty set, None), the 100% covers become normal covers. Otherwise the 100% ids and the chosen style."""
        if self._completed is None:
            return None, None
        if self._style not in sc.CASES:
            return set(), None
        return set(self._completed), sc.compose_treatment(self._style, self._marks)

    def _sync(self):
        """The preview shows a 100% cover in the chosen style, only when a page is loaded."""
        self._look.treatment = self.values()[1] or "none"
        self.choicesChanged.emit()

    def _theme_changed(self):
        """Halloween goes with the rosette alone: choosing it picks that and greys the marks out; going back restores what was picked before."""
        before = self._marks
        if self._look.theme != "classic":
            if self._marks_before is None:
                self._marks_before = self._marks
            self._marks = "rosette"
        elif self._marks_before is not None:
            self._marks, self._marks_before = self._marks_before, None
        if self._marks != before:
            self.marksChanged.emit()
        self.themeNoteChanged.emit()
        self._sync()

    # ----- the page -----
    def _set_status(self, text, kind, note=None):
        note = self._note if note is None else note
        if (text, kind, note) != (self._status, self._kind, self._note):
            self._status, self._kind, self._note = text, kind, note
            self.statusChanged.emit()

    @Slot(str)
    def loadPage(self, path):
        """Read the saved page on a worker thread. The newest request wins; the answer of an older one is dropped."""
        if not path:
            return
        self._req += 1
        self._pending += 1
        self.busyChanged.emit()
        self._set_status("Reading %s…" % os.path.basename(path), "wait")
        threading.Thread(target=self._worker, args=(self._req, path), daemon=True).start()

    @Slot(str)
    def loadPageUrl(self, url):
        """The answer of Qt's file dialog (a file: URL)."""
        self.loadPage(QDir.toNativeSeparators(QUrl(url).toLocalFile()))

    def _worker(self, req, path):
        """Off the UI thread. Only the app ids at 100% come back, never any text from the page (it holds a login token)."""
        try:
            done, error = completion.completed_apps(completion.read_games_page(path)), None
        except completion.PageError as e:
            done, error = None, str(e)
        except Exception:                            # never echo what went wrong in detail: it could quote the page
            done, error = None, "That file could not be read."
        try:
            self._read.emit(req, path, done, error)
        except RuntimeError:
            pass                                     # the window is closing: nobody is left to hear the answer

    def _on_read(self, req, path, done, error):
        self._pending -= 1
        self.busyChanged.emit()
        if req != self._req:                         # the user picked another page in the meantime
            return
        name = os.path.basename(path)                # only the file's name is shown, never anything from inside it
        if error:
            kept = " The page you loaded before is still used." if self._path else ""
            self._set_status("%s: %s%s" % (name, error, kept), "error")
            return
        self._path, self._completed = path, set(done)
        n = len(done)
        found = "Found %d %s at 100%% in %s." % (n, "game" if n == 1 else "games", name) if n else "No game in %s is at 100%% yet." % name
        self._set_status(found + " The game list from step 1 decides which games get covers.", "ok",
                         "Done with the page? You can delete %s and its folder: they hold a temporary login token for your Steam account, "
                         "which this app does not use or keep." % name)
        self.pathChanged.emit()
        self._sync()

    @Slot()
    def poll(self):
        """One look at the Downloads folder (call it every 1.5 s) for a saved games page. Stops once a page is loaded or while one is being read.
        One finished file is read; if more than one finished at once the others are offered again on the next look."""
        if self._completed is not None or self._pending:
            return
        found = self._watcher.poll()
        for path, _sig in found[1:]:
            self._watcher.forget(path)
        if found:
            self.loadPage(found[0][0])

    # ----- ways to get the file -----
    @Slot()
    def openPage(self):
        QDesktopServices.openUrl(QUrl(GAMES_PAGE_URL))
        # Qt cannot tell whether a browser really opened, so always show the way out
        self._set_status("Opening your browser… Log in to Steam if it asks and wait until your games have loaded. Then press %s and save the page "
                         "as “Webpage, Complete”, named games.html. Nothing opened? Click “Copy link” and paste it into your browser." % SAVE_KEY, "wait")

    @Slot()
    def copyLink(self):
        QGuiApplication.clipboard().setText(GAMES_PAGE_URL)
        self._set_status("Link copied. Paste it into your browser, log in if asked, then save the page as “Webpage, Complete”, "
                         "named games.html (%s)." % SAVE_KEY, "ok")

    @Slot()
    def browse(self):
        """Open the desktop's file chooser on another thread, so the window keeps painting while it is open."""
        if self._choosing:
            return
        self._choosing = True

        def ask():
            try:
                path = pick_file("Choose your saved games page", self._downloads, ("Web pages", "*.html *.htm"))
            except Exception:
                path = None                                     # no chooser worked: Qt's own dialog
            self._picked.emit(path)
        threading.Thread(target=ask, daemon=True).start()

    def _on_picked(self, path):
        self._choosing = False
        if path is None:
            self.needDialog.emit(self._downloads)
        elif path:
            self.loadPage(path)
