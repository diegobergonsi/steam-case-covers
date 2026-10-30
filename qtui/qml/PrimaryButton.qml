// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// The one filled button of a screen.
import QtQuick

Rectangle {
    id: root
    property string text: ""
    signal clicked()
    readonly property bool filled: true          // exactly one enabled filled button per screen (rule 2 of the guide)

    implicitWidth: label.implicitWidth + Theme.s32
    implicitHeight: 36
    radius: height / 2
    color: !enabled ? Theme.raised : area.containsMouse ? Qt.lighter(Theme.accent, Theme.hoverLift) : Theme.accent
    scale: area.pressed ? 0.95 : 1
    activeFocusOnTab: enabled
    Accessible.role: Accessible.Button
    Accessible.onPressAction: if (enabled) clicked()
    Accessible.name: text
    Behavior on scale { NumberAnimation { duration: Theme.dur(90) } }
    Behavior on color { ColorAnimation { duration: Theme.dur(120) } }

    Rectangle {                                   // keyboard focus ring
        anchors.fill: parent
        anchors.margins: -3
        radius: height / 2
        color: "transparent"
        border.width: root.activeFocus ? 2 : 0
        border.color: Theme.text
    }
    Text {
        id: label
        anchors.centerIn: parent
        text: root.text
        font.pixelSize: Theme.bodySize
        font.bold: true
        color: root.enabled ? Theme.accentInk : Theme.faint
    }
    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        enabled: root.enabled
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
    Keys.onPressed: (event) => {                  // Return, numpad Enter and Space; a held key does not repeat the action
        if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
            if (!event.isAutoRepeat && enabled) clicked()
            event.accepted = true
        }
    }
}
