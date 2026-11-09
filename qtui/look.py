# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Step 2 of the window: the look of the covers. The case colour, the theme and the two art switches, with a preview that follows them."""
from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from engine import steamcase as sc
from qtui import tones
from qtui.reasons import theme_label
from qtui.i18n import N_, tr

COLOUR_NOTE = N_("Only the original colour is checked for readable text.")
THEMES = ("classic",) + tuple(sc.THEMES)
PREVIEW_DELAY_MS = 60                       # one preview render per burst of slider changes: the newest tone wins


class Look(QObject):
    toneChanged = Signal()                  # any of the three (names, notes, swatches follow it)
    hueChanged = Signal()                   # one signal for each value: a slider's track must not be redrawn when only its own value moved
    satChanged = Signal()
    valChanged = Signal()
    themeChanged = Signal()
    treatmentChanged = Signal()
    artChanged = Signal()
    previewSourceChanged = Signal()
    ownCaseChanged = Signal()

    def __init__(self, shell, covers_dir, parent=None):
        super().__init__(parent)
        self._shell = shell
        self._treatment = "none"            # set by Hundred: the look of a 100% game in the preview ("none" or an sc.TREATMENTS name)
        self._serial = 0
        self._own = False                   # "My own case" for every game (the Look step of the step-by-step way); the file itself is kept by shell.owncase
        self._covers = covers_dir
        self._tone, self._theme = self._starting_look()
        self._source, self._hundred_source, self._marked_source = self._make_sources()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(PREVIEW_DELAY_MS)
        self._timer.timeout.connect(self._refresh_source)

    def _starting_look(self):
        """(tone, theme) of a window just opened: reopening shows the colour and theme of the covers already made."""
        tone, theme = tones.ORIGINAL, "classic"
        try:
            found = sc.existing_cover_colour(self._covers)
            if found:
                tone = tones.clamp_tone(*found)
            made = sc.existing_cover_theme(self._covers)
            if made in sc.THEMES:
                theme = made
        except Exception:
            pass
        return tone, theme

    def start_over(self):
        """The look of a window just opened. The shell has already put the two art switches back; the case file is kept."""
        self._own = False
        self._tone, self._theme = self._starting_look()
        for signal in (self.hueChanged, self.satChanged, self.valChanged, self.toneChanged, self.themeChanged, self.ownCaseChanged, self.artChanged):
            signal.emit()
        self._schedule()

    # ----- the preview -----
    def _make_sources(self):
        """(Look preview, 100% games preview, Make preview). Look never shows the marks of step 3, and step 3 never takes the colour or the theme of step 2 (it
        starts from the original colour in the classic case); Make shows the covers as they will be made, colour, theme and marks."""
        self._serial += 1
        if self._own:
            own = "image://preview/platform/%s/%d" % (sc.CUSTOM, self._serial)      # the case keeps its own colours: tone, theme and marks mean nothing in it
            return own, own, own

        def url(tone, theme, treatment):
            return "image://preview/%d/%d/%d/%s/%s/%d" % (*tone, theme, treatment, self._serial)
        return (url(self._tone, self._theme, "none"), url(tones.ORIGINAL, "classic", self._treatment), url(self._tone, self._theme, self._treatment))

    def _refresh_source(self):
        self._source, self._hundred_source, self._marked_source = self._make_sources()
        self.previewSourceChanged.emit()

    def _schedule(self):
        if not self._timer.isActive():      # a throttle, not a debounce: during a long drag the picture follows every 60 ms, and the last tone always shows
            self._timer.start()

    @Property(str, notify=previewSourceChanged)
    def previewSource(self):
        return self._source

    @Property(str, notify=previewSourceChanged)
    def hundredSource(self):
        return self._hundred_source

    @Property(str, notify=previewSourceChanged)
    def markedSource(self):
        return self._marked_source

    # ----- the colour -----
    def _set_tone(self, hue, sat, val):
        tone = tones.clamp_tone(hue, sat, val)
        if tone != self._tone:
            old, self._tone = self._tone, tone
            for i, signal in enumerate((self.hueChanged, self.satChanged, self.valChanged)):
                if old[i] != tone[i]:
                    signal.emit()
            self.toneChanged.emit()
            self._schedule()

    @Property(int, notify=hueChanged)
    def hue(self):
        return self._tone[0]

    @hue.setter
    def hue(self, value):
        self._set_tone(value, self._tone[1], self._tone[2])

    @Property(int, notify=satChanged)
    def sat(self):
        return self._tone[1]

    @sat.setter
    def sat(self, value):
        self._set_tone(self._tone[0], value, self._tone[2])

    @Property(int, notify=valChanged)
    def val(self):
        return self._tone[2]

    @val.setter
    def val(self, value):
        self._set_tone(self._tone[0], self._tone[1], value)

    @Property(str, notify=toneChanged)
    def toneName(self):
        return tones.tone_name(*self._tone)

    @Property(str, notify=toneChanged)
    def toneHint(self):
        return tones.tone_hint(*self._tone)

    @Property(str, notify=toneChanged)
    def colourNote(self):
        return "" if tones.same_tone(self._tone, tones.ORIGINAL) else tr(COLOUR_NOTE)

    @Property("QVariantList", constant=True)
    def swatchList(self):
        """The nine ready-made tones: the same list for ever, so nothing is rebuilt when the tone changes."""
        return tones.swatches()

    @Property(int, notify=toneChanged)
    def selectedSwatch(self):
        """Which of the nine is the current tone, or -1 for a custom one."""
        for i, x in enumerate(tones.swatches()):
            if tones.same_tone(self._tone, (x["hue"], x["sat"], x["val"])):
                return i
        return -1

    @Property("QVariantList", constant=True)
    def themes(self):
        return [{"key": k, "label": theme_label(k)} for k in THEMES]

    @Property("QVariantList", notify=toneChanged)
    def swatches(self):
        return [dict(x, selected=tones.same_tone(self._tone, (x["hue"], x["sat"], x["val"]))) for x in tones.swatches()]

    @Slot(int, int, int)
    def setTone(self, hue, sat, val):
        self._set_tone(hue, sat, val)

    @Slot(int)
    def pickSwatch(self, index):
        items = tones.swatches()
        if 0 <= index < len(items):
            x = items[index]
            self._set_tone(x["hue"], x["sat"], x["val"])

    @Slot(int, int, int, result=str)
    def colorFor(self, hue, sat, val):
        return sc.case_color(*tones.clamp_tone(hue, sat, val))

    @Slot(str, result=str)
    def trackStart(self, which):
        return self._track(which)[0]

    @Slot(str, result=str)
    def trackEnd(self, which):
        return self._track(which)[1]

    def _track(self, which):
        try:
            return tones.track_colors(*self._tone, which)
        except ValueError:
            return "#000000", "#000000"       # never an exception into QML

    @Slot(str, result="QVariantList")
    def trackColors(self, which):
        try:
            return tones.track_gradient(*self._tone, which)
        except ValueError:
            return []

    @Slot(result="QVariantList")
    def hueColors(self):
        return tones.hue_colors()

    # ----- the theme -----
    def _get_theme(self):
        return self._theme

    def _set_theme(self, value):
        if value in THEMES and value != self._theme:
            self._theme = value
            self.themeChanged.emit()
            self._schedule()

    theme = Property(str, _get_theme, _set_theme, notify=themeChanged)

    def _get_treatment(self):
        return self._treatment

    def _set_treatment(self, value):
        value = value if value == "none" or value in sc.TREATMENTS else "none"
        if value != self._treatment:
            self._treatment = value
            self.treatmentChanged.emit()
            self._schedule()

    treatment = Property(str, _get_treatment, _set_treatment, notify=treatmentChanged)

    # ----- my own case -----
    def _get_own(self):
        return self._own

    def _set_own(self, value):
        value = bool(value) and self._shell.owncase.available
        if value != self._own:
            self._own = value
            self.ownCaseChanged.emit()
            self._schedule()

    ownCase = Property(bool, _get_own, _set_own, notify=ownCaseChanged)

    @Slot()
    def chooseOwnCase(self):
        """Ask for a case file; once it is accepted every game is made in it."""
        self._shell.owncase.ask(self._use_own)

    def _use_own(self):
        self._own = True
        self.ownCaseChanged.emit()
        self._schedule()                        # a new file is a new picture even when the switch was already on

    # ----- the art switches (saved through the shell) -----
    def _get_skip(self):
        return self._shell.switchValue("skip_auto_art")

    def _set_skip(self, value):
        if bool(value) != self._get_skip():
            self._shell.setSwitch("skip_auto_art", bool(value))
            self.artChanged.emit()

    skipAutoArt = Property(bool, _get_skip, _set_skip, notify=artChanged)

    def _get_custom(self):
        return self._shell.switchValue("use_custom_art")

    def _set_custom(self, value):
        if bool(value) != self._get_custom():
            self._shell.setSwitch("use_custom_art", bool(value))
            self.artChanged.emit()

    useCustomArt = Property(bool, _get_custom, _set_custom, notify=artChanged)
