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
    property bool tabStop: true                         // one swatch is the Tab stop (the selected one); the arrow keys move between them
    signal picked()
    signal step(int delta)                              // an arrow key, Home (-100) or End (100): the owner moves the choice and the focus

    width: Theme.touchSize
    height: Theme.touchSize
    activeFocusOnTab: tabStop
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
        var k = event.key
        if (k === Qt.Key_Return || k === Qt.Key_Enter || k === Qt.Key_Space) {
            if (!event.isAutoRepeat) swatch.picked()
        } else if (k === Qt.Key_Right || k === Qt.Key_Down) swatch.step(1)
        else if (k === Qt.Key_Left || k === Qt.Key_Up) swatch.step(-1)
        else if (k === Qt.Key_Home) swatch.step(-100)
        else if (k === Qt.Key_End) swatch.step(100)
        else return
        event.accepted = true
    }
}
