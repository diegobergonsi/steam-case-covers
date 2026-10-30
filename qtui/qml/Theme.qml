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

    // elevation and states (docs/ui-guide.md)
    readonly property real cardShadowBlur: 0.8
    readonly property real cardShadowOpacity: 0.45
    readonly property int cardShadowOffset: 4
    readonly property real disabledOpacity: 0.6
    readonly property real hoverLift: 1.15

    // "Reduce effects": set from the shell; every duration goes through dur()
    property bool reduce: false
    function dur(ms) { return reduce ? 0 : ms }
}
