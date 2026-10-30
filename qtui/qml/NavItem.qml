// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// One entry of the left navigation. A locked step is dimmed, ignores clicks and is skipped by Tab.
import QtQuick

Item {
    id: root
    property string label: ""
    property string hint: ""                     // a small line under the name, e.g. "(optional)"
    property string stepState: "locked"          // open | done | active | locked
    property bool selected: false
    signal activated()

    readonly property bool locked: stepState === "locked"
    height: Theme.navRowHeight
    activeFocusOnTab: !locked
    Accessible.role: Accessible.Button
    Accessible.onPressAction: if (!locked) activated()
    Accessible.name: label + (hint !== "" ? " " + hint : "") + (locked ? ", locked" : stepState === "done" ? ", done" : "")

    Rectangle {                                   // keyboard focus ring
        anchors.fill: parent
        anchors.margins: Theme.hairline
        radius: Theme.radiusField
        color: "transparent"
        border.width: root.activeFocus ? Theme.focusRing : 0
        border.color: Theme.text
    }
    Column {
        x: Theme.s16 + Theme.s4
        anchors.verticalCenter: parent.verticalCenter
        Text {
            objectName: root.objectName + "_label"
            text: root.label
            font.pixelSize: Theme.bodySize
            color: root.locked ? Theme.faint : root.selected ? Theme.text : Theme.muted
            Behavior on color { ColorAnimation { duration: Theme.dur(200) } }
        }
        Text {
            objectName: root.objectName + "_hint"
            visible: root.hint !== ""
            width: root.width - Theme.s16 - Theme.s4 - Theme.s24          // the words stop before the "done" mark; a long one is cut
            elide: Text.ElideRight
            text: root.hint
            font.pixelSize: Theme.smallSize
            color: Theme.faint
        }
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
    Keys.onPressed: (event) => {                  // Return, numpad Enter and Space; a held key does not repeat the action
        if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
            if (!event.isAutoRepeat && !locked) activated()
            event.accepted = true
        }
    }
}
