// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// One entry of the left navigation. A locked step is dimmed, ignores clicks and is skipped by Tab.
import QtQuick

Item {
    id: root
    property string label: ""
    property string hint: ""                     // a small grey note after the name, e.g. "(optional)"
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
    readonly property real markSpace: Theme.s16 + Theme.s4 + Theme.s24          // the right edge is kept for the mark of a finished or locked step
    Row {                                         // the name and, on the same line, a small grey note such as "(optional)"
        x: Theme.s16 + Theme.s4
        anchors.verticalCenter: parent.verticalCenter
        spacing: Theme.s8
        Text {
            id: nameText
            objectName: root.objectName + "_label"
            width: Math.min(implicitWidth, root.width - x - root.markSpace - (hintText.visible ? hintText.implicitWidth + Theme.s8 : 0))
            elide: Text.ElideRight
            text: root.label
            font.pixelSize: Theme.bodySize
            color: root.locked ? Theme.faint : Theme.text                         // a step that cannot be opened is grey, the others are plain text
            Behavior on color { ColorAnimation { duration: Theme.dur(200) } }
        }
        Text {
            id: hintText
            objectName: root.objectName + "_hint"
            anchors.baseline: nameText.baseline
            visible: root.hint !== ""
            text: root.hint
            font.pixelSize: Theme.smallSize
            color: Theme.faint
        }
    }
    Text {                                        // a finished step changes its mark, not only its colour
        objectName: root.objectName + "_done"
        anchors.right: parent.right
        anchors.rightMargin: Theme.s16 + Theme.s4
        anchors.verticalCenter: parent.verticalCenter
        visible: root.stepState === "done"
        text: "✓"
        font.pixelSize: Theme.bodySize
        font.bold: true
        color: Theme.done
    }
    Item {                                        // so does a locked one: a small padlock, drawn so no font is needed
        objectName: root.objectName + "_lock"
        anchors.right: parent.right
        anchors.rightMargin: Theme.s16 + Theme.s4
        anchors.verticalCenter: parent.verticalCenter
        visible: root.locked
        width: Theme.lockWidth
        height: Theme.lockHeight + Theme.lockShackle
        Rectangle {                               // the shackle
            anchors.horizontalCenter: parent.horizontalCenter
            width: Theme.lockWidth - Theme.s4
            height: Theme.lockShackle + Theme.lockShackle
            radius: width / 2
            color: "transparent"
            border.width: Theme.focusRing
            border.color: Theme.faint
        }
        Rectangle {                               // the body
            anchors.bottom: parent.bottom
            width: parent.width
            height: Theme.lockHeight
            radius: Theme.hairline * Theme.focusRing
            color: Theme.faint
        }
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
