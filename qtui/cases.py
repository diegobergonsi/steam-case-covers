# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""The Case step of the manual flow: which case the ticked games go in. The choices are kept per game until Make; the covers themselves
(and the 100% marks, which have their own step) are made by Make."""
from PySide6.QtCore import Property, QObject, Signal, Slot

import steamcase as sc

ORDER = ("steam", "ps5", "ps4", "ps3", "xboxseries", "xboxone", "xbox360", "switch2", "switch")       # the Steam case first, then newest to oldest
LABELS = dict(sc.PLATFORM_LABELS, steam="Steam")


class Cases(QObject):
    selectedKeyChanged = Signal()
    assignmentsChanged = Signal()
    familyChanged = Signal()
    availabilityChanged = Signal()

    def __init__(self, shell, parent=None):
        super().__init__(parent)
        self._shell = shell
        self._key = ""
        self._assigned = {}                 # appid -> a platform of sc.PLATFORMS, or None for the Steam case
        self._family = False
        shell.picker.selectionChanged.connect(self.selectedKeyChanged)           # canAssign follows the ticks too
        shell.library.pathChanged.connect(self._library_changed)
        shell.library.installedOnlyChanged.connect(self._library_changed)

    @Property("QVariantList", constant=True)
    def choices(self):
        return [{"key": k, "label": LABELS[k]} for k in ORDER]

    @Property(str, notify=selectedKeyChanged)
    def selectedKey(self):
        return self._key

    @Slot(str)
    def pick(self, key):
        if key in ORDER and key != self._key:
            self._key = key
            self.selectedKeyChanged.emit()

    @Property(bool, notify=selectedKeyChanged)
    def canAssign(self):
        return bool(self._key) and self._shell.picker.selectedCount > 0

    @Slot()
    def assign(self):
        """Put the ticked games in the picked case; they are then unticked, so the next round starts clean."""
        if not self.canAssign:
            return
        games = self._shell.picker.selection()
        for appid in games:
            self._assigned[appid] = None if self._key == "steam" else self._key
        self._key = ""
        self.assignmentsChanged.emit()              # first: the games count as given a case before the ticks go, or the Case step would look locked for a moment
        self._shell.picker.untick(games)
        self.selectedKeyChanged.emit()

    def assigned(self):
        """{appid: platform or None (the Steam case)} for make_covers."""
        return dict(self._assigned)

    @Property(int, notify=assignmentsChanged)
    def assignedCount(self):
        return len(self._assigned)

    @Property("QVariantList", notify=assignmentsChanged)
    def summary(self):
        """{"label", "count"} for every case in use, in the order of the choices."""
        used = [None if v is None else v for v in self._assigned.values()]
        return [{"label": LABELS[k], "count": used.count(None if k == "steam" else k)} for k in ORDER if (None if k == "steam" else k) in used]

    def _get_family(self):
        return self._family

    def _set_family(self, value):
        value = bool(value)
        if value != self._family:
            self._family = value
            self.familyChanged.emit()

    family = Property(bool, _get_family, _set_family, notify=familyChanged)

    @Property(bool, notify=availabilityChanged)
    def familyAvailable(self):
        """Family games are only known from a game list file (an installed-only run knows nothing about ownership)."""
        library = self._shell.library
        return (not library.installedOnly) and bool(library.path)

    def _library_changed(self):
        self.availabilityChanged.emit()
        if self._assigned:                  # the games belong to the old list
            self._assigned = {}
            self.assignmentsChanged.emit()

    @Slot()
    def reset(self):
        self._key, self._assigned, self._family = "", {}, False
        self.selectedKeyChanged.emit()
        self.assignmentsChanged.emit()
        self.familyChanged.emit()
