// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// A small flag that chooses the language of the window. `current` marks the one in use (full strength, with a ring); `name` is the language in its own words, read out
// by a screen reader. `activated()` says it was chosen.
import QtQuick
import "."

Item {
    id: flag
    property url source: ""
    property string name: ""
    property bool current: false
    signal activated()

    width: Theme.s32
    height: Theme.s24
    activeFocusOnTab: true
    Accessible.role: Accessible.RadioButton
    Accessible.name: name
    Accessible.checked: current
    Accessible.onPressAction: activated()

    Rectangle {                                   // the ring: the language in use, and the keyboard focus
        anchors.fill: parent
        radius: Theme.radiusField
        color: "transparent"
        border.width: flag.activeFocus || flag.current ? Theme.focusRing : 0
        border.color: flag.activeFocus ? Theme.text : Theme.muted
    }
    Image {
        anchors.centerIn: parent
        source: flag.source
        width: Theme.s24
        height: Theme.s16
        fillMode: Image.PreserveAspectFit
        opacity: flag.current || area.containsMouse ? 1 : Theme.disabledOpacity
    }
    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: flag.activated()
    }
    Keys.onPressed: (event) => {
        if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
            if (!event.isAutoRepeat) activated()
            event.accepted = true
        }
    }
}
