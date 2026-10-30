# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Step 2 of the window: the look of the covers. The case colour, the theme and the two art switches, with a preview that follows them."""
from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

import steamcase as sc
from qtui import tones

COLOUR_NOTE = "Only the original colour is checked for readable text."
THEMES = ("classic",) + tuple(sc.THEMES)
PREVIEW_DELAY_MS = 60                       # one preview render per burst of slider changes: the newest tone wins


class Look(QObject):
    toneChanged = Signal()
    themeChanged = Signal()
    treatmentChanged = Signal()
    artChanged = Signal()
    previewSourceChanged = Signal()

    def __init__(self, shell, covers_dir, parent=None):
        super().__init__(parent)
        self._shell = shell
        self._tone = tones.ORIGINAL
        self._theme = "classic"
        self._treatment = "none"            # plan 4: the look of a 100% game in the preview ("none" or an sc.TREATMENTS name)
        self._serial = 0
        try:                                # reopening the window shows the colour and theme of the covers already made
            found = sc.existing_cover_colour(covers_dir)
            if found:
                self._tone = tones.clamp_tone(*found)
            theme = sc.existing_cover_theme(covers_dir)
            if theme in sc.THEMES:
                self._theme = theme
        except Exception:
            pass
        self._source = self._make_source()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(PREVIEW_DELAY_MS)
        self._timer.timeout.connect(self._refresh_source)

    # ----- the preview -----
    def _make_source(self):
        self._serial += 1
        hue, sat, val = self._tone
        return "image://preview/%d/%d/%d/%s/%s/%d" % (hue, sat, val, self._theme, self._treatment, self._serial)

    def _refresh_source(self):
        self._source = self._make_source()
        self.previewSourceChanged.emit()

    def _schedule(self):
        self._timer.start()                 # restarts the quiet moment while changes keep coming

    @Property(str, notify=previewSourceChanged)
    def previewSource(self):
        return self._source

    # ----- the colour -----
    def _set_tone(self, hue, sat, val):
        tone = tones.clamp_tone(hue, sat, val)
        if tone != self._tone:
            self._tone = tone
            self.toneChanged.emit()
            self._schedule()

    @Property(int, notify=toneChanged)
    def hue(self):
        return self._tone[0]

    @hue.setter
    def hue(self, value):
        self._set_tone(value, self._tone[1], self._tone[2])

    @Property(int, notify=toneChanged)
    def sat(self):
        return self._tone[1]

    @sat.setter
    def sat(self, value):
        self._set_tone(self._tone[0], value, self._tone[2])

    @Property(int, notify=toneChanged)
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
        return "" if tones.same_tone(self._tone, tones.ORIGINAL) else COLOUR_NOTE

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

    @Property(str, constant=True)
    def themeNote(self):
        return ""                              # plan 4: "The Halloween case shows the rosette only..."

    def _get_treatment(self):
        return self._treatment

    def _set_treatment(self, value):
        value = value if value == "none" or value in sc.TREATMENTS else "none"
        if value != self._treatment:
            self._treatment = value
            self.treatmentChanged.emit()
            self._schedule()

    treatment = Property(str, _get_treatment, _set_treatment, notify=treatmentChanged)

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
