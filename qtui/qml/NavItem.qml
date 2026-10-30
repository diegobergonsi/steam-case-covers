// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// One entry of the left navigation. A locked step is dimmed, ignores clicks and is skipped by Tab.
import QtQuick

Item {
    id: root
    property string label: ""
    property string stepState: "locked"          // open | done | active | locked
    property bool selected: false
    signal activated()

    readonly property bool locked: stepState === "locked"
    height: 40
    activeFocusOnTab: !locked
    Accessible.role: Accessible.Button
    Accessible.name: label + (locked ? ", locked" : stepState === "done" ? ", done" : "")

    Rectangle {                                   // keyboard focus ring
        anchors.fill: parent
        anchors.margins: 1
        radius: 10
        color: "transparent"
        border.width: root.activeFocus ? 2 : 0
        border.color: Theme.text
    }
    Text {
        x: Theme.s16 + Theme.s4
        anchors.verticalCenter: parent.verticalCenter
        text: root.label
        font.pixelSize: Theme.bodySize
        color: root.locked ? Theme.faint : root.selected ? Theme.text : Theme.muted
        Behavior on color { ColorAnimation { duration: Theme.dur(180) } }
    }
    Text {                                        // a finished step also changes its mark, not only its colour
        anchors.right: parent.right
        anchors.rightMargin: Theme.s16 + Theme.s4
        anchors.verticalCenter: parent.verticalCenter
        visible: root.stepState === "done"
        text: "✓"
        font.pixelSize: Theme.bodySize
        font.bold: true
        color: Theme.done
    }
    MouseArea {
        anchors.fill: parent
        enabled: !root.locked
        cursorShape: Qt.PointingHandCursor
        onClicked: root.activated()
    }
    Keys.onReturnPressed: if (!locked) activated()
    Keys.onSpacePressed: if (!locked) activated()
}
