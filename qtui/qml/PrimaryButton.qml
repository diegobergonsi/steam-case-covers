// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// The one filled button of a screen.
import QtQuick

Rectangle {
    id: root
    property string text: ""
    signal clicked()

    implicitWidth: label.implicitWidth + Theme.s32
    implicitHeight: 36
    radius: height / 2
    color: !enabled ? Theme.raised : area.containsMouse ? Qt.lighter(Theme.accent, 1.15) : Theme.accent
    scale: area.pressed ? 0.95 : 1
    activeFocusOnTab: enabled
    Accessible.role: Accessible.Button
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
    Keys.onReturnPressed: if (enabled) clicked()
    Keys.onSpacePressed: if (enabled) clicked()
}
