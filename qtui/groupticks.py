# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""The saved groups of covers made by hand, each with a box: what the usual Make and Reset show so a group is repainted or reset only when its box is ticked.
Nothing is ticked at first."""
from PySide6.QtCore import Property, QObject, Signal, Slot

import groups
from qtui.cases import case_label, group_caption


class GroupTicks(QObject):
    changed = Signal()

    def __init__(self, covers_dir, parent=None):
        super().__init__(parent)
        self._covers = covers_dir
        self._groups = groups.load(covers_dir)
        self._ticked = set()

    @Property("QVariantList", notify=changed)
    def choices(self):
        """{"id", "name", "label" (its case), "count", "ticked"} for every saved group."""
        return [{"id": g["id"], "name": g["name"], "label": case_label(g["case"]), "caption": group_caption(g["name"], case_label(g["case"]), len(g["games"])), "count": len(g["games"]), "ticked": g["id"] in self._ticked} for g in self._groups]

    @Property(int, notify=changed)
    def count(self):
        """How many groups are ticked."""
        return len(self._ticked)

    @Slot(str)
    def toggle(self, group_id):
        if any(g["id"] == group_id for g in self._groups):
            self._ticked ^= {group_id}
            self.changed.emit()

    @Slot()
    def refresh(self):
        """Read the file again (the manual way may have changed it); ticks of groups that are gone are forgotten."""
        self._groups = groups.load(self._covers)
        self._ticked &= {g["id"] for g in self._groups}
        self.changed.emit()

    def clear(self):
        self._ticked.clear()
        self.changed.emit()

    def ids(self):
        return set(self._ticked)

    def ticked(self):
        """The ticked groups as groups.py keeps them."""
        return [g for g in self._groups if g["id"] in self._ticked]

    def groups(self):
        return list(self._groups)
