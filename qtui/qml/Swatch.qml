// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// A ready-made colour: a circle a finger can hit. It reports `picked`; the owner decides what is selected.
import QtQuick
import "."

Item {
    id: swatch
    property color color: Theme.raised
    property bool selected: false
    property string name: ""
    signal picked()

    width: Theme.touchSize
    height: Theme.touchSize
    activeFocusOnTab: true
    Accessible.role: Accessible.RadioButton
    Accessible.name: name
    Accessible.checkable: true
    Accessible.checked: selected
    Accessible.onPressAction: swatch.picked()

    Rectangle {                                         // keyboard focus ring
        anchors.fill: parent
        radius: width / 2
        color: "transparent"
        border.width: swatch.activeFocus ? Theme.focusRing : 0
        border.color: Theme.text
    }
    Rectangle {
        anchors.centerIn: parent
        width: parent.width - 2 * Theme.s4
        height: width
        radius: width / 2
        color: swatch.color
        border.width: swatch.selected ? Theme.ringOffset : Theme.hairline
        border.color: swatch.selected ? Theme.text : Theme.edge
        Behavior on border.width { NumberAnimation { duration: Theme.dur(120) } }
    }
    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: swatch.picked()
    }
    Keys.onPressed: (event) => {
        if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
            if (!event.isAutoRepeat) swatch.picked()
            event.accepted = true
        }
    }
}
