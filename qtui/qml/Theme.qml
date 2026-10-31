// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// The design tokens of docs/ui-guide.md. Every colour, size and duration in the window comes from here, and nowhere else.
pragma Singleton
import QtQuick

QtObject {
    readonly property color bg: "#11151c"
    readonly property color card: "#182433"
    readonly property color raised: "#22344a"
    readonly property color accent: "#66c0f4"
    readonly property color text: "#e6edf3"
    readonly property color muted: "#93a7bb"
    readonly property color faint: "#7d92a8"
    readonly property color edge: "#5d7a96"
    readonly property color done: "#5ba32b"
    readonly property color warning: "#f0b429"
    readonly property color error: "#ff7b72"
    readonly property color accentInk: "#0b141d"
    readonly property color shadow: "#000000"
    readonly property color navBg: Qt.darker(bg, 1.3)          // the navigation panel: the background, a little darker

    // spacing grid (4 px) and corner radius
    readonly property int s4: 4
    readonly property int s8: 8
    readonly property int s12: 12
    readonly property int s16: 16
    readonly property int s24: 24
    readonly property int s32: 32
    readonly property int s48: 48
    readonly property int radiusField: 8
    readonly property int radiusCard: 14

    // type sizes
    readonly property int titleSize: 26
    readonly property int sectionSize: 16
    readonly property int bodySize: 14
    readonly property int smallSize: 12

    // sizes of the window and of the controls (docs/ui-guide.md)
    readonly property int windowWidth: 900
    readonly property int windowHeight: 560
    readonly property int windowMinWidth: 640
    readonly property int windowMinHeight: 420
    readonly property int navWidth: 230
    readonly property int navTop: 72
    readonly property int navRowHeight: 40
    readonly property int navHighlightInset: 3
    readonly property int chromeWidth: navWidth + 2 * s32 + s8 + 2 * s16          // the window width that is not inside a section: the nav, the margins, the shadow room and the card padding
    readonly property int navHighlightHeight: navRowHeight - 2 * navHighlightInset
    readonly property int controlHeight: 36
    readonly property int fieldRowHeight: 32
    readonly property int infoSize: 24
    readonly property int iconSize: 20
    readonly property int iconPixels: 40
    readonly property int switchWidth: 38
    readonly property int switchHeight: 22
    readonly property int knobSize: 16
    readonly property int knobInset: 3
    readonly property int tipMaxWidth: 360
    readonly property int tipTextSize: 13
    readonly property int touchSize: 36                 // the smallest thing a finger must hit (the Steam Deck)
    readonly property int sliderTrack: 14
    readonly property int previewWidth: 200
    readonly property int previewHeight: 300
    readonly property int sectionMinWidth: 300          // below this the sections no longer fit beside the preview
    readonly property int minSpan: 1                    // a length that is never zero, to divide by
    readonly property int hairline: 1
    readonly property int focusRing: 2
    readonly property int ringOffset: 3
    readonly property int slideOffset: 30
    readonly property int dialogWidth: 440
    readonly property int progressHeight: 8
    readonly property int lockWidth: 12                  // the padlock of a locked step: its body, the height of the body and the rise of the shackle
    readonly property int lockHeight: 9
    readonly property int lockShackle: 4
    readonly property int thumbWidth: 60
    readonly property int thumbHeight: 90
    readonly property int thumbPixels: 120               // the picture is read at twice its size, for sharp edges on screens with more pixels

    // elevation and states (docs/ui-guide.md)
    readonly property real cardShadowBlur: 0.8
    readonly property real cardShadowOpacity: 0.45
    readonly property int cardShadowOffset: 4
    readonly property real raisedShadowBlur: 1.0          // the raised elevation of the guide (12 px down, 32 px blur): a question above the window
    readonly property int raisedShadowOffset: 12
    readonly property real disabledOpacity: 0.6
    readonly property real hoverLift: 1.15
    readonly property real scrimOpacity: 0.6              // the dimmed window behind a question

    // "Reduce effects": set from the shell; every duration goes through dur()
    property bool reduce: false
    function dur(ms) { return reduce ? 0 : ms }
}
