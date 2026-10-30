// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// The small "i": its text shows on hover or keyboard focus, and a click or Enter keeps it open (for touch screens).
import QtQuick
import QtQuick.Controls
import "."

Item {
    id: tip
    property string text: ""
    property bool pinned: false
    width: 24
    height: 24
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: "More information"
    Accessible.description: text
    Accessible.onPressAction: pinned = !pinned

    Rectangle {
        anchors.fill: parent
        radius: width / 2
        color: "transparent"
        border.width: tip.activeFocus ? 2 : 1
        border.color: tip.activeFocus ? Theme.text : Theme.accent
        Text { anchors.centerIn: parent; text: "i"; color: Theme.accent; font.pixelSize: Theme.smallSize; font.bold: true }
    }
    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: tip.pinned = !tip.pinned
    }
    Keys.onPressed: (event) => {
        if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
            if (!event.isAutoRepeat) tip.pinned = !tip.pinned
            event.accepted = true
        }
    }
    onActiveFocusChanged: if (!activeFocus) pinned = false

    ToolTip {
        visible: area.containsMouse || tip.activeFocus || tip.pinned
        delay: 0
        timeout: -1
        width: Math.min(360, tip.Window.width - 2 * Theme.s32)
        padding: Theme.s12
        contentItem: Text { text: tip.text; wrapMode: Text.WordWrap; color: Theme.text; font.pixelSize: Theme.smallSize + 1 }
        background: Rectangle { color: Theme.raised; radius: Theme.radiusField; border.width: 1; border.color: Theme.edge }
    }
}
