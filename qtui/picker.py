# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""The Games step of the manual flow: the games of the game list by name, a search box and a tick box per game. The names come from Steam's store
(a game list holds only numbers), so the list is read on a worker thread; what is ticked is kept here, in Python, whatever the search shows."""
import threading

from PySide6.QtCore import Property, QAbstractListModel, QModelIndex, QObject, Qt, Signal, Slot

import steamcase as sc
from qtui.i18n import N_, tr, trn

NO_GAMES = N_("No games found. Install a game first, or load your userdata.json.")


class RowsModel(QAbstractListModel):
    """The rows the search shows, for the list on screen. Ticking a game only changes that row's data: the list keeps its place."""
    Appid, Name, Selected = Qt.UserRole + 1, Qt.UserRole + 2, Qt.UserRole + 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = []

    def roleNames(self):
        return {self.Appid: b"appid", self.Name: b"name", self.Selected: b"selected"}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        row = self._rows[index.row()]
        return {self.Appid: row["appid"], self.Name: row["name"], self.Selected: row["selected"]}.get(role)

    def set_rows(self, rows):
        """Show these rows: only the tick of a row that is still there changes in place, any other set of rows is a reset."""
        if [r["appid"] for r in rows] == [r["appid"] for r in self._rows]:
            old, self._rows = self._rows, rows
            for i, (a, b) in enumerate(zip(old, rows)):
                if a["selected"] != b["selected"]:
                    self.dataChanged.emit(self.index(i, 0), self.index(i, 0), [self.Selected])
            return
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()


class Picker(QObject):
    loadingChanged = Signal()
    rowsChanged = Signal()
    queryChanged = Signal()
    selectionChanged = Signal()
    statusChanged = Signal()
    failed = Signal(str, str)               # a title and the words of an error, for a box the user cannot miss
    _loaded = Signal(int, object, object, object)           # request, [(appid, name)], the store errors, the words of an error (from the worker)

    def __init__(self, shell, parent=None):
        super().__init__(parent)
        self._shell = shell
        self._all = []                      # [(appid, name)] sorted by name
        self._selected = set()
        self._query = ""
        self._loading = False
        self._req = 0
        self._key = None                    # what the list on screen was made for: (game list path, installed only)
        self._note = ""                     # a sentence about the last load (names that could not be loaded)
        self._error = ""
        self._rows = []
        self._model = RowsModel(self)
        self._loaded.connect(self._on_loaded)
        shell.library.pathChanged.connect(self._library_changed)
        shell.library.installedOnlyChanged.connect(self._library_changed)

    # ----- properties -----
    @Property(bool, notify=loadingChanged)
    def loading(self):
        return self._loading

    @Property("QVariantList", notify=rowsChanged)
    def rows(self):
        """The games the search shows: {"appid", "name", "selected"}."""
        return self._rows

    @Property(QObject, constant=True)
    def model(self):
        """The same rows as a list model, for the list on screen."""
        return self._model

    def _get_query(self):
        return self._query

    def _set_query(self, text):
        text = str(text)
        if text != self._query:
            self._query = text
            self._refresh()
            self.queryChanged.emit()

    query = Property(str, _get_query, _set_query, notify=queryChanged)

    @Property(int, notify=selectionChanged)
    def selectedCount(self):
        return len(self._selected)

    @Property(str, notify=statusChanged)
    def status(self):
        if self._loading:
            return tr("Loading your games…")
        if self._error:
            return self._error
        if not self._all:
            return "" if self._key is None else tr(NO_GAMES)
        if not self._rows:
            return tr("No games match “%s”.") % self._query.strip()
        return (trn("%n game.|%n games.", len(self._all)) + " " + self._note).strip()

    @Property(str, notify=statusChanged)
    def statusKind(self):
        if self._loading or (self._note and self._all and not self._error):
            return "wait"
        return "error" if self._error or (self._key is not None and not self._all) else "ok"

    def selection(self):
        """The ticked games' app ids, sorted."""
        return sorted(self._selected)

    # ----- the list -----
    def _library_key(self):
        library = self._shell.library
        return (library.path, bool(library.installedOnly))

    def _library_changed(self):
        """The game list changed: what was ticked belongs to the old one, and an answer still on its way is for the old one too."""
        if self._key is None and not self._loading and not self._all and not self._selected:
            return
        self._req += 1                                  # the worker's answer is now stale and will be dropped
        was_loading, self._loading = self._loading, False
        self._all, self._rows, self._key, self._note, self._error = [], [], None, "", ""
        self._model.set_rows([])
        if was_loading:
            self.loadingChanged.emit()
        if self._selected:
            self._selected = set()
            self.selectionChanged.emit()
        self.rowsChanged.emit()
        self.statusChanged.emit()

    def _refresh(self):
        words = self._query.casefold().split()
        self._rows = [{"appid": a, "name": n, "selected": a in self._selected} for a, n in self._all if all(w in n.casefold() for w in words)]
        self._model.set_rows(self._rows)
        self.rowsChanged.emit()
        self.statusChanged.emit()

    @Slot()
    def ensureLoaded(self):
        """Read the games unless the list on screen is already the one for this game list."""
        if not self._loading and self._key != self._library_key():
            self.load()

    @Slot()
    def load(self):
        if self._loading:
            return
        key = self._library_key()
        self._req += 1
        self._loading, self._error, self._note = True, "", ""
        self.loadingChanged.emit()
        self.statusChanged.emit()
        threading.Thread(target=self._worker, args=(self._req, None if key[1] else key[0] or None, key), daemon=True).start()

    def _worker(self, req, library, key):
        """Off the UI thread: the games of the list and their names from Steam's store."""
        rows = errors = error = None
        try:
            games, _ = sc.load_library(sc.steam_dir(), library)
            errors = []
            rows = sc.list_games(games, errors=errors)
        except sc.SteamcaseError as e:
            error = str(e)
        except Exception as e:                          # never leave the window stuck in "Loading"
            error = tr("Unexpected problem: %s") % e
        try:
            self._loaded.emit(req, rows, errors, (error, key))
        except RuntimeError:
            pass                                        # the window is closing: nobody is left to hear the answer

    def _on_loaded(self, req, rows, errors, error_and_key):
        error, key = error_and_key
        if req != self._req:
            return
        self._loading = False
        self.loadingChanged.emit()
        if error:
            self._all, self._error, self._key = [], error, None
            self._selected = set()
            self._refresh()
            self.selectionChanged.emit()
            self.failed.emit(tr("Cannot list your games"), error)
            return
        self._key = key
        self._all = sorted(rows, key=lambda r: (r[1].casefold(), r[0]))
        self._selected &= {a for a, _ in self._all}
        if errors and not self._all:
            self._error = tr("Could not reach Steam's servers: %s.") % sc.explain_error(errors[-1]).rstrip(".")
            self._key = None
            self.failed.emit(tr("Cannot list your games"), self._error)
        elif errors:
            self._note = tr("Some names could not be loaded (connection problem?), so those games are missing.")
        self._refresh()
        self.selectionChanged.emit()

    # ----- ticking -----
    @Slot(int)
    def toggle(self, appid):
        self._selected ^= {appid}
        self._refresh()
        self.selectionChanged.emit()

    @Slot()
    def selectAllShown(self):
        self._selected |= {r["appid"] for r in self._rows}
        self._refresh()
        self.selectionChanged.emit()

    @Slot()
    def clearAll(self):
        if self._selected:
            self._selected = set()
            self._refresh()
            self.selectionChanged.emit()

    def untick(self, appids):
        """Take these games out of the selection (the Case step calls this once they have a case)."""
        gone = self._selected & set(appids)
        if gone:
            self._selected -= gone
            self._refresh()
            self.selectionChanged.emit()
