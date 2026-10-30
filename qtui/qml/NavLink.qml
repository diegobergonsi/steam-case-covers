// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// A link at the bottom of the navigation (Discord, Check for updates): a quiet button with a focus ring. `text` is its name; `activated()` says it was chosen.
import QtQuick
import "."

Item {
    id: link
    property string text: ""
    property url icon: ""
    signal activated()

    height: Theme.navRowHeight
    activeFocusOnTab: enabled
    opacity: enabled ? 1 : Theme.disabledOpacity
    Accessible.role: Accessible.Button
    Accessible.name: text
    Accessible.onPressAction: if (enabled) activated()

    Rectangle {                                   // keyboard focus ring
        anchors.fill: parent
        anchors.margins: Theme.hairline
        radius: Theme.radiusField
        color: "transparent"
        border.width: link.activeFocus ? Theme.focusRing : 0
        border.color: Theme.text
    }
    Row {
        x: Theme.s24
        anchors.verticalCenter: parent.verticalCenter
        spacing: Theme.s8
        Image {
            visible: link.icon != ""
            source: link.icon
            width: Theme.iconSize
            height: Theme.iconSize
            sourceSize.width: Theme.iconPixels
            sourceSize.height: Theme.iconPixels
            fillMode: Image.PreserveAspectFit
        }
        Text { text: link.text; color: area.containsMouse ? Theme.text : Theme.muted; font.pixelSize: Theme.bodySize }
    }
    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        enabled: link.enabled
        cursorShape: Qt.PointingHandCursor
        onClicked: link.activated()
    }
    Keys.onPressed: (event) => {
        if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
            if (!event.isAutoRepeat && enabled) activated()
            event.accepted = true
        }
    }
}
