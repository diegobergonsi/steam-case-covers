# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""The object the QML window talks to: which step is shown, which steps are open, and the remembered switches."""
from PySide6.QtCore import Property, QObject, Signal, Slot

from qtui import settings, steps

FACTS = ("ready", "look_done", "hundred_done", "covers_made", "applied")


class Shell(QObject):
    stepsChanged = Signal()
    currentChanged = Signal()
    reduceEffectsChanged = Signal()

    def __init__(self, settings_path=None, parent=None):
        super().__init__(parent)
        self._path = settings_path
        self._values = settings.load_settings(settings_path)
        self._facts = {k: False for k in FACTS}
        self._current = 0
        self._steps = self._build()

    def _build(self):
        states = steps.step_states(**self._facts)
        return [{"key": k, "label": steps.LABELS[k], "state": states[k]} for k in steps.STEPS]

    def _save(self):
        settings.save_settings(self._values, self._path)

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
