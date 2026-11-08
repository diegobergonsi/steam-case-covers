# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Manage a group from Home: its name and its games, kept in a window of their own. Rename, removing games and deleting are saved at once (groups.json and the
group note of the covers); games added are held in Cases until the next make, because their covers do not exist yet and a group is saved only with games that
have one. The ticks here are Manage's own: they never touch the ticks of the Pick games step."""
from PySide6.QtCore import Property, QObject, Signal, Slot

from engine import groups
from engine import steamcase as sc
from qtui.i18n import N_, tr
from qtui.picker import RowsModel

NO_GAMES_TICKED = N_("No games ticked. Saving would delete this group.")
SAVED = N_("Saved. Your covers change the next time you make covers, with \u201cSame case\u201d or \u201cPick games\u201d.")
DELETED = N_("Deleted. Your covers change the next time you make covers, with \u201cSame case\u201d or \u201cPick games\u201d.")


class GroupManager(QObject):
    changed = Signal()
    saved = Signal()                        # the groups file changed: whoever shows or keeps the groups reads them again (the shell connects them)
    failed = Signal(str, str)               # a title and the words of an error, for a box the user cannot miss

    def __init__(self, shell, covers_dir, parent=None):
        super().__init__(parent)
        self._shell = shell
        self._covers = covers_dir
        self._model = RowsModel(self)
        self._open, self._gid, self._title, self._name, self._error, self._query = False, "", "", "", "", ""
        self._ticked = set()
        self._saved = []                    # the group's games as the file had them when the window opened
        self._others = {}                   # appid -> name of the group it is in now, for the games of other groups
        shell.picker.rowsChanged.connect(self._rebuild)
        shell.picker.loadingChanged.connect(self._rebuild)

    # ----- what the window shows -----
    @Property(QObject, constant=True)
    def model(self):
        return self._model

    @Property(bool, notify=changed)
    def isOpen(self):
        return self._open

    @Property(bool, notify=changed)
    def canOpen(self):
        """Not while Steam is being worked on or covers are being made (the shell tells `changed` when that changes)."""
        return not self._shell.apply.busy and not self._shell.make.running

    @Property(str, notify=changed)
    def groupId(self):
        return self._gid

    @Property(str, notify=changed)
    def title(self):
        """The name the group has now (saved)."""
        return self._title

    def _get_name(self):
        return self._name

    def _set_name(self, value):
        value = str(value)
        if value != self._name:
            self._name, self._error = value, ""
            self.changed.emit()

    name = Property(str, _get_name, _set_name, notify=changed)

    def _get_query(self):
        return self._query

    def _set_query(self, value):
        value = str(value)
        if value != self._query:
            self._query = value
            self._rebuild()

    query = Property(str, _get_query, _set_query, notify=changed)

    @Property(int, notify=changed)
    def tickedCount(self):
        return len(self._ticked)

    @Property(str, notify=changed)
    def warning(self):
        return tr(NO_GAMES_TICKED) if self._open and not self._ticked else ""

    @Property(str, notify=changed)
    def error(self):
        return self._error

    @Property(bool, notify=changed)
    def loading(self):
        return self._shell.picker.loading

    @Property(bool, notify=changed)
    def canSave(self):
        """Only when the library is listed: without its names a game of the group could not be told from one that is gone."""
        return self._open and not self._shell.picker.loading and bool(self._shell.picker.games())

    # ----- opening and closing -----
    @Slot(str)
    def open(self, group_id):
        if self._open or not self.canOpen:
            return
        group = next((g for g in groups.load(self._covers) if g["id"] == group_id), None)
        if group is None:
            return
        self._open, self._gid, self._title, self._name, self._error, self._query = True, group_id, group["name"], group["name"], "", ""
        self._ticked, self._saved = set(group["games"]), list(group["games"])
        self._read_others()
        self._shell.picker.ensureLoaded()
        self._rebuild()

    def _read_others(self):
        self._others = {a: g["name"] for g in groups.load(self._covers) if g["id"] != self._gid for a in g["games"]}

    def _close(self):
        self._open, self._ticked, self._saved, self._others = False, set(), [], {}
        self._model.set_rows([])
        self.changed.emit()

    @Slot()
    def cancel(self):
        if self._open:
            self._close()

    def _rebuild(self):
        if not self._open:
            self.changed.emit()
            return
        listed = self._shell.picker.games()
        known = {a for a, _ in listed}
        missing = [(a, "Game %d" % a) for a in self._saved if a not in known]         # a game the store no longer names stays, so Save never drops it unseen
        every = sorted(listed + missing, key=lambda r: (r[0] not in self._saved, r[1].casefold(), r[0]))      # the group's own games first, each part by name; fixed while open, so rows do not jump when ticking
        words = self._query.casefold().split()
        rows = [{"appid": a, "name": n, "selected": a in self._ticked, "tag": self._others.get(a, "")}
                for a, n in every if all(w in n.casefold() for w in words)]
        self._model.set_rows(rows)
        self.changed.emit()

    @Slot(int)
    def toggle(self, appid):
        if self._open:
            self._ticked ^= {appid}
            self._rebuild()

    # ----- saving -----
    def _persist(self, change):
        """Run a change of the files; False, and a box for the person, if the disk refused it."""
        try:
            change()
        except OSError as e:
            self.failed.emit(tr("Could not save your groups"), tr("Your groups could not be saved: %s") % e)
            return False
        return True

    def _write(self, remaining, let_go):
        """Save the groups that remain, then take the group note off the covers of the games that left (a note too many does no harm if the first step fails)."""
        groups.save(self._covers, remaining)
        sc.forget_group(self._covers, set(let_go))

    @Slot()
    def rename(self):
        if not self._open:
            return
        try:
            renamed = groups.rename(groups.load(self._covers), self._gid, self._name)
        except ValueError as e:
            self._error = str(e)
            self.changed.emit()
            return
        if not self._persist(lambda: groups.save(self._covers, renamed)):
            return
        self._title, self._name, self._error = self._name.strip(), self._name.strip(), ""
        self.saved.emit()
        self._read_others()
        self._rebuild()

    @Slot()
    def save(self):
        if not self.canSave:
            return
        fresh = groups.load(self._covers)
        group = next((g for g in fresh if g["id"] == self._gid), None)
        if group is None:                                   # deleted elsewhere while the window was open
            self._close()
            return
        if not self._ticked:
            self.deleteGroup()
            return
        removed = [a for a in group["games"] if a not in self._ticked]
        added = [a for a in sorted(self._ticked) if a not in group["games"]]
        if not removed and not added:
            self._close()
            return
        if removed and not self._persist(lambda: self._write(groups.drop_games(fresh, removed), removed)):
            return
        if added:
            self._shell.cases.stage(self._gid, added)       # before the groups are read again, so a group left empty by the removals still gets them
        self.saved.emit()
        self._close()
        self._shell.toast.emit(tr(SAVED))

    @Slot()
    def deleteGroup(self):
        if not self._open:
            return
        fresh = groups.load(self._covers)
        group = next((g for g in fresh if g["id"] == self._gid), None)
        if group is not None and not self._persist(lambda: self._write(groups.delete(fresh, self._gid), group["games"])):
            return
        self._shell.cases.deleteGroup(self._gid)            # games put in it earlier in this run are let go too
        self.saved.emit()
        self._close()
        self._shell.toast.emit(tr(DELETED))
