# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""The object the QML window talks to: which step is shown, which steps are open, and the remembered switches."""
from PySide6.QtCore import Property, QObject, Signal, Slot

from engine import steamcase as sc
from qtui import i18n, settings, steps, system
from qtui.apply import Apply
from qtui.cases import Cases
from qtui.hundred import Hundred
from qtui.i18n import N_, tr
from qtui.library import Library
from qtui.look import Look
from qtui.make import Make
from qtui.owncase import OwnCase
from qtui.picker import Picker
from qtui.updates import Updates

START_OVER_DONE = N_("Everything was reset to the starting point. Your saved cases, covers and groups were not changed.")
FACTS = ("ready", "look_done", "hundred_done", "covers_made", "applied")
MANUAL_FACTS = ("picked", "assigned")           # only the manual flow reads these


def no_facts():
    """Nothing is done yet: what a window just opened knows."""
    return {k: False for k in FACTS + MANUAL_FACTS}


class Shell(QObject):
    stepsChanged = Signal()
    currentChanged = Signal()
    reduceEffectsChanged = Signal()
    flowChanged = Signal()
    switchChanged = Signal()                    # whether the other way can be chosen
    toast = Signal(str)                         # a short message for the window to show for a moment
    flowNameChanged = Signal()                  # the way in use, or the language its name is in
    languageChanged = Signal()
    startedOver = Signal()                      # the window went back to its starting point (the preview pictures in memory go too)

    def __init__(self, settings_path=None, downloads=None, covers_dir=None, parent=None):
        super().__init__(parent)
        self._path = settings_path
        self._values = settings.load_settings(settings_path)
        i18n.set_language(settings.load_language(settings_path) or i18n.system_language())      # the saved choice wins over the system's language
        i18n.use_in_engine()
        self._facts = no_facts()
        self._flow = "natural"                  # or "manual": ticking games and giving them a console case
        self._current = 0
        self._steps = self._build()
        self._had_covers = bool(sc.find_covers(covers_dir or sc.default_covers_dir()))       # covers made in an earlier session
        self._library = Library(self, downloads or system.downloads_dir(), self)
        self._owncase = OwnCase(covers_dir or sc.default_covers_dir(), downloads or system.downloads_dir(), self, busy=lambda: self._make.running)
        self._look = Look(self, covers_dir or sc.default_covers_dir(), self)
        self._hundred = Hundred(self, downloads or system.downloads_dir(), self)
        self._picker = Picker(self, self)
        covers = covers_dir or sc.default_covers_dir()
        self._cases = Cases(self, self, covers)
        self._make = Make(self, covers, account=lambda: self._apply.accountChoice(), parent=self)
        self._apply = Apply(self, self._make, covers, self)
        self._apply.canApplyChanged.connect(self._make._availability)
        self.flowChanged.connect(self.flowNameChanged)
        self.languageChanged.connect(self.flowNameChanged)
        self._make.runningChanged.connect(self.switchChanged)
        self._apply.canApplyChanged.connect(self.switchChanged)
        self._updates = Updates(self)
        self._library.restore()                 # the game list of the last run, if it is still there
        self._picker.selectionChanged.connect(lambda: self.setFact("picked", self._picker.selectedCount > 0))
        self._cases.assignmentsChanged.connect(lambda: self.setFact("assigned", self._cases.assignedCount > 0))

    def _build(self):
        manual = self._flow == "manual"
        if manual:
            states = steps.manual_step_states(**{k: self._facts[k] for k in ("ready", "picked", "assigned", "hundred_done", "covers_made", "applied")})
        else:
            states = steps.step_states(**{k: self._facts[k] for k in FACTS})
        names = steps.labels(self._flow)
        return [{"key": k, "label": names[k], "hint": steps.hint(k, states[k]), "state": states[k]} for k in (steps.STEPS_MANUAL if manual else steps.STEPS)]

    @Property(str, notify=flowChanged)
    def flow(self):
        return self._flow

    def _switch(self, flow):
        """Change the way through the window. Not while covers are made or added to Steam, and nothing happens if it is the flow already."""
        if flow == self._flow or not self.canSwitch:
            return
        self._flow = flow
        self._steps = self._build()
        self.flowChanged.emit()
        self.stepsChanged.emit()
        self._current = self.resume
        self.currentChanged.emit()

    @Property(str, notify=flowNameChanged)
    def flowName(self):
        """The short name of the way in use, for the heading of the navigation and of Home's progress."""
        return tr(N_("Pick games") if self._flow == "manual" else N_("Same case"))

    @Property(bool, notify=switchChanged)
    def canSwitch(self):
        """The other way can be chosen: not while covers are made or added to Steam."""
        return not (self._make.running or self._apply.busy)

    @Slot()
    def startOver(self):
        """Put the window back to what a fresh start shows: the way, the steps, the game list (and the note of its path), the look, the games page, the cases not
        made yet, what Make and Apply remember, the five switches. Nothing saved is touched: groups, covers, the case file, Steam and the language stay.
        Not while covers are made or added to Steam."""
        if not self.canSwitch:
            return
        self._values = dict(settings.DEFAULTS)
        self._save()
        settings.forget_library(self._path)
        self._flow = "natural"
        self._facts = no_facts()
        self._steps = self._build()
        self._current = 0
        self._library.start_over()                  # also puts the facts of the list right
        self._picker.start_over()
        self._look.start_over()
        self._hundred.start_over()
        self._cases.reset()
        self._make.start_over()
        self._apply.start_over()
        self.reduceEffectsChanged.emit()
        self.flowChanged.emit()
        self.stepsChanged.emit()
        self.currentChanged.emit()
        self.startedOver.emit()
        self.toast.emit(tr(START_OVER_DONE))

    @Slot(str, result=int)
    def stepCount(self, flow):
        """How many steps a way has, Home not counted."""
        return len(steps.STEPS_MANUAL if flow == "manual" else steps.STEPS) - 1

    @Slot(str)
    def startPath(self, flow):
        """A card of Home was chosen: the other way is switched to, the way already in use is continued."""
        if flow == self._flow:
            self.go(self.resume)
        else:
            self._switch(flow)

    @Slot(str, result=int)
    def stepIndex(self, key):
        """Where a step is in the steps of this flow, or -1."""
        return next((i for i, step in enumerate(self._steps) if step["key"] == key), -1)

    @Slot(str)
    def goKey(self, key):
        """Show a step by its name; a locked or unknown one is ignored."""
        for i, step in enumerate(self._steps):
            if step["key"] == key:
                self.go(i)
                return

    def _save(self):
        settings.save_settings(self._values, self._path)

    @Property(str, notify=languageChanged)
    def language(self):
        return i18n.language()

    @Slot(str)
    def setLanguage(self, code):
        """Change the language of the window now and remember it. A language we do not have, or the one in use, changes nothing."""
        if code not in settings.LANGUAGE_CODES or code == i18n.language():
            return
        i18n.set_language(code)
        settings.save_language(code, self._path)
        self._steps = self._build()
        i18n.announce_change(self)
        self.languageChanged.emit()

    @property
    def settingsPath(self):
        return self._path

    @Property(bool, notify=stepsChanged)
    def returning(self):
        """Home shows the Dashboard instead of the Welcome: some step is done, or covers from an earlier session are on disk."""
        return self._had_covers or any(self._facts.values())

    @Property(int, notify=stepsChanged)
    def resume(self):
        """The step Continue leads to: the first one not done. When all are, the first step again; by hand, the games to pick (the game list is the same
        screen in both ways, so landing on it would look like the other way)."""
        again = max(self.stepIndex("pick"), 1) if self._flow == "manual" else 1
        return next((i for i, step in enumerate(self._steps) if step["state"] == "active"), again)

    @Property(QObject, constant=True)
    def library(self):
        return self._library

    @Property(QObject, constant=True)
    def look(self):
        return self._look

    @Property(QObject, constant=True)
    def owncase(self):
        return self._owncase

    @Property(QObject, constant=True)
    def hundred(self):
        return self._hundred

    @Property(QObject, constant=True)
    def picker(self):
        return self._picker

    @Property(QObject, constant=True)
    def cases(self):
        return self._cases

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
