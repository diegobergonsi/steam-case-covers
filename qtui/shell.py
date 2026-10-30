# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""The object the QML window talks to: which step is shown, which steps are open, and the remembered switches."""
from PySide6.QtCore import Property, QObject, Signal, Slot

import steamcase as sc
from qtui import settings, steps, system
from qtui.apply import Apply
from qtui.hundred import Hundred
from qtui.library import Library
from qtui.look import Look
from qtui.make import Make
from qtui.updates import Updates

FACTS = ("ready", "look_done", "hundred_done", "covers_made", "applied")


class Shell(QObject):
    stepsChanged = Signal()
    currentChanged = Signal()
    reduceEffectsChanged = Signal()

    def __init__(self, settings_path=None, downloads=None, covers_dir=None, parent=None):
        super().__init__(parent)
        self._path = settings_path
        self._values = settings.load_settings(settings_path)
        self._facts = {k: False for k in FACTS}
        self._current = 0
        self._steps = self._build()
        self._had_covers = bool(sc.find_covers(covers_dir or sc.default_covers_dir()))       # covers made in an earlier session
        self._library = Library(self, downloads or system.downloads_dir(), self)
        self._look = Look(self, covers_dir or sc.default_covers_dir(), self)
        self._hundred = Hundred(self, downloads or system.downloads_dir(), self)
        covers = covers_dir or sc.default_covers_dir()
        self._make = Make(self, covers, account=lambda: self._apply.accountChoice(), parent=self)
        self._apply = Apply(self, self._make, covers, self)
        self._apply.canApplyChanged.connect(self._make._availability)
        self._updates = Updates(self)

    def _build(self):
        states = steps.step_states(**self._facts)
        return [{"key": k, "label": steps.LABELS[k], "hint": steps.HINTS.get(k, ""), "state": states[k]} for k in steps.STEPS]

    def _save(self):
        settings.save_settings(self._values, self._path)

    @Property(bool, notify=stepsChanged)
    def returning(self):
        """Home shows the Dashboard instead of the Welcome: some step is done, or covers from an earlier session are on disk."""
        return self._had_covers or any(self._facts.values())

    @Property(int, notify=stepsChanged)
    def resume(self):
        """The step Continue leads to: the first one not done, or the first step again when all are."""
        return next((i for i, step in enumerate(self._steps) if step["state"] == "active"), 1)

    @Property(QObject, constant=True)
    def library(self):
        return self._library

    @Property(QObject, constant=True)
    def look(self):
        return self._look

    @Property(QObject, constant=True)
    def hundred(self):
        return self._hundred

    @Property(QObject, constant=True)
    def make(self):
        return self._make

    @Property(QObject, constant=True)
    def updates(self):
        return self._updates

    @Property(QObject, constant=True)
    def apply(self):
        return self._apply

    @Slot()
    def poll(self):
        """One look at the Downloads folder for the files the user saves from the browser (call it every 1.5 s)."""
        self._library.poll()
        self._hundred.poll()
        self._apply.poll()

    @Property("QVariantList", notify=stepsChanged)
    def steps(self):
        return self._steps

    @Property(int, notify=currentChanged)
    def current(self):
        return self._current

    def _get_reduce(self):
        return self._values["reduce_effects"]

    def _set_reduce(self, value):
        value = bool(value)
        if value != self._values["reduce_effects"]:
            self._values["reduce_effects"] = value
            self._save()
            self.reduceEffectsChanged.emit()

    reduceEffects = Property(bool, _get_reduce, _set_reduce, notify=reduceEffectsChanged)

    @Slot(int)
    def go(self, index):
        """Show a step; a locked or non-existing one is ignored."""
        if 0 <= index < len(self._steps) and self._steps[index]["state"] != "locked" and index != self._current:
            self._current = index
            self.currentChanged.emit()

    @Slot()
    def next(self):
        self.go(self._current + 1)

    @Slot(str, bool)
    def setFact(self, name, value):
        if name in self._facts and self._facts[name] != bool(value):
            self._facts[name] = bool(value)
            self._steps = self._build()
            self.stepsChanged.emit()
            if self._steps[self._current]["state"] == "locked":              # e.g. installed-only was switched off under a later step
                self._current = max(i for i in range(self._current) if self._steps[i]["state"] != "locked")
                self.currentChanged.emit()

    @Slot(str, result=bool)
    def switchValue(self, key):
        return self._values.get(key, False) if key in settings.SETTING_KEYS else False

    @Slot(str, bool)
    def setSwitch(self, key, value):
        if key == "reduce_effects":
            self._set_reduce(value)
        elif key in settings.SETTING_KEYS and self._values[key] != bool(value):
            self._values[key] = bool(value)
            self._save()
